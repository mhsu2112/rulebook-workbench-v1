import json
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import REPO
from test_server import approot, transport  # noqa: F401  (fixtures)
from workbench.acquire import Acquirer, html_to_text, plan_for_item, xml_to_text
from workbench.server import create_app

SNAP = "2026-07-18"

FAKE_CFR = "<?xml version='1.0'?><DIV5><HEAD>PART 1022</HEAD><P>" + \
    "Each money services business shall develop, implement, and maintain an effective anti-money laundering program. " * 30 + "</P></DIV5>"
FAKE_HTML = "<html><head><script>x()</script></head><body><h1>Rule 3310</h1><p>" + \
    "Each member shall develop and implement a written anti-money laundering program. " * 30 + "</p></body></html>"


def corpus_transport(fail_ids=()):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for fid in fail_ids:
            if fid in url:
                return httpx.Response(500, text="boom")
        if "ecfr.gov" in url:
            return httpx.Response(200, content=FAKE_CFR.encode(),
                                  headers={"content-type": "application/xml"})
        return httpx.Response(200, content=FAKE_HTML.encode(),
                              headers={"content-type": "text/html"})
    return httpx.MockTransport(handler)


def test_plan_cfr_uses_pinned_snapshot_and_all_parts():
    item = {"item_id": "12-cfr-326-353-fdic", "family": "regulation_fba",
            "locator": "12 CFR 326.8 and 12 CFR Part 353", "url": "https://example.gov/x"}
    urls = plan_for_item(item, SNAP)
    assert urls[0] == f"https://www.ecfr.gov/api/versioner/v1/full/{SNAP}/title-12.xml?part=326"
    assert urls[1] == f"https://www.ecfr.gov/api/versioner/v1/full/{SNAP}/title-12.xml?part=353"
    assert urls[2] == "https://example.gov/x"  # census URL as fallback


def test_plan_statute_uses_uscode_viewer():
    item = {"item_id": "31-usc-5318", "family": "statute", "locator": "31 U.S.C. 5318", "url": None}
    urls = plan_for_item(item, SNAP)
    assert "uscode.house.gov" in urls[0] and "title31" in urls[0] and "section5318" in urls[0]


def test_extractors_strip_markup():
    assert "money services business" in xml_to_text(FAKE_CFR)
    t = html_to_text(FAKE_HTML)
    assert "written anti-money laundering program" in t and "x()" not in t


def _mini_items():
    return [
        {"item_id": "31-cfr-1022", "family": "regulation_fincen", "locator": "31 CFR Part 1022",
         "url": "https://www.fincen.gov/x", "title": "MSB rules", "issuer": "FinCEN", "status": "live"},
        {"item_id": "FINRA-3310", "family": "sro_rule_guidance", "locator": "Rule 3310",
         "url": "https://www.finra.org/rules/3310", "title": "AML program", "issuer": "FINRA", "status": "live"},
        {"item_id": "broken-item", "family": "guidance_fincen", "locator": "x",
         "url": "https://dead.example/gone", "title": "Dead", "issuer": "?", "status": "live"},
    ]


def test_acquire_fetches_records_and_resumes(tmp_path):
    acq = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:abc",
                   transport=corpus_transport(fail_ids=["dead.example"]))
    r = acq.acquire(_mini_items(), limit=10)
    assert r["counts"] == {"fetched": 2, "error": 1, "pending": 0}
    assert (tmp_path / "governed/corpus_texts/31-cfr-1022.txt").exists()
    assert (tmp_path / "governed/corpus_texts/31-cfr-1022.xml").exists()
    reg = json.loads((tmp_path / "governed/corpus_texts/acquisition.json").read_text())
    rec = reg["items"]["31-cfr-1022"]
    assert rec["manifest_hash"] == "sha256:abc" and rec["raw_sha256"].startswith("sha256:")
    assert reg["items"]["broken-item"]["status"] == "error"
    # resume: nothing re-fetched, errors kept unless retry_errors
    r2 = acq.acquire(_mini_items(), limit=10)
    assert r2["processed"] == 0
    r3 = acq.acquire(_mini_items(), limit=10, retry_errors=True)
    assert r3["processed"] == 1  # only the errored item retried


