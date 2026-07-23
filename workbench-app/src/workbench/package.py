"""Program package builder (spec/54 §2.3c, §2.5).

Bundles a whole program into one organized .zip a colleague can open WITHOUT
the app: the readable rendered documents, the full governed source-of-truth
tree, the decision log (json + csv), the corpus manifest (json + csv), and —
for the OWNER's own record — the restricted transcripts in a clearly-marked
folder with a README. The separate share path (package-share.sh) still strips
restricted content; this owner export is the "download my full record" path.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Optional


def _csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


def _decisions_rows(pdir: Path) -> list[dict]:
    log = pdir / "governed" / "decisions.log.jsonl"
    rows = []
    if log.exists():
        for line in log.read_text().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            who = d.get("decided_by") or {}
            rows.append({
                "entry_id": d.get("entry_id", ""), "timestamp": d.get("timestamp", ""),
                "type": d.get("type", ""),
                "decided_by": who.get("name", ""), "role": who.get("role") or who.get("capacity", ""),
                "decision": d.get("decision", ""), "rationale": d.get("rationale", ""),
            })
    return rows


def _manifest_rows(man: Optional[dict]) -> list[dict]:
    if not man:
        return []
    return [{
        "item_id": i.get("item_id", ""), "title": i.get("title", ""),
        "issuer": i.get("issuer", ""), "family": i.get("family", ""),
        "status": i.get("status", ""), "locator": i.get("locator", ""),
        "evidence_role": i.get("evidence_role", "") or "", "url": i.get("url", "") or "",
    } for i in man.get("items", [])]


_RESTRICTED_README = (
    "RESTRICTED — sensitive working material (ADR-016)\n"
    "================================================\n\n"
    "This folder contains the interview and discovery transcripts that produced\n"
    "this program's Purpose Statement and corpus. They are included here because\n"
    "this is the OWNER's complete record of the program. They are NOT included in\n"
    "packages meant for sharing with others (the share export strips this folder).\n"
    "Handle accordingly.\n"
)


def build(pdir: str | Path, pid: str, *, renders: Optional[dict] = None,
          manifest_doc: Optional[dict] = None, include_restricted: bool = True) -> bytes:
    """Return the bytes of an organized .zip for one program.

    renders: {archive_relative_path: html_string} for freshly-rendered documents
    (the caller computes these; each is best-effort and may be absent).
    """
    pdir = Path(pdir)
    renders = renders or {}
    files: dict[str, bytes] = {}   # archive path -> bytes

    root = f"{pid}-package"

    # 1) Readable rendered documents (the point of the package).
    for rel, html in renders.items():
        if html:
            files[f"{root}/documents/{rel}"] = html.encode() if isinstance(html, str) else html

    # 2) Full governed source-of-truth tree, structure preserved.
    gov = pdir / "governed"
    if gov.is_dir():
        for f in gov.rglob("*"):
            if f.is_file():
                files[f"{root}/governed/{f.relative_to(gov).as_posix()}"] = f.read_bytes()

    # 3) Derived, reader-friendly exports.
    files[f"{root}/decision-log.csv"] = _csv_bytes(
        _decisions_rows(pdir),
        ["entry_id", "timestamp", "type", "decided_by", "role", "decision", "rationale"])
    files[f"{root}/manifest.csv"] = _csv_bytes(
        _manifest_rows(manifest_doc),
        ["item_id", "title", "issuer", "family", "status", "locator", "evidence_role", "url"])

    # 4) Restricted transcripts — owner record only, clearly marked.
    restricted = pdir / "restricted"
    if include_restricted and restricted.is_dir():
        any_r = False
        for f in restricted.rglob("*"):
            if f.is_file():
                any_r = True
                files[f"{root}/restricted/{f.relative_to(restricted).as_posix()}"] = f.read_bytes()
        if any_r:
            files[f"{root}/restricted/README.txt"] = _RESTRICTED_README.encode()

    # 5) Cover page + integrity manifest.
    files[f"{root}/index.html"] = _cover_html(pid, files, root).encode()
    files[f"{root}/MANIFEST.txt"] = _integrity_manifest(files, root).encode()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            z.writestr(name, files[name])
    return buf.getvalue()


def _integrity_manifest(files: dict, root: str) -> str:
    lines = [f"Program package: {root}", "sha256  size  path", ""]
    for name in sorted(files):
        if name.endswith("MANIFEST.txt"):
            continue
        b = files[name]
        lines.append(f"{hashlib.sha256(b).hexdigest()}  {len(b):>9}  {name[len(root) + 1:]}")
    return "\n".join(lines) + "\n"


def _cover_html(pid: str, files: dict, root: str) -> str:
    docs = sorted(n[len(root) + 1:] for n in files if "/documents/" in n)
    doc_links = "".join(
        f'<li><a href="{d}">{d.split("/")[-1]}</a></li>' for d in docs) or "<li>(none rendered)</li>"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{pid} — program package</title>
<style>body{{font:15px/1.6 -apple-system,Segoe UI,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1.2rem;color:#1a1f2e}}
h1{{border-bottom:2px solid #1a1f2e;padding-bottom:.3rem}}code{{background:#f4f6fa;padding:1px 4px;border-radius:4px}}
.dim{{color:#5a6172;font-size:.92rem}}</style></head><body>
<h1>{pid}</h1>
<p>This is a complete, self-contained package of the regulatory-consolidation
program <b>{pid}</b>, produced by the Rulebook Workbench. Nothing here is
operative law — these are evidenced working papers for the authority that owns
the rules.</p>
<h2>Readable documents</h2>
<ul>{doc_links}</ul>
<h2>What's in this package</h2>
<ul>
<li><code>documents/</code> — the rendered Blueprint, Target Blueprint, and Crosswalk (open these).</li>
<li><code>governed/</code> — the full source-of-truth tree: manifest, extractions, registers, corpus texts, decision log.</li>
<li><code>decision-log.csv</code> — every human decision, on the record.</li>
<li><code>manifest.csv</code> — the corpus, as a spreadsheet.</li>
<li><code>restricted/</code> — interview/discovery transcripts (owner record only; see its README).</li>
<li><code>MANIFEST.txt</code> — a hash + size for every file, for integrity.</li>
</ul>
<p class="dim">The tool proposes and checks; people decide. See the decision log
for who decided what, and why.</p>
</body></html>"""
