"""Distillation (M3.2, instruction set P2): corpus texts → per-item blueprint
extractions → defect register.

Discipline encoded here, not merely prompted:
- Extraction is scoped by the RATIFIED Purpose Statement's scope sentence.
- Every citation quote is verified by CODE against the source text
  (whitespace-normalized containment). A model cannot invent a citation and
  have it counted; unverified quotes are flagged, and an extraction whose
  citations are mostly unverified is recorded as an error, not a result.
- The fidelity rule (P2.3): contradictions are preserved, never harmonized —
  the prompt says so and the defect pass exists to record them.
- Oversized texts get a cheap long-context FOCUS pass before the expensive
  extraction, so cost scales with relevance, not raw size.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

FOCUS_LIMIT = 300_000       # chars; larger texts get the focus pass. Mid-size
                            # texts go straight to extraction — the focus output
                            # cap truncates them worse than one long read.
FOCUS_CHUNK = 350_000       # chars per focus-pass call (cheap 1M-ctx model)
MIN_VERIFIED_RATIO = 0.6    # below this, the extraction is an error, not a result

DEFECT_TAXONOMY = """D1 conflicting requirements (incompatible duties across sources)
D2 divergent definitions (one term, materially different definitions)
D3 duplicate provisions (same duty stated in multiple instruments)
D4 undefined material term
D5 dead or dangling reference
D6 superseded-in-substance but never revoked
D7 scattered requirement (one obligation assembled only by reading several instruments)
D8 obsolete/archaic provision
D9 gap (obligation implied by structure or enforcement but stated nowhere)
D10 applicability inconsistency (scope/threshold mismatch across instruments)"""

FOCUS_PROMPT = """Return VERBATIM — completely unchanged, no commentary, no summaries — every
passage from the text below that is relevant to this scope:

{scope}

EXCLUDE tables of contents, section-title listings, indexes, and other
headings-only material: a section caption matters only when its OPERATIVE
TEXT (duties, definitions, conditions) is present — return that operative
text. Prioritize operative text over front matter if space is tight.

Concatenate the passages separated by lines containing only '---'. Include
enough surrounding context for each passage to be intelligible. If nothing is
relevant, return exactly: NONE

===== TEXT =====
{text}"""

EXTRACT_PROMPT = """You are performing Phase 2 distillation (instruction set P2.2) for program
{program_id}. Produce the typed BlueprintExtraction JSON per the schema.

RATIFIED SCOPE (extract ONLY content within it):
{scope}

Rules:
- obligations are element-table rows: actor / modality / action / trigger /
  threshold / exceptions. One row per distinct duty. Modality from the text
  itself (shall|must -> must; shall not -> must_not; should -> should;
  may -> may; duties contingent on elections/conditions -> conditional).
- EVERY obligation, objective, definition, and interaction carries at least
  one citation whose "quote" is a VERBATIM span (<=350 chars) copied EXACTLY
  from the source text below. Quotes are machine-checked against the source;
  paraphrased or invented quotes are rejected and discredit the extraction.
- FIDELITY RULE (P2.3): preserve the text's own terms. Do NOT harmonize,
  resolve, modernize, or improve anything. If the text is ambiguous or
  internally inconsistent, extract it as written and say so in notes.
- definitions: defined terms with definitions as given; ALSO record material
  scope-relevant terms the text uses but does not define, with definition
  "(undefined here)".
- interactions: cross-references to other instruments, as the text gives them.
- If nothing in this source falls within the scope, set nothing_in_scope
  true and leave the arrays empty.

SOURCE ITEM: {item_id} — {title}
  issuer: {issuer} | locator: {locator} | status: {status} | evidence role: {role}
{ceiling_note}
===== SOURCE TEXT =====
{text}"""

DEFECT_PROMPT = """You are performing Phase 2 defect detection (instruction set P2.5) for program
{program_id}, over the distilled extractions below. Report typed findings per
the schema. Taxonomy (use ONLY these codes):

{taxonomy}

Rules:
- Findings are OBSERVATIONS with citations, never fixes — proposing a fix
  here is a rule violation (fixes belong to Phase 3).
- Only report what is observable IN THE PROVIDED EXTRACTIONS; each location
  names the item_id and, where possible, a verbatim quote (<=350 chars) taken
  from the extraction quotes below (these are machine-checked).