def test_acquire_refuses_foreign_manifest_hash(tmp_path):
    acq = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:abc",
                   transport=corpus_transport())
    acq.acquire(_mini_items()[:1], limit=1)
    acq2 = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:DIFFERENT",
                    transport=corpus_transport())
    with pytest.raises(ValueError, match="different manifest hash"):
        acq2.acquire(_mini_items(), limit=1)


def test_endpoints_gated_on_frozen_manifest(approot):  # noqa: F811
    (approot / "data").mkdir(exist_ok=True)
    shutil.copy(REPO / "data" / "aml-program-rules-slice.json",
                approot / "data" / "aml-program-rules-slice.json")
    app = create_app(root=approot, transport=corpus_transport(), api_key="test-key")
    c = TestClient(app)
    c.post("/api/programs", json={"program_id": "p1"})
    assert c.get("/api/programs/p1/corpus/status").status_code == 404      # no manifest
    c.post("/api/programs/p1/manifest/import", json={"slice_id": "aml-program-rules-slice"})
    assert c.get("/api/programs/p1/corpus/status").status_code == 409      # unfrozen
    assert c.post("/api/programs/p1/corpus/acquire", json={}).status_code == 409
    c.post("/api/programs/p1/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "r"})
    c.post("/api/programs/p1/manifest/freeze",
           json={"name": "M", "role": "Corpus Steward", "rationale": "r"})
    s = c.get("/api/programs/p1/corpus/status").json()
    assert s["counts"] == {"fetched": 0, "error": 0, "pending": 42, "excluded": 0}
    r = c.post("/api/programs/p1/corpus/acquire", json={"limit": 5}).json()
    assert r["processed"] == 5 and r["counts"]["fetched"] == 5 and r["counts"]["pending"] == 37
    # batch through the rest
    while True:
        r = c.post("/api/programs/p1/corpus/acquire", json={"limit": 20}).json()
        if r["counts"]["pending"] == 0:
            break
    assert r["counts"]["fetched"] == 42 and r["counts"]["error"] == 0
    s2 = c.get("/api/programs/p1/corpus/status").json()
    assert s2["counts"]["fetched"] == 42
    assert (approot / "programs/p1/governed/corpus_texts/FINRA-3310.txt").exists()


def test_plan_rescues_urls_from_locator():
    # the frozen manifest's FBA enforcement item has a mangled url field;
    # the locator carries the real URLs and the plan must find them (OR-7:
    # interpret the datum, never mutate it)
    item = {"item_id": "enf-index-x", "family": "enforcement_index",
            "locator": "OCC EASearch: https://apps.occ.gov/EASearch ; FRB: https://www.federalreserve.gov/x",
            "url": "OCC"}
    urls = plan_for_item(item, SNAP)
    assert urls[0] == "https://apps.occ.gov/EASearch"
    assert "federalreserve.gov" in urls[1]


def test_extract_sniffs_content_not_extension():
    from workbench.acquire import extract_text
    # PDF-named URL serving HTML → treated as HTML, no pypdf crash
    text, ext = extract_text("text/html", "https://x.gov/doc.pdf", FAKE_HTML.encode())
    assert ext == "html" and "anti-money laundering" in text
    # real PDF magic bytes → routed to the PDF extractor
    from pypdf import PdfWriter
    import io as _io
    w = PdfWriter(); w.add_blank_page(width=72, height=72)
    buf = _io.BytesIO(); w.write(buf)
    text2, ext2 = extract_text("text/html", "https://x.gov/page", buf.getvalue())
    assert ext2 == "pdf"


def test_browser_headers_sent(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.headers))
        return httpx.Response(200, content=FAKE_HTML.encode(),
                              headers={"content-type": "text/html"})

    acq = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:x",
                   transport=httpx.MockTransport(handler))
    acq.acquire(_mini_items()[:1], limit=1)
    assert seen["user-agent"].startswith("Mozilla/5.0")
    assert "text/html" in seen["accept"]


def test_url_override_wins(tmp_path):
    urls_hit = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls_hit.append(str(request.url))
        return httpx.Response(200, content=FAKE_HTML.encode(),
                              headers={"content-type": "text/html"})

    acq = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:x",
                   transport=httpx.MockTransport(handler))
    (tmp_path / "governed/corpus_texts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "governed/corpus_texts/url_overrides.json").write_text(
        json.dumps({"31-cfr-1022": "https://override.example/better-source"}))
    acq.acquire(_mini_items()[:1], limit=1)
    assert urls_hit[0] == "https://override.example/better-source"


