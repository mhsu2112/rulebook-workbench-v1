"""Refactor pass (M4 / instruction set §9A): Defect Register → proposed
operations → human-dispositioned queue → Target Blueprint.

Governance shape, enforced in code:
- P3.1 whitelist: operations come from the schema enum; free-form edits cannot
  exist as records.
- P3.3 / NG2: the model's effect class is a DRAFT. Disposition REQUIRES the
  human's confirmed class; the register keeps both, and the ratified artifact
  discloses the manual-classification posture.
- P3.4 routing (OR-1): change/unresolved MUST NOT finalize in this pass —
  the disposition layer rejects the attempt; those moves park to the Redesign
  Backlog.
- P3.6: every disposition emits a decision-log entry via the server's dl_fn.
- P3.8: ratification requires zero open reviews, all findings processed, and
  an invariants run; the Target Blueprint is the derived blueprint plus the
  ordered finalized operation trace (the PRD's sanctioned demo form).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import hashlib

from workbench.distill import verify_citations

WHITELIST = ["MERGE", "SPLIT", "INTRODUCE", "REPEAL", "RELOCATE",
             "CANONICALIZE-DEFINITION", "DEFINE-TERM", "SUBSTITUTE-TERM",
             "NORMALIZE-ELEMENTS", "FACTOR-EXCEPTION", "ELEVATE-GENERAL-RULE",
             "RESOLVE-CROSS-REFERENCE", "RELATE-OBLIGATION"]
EFFECT_CLASSES = ["codify", "clarify", "fill_gap", "change", "unresolved"]
REVIEW_ROLES = ("Policy Reviewer", "Program Owner")

PROPOSE_PROMPT = """You are running the refactor pass (instruction set P3.2) for program
{program_id}. Given ONE defect finding from the Defect Register and the
relevant Derived Blueprint extractions, propose candidate operation(s) that
resolve the defect AT BLUEPRINT LEVEL. Produce the typed OperationProposal
JSON per the schema.

RATIFIED SCOPE: {scope}

HARD RULES:
- P3.1 whitelist. Every move is one of: MERGE, SPLIT, INTRODUCE, REPEAL,
  RELOCATE, CANONICALIZE-DEFINITION, DEFINE-TERM, SUBSTITUTE-TERM (strictly
  meaning-preserving), NORMALIZE-ELEMENTS, FACTOR-EXCEPTION,
  ELEVATE-GENERAL-RULE, RESOLVE-CROSS-REFERENCE, RELATE-OBLIGATION. If the
  defect needs a move the whitelist cannot express, put that in
  cannot_express and propose nothing improvised.
- ADR-005: INTRODUCE may only make explicit a duty the sources already
  establish. If the duty would be new, do not soften it — propose it anyway
  and say so in the rationale; classification will route it to the Redesign
  Backlog (that is the honest path, not a failure).
- P3.5: where two live sources conflict, newest-wins applies ONLY where
  supersession is explicit in the sources. Otherwise a proposed resolution is
  a policy choice — say so.
- ADR-003 product boundary: proposals are advisory blueprint moves addressed
  to an Authority, never operative legal text. Do not draft rule language.
- Every operation carries at least one citation whose quote is a VERBATIM
  span (<=800 chars) from the source texts excerpted below. Quotes are
  machine-checked; invented quotes discredit the proposal.
- This is the refactor pass: fix the drawing, not the bricks. Do not change
  what the law requires.

DEFECT FINDING ({finding_ref}):
{finding}

RELEVANT BLUEPRINT EXTRACTIONS (structured, from the Derived Blueprint):
{extractions}

SOURCE TEXT EXCERPTS (for citation quotes):
{sources}"""

CLASSIFY_PROMPT = """You are drafting an effect-class analysis (instruction set P3.3 / ADR-008)
for ONE proposed refactor operation in program {program_id}. Produce the typed
EffectClassificationDraft JSON per the schema.

Your output is a DRAFT for a human classifier — the baseline_set_for resolver
is not yet implemented, so classification is a human act and you are its
preparation, not its replacement. Reason per spec/20 §3: for every cell
(actor, activity, jurisdiction) the operation touches, does the baseline —
legal hierarchy and delegation, applicability, status controls, evidentiary
ceilings — already require the operation's output?