- Cross-instrument findings (D1, D2, D3, D7, D10) must cite ALL instruments
  involved. Be precise about which duties or definitions diverge and how.
- If the extractions show no defects of a given type, do not invent any.

SCOPE REMINDER: {scope}

===== EXTRACTIONS ({label}) =====
{extractions}"""


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def normalize_citations(extraction: dict) -> None:
    """Losslessly canonicalize citation entries in place: models sometimes emit
    bare quote strings instead of {"quote": ...} objects. The machine check is
    the real gate; the shape must not be the thing that kills an extraction."""
    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "citations" and isinstance(v, list):
                    obj[k] = [{"quote": c} if isinstance(c, str) else c for c in v]
                else:
                    walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)
    walk(extraction)


def verify_citations(extraction: dict, source_text: str) -> tuple[int, int]:
    """Set citation.verified in place via code. Returns (verified, total)."""
    normalize_citations(extraction)
    hay = _norm(source_text)
    verified = total = 0
    def walk(obj):
        nonlocal verified, total
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "citations" and isinstance(v, list):
                    for c in v:
                        if isinstance(c, dict) and c.get("quote"):
                            total += 1
                            ok = _norm(c["quote"]) in hay
                            c["verified"] = ok
                            verified += ok
                else:
                    walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)
    walk(extraction)
    return verified, total


class Distiller:
    """call_fn(task_id, messages) -> (output, stamp) — the server's routed,
    stamped, budgeted call. The Distiller adds no model access of its own."""

    def __init__(self, program_dir: str | Path, *, program_id: str, scope: str,
                 manifest_hash: str, call_fn: Callable):
        self.pdir = Path(program_dir)
        self.program_id = program_id
        self.scope = scope
        self.manifest_hash = manifest_hash
        self.call = call_fn
        self.bdir = self.pdir / "governed" / "blueprint"
        self.bdir.mkdir(parents=True, exist_ok=True)
        self.register_path = self.bdir / "extraction_register.json"

    # ---------- register ----------

    def register(self) -> dict:
        if self.register_path.exists():
            reg = json.loads(self.register_path.read_text())
            if reg.get("manifest_hash") != self.manifest_hash:
                raise ValueError("Extraction register belongs to a different manifest hash — refusing to mix")
            return reg
        return {"manifest_hash": self.manifest_hash, "items": {}}

    def _save(self, reg: dict) -> None:
        self.register_path.write_text(json.dumps(reg, indent=2))

    def _source_text(self, item_id: str) -> str | None:
        p = self.pdir / "governed" / "corpus_texts" / f"{item_id}.txt"
        return p.read_text() if p.exists() else None

    # ---------- extraction ----------

    def _focus(self, text: str) -> tuple[str, float]:
        """Cheap long-context pass: keep only scope-relevant passages."""
        pieces, cost = [], 0.0
        for i in range(0, len(text), FOCUS_CHUNK):
            out, stamp = self.call("distill_focus", [{"role": "user", "content":
                FOCUS_PROMPT.format(scope=self.scope, text=text[i:i + FOCUS_CHUNK])}])
            cost += stamp["cost"]["usd"]
            if out and out.strip() != "NONE":
                pieces.append(out.strip())
        return ("\n---\n".join(pieces) or "NONE"), cost

    def extract_item(self, item: dict) -> dict:
        iid = item["item_id"]
        text = self._source_text(iid)
        if text is None:
            return {"status": "error", "errors": [f"no acquired text for {iid} — acquire first"]}
        cost = 0.0
        focused = False
        if len(text) > FOCUS_LIMIT:
            text, cost = self._focus(text)
            focused = True
            if text == "NONE":
                doc = {"item_id": iid, "nothing_in_scope": True, "objectives": [],
                       "obligations": [], "definitions": [], "interactions": [],
                       "notes": "focus pass found no scope-relevant passages"}
                return self._record(item, doc, cost, focused, verified=0, total=0)
        ceiling = ""
        role = item.get("evidence_role") or ""
        if role in ("enforcement_evidence",):
            ceiling = ("CEILING NOTE: this source is enforcement evidence — it evidences applied "
                       "expectations and may NOT establish an operative duty; extract observations "
                       "as interactions/notes, not as obligations.\n")
        elif role in ("reform_proposal", "horizon"):
            ceiling = ("CEILING NOTE: this source is a proposal/horizon item — it never anchors a "
                       "current-law claim; extract its proposed content as interactions/notes with "
                       "objectives marked 'stated', never as operative obligations.\n")
        out, stamp = self.call("distill_extract", [{"role": "user", "content":
            EXTRACT_PROMPT.format(program_id=self.program_id, scope=self.scope,
                                  item_id=iid, title=item.get("title", ""),
                                  issuer=item.get("issuer", ""), locator=item.get("locator", ""),
                                  status=item.get("status", ""), role=role or "?",
                                  ceiling_note=ceiling, text=text)}])
        cost += stamp["cost"]["usd"]
        out["item_id"] = iid
        source_full = self._source_text(iid) or ""
        verified, total = verify_citations(out, source_full)
        if total > 0 and verified / total < MIN_VERIFIED_RATIO:
            return {"status": "error",
                    "errors": [f"citation verification failed: only {verified}/{total} quotes "
                               f"found verbatim in source — extraction rejected (OR-3)"],
                    "cost_usd": round(cost, 6)}
        substantive = (out.get("obligations") or out.get("definitions")
                       or out.get("objectives") or out.get("interactions"))
        if substantive and total == 0:
            return {"status": "error",
                    "errors": ["extraction makes claims but carries zero citations — "
                               "uncited claims may not enter the blueprint (OR-3)"],
                    "cost_usd": round(cost, 6)}
        return self._record(item, out, cost, focused, verified, total)

    def _record(self, item: dict, doc: dict, cost: float, focused: bool,
                verified: int, total: int) -> dict:
        iid = item["item_id"]
        (self.bdir / f"{iid}.json").write_text(json.dumps(doc, indent=2))
        return {"status": "extracted", "extracted_at": datetime.now(timezone.utc).isoformat(),
                "family": item.get("family"), "focused": focused,
                "obligations": len(doc.get("obligations", [])),
                "definitions": len(doc.get("definitions", [])),
                "nothing_in_scope": doc.get("nothing_in_scope", False),
                "citations_verified": verified, "citations_total": total,
                "cost_usd": round(cost, 6), "manifest_hash": self.manifest_hash}

    def reconcile(self, items: list[dict]) -> dict:
        """Make the register agree with the files and the current source texts.
        Multiple processes have raced these registers before (undead servers);
        the durable rule is: the extraction FILES + current corpus texts are
        the truth, the register is derived. Stale ∅-extractions written from a
        since-replaced source are evicted so they re-run."""
        from workbench.acquire import looks_blocked
        reg = self.register()
        changed = False
        for item in items:
            iid = item["item_id"]
            f = self.bdir / f"{iid}.json"
            rec = reg["items"].get(iid)
            if not f.exists():
                if rec and rec.get("status") == "extracted":
                    reg["items"].pop(iid, None)     # file gone -> pending again
                    changed = True
                continue
            doc = json.loads(f.read_text())
            src = self._source_text(iid) or ""
            # Evict ONLY when the source text was re-acquired AFTER this
            # extraction was written AND the extraction now disagrees with it
            # (empty against real text, or quotes no longer verbatim). A
            # legitimately-empty extraction of an unchanged source is a result,
            # not staleness — re-running it forever would burn budget for
            # nothing (learned from the enforcement-index ∅ loop).
            src_path = self.pdir / "governed" / "corpus_texts" / f"{iid}.txt"
            source_newer = (src_path.exists()
                            and src_path.stat().st_mtime > f.stat().st_mtime + 1)
            verified, total = verify_citations(doc, src)
            disagrees = ((doc.get("nothing_in_scope") and len(src) > 5000
                          and not looks_blocked(src))
                         or (total > 0 and verified / total < MIN_VERIFIED_RATIO))
            if source_newer and disagrees:
                f.unlink()                          # extraction predates the current source
                reg["items"].pop(iid, None)
                changed = True
                continue
            entry = {"status": "extracted",
                     "extracted_at": (rec or {}).get("extracted_at", "reconciled"),
                     "family": item.get("family"), "focused": (rec or {}).get("focused", False),
                     "obligations": len(doc.get("obligations", [])),
                     "definitions": len(doc.get("definitions", [])),
                     "nothing_in_scope": doc.get("nothing_in_scope", False),
                     "citations_verified": verified, "citations_total": total,
                     "cost_usd": (rec or {}).get("cost_usd", 0.0),
                     "manifest_hash": self.manifest_hash}
            if rec != entry:
                f.write_text(json.dumps(doc, indent=2))   # persist refreshed verified flags
                reg["items"][iid] = entry
                changed = True
        if changed:
            self._save(reg)
        return reg

    def run(self, items: list[dict], *, limit: int = 4, retry_errors: bool = False) -> dict:
        self.reconcile(items)
        reg = self.register()
        done = 0
        for item in items:
            iid = item["item_id"]
            rec = reg["items"].get(iid)
            if rec and (rec["status"] == "extracted" or (rec["status"] == "error" and not retry_errors)):
                continue
            if done >= limit:
                break
            done += 1
            try:
                reg["items"][iid] = self.extract_item(item)
            except Exception as e:  # noqa: BLE001 — per-item resilience
                reg["items"][iid] = {"status": "error", "errors": [f"{type(e).__name__}: {str(e)[:800]}"]}
            self._save(reg)
        counts = {"extracted": 0, "error": 0, "pending": 0}
        for it in items:
            st = reg["items"].get(it["item_id"], {}).get("status", "pending")
            counts[st if st in counts else "pending"] += 1
        return {"processed": done, "counts": counts, "items": reg["items"]}

    # ---------- defects ----------

    def _extraction(self, item_id: str) -> dict | None:
        p = self.bdir / f"{item_id}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def detect_defects(self, items: list[dict], *, family: str | None) -> dict:
        """family=None -> cross-corpus definitions/obligations pass."""
        if family:
            chosen = [i for i in items if i.get("family") == family]
            label = f"family: {family}"
        else:
            chosen = items
            label = "cross-corpus (definitions and duties across all families)"
        docs = []
        for it in chosen:
            ex = self._extraction(it["item_id"])
            if ex and not ex.get("nothing_in_scope"):
                slim = {k: ex.get(k) for k in ("item_id", "obligations", "definitions", "interactions", "notes")}
                docs.append(slim)
        if not docs:
            return {"findings": [], "note": "no extractions available for this selection"}
        out, stamp = self.call("defect_detect", [{"role": "user", "content":
            DEFECT_PROMPT.format(program_id=self.program_id, taxonomy=DEFECT_TAXONOMY,
                                 scope=self.scope, label=label,
                                 extractions=json.dumps(docs)[:700_000])}])
        findings = out.get("findings", [])
        # verify defect quotes against extraction quotes + source texts
        for f in findings:
            for loc in f.get("locations", []):
                q = loc.get("quote")
                if not q:
                    continue
                src = self._source_text(loc.get("item_id", "")) or ""
                loc["verified"] = _norm(q) in _norm(src) if src else False
        run_id = f"defects-{family or 'cross'}"
        reg_dir = self.pdir / "governed" / "registers"
        reg_dir.mkdir(parents=True, exist_ok=True)
        dpath = reg_dir / "defects.json"
        existing = json.loads(dpath.read_text()) if dpath.exists() else {"manifest_hash": self.manifest_hash, "runs": {}}
        existing["runs"][run_id] = {
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "scope_label": label, "cost_usd": stamp["cost"]["usd"],
            "findings": findings,
        }
        dpath.write_text(json.dumps(existing, indent=2))
        return {"run_id": run_id, "findings": findings, "cost_usd": stamp["cost"]["usd"]}

    def defects(self) -> dict:
        dpath = self.pdir / "governed" / "registers" / "defects.json"
        return json.loads(dpath.read_text()) if dpath.exists() else {"runs": {}}

    # ---------- assembly ----------

    def assemble(self, items: list[dict]) -> dict:
        fams: dict = {}
        for it in items:
            fam = it.get("family", "?")
            ex = self._extraction(it["item_id"])
            entry = fams.setdefault(fam, {"items": [], "obligations": 0, "definitions": 0})
            entry["items"].append({"item_id": it["item_id"], "extracted": ex is not None,
                                   "nothing_in_scope": bool(ex and ex.get("nothing_in_scope"))})
            if ex:
                entry["obligations"] += len(ex.get("obligations", []))
                entry["definitions"] += len(ex.get("definitions", []))
        defect_runs = self.defects().get("runs", {})
        n_findings = sum(len(r.get("findings", [])) for r in defect_runs.values())
        return {"program_id": self.program_id, "manifest_hash": self.manifest_hash,
                "families": fams, "defect_runs": list(defect_runs.keys()),
                "defect_findings": n_findings}
