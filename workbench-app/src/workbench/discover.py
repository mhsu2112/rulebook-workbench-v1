"""Assisted source discovery (P1 census helper) — spec/53.

The census (deciding WHICH sources make up the corpus) was the last manual
seam in an otherwise governed chain. This module closes it WITHOUT letting the
machine decide scope: it proposes candidate sources; a human accepts them into
the manifest via the existing add_item path. Discovery writes nothing and
freezes nothing — it fills a review queue.

Two lanes feed one queue (Program Owner's choice: catalog-anchored, model-
expanded):

  • catalog lane — direct queries to authoritative catalogs (eCFR search API,
    Federal Register API). Locators are real by construction; marked verified.
  • model lane — a model proposes sources it knows are relevant (recall);
    every CFR/USC locator it emits is VERIFIED against the live catalog before
    it can be shown as clean. Unverifiable proposals are surfaced flagged,
    never laundered into confident citations.

Every external call is best-effort and isolated: partial results are the norm
and are always labelled partial (notes[]). Nothing here raises for a network
failure — a dead catalog degrades the queue, it does not break discovery.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import quote_plus

import httpx

from .acquire import CFR_RE, USCODE_URL, ECFR_URL, looks_blocked, html_to_text

# U.S.C. citation shapes the model tends to emit: "12 U.S.C. 1430", "12 USC 1430(a)".
USC_CITE_RE = re.compile(r"(\d+)\s*U\.?\s*S\.?\s*C\.?\s*(?:§+\s*)?(\d+[a-z]?)", re.I)

ECFR_SEARCH = "https://www.ecfr.gov/api/search/v1/results?query={q}&per_page={n}"
FEDREG_SEARCH = (
    "https://www.federalregister.gov/api/v1/documents.json?per_page={n}"
    "&order=relevance&conditions[term]={q}"
    "&fields[]=title&fields[]=citation&fields[]=html_url&fields[]=type"
    "&fields[]=agencies&fields[]=publication_date&fields[]=document_number"
)

_UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json,text/html,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_QUEUE = 60  # hard cap; truncation is always reported in notes (no silent caps)


def slugify(text: str, *, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:maxlen].strip("-") or "source"


def cfr_key(locator: str) -> Optional[str]:
    """Normalized (title, part) key for a CFR citation, for dedup. None if not CFR."""
    m = CFR_RE.search(locator or "")
    return f"{m.group(1)}cfr{m.group(2)}" if m else None


def usc_key(locator: str) -> Optional[str]:
    m = USC_CITE_RE.search(locator or "")
    return f"{m.group(1)}usc{m.group(2).lower()}" if m else None


@dataclass
class Candidate:
    proposed_item_id: str
    title: str
    issuer: str
    family: str
    status: str
    locator: str
    url: Optional[str]
    evidence_role: Optional[str]
    rationale: str
    origin: str          # "catalog" | "model"
    verified: bool
    verify_note: str
    _dedup_key: str = field(default="", repr=False)

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("_dedup_key", None)
        return d


class Discoverer:
    """Propose candidate corpus sources for human review. Never touches the manifest."""

    def __init__(self, *, snapshot_date: str,
                 transport: Optional[httpx.BaseTransport] = None, timeout: float = 30.0):
        self.snapshot_date = snapshot_date
        self.transport = transport
        self.timeout = timeout

    # ---------------- catalog lane ----------------

    def _ecfr_search(self, client: httpx.Client, query: str, notes: list[str],
                     limit: int = 12) -> list[Candidate]:
        r = client.get(ECFR_SEARCH.format(q=quote_plus(query), n=limit))
        if r.status_code != 200:
            notes.append(f"eCFR search '{query}' → HTTP {r.status_code}; skipped")
            return []
        results = (r.json() or {}).get("results") or []
        out: list[Candidate] = []
        for res in results:
            h = res.get("hierarchy") or {}
            title, part = h.get("title"), h.get("part")
            if not title or not part:
                continue  # need part-level to build a locator acquisition can use
            heads = res.get("headings") or {}
            name = _clean_heading(heads.get("part")) or f"{title} CFR Part {part}"
            issuer = _issuer_from_chapter(heads.get("chapter")) or f"CFR Title {title}"
            out.append(Candidate(
                proposed_item_id=f"{title}-cfr-{part}",
                title=name, issuer=issuer, family="regulation", status="live",
                locator=f"{title} CFR Part {part}", url=None, evidence_role=None,
                rationale=f"eCFR search hit for “{query}”.",
                origin="catalog", verified=True,
                verify_note=f"eCFR search: Title {title} Part {part}",
                _dedup_key=f"{title}cfr{part}"))
        return out

    def _fedreg_search(self, client: httpx.Client, query: str, notes: list[str],
                       limit: int = 8) -> list[Candidate]:
        r = client.get(FEDREG_SEARCH.format(q=quote_plus(query), n=limit))
        if r.status_code != 200:
            notes.append(f"Federal Register search '{query}' → HTTP {r.status_code}; skipped")
            return []
        docs = (r.json() or {}).get("results") or []
        out: list[Candidate] = []
        for d in docs:
            title = (d.get("title") or "").strip()
            if not title:
                continue
            agencies = d.get("agencies") or []
            issuer = ""
            if agencies and isinstance(agencies[0], dict):
                issuer = agencies[0].get("name") or agencies[0].get("raw_name") or ""
            issuer = issuer or "Federal Register"
            typ = (d.get("type") or "").strip()
            status = "proposed" if "proposed" in typ.lower() else "live"
            cite = (d.get("citation") or "").strip()
            docnum = (d.get("document_number") or "").strip()
            locator = cite or (f"Federal Register doc {docnum}" if docnum else "Federal Register")
            slug = docnum or slugify(title)
            out.append(Candidate(
                proposed_item_id=f"fr-{slug}",
                title=title, issuer=issuer, family="guidance", status=status,
                locator=locator, url=d.get("html_url"), evidence_role=None,
                rationale=f"Federal Register {typ or 'document'} matching “{query}”"
                          + (f" ({d.get('publication_date')})" if d.get("publication_date") else "") + ".",
                origin="catalog", verified=True,
                verify_note=f"Federal Register API: {docnum or cite or 'match'}",
                _dedup_key=f"fr-{slug}"))
        return out

    # ---------------- verification (for the model lane) ----------------

    def _verify_cfr(self, client: httpx.Client, title: str, part: str) -> tuple[bool, str]:
        """A CFR locator is verified by the SAME fetch acquisition will make — so
        'verified' means 'acquire will find this' (DL-002 date rescue included)."""
        url = ECFR_URL.format(date=self.snapshot_date, title=title, part=part)
        try:
            r = client.get(url)
            if r.status_code == 404 and "/api/versioner/" in url:
                m = re.search(r"most recent issue date of (\d{4}-\d{2}-\d{2})", r.text)
                if m and m.group(1) <= self.snapshot_date:
                    url = re.sub(r"/full/\d{4}-\d{2}-\d{2}/", f"/full/{m.group(1)}/", url)
                    r = client.get(url)
            if r.status_code == 200 and len(r.content) > 500:
                return True, f"eCFR versioner {self.snapshot_date}: Title {title} Part {part} present"
            return False, f"eCFR versioner → HTTP {r.status_code} for Title {title} Part {part}"
        except Exception as e:  # noqa: BLE001 — verification is best-effort
            return False, f"eCFR versioner check failed: {type(e).__name__}"

    def _verify_usc(self, client: httpx.Client, title: str, section: str) -> tuple[bool, str]:
        url = USCODE_URL.format(title=title, section=section)
        try:
            r = client.get(url)
            if r.status_code != 200 or not r.content:
                return False, f"uscode.house.gov → HTTP {r.status_code} for {title} U.S.C. {section}"
            text = html_to_text(r.text) if b"<" in r.content[:200] else r.text
            if looks_blocked(text) or len(text) < 200:
                return False, f"uscode.house.gov returned no usable text for {title} U.S.C. {section}"
            return True, f"uscode.house.gov: {title} U.S.C. {section} present"
        except Exception as e:  # noqa: BLE001
            return False, f"uscode.house.gov check failed: {type(e).__name__}"

    def _from_model(self, client: httpx.Client, raw: dict) -> Optional[Candidate]:
        title = (raw.get("title") or "").strip()
        issuer = (raw.get("issuer") or "").strip()
        family = (raw.get("family") or "").strip() or "regulation"
        if not title or not issuer:
            return None  # add_item requires both; a candidate that can't be accepted is noise
        rationale = (raw.get("rationale") or "").strip()
        evidence_role = raw.get("evidence_role") or None
        status = raw.get("status") or "live"

        cfr = (raw.get("cfr_locator") or "").strip()
        usc = (raw.get("usc_locator") or "").strip()
        url = (raw.get("url") or "").strip() or None

        # Prefer a CFR locator, then USC, then a URL-only guidance candidate.
        m = CFR_RE.search(cfr) or CFR_RE.search(usc)
        if m:
            t, p = m.group(1), m.group(2)
            ok, note = self._verify_cfr(client, t, p)
            return Candidate(
                proposed_item_id=f"{t}-cfr-{p}",
                title=title, issuer=issuer, family=family or "regulation", status=status,
                locator=f"{t} CFR Part {p}", url=url, evidence_role=evidence_role,
                rationale=rationale, origin="model", verified=ok, verify_note=note,
                _dedup_key=f"{t}cfr{p}")
        mu = USC_CITE_RE.search(usc) or USC_CITE_RE.search(cfr)
        if mu:
            t, s = mu.group(1), mu.group(2).lower()
            ok, note = self._verify_usc(client, t, s)
            return Candidate(
                proposed_item_id=f"{t}-usc-{s}",
                title=title, issuer=issuer, family=family or "statute", status=status,
                locator=f"{t} U.S.C. {s}", url=url, evidence_role=evidence_role,
                rationale=rationale, origin="model", verified=ok, verify_note=note,
                _dedup_key=f"{t}usc{s}")
        # No parseable statutory/regulatory locator — a URL-only or descriptive
        # candidate. Cannot be machine-verified; surfaced flagged, never clean.
        locator = url or "(no locator — human to supply)"
        note = ("URL not machine-verifiable; confirm before freezing" if url
                else "no citable locator; the model could not pin an exact citation")
        return Candidate(
            proposed_item_id=slugify(title),
            title=title, issuer=issuer, family=family, status=status,
            locator=locator, url=url, evidence_role=evidence_role,
            rationale=rationale, origin="model", verified=False, verify_note=note,
            _dedup_key=f"desc-{slugify(title)}")

    # ---------------- orchestration ----------------

    def discover(self, *, terms: list[str], model_candidates: Optional[list[dict]] = None,
                 existing_items=()) -> dict:
        notes: list[str] = []
        existing_ids = {i.get("item_id") for i in existing_items}
        existing_keys = set()
        for i in existing_items:
            for k in (cfr_key(i.get("locator", "")), usc_key(i.get("locator", ""))):
                if k:
                    existing_keys.add(k)

        collected: list[Candidate] = []
        query = " ".join(terms).strip()
        with httpx.Client(transport=self.transport, timeout=self.timeout,
                          follow_redirects=True, headers=_UA) as client:
            if query:
                try:
                    collected += self._ecfr_search(client, query, notes)
                except Exception as e:  # noqa: BLE001
                    notes.append(f"eCFR search unavailable ({type(e).__name__}) — other lanes still ran")
                try:
                    collected += self._fedreg_search(client, query, notes)
                except Exception as e:  # noqa: BLE001
                    notes.append(f"Federal Register search unavailable ({type(e).__name__}) — other lanes still ran")
            elif not model_candidates:
                notes.append("No search terms and no model proposals — nothing to discover")
            for raw in (model_candidates or []):
                cand = self._from_model(client, raw)
                if cand:
                    collected.append(cand)

        # Dedup vs existing manifest and within the queue; drop what's already in.
        seen: set[str] = set()
        deduped: list[Candidate] = []
        dropped_existing = 0
        for c in collected:
            key = c._dedup_key or c.proposed_item_id
            if key in existing_keys or c.proposed_item_id in existing_ids:
                dropped_existing += 1
                continue
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
        if dropped_existing:
            notes.append(f"{dropped_existing} candidate(s) already in your corpus were dropped")

        # Ensure proposed_item_ids are unique against the manifest AND each other.
        used = set(existing_ids)
        for c in deduped:
            base = c.proposed_item_id
            iid, n = base, 2
            while iid in used:
                iid, n = f"{base}-{n}", n + 1
            c.proposed_item_id = iid
            used.add(iid)

        # Rank: verified catalog, verified model, then unverified.
        def rank(c: Candidate):
            return (0 if c.verified else 1, 0 if c.origin == "catalog" else 1)
        deduped.sort(key=rank)

        if len(deduped) > MAX_QUEUE:
            notes.append(f"Showing top {MAX_QUEUE} of {len(deduped)} candidates "
                         "(refine your terms to narrow); the rest are not shown")
            deduped = deduped[:MAX_QUEUE]

        counts = {
            "catalog": sum(1 for c in deduped if c.origin == "catalog"),
            "model": sum(1 for c in deduped if c.origin == "model"),
            "verified": sum(1 for c in deduped if c.verified),
            "queued": len(deduped),
        }
        return {"terms": terms, "counts": counts, "notes": notes,
                "candidates": [c.as_dict() for c in deduped]}


def _clean_heading(h: Optional[str]) -> str:
    """'PART 1266—FEDERAL HOME LOAN BANK ADVANCES' → readable title-case-ish."""
    if not h:
        return ""
    return re.sub(r"\s+", " ", h).strip()


def _issuer_from_chapter(chapter: Optional[str]) -> str:
    """eCFR chapter heading usually names the agency, e.g.
    'CHAPTER XII—FEDERAL HOUSING FINANCE AGENCY' → 'Federal Housing Finance Agency'."""
    if not chapter:
        return ""
    m = re.search(r"[—–-]\s*(.+)$", chapter)
    name = (m.group(1) if m else chapter).strip()
    # Title-case an ALL-CAPS agency name; leave mixed case alone.
    if name and name == name.upper():
        name = name.title().replace("Llc", "LLC")
    return name
