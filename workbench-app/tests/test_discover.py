"""Tests for assisted source discovery (spec/53).

Discovery must: verify model-proposed locators against the live catalog (mocked
here), surface unverifiable proposals FLAGGED rather than clean, dedupe against
the existing manifest, degrade (not crash) when a catalog is down, and NEVER
mutate the manifest.
"""
import json

import httpx
import pytest

from workbench.discover import Discoverer, cfr_key, usc_key, slugify

SNAP = "2026-07-18"

_ECFR_SEARCH = {
    "results": [
        {"hierarchy": {"title": "12", "part": "1266"},
         "headings": {"part": "PART 1266—FEDERAL HOME LOAN BANK ADVANCES",
                      "chapter": "CHAPTER XII—FEDERAL HOUSING FINANCE AGENCY"}},
        {"hierarchy": {"title": "12", "part": "1290"},
         "headings": {"part": "PART 1290—COMMUNITY SUPPORT",
                      "chapter": "CHAPTER XII—FEDERAL HOUSING FINANCE AGENCY"}},
        {"hierarchy": {"title": "12", "part": "1291"},
         "headings": {"part": "PART 1291—AFFORDABLE HOUSING PROGRAM",
                      "chapter": "CHAPTER XII—FEDERAL HOUSING FINANCE AGENCY"}},
        {"hierarchy": {"title": "12", "part": None}, "headings": {}},  # subtitle-level → skipped
    ]
}

_FEDREG = {
    "results": [
        {"title": "Federal Home Loan Bank Advances; Final Rule",
         "agencies": [{"name": "Federal Housing Finance Agency"}],
         "html_url": "https://www.federalregister.gov/documents/2026/01/02/x",
         "type": "Rule", "citation": "91 FR 100", "document_number": "2026-00001",
         "publication_date": "2026-01-02"},
    ]
}


def _big_xml(part):
    return ("<?xml version='1.0'?><DIV>" + ("advances collateral membership " * 60)
            + f"part {part}</DIV>").encode()


def catalog_transport(*, ecfr_search_status=200, fedreg_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/api/search/v1/results" in u:
            return httpx.Response(ecfr_search_status, json=_ECFR_SEARCH if ecfr_search_status == 200 else {})
        if "federalregister.gov/api/v1/documents" in u:
            return httpx.Response(fedreg_status, json=_FEDREG if fedreg_status == 200 else {})
        if "/api/versioner/v1/full/" in u:
            # Valid parts verify; 9999 is bogus -> 404 with no rescue date.
            if "part=9999" in u:
                return httpx.Response(404, text="no content")
            return httpx.Response(200, content=_big_xml("ok"))
        if "uscode.house.gov" in u:
            if "section1430" in u:
                return httpx.Response(200, text="<p>" + "advances to members " * 40 + "</p>")
            return httpx.Response(404, text="not found")
        return httpx.Response(500, text="unexpected url " + u)
    return httpx.MockTransport(handler)


MODEL_CANDS = [
    {"title": "FHLBank advances rule", "issuer": "FHFA", "family": "regulation",
     "cfr_locator": "12 CFR Part 1266", "rationale": "core advances rule"},         # dup of catalog 1266
    {"title": "Bogus part", "issuer": "Nobody", "family": "regulation",
     "cfr_locator": "99 CFR Part 9999", "rationale": "should fail verification"},   # unverified
    {"title": "FHLBank Act — advances", "issuer": "Congress", "family": "statute",
     "usc_locator": "12 U.S.C. 1430", "rationale": "statutory basis"},              # verified USC
    {"title": "AB 2026-01 advances guidance", "issuer": "FHFA", "family": "guidance",
     "url": "https://www.fhfa.gov/guidance/ab-2026-01", "rationale": "interpretive guidance"},  # url-only, unverified
    {"title": "", "issuer": "X", "family": "regulation", "rationale": "no title -> dropped"},
]


def test_discover_verifies_and_ranks():
    d = Discoverer(snapshot_date=SNAP, transport=catalog_transport())
    res = d.discover(terms=["fhlbank", "advances"], model_candidates=MODEL_CANDS, existing_items=[])
    cands = res["candidates"]
    by_id = {c["proposed_item_id"]: c for c in cands}

    # 1266 appears once (catalog wins the dedup), USC verified, bogus flagged, url-only flagged.
    assert "12-cfr-1266" in by_id and by_id["12-cfr-1266"]["origin"] == "catalog"
    assert by_id["12-cfr-1266"]["verified"] is True
    assert by_id["12-usc-1430"]["verified"] is True
    assert by_id["99-cfr-9999"]["verified"] is False
    # url-only descriptive candidate: unverified, never shown as clean
    url_only = [c for c in cands if c["origin"] == "model" and c["locator"].startswith("https://")]
    assert url_only and url_only[0]["verified"] is False
    # empty-title candidate was dropped
    assert not any(c["title"] == "" for c in cands)

    # Ranking: every verified candidate precedes every unverified one.
    verified_flags = [c["verified"] for c in cands]
    assert verified_flags == sorted(verified_flags, reverse=True)
    # First candidate is a verified catalog hit.
    assert cands[0]["verified"] is True and cands[0]["origin"] == "catalog"

    c = res["counts"]
    assert c["queued"] == len(cands) and c["verified"] >= 3 and c["catalog"] >= 2


def test_discover_dedupes_against_existing_manifest():
    existing = [{"item_id": "already-1291", "locator": "12 CFR Part 1291", "family": "regulation"}]
    d = Discoverer(snapshot_date=SNAP, transport=catalog_transport())
    res = d.discover(terms=["advances"], model_candidates=[], existing_items=existing)
    keys = {cfr_key(c["locator"]) for c in res["candidates"]}
    assert "12cfr1291" not in keys           # already in the corpus -> dropped
    assert "12cfr1266" in keys and "12cfr1290" in keys
    assert any("already in your corpus" in n for n in res["notes"])


def test_discover_unique_item_ids_against_manifest():
    # Existing item collides with a catalog candidate's natural id -> queue must rename.
    existing = [{"item_id": "12-cfr-1290", "locator": "somewhere else", "family": "x"}]
    d = Discoverer(snapshot_date=SNAP, transport=catalog_transport())
    res = d.discover(terms=["advances"], model_candidates=[], existing_items=existing)
    ids = [c["proposed_item_id"] for c in res["candidates"]]
    assert len(ids) == len(set(ids))          # unique within the queue
    assert "12-cfr-1290" not in ids           # renamed away from the existing id (locator differs, so not deduped)


def test_discover_degrades_when_ecfr_search_down():
    d = Discoverer(snapshot_date=SNAP, transport=catalog_transport(ecfr_search_status=503))
    res = d.discover(terms=["advances"], model_candidates=MODEL_CANDS, existing_items=[])
    # eCFR down, but Federal Register + model lanes still produced candidates.
    assert res["candidates"]
    assert any("eCFR search" in n and "503" in n for n in res["notes"])
    # The verified USC model candidate still made it through.
    assert any(c["proposed_item_id"] == "12-usc-1430" and c["verified"] for c in res["candidates"])


def test_helpers():
    assert cfr_key("12 CFR Part 1266") == "12cfr1266"
    assert cfr_key("no citation here") is None
    assert usc_key("12 U.S.C. 1430") == "12usc1430"
    assert slugify("PART 1266—FEDERAL HOME LOAN BANK ADVANCES!!!").startswith("part-1266")


from workbench.discover import detect_jurisdictions

_UK_FEED = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><title>OTC Derivatives Regulations 2019</title>'
            '<id>http://www.legislation.gov.uk/uksi/2019/335</id></entry>'
            '<entry><title>UK EMIR</title>'
            '<id>http://www.legislation.gov.uk/eur/2012/648</id></entry></feed>')


