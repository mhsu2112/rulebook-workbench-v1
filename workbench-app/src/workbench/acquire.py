"""Corpus text acquisition (M3.1): fetch the actual text of each frozen-manifest
item into the program's text store, hash-stamped against the manifest.

Sources: eCFR versioner API for CFR parts AT THE PINNED SNAPSHOT DATE (the
DL-002 discipline made executable), uscode.house.gov for U.S. Code sections,
and each item's census URL for guidance/manual/SRO/enforcement materials.
Public regulatory text → governed store. Every fetch is recorded; failures
are per-item and retryable, never run-fatal.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

import httpx

CFR_RE = re.compile(r"(\d+)\s+CFR\s+(?:Parts?\s+)?(\d+)")
USC_ID_RE = re.compile(r"^(\d+)-usc-(\d+[a-z]?)")
URL_RE = re.compile(r"https?://[^\s;,)\"']+")

ECFR_URL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml?part={part}"
USCODE_URL = ("https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title{title}-"
              "section{section}&num=0&edition=prelim")

# Anti-scraping shells come back as HTTP 200 with plausible-looking HTML.
# A "fetch" that stores one of these poisons everything downstream, so the
# guard is part of acquisition, not distillation (fetched must mean fetched
# the right thing).
_BLOCK_SIGNS = ("request access", "automated scraping", "captcha",
                "are you a robot", "verify you are human",
                "enable javascript and cookies")


# Acquisition records in any of these states are DONE — they are skipped by
# acquire() and must never be overwritten by an automated retry. 'fetched' is
# the fetcher's own success; 'browser_assisted' and 'manual' record texts that
# arrived through a governed side door (rendered capture, recorded slice).
DONE_STATUSES = ("fetched", "browser_assisted", "manual")


def looks_blocked(text: str) -> bool:
    if len(text) > 5000:   # real source text is never this short AND blocky
        return False
    low = text.casefold()
    return any(s in low for s in _BLOCK_SIGNS)


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "head", "nav"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    p = _TextExtractor()
    p.feed(markup)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def xml_to_text(markup: str) -> str:
    # eCFR full XML: strip tags, keep text flow
    text = re.sub(r"<[^>]+>", " ", markup)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()


def plan_for_item(item: dict, snapshot_date: str) -> list[str]:
    """Ordered candidate URLs for one manifest item. First success wins;
    CFR items may need several (one per distinct title/part in the locator)."""
    fam = item.get("family", "")
    urls: list[str] = []
    # ANY item whose locator cites the CFR gets eCFR candidates — the family
    # label is presentation, the locator is the datum (learned the hard way:
    # regulation_frb/regulation_fhfa items were silently skipped).
    seen = set()
    for title, part in CFR_RE.findall(item.get("locator", "")):
        if (title, part) not in seen:
            seen.add((title, part))
            urls.append(ECFR_URL.format(date=snapshot_date, title=title, part=part))
    if fam == "statute":
        m = USC_ID_RE.match(item.get("item_id", ""))
        if m:
            urls.append(USCODE_URL.format(title=m.group(1), section=m.group(2)))
    if item.get("url"):
        urls.append(item["url"])  # census URL as primary (guidance etc.) or fallback (CFR/USC)
    # Any URLs embedded in the locator text are additional candidates — this
    # rescues items whose url field is malformed WITHOUT touching the frozen
    # manifest (OR-7: the datum is immutable; its interpretation is ours).
    urls += URL_RE.findall(item.get("locator", ""))
    seen, out = set(), []
    for u in urls:
        if u and u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def extract_text(content_type: str, url: str, data: bytes) -> tuple[str, str]:
    """Return (text, raw_ext). Routes by CONTENT SNIFFING first — live servers
    lie: PDF links serve HTML interstitials, HTML content-types serve PDFs."""
    if data[:5] == b"%PDF-":
        return pdf_to_text(data), "pdf"
    ct = (content_type or "").lower()
    body = data.decode("utf-8", errors="replace")
    if body.lstrip().startswith("<?xml") or ("xml" in ct and "html" not in ct):
        return xml_to_text(body), "xml"
    return html_to_text(body), "html"


class Acquirer:
    """Fetch texts for frozen-manifest items into governed/corpus_texts/."""

    def __init__(self, program_dir: str | Path, *, snapshot_date: str,
                 manifest_hash: str, transport: Optional[httpx.BaseTransport] = None):
        self.dir = Path(program_dir) / "governed" / "corpus_texts"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_date = snapshot_date
        self.manifest_hash = manifest_hash
        self.transport = transport
        self.register_path = self.dir / "acquisition.json"
        self.overrides_path = self.dir / "url_overrides.json"

    def overrides(self) -> dict:
        """Per-item URL overrides (curator-maintained): consulted FIRST.
        For sources that block non-browser clients or moved."""
        if self.overrides_path.exists():
            return json.loads(self.overrides_path.read_text())
        return {}

    def register(self) -> dict:
        if self.register_path.exists():
            return json.loads(self.register_path.read_text())
        return {"manifest_hash": self.manifest_hash, "snapshot_date": self.snapshot_date, "items": {}}

    def _save(self, reg: dict) -> None:
        self.register_path.write_text(json.dumps(reg, indent=2))

    def acquire(self, items: list[dict], *, limit: int = 8, retry_errors: bool = False) -> dict:
        reg = self.register()
        if reg.get("manifest_hash") != self.manifest_hash:
            raise ValueError("Acquisition register belongs to a different manifest hash — "
                             "the corpus changed identity; refusing to mix")
        done = 0
        with httpx.Client(transport=self.transport, timeout=60,
                          follow_redirects=True,
                          headers={
                              "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                                             "Chrome/126.0.0.0 Safari/537.36"),
                              "Accept": ("text/html,application/xhtml+xml,application/xml;"
                                         "q=0.9,application/pdf;q=0.9,*/*;q=0.8"),
                              "Accept-Language": "en-US,en;q=0.9",
                          }) as client:
            for item in items:
                iid = item["item_id"]
                rec = reg["items"].get(iid)
                if rec and (rec["status"] in DONE_STATUSES
                            or (rec["status"] == "error" and not retry_errors)):
                    continue
                if done >= limit:
                    break
                done += 1
                result = self._fetch_one(client, item)
                # Never clobber a good record with a failure (regression:
                # browser-assisted entries were overwritten to 'error' by a
                # later retry sweep, orphaning their perfectly good texts).
                if result["status"] == "error" and rec and rec.get("status") in DONE_STATUSES:
                    result = rec
                reg["items"][iid] = result
                self._save(reg)
        counts = {"fetched": 0, "error": 0, "pending": 0}
        for it in items:
            st = reg["items"].get(it["item_id"], {}).get("status", "pending")
            counts[st if st in counts else "pending"] += 1
        return {"processed": done, "counts": counts, "items": reg["items"]}

    def _fetch_one(self, client: httpx.Client, item: dict) -> dict:
        iid = item["item_id"]
        errors = []
        candidates = plan_for_item(item, self.snapshot_date)
        override = self.overrides().get(iid)
        if override:
            candidates = [override] + [u for u in candidates if u != override]
        if not candidates:
            # Nothing to fetch (e.g. a non-US source the auto-planner can't map,
            # with no URL on the manifest item). "Retry" can't help until a URL is
            # supplied — say so instead of erroring silently.
            return {"status": "error",
                    "errors": ["no source URL for this item — add one (e.g. a legislation.gov.uk "
                               "or official page link) and retry"],
                    "attempted_at": datetime.now(timezone.utc).isoformat()}
        for url in candidates:
            try:
                r = client.get(url)
                # eCFR versioner rescue: a snapshot date past the title's most
                # recent issue date 404s, with the correct date in the error
                # body. The state of the CFR on the snapshot date IS the last
                # issuance on or before it, so retrying at that date honors
                # DL-002 (interpret the frozen datum, never mutate it).
                if r.status_code == 404 and "/api/versioner/" in url:
                    m = re.search(r"most recent issue date of (\d{4}-\d{2}-\d{2})", r.text)
                    if m and m.group(1) <= self.snapshot_date:
                        url = re.sub(r"/full/\d{4}-\d{2}-\d{2}/", f"/full/{m.group(1)}/", url)
                        r = client.get(url)
                if r.status_code != 200 or not r.content:
                    errors.append(f"{url} -> HTTP {r.status_code}")
                    continue
                text, ext = extract_text(r.headers.get("content-type", ""), url, r.content)
                if len(text) < 200:  # degenerate page (error shells, redirects-to-nothing)
                    errors.append(f"{url} -> only {len(text)} chars extracted")
                    continue
                if looks_blocked(text):  # anti-scraping shells return HTTP 200
                    errors.append(f"{url} -> block/CAPTCHA page detected, not source content")
                    continue
                (self.dir / f"{iid}.txt").write_text(text)
                (self.dir / f"{iid}.{ext}").write_bytes(r.content)
                return {
                    "status": "fetched", "source_url": url,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "raw_sha256": "sha256:" + hashlib.sha256(r.content).hexdigest(),
                    "raw_bytes": len(r.content), "text_chars": len(text), "raw_ext": ext,
                    "manifest_hash": self.manifest_hash, "snapshot_date": self.snapshot_date,
                }
            except Exception as e:  # noqa: BLE001 — per-item resilience by design
                errors.append(f"{url} -> {type(e).__name__}: {str(e)[:160]}")
        return {"status": "error", "errors": errors,
                "attempted_at": datetime.now(timezone.utc).isoformat()}