- codify: the baseline already requires it
- clarify: the baseline supports it but ambiguously
- fill_gap: the duty already exists for the cell and the move merely makes it
  explicit (ADR-005) — say precisely which source establishes the duty
- change: the baseline requires something else or nothing
- unresolved: the baseline itself is indeterminate (routes like change)

Evidentiary ceilings: enforcement evidence NEVER independently establishes an
operative duty; proposed rules never anchor current-law claims. If the
operation's support leans on either, flag it and classify accordingly.

RATIFIED SCOPE: {scope}

DEFECT FINDING: {finding}

PROPOSED OPERATION:
{operation}

RELEVANT BLUEPRINT EXTRACTIONS:
{extractions}"""


def route(effect_class: str) -> str:
    """P3.4 routing table. codify -> eligible (sampled review); clarify and
    fill_gap -> needs_review; change/unresolved -> parked (Redesign Backlog)."""
    if effect_class == "codify":
        return "eligible"
    if effect_class in ("clarify", "fill_gap"):
        return "needs_review"
    return "parked"


class RefactorError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


class Refactorer:
    """call_fn(task_id, messages) -> (output, stamp); dl_fn(entry_dict) -> entry_id."""

    def __init__(self, program_dir: str | Path, *, program_id: str, scope: str,
                 mode: str, manifest_hash: str, call_fn: Callable,
                 dl_fn: Optional[Callable] = None):
        self.pdir = Path(program_dir)
        self.gdir = self.pdir / "governed"
        self.rdir = self.gdir / "registers"
        self.rdir.mkdir(parents=True, exist_ok=True)
        self.bdir = self.gdir / "blueprint"
        self.program_id = program_id
        self.scope = scope
        self.mode = mode                      # "refactor" | "redesign"
        self.manifest_hash = manifest_hash
        self.call = call_fn
        self.dl = dl_fn or (lambda e: None)
        self.register_path = self.rdir / "operations.json"

    # ---------- inputs ----------

    def findings(self) -> list[dict]:
        """Flatten the defect register into stable-ref findings, worked in
        blast-radius order (P3.2): definition defects first, then duplicates/
        conflicts, then references."""
        dpath = self.rdir / "defects.json"
        if not dpath.exists():
            return []
        d = json.loads(dpath.read_text())
        out = []
        for run_id, run in sorted(d.get("runs", {}).items()):
            for i, f in enumerate(run.get("findings", [])):
                out.append({"finding_ref": f"{run_id}#{i}", **f})
        order = {"D2": 0, "D4": 1, "D3": 2, "D1": 3, "D10": 4, "D7": 5,
                 "D5": 6, "D6": 7, "D8": 8, "D9": 9}
        out.sort(key=lambda f: (order.get(f.get("code"), 99), f["finding_ref"]))
        return out

    def _extraction_excerpt(self, item_id: str, limit: int = 6000) -> str:
        p = self.bdir / f"{item_id}.json"
        if not p.exists():
            return f"({item_id}: no extraction)"
        doc = json.loads(p.read_text())
        slim = {"item_id": item_id,
                "obligations": doc.get("obligations", []),
                "definitions": doc.get("definitions", []),
                "interactions": doc.get("interactions", [])}
        return json.dumps(slim)[:limit]

    def _source_excerpt(self, item_id: str, limit: int = 8000) -> str:
        p = self.gdir / "corpus_texts" / f"{item_id}.txt"
        return p.read_text()[:limit] if p.exists() else ""

    def _finding_items(self, finding: dict) -> list[str]:
        return sorted({loc.get("item_id") for loc in finding.get("locations", [])
                       if loc.get("item_id")})

    # ---------- register ----------

    def register(self) -> dict:
        if self.register_path.exists():
            return json.loads(self.register_path.read_text())
        return {"manifest_hash": self.manifest_hash, "operations": {},
                "findings_processed": {}, "cannot_express": []}

    def _save(self, reg: dict) -> None:
        self.register_path.write_text(json.dumps(reg, indent=2))

    # ---------- propose (P3.2 + P3.3) ----------

    def propose(self, *, limit: int = 4, retry_errors: bool = False) -> dict:
        reg = self.register()
        done = 0
        for finding in self.findings():
            ref = finding["finding_ref"]
            rec = reg["findings_processed"].get(ref)
            if rec and (rec.get("status") == "processed"
                        or (rec.get("status") == "error" and not retry_errors)):
                continue
            if done >= limit:
                break
            done += 1
            try:
                reg["findings_processed"][ref] = self._propose_one(reg, finding)
            except Exception as e:  # noqa: BLE001 — per-finding resilience
                reg["findings_processed"][ref] = {
                    "status": "error", "errors": [f"{type(e).__name__}: {str(e)[:800]}"]}
            self._save(reg)
        return self.summary(reg)

    def _propose_one(self, reg: dict, finding: dict) -> dict:
        ref = finding["finding_ref"]
        items = self._finding_items(finding)
        extractions = "\n".join(self._extraction_excerpt(i) for i in items) or "(none)"
        sources = "\n\n".join(f"===== {i} =====\n{self._source_excerpt(i)}"
                              for i in items) or "(none)"
        finding_body = json.dumps({k: v for k, v in finding.items()
                                   if k != "finding_ref"})
        cost = 0.0
        out, stamp = self.call("operation_propose", [{"role": "user", "content":
            PROPOSE_PROMPT.format(program_id=self.program_id, scope=self.scope,
                                  finding_ref=ref, finding=finding_body,
                                  extractions=extractions, sources=sources)}])
        cost += stamp["cost"]["usd"]
        if out.get("cannot_express"):
            reg["cannot_express"].append({"finding_ref": ref,
                                          "note": out["cannot_express"],
                                          "logged_at": _now()})
        op_ids = []
        source_all = "\n".join(self._source_excerpt(i, limit=200_000) for i in items)
        for op in out.get("operations", []):
            if op.get("op_type") not in WHITELIST:
                # RECALIBRATE (and anything else outside the refactor whitelist)
                # is a redesign-pass move — record, never queue (P3.1)
                reg["cannot_express"].append({
                    "finding_ref": ref,
                    "note": f"{op.get('op_type')} is outside the refactor-pass whitelist — "
                            "redesign-pass move, not queued",
                    "logged_at": _now()})
                continue
            verified, total = verify_citations(op, source_all)
            if total > 0 and verified == 0:
                # a proposal whose every quote fails the machine check may not
                # enter the queue (OR-3 discipline extends to Phase 3)
                reg["cannot_express"].append({
                    "finding_ref": ref,
                    "note": f"proposal for {op.get('op_type')} rejected: 0/{total} citation quotes verified",
                    "logged_at": _now()})
                continue
            cls, stamp2 = self.call("effect_classify_assist", [{"role": "user", "content":
                CLASSIFY_PROMPT.format(program_id=self.program_id, scope=self.scope,
                                       finding=finding_body, operation=json.dumps(op),
                                       extractions=extractions)}])
            cost += stamp2["cost"]["usd"]
            op_id = f"OP-{len(reg['operations']) + 1:03d}"
            reg["operations"][op_id] = {
                "op_id": op_id, "finding_ref": ref,
                "defect_code": finding.get("code"),
                "defect_title": finding.get("title"),
                "operation": op,
                "citations_verified": verified, "citations_total": total,
                "draft_classification": cls,
                "status": route(cls["draft_effect_class"]),
                "proposed_at": _now(),
                "disposition": None,
            }
            op_ids.append(op_id)
        return {"status": "processed", "op_ids": op_ids,
                "cost_usd": round(cost, 6), "processed_at": _now()}

    # ---------- disposition (P3.4 routing + P3.6 logging) ----------

    def disposition(self, op_id: str, *, name: str, role: str, action: str,
                    effect_class: str, rationale: str,
                    modified_proposal: Optional[str] = None) -> dict:
        reg = self.register()
        op = reg["operations"].get(op_id)
        if not op:
            raise RefactorError(404, f"unknown operation {op_id}")
        if op["status"] in ("finalized", "rejected"):
            raise RefactorError(409, f"{op_id} already dispositioned ({op['status']})")
        if role not in REVIEW_ROLES:
            raise RefactorError(403, f"disposition requires one of {REVIEW_ROLES} (OR-4)")
        if not (rationale or "").strip():
            raise RefactorError(400, "a disposition without a rationale is not a decision — rationale required")
        if effect_class not in EFFECT_CLASSES:
            raise RefactorError(400, f"effect_class must be one of {EFFECT_CLASSES} — "
                                     "this is the HUMAN classification (NG2); the model's draft does not count")
        if action not in ("accept", "modify", "reject", "park"):
            raise RefactorError(400, "action must be accept | modify | reject | park")
        if action in ("accept", "modify") and effect_class in ("change", "unresolved"):
            raise RefactorError(403,
                "OR-1: change/unresolved-class moves MUST NOT finalize in the refactor pass "
                "— park to the Redesign Backlog or reject")
        if action == "modify" and not (modified_proposal or "").strip():
            raise RefactorError(400, "modify requires the modified proposal text")

        op["disposition"] = {
            "reviewer": {"name": name, "role": role},
            "action": action, "effect_class": effect_class,
            "draft_effect_class": op["draft_classification"]["draft_effect_class"],
            "rationale": rationale, "modified_proposal": modified_proposal,
            "timestamp": _now(),
        }
        op["status"] = {"accept": "finalized", "modify": "finalized",
                        "reject": "rejected", "park": "parked"}[action]
        self._save(reg)
        self.dl({
            "type": "disposition",
            "artifact": f"registers/operations.json#{op_id}",
            "artifact_version": "0.1",
            "decision": f"{action} {op['operation']['op_type']} ({op_id}) as {effect_class} "
                        f"for {op['finding_ref']}",
            "rationale": rationale,
            "decided_by": {"name": name, "role": role},
        })
        return op

    # ---------- invariants (P3.7) ----------

    def invariants(self) -> dict:
        reg = self.register()
        checks = []
        # definitional uniqueness across the blueprint (post-finalization goal)
        terms: dict[str, set] = {}
        for f in self.bdir.glob("*.json"):
            if f.name == "extraction_register.json":
                continue
            doc = json.loads(f.read_text())
            for d in doc.get("definitions", []):
                t = (d.get("term") or "").strip().casefold()
                if t and d.get("definition") not in (None, "(undefined here)"):
                    terms.setdefault(t, set()).add(d["definition"].strip())
        multi = {t: len(v) for t, v in terms.items() if len(v) > 1}
        canonicalized = {op["operation"].get("parameters") or "" for op in
                        reg["operations"].values()
                        if op["status"] == "finalized"
                        and op["operation"]["op_type"] == "CANONICALIZE-DEFINITION"}
        checks.append({
            "name": "definitional_uniqueness",
            "status": "warn" if multi else "pass",
            "details": f"{len(multi)} terms with >1 materially distinct definitions remain in the "
                       f"derived blueprint; {len(canonicalized)} CANONICALIZE-DEFINITION operations "
                       "finalized against them. In operation-trace form the trace records the fix; "
                       "the underlying extractions intentionally keep the as-built divergence (P2.3)."})
        # referential integrity of the operation trace
        known = {f.stem for f in self.bdir.glob("*.json")}
        dangling = [op["op_id"] for op in reg["operations"].values()
                    for t in op["operation"]["targets"]
                    if t["item_id"] not in known]
        checks.append({"name": "operation_referential_integrity",
                       "status": "fail" if dangling else "pass",
                       "details": f"operations targeting unknown blueprint items: {dangling or 'none'}"})
        # no open reviews / undispositioned findings
        open_reviews = [o["op_id"] for o in reg["operations"].values()
                        if o["status"] in ("needs_review", "eligible")]
        checks.append({"name": "zero_open_dispositions",
                       "status": "fail" if open_reviews else "pass",
                       "details": f"open: {open_reviews or 'none'}"})
        # every defect finding processed
        unprocessed = [f["finding_ref"] for f in self.findings()
                       if reg["findings_processed"].get(f["finding_ref"], {}).get("status") != "processed"]
        checks.append({"name": "defect_register_fully_worked",
                       "status": "fail" if unprocessed else "pass",
                       "details": f"unworked findings: {len(unprocessed)}"})
        report = {"ran_at": _now(), "checks": checks,
                  "pass": all(c["status"] != "fail" for c in checks)}
        (self.rdir / "invariants.json").write_text(json.dumps(report, indent=2))
        return report

    # ---------- ratify (P3.8) ----------

    def ratify(self, *, name: str, role: str, rationale: str) -> dict:
        if role != "Program Owner":
            raise RefactorError(403, "ratification is the Program Owner's act (OR-4)")
        if not (rationale or "").strip():
            raise RefactorError(400, "rationale required")
        reg = self.register()
        report = self.invariants()
        if not report["pass"]:
            failing = [c["name"] for c in report["checks"] if c["status"] == "fail"]
            raise RefactorError(409, f"invariants failing: {failing} — resolve or log exceptions first")
        tb_path = self.gdir / "target_blueprint.json"
        if tb_path.exists():
            raise RefactorError(409, "already ratified — the Target Blueprint is frozen (OR-7)")
        ops = [op for op in reg["operations"].values() if op["status"] == "finalized"]
        ops.sort(key=lambda o: o["op_id"])
        parked = [op["op_id"] for op in reg["operations"].values() if op["status"] == "parked"]
        reviewers = {op["disposition"]["reviewer"]["name"] for op in reg["operations"].values()
                     if op.get("disposition")}
        label = ("Refactored Blueprint (certified — redesign baseline)"
                 if self.mode == "redesign" else "Target Blueprint")
        doc = {
            "label": label, "program_id": self.program_id, "mode": self.mode,
            "based_on": {"manifest_hash": self.manifest_hash,
                         "derived_blueprint_items": sorted(
                             f.stem for f in self.bdir.glob("*.json")
                             if f.name != "extraction_register.json")},
            "operation_trace": ops,
            "redesign_backlog": parked,
            "cannot_express_log": reg.get("cannot_express", []),
            "invariants_report": report,
            "disclosures": {
                "manual_effect_classification": True,   # P3.3 posture until the resolver exists
                "operation_trace_form": "The Target Blueprint is the Derived Blueprint plus this "
                                        "ordered operation trace; a materialized composite is v2 (backlog B6).",
                "adjudication": ("non_gating_demo_only (single reviewer)" if len(reviewers) <= 1
                                 else f"reviewers: {sorted(reviewers)}"),
            },
            "ratified_by": {"name": name, "role": role},
            "ratified_at": _now(), "rationale": rationale,
        }
        doc["content_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(doc["operation_trace"], sort_keys=True).encode()).hexdigest()
        tb_path.write_text(json.dumps(doc, indent=2))
        self.dl({
            "type": "ratification",
            "artifact": "target_blueprint.json", "artifact_version": "1.0",
            "decision": f"Ratify {label}: {len(ops)} operations finalized, "
                        f"{len(parked)} parked to Redesign Backlog",
            "rationale": rationale, "decided_by": {"name": name, "role": role},
        })
        return doc

    # ---------- summary ----------

    def summary(self, reg: Optional[dict] = None) -> dict:
        reg = reg or self.register()
        counts = {"needs_review": 0, "eligible": 0, "finalized": 0,
                  "parked": 0, "rejected": 0}
        for op in reg["operations"].values():
            counts[op["status"]] = counts.get(op["status"], 0) + 1
        total = len(self.findings())
        processed = sum(1 for v in reg["findings_processed"].values()
                        if v.get("status") == "processed")
        errors = [k for k, v in reg["findings_processed"].items()
                  if v.get("status") == "error"]
        inv = None
        ipath = self.rdir / "invariants.json"
        if ipath.exists():
            inv = json.loads(ipath.read_text())
        ratified = (self.gdir / "target_blueprint.json").exists()
        return {"findings_total": total, "findings_processed": processed,
                "findings_errors": errors, "counts": counts,
                "operations": reg["operations"],
                "cannot_express": reg.get("cannot_express", []),
                "invariants": inv, "ratified": ratified, "mode": self.mode,
                "cost_usd": round(sum(v.get("cost_usd", 0)
                                      for v in reg["findings_processed"].values()), 4)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