def uk_transport():
    def handler(request):
        u = str(request.url)
        def J(o): return httpx.Response(200, json=o)
        if "legislation.gov.uk/all/data.feed" in u:
            return httpx.Response(200, text=_UK_FEED)
        if "missing-404" in u or "/404" in u:                 # intended-dead source -> unverifiable
            return httpx.Response(404, text="not found")
        if "legislation.gov.uk" in u or "fca.org.uk" in u:   # a resolvable full-text/official URL
            return httpx.Response(200, text="<p>" + ("advances reporting obligation " * 60) + "</p>")
        if "/api/search/v1/results" in u:
            return httpx.Response(200, json={"results": []})
        if "federalregister.gov" in u:
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404, text="x")
    return httpx.MockTransport(handler)


def test_detect_jurisdictions():
    assert detect_jurisdictions("UK EMIR reporting; FCA handbook; onshored retained EU") == ["uk"]
    assert detect_jurisdictions("12 CFR and FinCEN federal register") == ["us"]
    assert "eu" in detect_jurisdictions("EUR-Lex ESMA guidelines")
    assert detect_jurisdictions("") == ["us"]          # default


def test_uk_catalog_lane():
    d = Discoverer(snapshot_date=SNAP, transport=uk_transport())
    res = d.discover(terms=["derivatives reporting"], model_candidates=[], existing_items=[], jurisdictions=["uk"])
    ids = {c["proposed_item_id"] for c in res["candidates"]}
    assert "uk-uksi-2019-335" in ids and "uk-eu... " not in ids  # eur parsed as uk-eur-2012-648
    assert any(c["proposed_item_id"] == "uk-eur-2012-648" for c in res["candidates"])
    uk = next(c for c in res["candidates"] if c["proposed_item_id"] == "uk-uksi-2019-335")
    assert uk["verified"] and uk["url"].endswith("/uksi/2019/335/data.xml") and uk["origin"] == "catalog"


def test_model_lane_verifies_non_us_url():
    d = Discoverer(snapshot_date=SNAP, transport=uk_transport())
    cands = [{"title": "UK EMIR art. 9", "issuer": "UK Parliament", "family": "regulation",
              "locator": "UK EMIR art. 9", "url": "https://www.legislation.gov.uk/eur/2012/648",
              "rationale": "core reporting obligation"},
             {"title": "Dead source", "issuer": "X", "family": "guidance",
              "url": "https://www.fca.org.uk/missing-404", "rationale": "x"}]
    # note: the 404 url returns 404 in uk_transport -> unverified; the legislation one resolves
    res = d.discover(terms=[], model_candidates=cands, existing_items=[], jurisdictions=["uk"])
    by_loc = {c["locator"]: c for c in res["candidates"]}
    good = next(c for c in res["candidates"] if "legislation.gov.uk" in (c["url"] or ""))
    assert good["verified"] is True and good["origin"] == "model" and good["locator"] == "UK EMIR art. 9"
    dead = next(c for c in res["candidates"] if "missing-404" in (c["url"] or ""))
    assert dead["verified"] is False