def test_plan_builds_ecfr_for_any_cfr_locator():
    # regression: regulation_frb / regulation_fhfa families were skipped
    for fam, loc, part in [("regulation_frb", "12 CFR Part 201", "201"),
                           ("regulation_fhfa", "12 CFR Part 1266", "1266")]:
        item = {"item_id": "x", "family": fam, "locator": loc, "url": "https://agency.gov/page"}
        urls = plan_for_item(item, SNAP)
        assert urls[0] == f"https://www.ecfr.gov/api/versioner/v1/full/{SNAP}/title-12.xml?part={part}"
        assert urls[1] == "https://agency.gov/page"


BLOCK_PAGE = ("<html><body><h1>Request Access</h1><p>Due to aggressive automated scraping "
              "of FederalRegister.gov and eCFR.gov, programmatic access to these sites is "
              "limited to our developer APIs. "
              "Please visit the FederalRegister.gov API documentation or the eCFR.gov API "
              "documentation to learn more about how to access the API. " * 4 +
              "</p></body></html>")


def test_block_page_detected_not_recorded_as_fetched(tmp_path):
    """Regression: eCFR served an HTTP-200 CAPTCHA shell that was stored as a
    'fetched' corpus text and silently emptied nine CFR extractions."""
    from workbench.acquire import looks_blocked
    assert looks_blocked(html_to_text(BLOCK_PAGE))
    assert not looks_blocked(html_to_text(FAKE_HTML))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=BLOCK_PAGE.encode(),
                              headers={"content-type": "text/html"})

    acq = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:x",
                   transport=httpx.MockTransport(handler))
    r = acq.acquire(_mini_items()[:1], limit=1)
    rec = list(r["items"].values())[0]
    assert rec["status"] == "error"
    assert any("block/CAPTCHA" in e for e in rec["errors"])
    assert not (tmp_path / "governed/corpus_texts/31-cfr-1022.txt").exists()


def test_ecfr_snapshot_past_issue_date_rescued(tmp_path):
    """Regression: versioner API 404s when the pinned snapshot postdates the
    title's most recent issue date; the fetcher retries at that issue date
    (the CFR's state ON the snapshot date), honoring DL-002."""
    urls_hit = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        urls_hit.append(url)
        if "/api/versioner/" in url and SNAP in url:
            return httpx.Response(404, json={"error":
                f"The requested date {SNAP} is past the title's most recent "
                "issue date of 2026-07-16, see the API for details"})
        if "/api/versioner/" in url and "2026-07-16" in url:
            return httpx.Response(200, content=FAKE_CFR.encode(),
                                  headers={"content-type": "application/xml"})
        return httpx.Response(200, content=BLOCK_PAGE.encode(),
                              headers={"content-type": "text/html"})

    acq = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:x",
                   transport=httpx.MockTransport(handler))
    r = acq.acquire(_mini_items()[:1], limit=1)
    rec = list(r["items"].values())[0]
    assert rec["status"] == "fetched"
    assert "2026-07-16" in rec["source_url"]
    assert any(SNAP in u for u in urls_hit)  # pinned date tried first


def test_good_records_never_clobbered_by_retry(tmp_path):
    """Regression: browser_assisted register entries were re-fetched by a later
    sweep (403) and overwritten to 'error', orphaning their good texts."""
    (tmp_path / "governed/corpus_texts").mkdir(parents=True)
    reg = {"manifest_hash": "sha256:x", "snapshot_date": SNAP,
           "items": {"31-cfr-1022": {"status": "browser_assisted",
                                     "method": "browser_assisted", "text_chars": 9000}}}
    (tmp_path / "governed/corpus_texts/acquisition.json").write_text(json.dumps(reg))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403, text="forbidden")

    acq = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:x",
                   transport=httpx.MockTransport(handler))
    r = acq.acquire(_mini_items()[:1], limit=5, retry_errors=True)
    assert calls == []                       # done statuses are skipped entirely
    assert r["items"]["31-cfr-1022"]["status"] == "browser_assisted"
