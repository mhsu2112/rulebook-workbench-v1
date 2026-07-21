"""Redesign pass (instruction set §9B: P0.9 + P3D.1–P3D.7) and successor
chartering (ADR-007 sequence split).

Governance shape, enforced in code:
- P0.9: MandateHypotheses are adopted / amended / discarded ONLY by an
  identity-asserted Principal, each with rationale; adoption never happens by
  default, silence, or the workbench. The Ratified Mandate is versioned and
  frozen; ranking must totally order the adopted objectives.
- P3D.4: every proposed move carries an objective hook naming an ADOPTED
  objective; hookless or hypothesis-hooked moves cannot enter review. All
  change-class dispositions are the Principal's (or named delegate's).
  Nothing auto-finalizes.
- P3D.5: an unranked tradeoff cannot be resolved in review — the move is
  RETURNED to the Principal as a proposed Mandate amendment, logged.
- P3D.7: the imported Redesign Backlog must end empty of undecided items:
  adopt / decline / defer, each logged.
- Exit: every adopted objective served by a finalized move or explicitly
  deferred with the Principal's rationale; then Program-Owner ratification.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from workbench.distill import verify_citations
from workbench.refactor import RefactorError

REDESIGN_WHITELIST = ["MERGE", "SPLIT", "INTRODUCE", "REPEAL", "RELOCATE",
                      "CANONICALIZE-DEFINITION", "DEFINE-TERM", "SUBSTITUTE-TERM",
                      "NORMALIZE-ELEMENTS", "FACTOR-EXCEPTION", "ELEVATE-GENERAL-RULE",
                      "RESOLVE-CROSS-REFERENCE", "RELATE-OBLIGATION", "RECALIBRATE"]

MISALIGN_PROMPT = """You are performing P3D.2 for redesign program {program_id}: evaluate the
Refactored Blueprint against each Ratified Mandate objective and report typed
MisalignmentFindings per the schema. Findings, not decisions: cite blueprint
elements and objectives; propose NO fixes; adjudicate NO tradeoffs.

Taxonomy (use ONLY these codes):
M1 objective unserved or underserved (no blueprint mechanism advances it)
M2 provision serves no Mandate objective (candidate for repeal or renewed justification)
M3 burden disproportionate to the objective served
M4 objectives conflict as implemented (one advanced by defeating a higher-ranked one — cite the ranking)
M5 objective served only indirectly or fragilely (accident of drafting, not design)

RATIFIED MANDATE (the only source of objectives — ranked; constraints bind):
{mandate}

REFACTORED BLUEPRINT DIGEST:
{digest}

FINALIZED REFACTOR OPERATION TRACE (the baseline includes these):
{trace}"""

REDESIGN_PROPOSE_PROMPT = """You are performing P3D.4 for redesign program {program_id}: given ONE
misalignment finding, propose candidate move(s) that serve the Ratified
Mandate. Produce the typed OperationProposal JSON per the schema.

RATIFIED MANDATE (ranked objectives; constraints bind):
{mandate}

HARD RULES:
- Whitelist: {whitelist}. RECALIBRATE (adjust a threshold, ratio, frequency,
  deadline, or applicability line) and unconstrained INTRODUCE are now
  permitted — under change-class governance. Free-form edits remain
  prohibited; use cannot_express for whitelist gaps.
- EVERY operation MUST carry objective_hook naming an ADOPTED objective id
  from the Mandate above and stating how the move serves it. A move you
  cannot hook must not be proposed.
- P3D.5 tradeoff rule: if the move advances one objective at cost to another,
  fill the tradeoff field. ranking_basis must quote the Mandate's ranking; if
  the Mandate does not rank the pair, set ranking_basis null — the system
  will return the move to the Principal. NEVER resolve an unranked tradeoff
  yourself.
- Constraints in the Mandate (statutory floors etc.) are inviolable: a move
  that would breach one goes in cannot_express with the constraint named.
- Citations: verbatim quotes (<=800 chars) from the source texts below,
  machine-checked. For INTRODUCE moves creating genuinely new duties, cite
  the evidence motivating the gap (the finding's basis), and say plainly in
  the rationale that the duty is NEW.
- ADR-003: advisory blueprint moves addressed to an Authority — never draft
  operative legal text.

MISALIGNMENT FINDING ({finding_ref}):
{finding}

RELEVANT BLUEPRINT EXTRACTIONS:
{extractions}

SOURCE TEXT EXCERPTS:
{sources}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- chartering

def charter_successor(pred_dir: Path, succ_dir: Path, *, pred_id: str,
                      succ_id: str) -> dict:
    """ADR-007: create the redesign successor from a ratified refactor
    predecessor. Copies corpus identity (frozen manifest), the blueprint
    store, texts, the certified baseline, and the preserved hypotheses."""
    tb_path = pred_dir / "governed" / "target_blueprint.json"
    if not tb_path.exists():
        raise RefactorError(409, f"{pred_id} has not ratified its Target Blueprint — "
                                 "the successor charters from a certified baseline (OR-8)")
    if succ_dir.exists():
        raise RefactorError(409, f"program {succ_id} already exists")
    g_pred, g_succ = pred_dir / "governed", succ_dir / "governed"
    (g_succ / "registers").mkdir(parents=True)
    shutil.copytree(g_pred / "manifest", g_succ / "manifest")
    shutil.copytree(g_pred / "blueprint", g_succ / "blueprint")
    (g_succ / "corpus_texts").mkdir()
    for f in (g_pred / "corpus_texts").glob("*"):
        if f.suffix in (".txt", ".json"):
            shutil.copy(f, g_succ / "corpus_texts" / f.name)
    shutil.copy(tb_path, g_succ / "refactored_baseline.json")
    if (g_pred / "blueprint_summary.json").exists():
        shutil.copy(g_pred / "blueprint_summary.json", g_succ / "blueprint_summary.json")
    r_pred = pred_dir / "restricted"
    if (r_pred / "mandate_hypotheses.json").exists():
        (succ_dir / "restricted").mkdir(parents=True, exist_ok=True)
        shutil.copy(r_pred / "mandate_hypotheses.json",
                    succ_dir / "restricted" / "mandate_hypotheses.json")
    ps = json.loads((g_pred / "purpose_statement.json").read_text())
    baseline_hash = json.loads(tb_path.read_text()).get("content_hash", "")
    ps["program_id"] = succ_id
    ps["statement_id"] = f"ps-{succ_id}"
    ps["synthesis"]["recommended_mode"] = {
        "mode": "redesign",
        "basis_answer_ids": ps["synthesis"]["recommended_mode"].get("basis_answer_ids", []),
        "mode_consistency_note": (f"Successor program chartered per ADR-007 from {pred_id}: "
                                  f"the deferred redesign-flavored aspirations proceed here, against "
                                  f"the certified Refactored Blueprint baseline ({baseline_hash}). "
                                  "The predecessor's interview and elections carry over; the mode "
                                  "election for THIS program is redesign, as chartered."),
    }
    ps["synthesis"]["scope_sentence"]["text"] += (
        f" [Program 2: redesign under the Ratified Mandate, baseline {baseline_hash}]")
    ps["status"] = "awaiting_ratification"
    ps["ratification"] = {"status": "awaiting_ratification"}
    ps["open_items"] = [{"item_id": "OI-P2-1",
                         "description": "Ratify the Mandate (P0.9) before the redesign pass — "
                                        "hypotheses confer no authority",
                         "owner": "Principal", "blocking": False}]
    (g_succ / "purpose_statement.json").write_text(json.dumps(ps, indent=2))
    return {"successor": succ_id, "baseline_hash": baseline_hash,
            "hypotheses_transferred": (succ_dir / "restricted" / "mandate_hypotheses.json").exists()}


# ---------------------------------------------------------------- the pass

class Redesigner:
    def __init__(self, program_dir: str | Path, *, program_id: str, scope: str,
                 call_fn: Callable, dl_fn: Optional[Callable] = None):
        self.pdir = Path(program_dir)
        self.gdir = self.pdir / "governed"
        self.rdir = self.gdir / "registers"
        self.rdir.mkdir(parents=True, exist_ok=True)
        self.bdir = self.gdir / "blueprint"
        self.program_id = program_id
        self.scope = scope
        self.call = call_fn
        self.dl = dl_fn or (lambda e: None)
        self.register_path = self.rdir / "redesign_operations.json"

    # ---------- P0.9 mandate ----------

    def hypotheses(self) -> dict | None:
        p = self.pdir / "restricted" / "mandate_hypotheses.json"
        return json.loads(p.read_text()) if p.exists() else None

    def mandate(self) -> dict | None:
        p = self.gdir / "ratified_mandate.json"
        return json.loads(p.read_text()) if p.exists() else None

    def ratify_mandate(self, *, name: str, role: str, decisions: list[dict],
                       ranking: list[str], constraints: list[str],
                       rationale: str) -> dict:
        if role != "Principal":
            raise RefactorError(403, "Mandate adoption is the Principal's act (P0.9) — "
                                     "no other role may promote hypotheses")
        if not (rationale or "").strip():
            raise RefactorError(400, "rationale required")
        if self.mandate():
            raise RefactorError(409, "Mandate already ratified — amendments are a logged "
                                     "Principal act (P3D.1), not a re-ratification")
        hyp = self.hypotheses()
        if not hyp:
            raise RefactorError(409, "no MandateHypotheses on file — run/import P0.1 material first")
        by_id = {o["objective_id"]: o for o in hyp.get("objectives", [])}
        decided = {d["objective_id"]: d for d in decisions}
        missing = sorted(set(by_id) - set(decided))
        if missing:
            raise RefactorError(400, f"every hypothesis must be dispositioned; missing: {missing} "
                                     "(adopt, amend, or discard — silence adopts nothing)")
        adopted = []
        for oid, d in decided.items():
            if d.get("action") not in ("adopt", "amend", "discard"):
                raise RefactorError(400, f"{oid}: action must be adopt | amend | discard")
            if not (d.get("rationale") or "").strip():
                raise RefactorError(400, f"{oid}: per-objective rationale required")
            if d["action"] == "discard":
                continue
            src = by_id.get(oid, {})
            statement = (d.get("amended_statement") or "").strip() if d["action"] == "amend" \
                else src.get("statement", "")
            if d["action"] == "amend" and not statement:
                raise RefactorError(400, f"{oid}: amend requires amended_statement")
            adopted.append({
                "objective_id": oid, "statement": statement,
                "origin": {"hypothesis_attribution": src.get("attribution"),
                           "action": d["action"]},
                "policy_choice": {"adopted_by": {"name": name, "role": "Principal"},
                                  "timestamp": _now(), "rationale": d["rationale"]},
            })
        if not adopted:
            raise RefactorError(400, "a Mandate with zero adopted objectives cannot anchor a "
                                     "redesign — adopt at least one or stop the program")
        adopted_ids = {o["objective_id"] for o in adopted}
        if set(ranking) != adopted_ids:
            raise RefactorError(400, f"ranking must totally order the adopted objectives "
                                     f"{sorted(adopted_ids)} — got {ranking}")
        doc = {"mandate_id": f"rm-{self.program_id}", "program_id": self.program_id,
               "version": "1.0", "status": "ratified",
               "objectives": adopted, "ranking": ranking,
               "constraints": constraints or [],
               "ratified_by": {"name": name, "role": "Principal", "identity_verified": True},
               "ratified_at": _now(), "rationale": rationale}
        doc["content_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(doc, sort_keys=True).encode()).hexdigest()
        (self.gdir / "ratified_mandate.json").write_text(json.dumps(doc, indent=2))
        self.dl({"type": "ratification", "artifact": "ratified_mandate.json",
                 "artifact_version": "1.0",
                 "decision": f"Ratify Mandate: {len(adopted)} objectives adopted "
                             f"({len(by_id) - len(adopted)} discarded), ranked; "
                             f"{len(constraints or [])} constraints",
                 "rationale": rationale,
                 "decided_by": {"name": name, "role": "Principal"}})
        return doc

    def _mandate_or_409(self) -> dict:
        m = self.mandate()
        if not m:
            raise RefactorError(409, "No Ratified Mandate — the redesign pass MUST NOT run on "
                                     "hypotheses (P0.9); ratify the Mandate first")
        return m

    def _mandate_text(self, m: dict) -> str:
        lines = [f"{o['objective_id']}: {o['statement']}" for o in m["objectives"]]
        lines.append("RANKING (highest first): " + " > ".join(m["ranking"]))
        for c in m.get("constraints", []):
            lines.append("CONSTRAINT: " + c)
        return "\n".join(lines)

    # ---------- P3D.2 misalignment ----------

    def detect_misalignments(self) -> dict:
        m = self._mandate_or_409()
        from workbench.render import build_digest
        digest, _ = build_digest(self.pdir)
        baseline = json.loads((self.gdir / "refactored_baseline.json").read_text())
        trace = json.dumps([{ "op_id": o["op_id"], "type": o["operation"]["op_type"],
                              "proposal": o["operation"]["proposal"][:200]}
                            for o in baseline.get("operation_trace", [])])
        out, stamp = self.call("misalign_detect", [{"role": "user", "content":
            MISALIGN_PROMPT.format(program_id=self.program_id,
                                   mandate=self._mandate_text(m),
                                   digest=digest[:200_000], trace=trace)}])
        known = {o["objective_id"] for o in m["objectives"]}
        for f in out.get("findings", []):
            f["objective_ids"] = [o for o in f["objective_ids"] if o in known] or ["UNMATCHED"]
        doc = {"ran_at": _now(), "mandate_hash": m["content_hash"],
               "cost_usd": stamp["cost"]["usd"], "findings": out.get("findings", [])}
        (self.rdir / "misalignments.json").write_text(json.dumps(doc, indent=2))
        return doc

    def misalignments(self) -> dict | None:
        p = self.rdir / "misalignments.json"
        return json.loads(p.read_text()) if p.exists() else None

    # ---------- register ----------

    def register(self) -> dict:
        if self.register_path.exists():
            return json.loads(self.register_path.read_text())
        reg = {"operations": {}, "findings_processed": {}, "cannot_express": [],
               "backlog": {}}
        baseline = self.gdir / "refactored_baseline.json"
        if baseline.exists():
            tb = json.loads(baseline.read_text())
            reg["backlog"] = {op_id: {"op_id": op_id, "status": "undecided"}
                              for op_id in tb.get("redesign_backlog", [])}
        return reg

    def _save(self, reg: dict) -> None:
        self.register_path.write_text(json.dumps(reg, indent=2))

    # ---------- P3D.4 propose ----------

    def findings(self) -> list[dict]:
        mis = self.misalignments()
        if not mis:
            return []
        return [{"finding_ref": f"mis#{i}", **f} for i, f in enumerate(mis["findings"])]

    def _extraction_excerpt(self, item_id: str, limit: int = 6000) -> str:
        p = self.bdir / f"{item_id}.json"
        if not p.exists():
            return f"({item_id}: no extraction)"
        d = json.loads(p.read_text())
        return json.dumps({"item_id": item_id, "obligations": d.get("obligations", []),
                           "definitions": d.get("definitions", [])})[:limit]

    def _source_excerpt(self, item_id: str, limit: int = 8000) -> str:
        p = self.gdir / "corpus_texts" / f"{item_id}.txt"
        return p.read_text()[:limit] if p.exists() else ""

    def propose(self, *, limit: int = 4, retry_errors: bool = False) -> dict:
        m = self._mandate_or_409()
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
                reg["findings_processed"][ref] = self._propose_one(reg, m, finding)
            except Exception as e:  # noqa: BLE001
                reg["findings_processed"][ref] = {
                    "status": "error", "errors": [f"{type(e).__name__}: {str(e)[:800]}"]}
            self._save(reg)
        return self.summary(reg)

    def _propose_one(self, reg: dict, m: dict, finding: dict) -> dict:
        ref = finding["finding_ref"]
        items = [r for r in finding.get("blueprint_refs", [])
                 if (self.bdir / f"{r}.json").exists()][:6]
        extractions = "\n".join(self._extraction_excerpt(i) for i in items) or "(none)"
        sources = "\n\n".join(f"===== {i} =====\n{self._source_excerpt(i)}"
                              for i in items) or "(none)"
        finding_body = json.dumps({k: v for k, v in finding.items() if k != "finding_ref"})
        cost = 0.0
        out, stamp = self.call("redesign_propose", [{"role": "user", "content":
            REDESIGN_PROPOSE_PROMPT.format(program_id=self.program_id,
                                           mandate=self._mandate_text(m),
                                           whitelist=", ".join(REDESIGN_WHITELIST),
                                           finding_ref=ref, finding=finding_body,
                                           extractions=extractions, sources=sources)}])
        cost += stamp["cost"]["usd"]
        if out.get("cannot_express"):
            reg["cannot_express"].append({"finding_ref": ref, "note": out["cannot_express"],
                                          "logged_at": _now()})
        adopted_ids = {o["objective_id"] for o in m["objectives"]}
        op_ids = []
        source_all = "\n".join(self._source_excerpt(i, limit=200_000) for i in items)
        for op in out.get("operations", []):
            hook = op.get("objective_hook")
            if not hook or hook.get("objective_id") not in adopted_ids:
                # No hook, or hooked to something the Principal never adopted:
                # the move is RETURNED, not reviewed (P3D.4 / Example F).
                reg["cannot_express"].append({
                    "finding_ref": ref,
                    "note": f"{op.get('op_type')} returned: objective hook "
                            f"{'missing' if not hook else repr(hook.get('objective_id')) + ' is not an adopted objective'}"
                            " — hypotheses and enthusiasm confer no authority",
                    "logged_at": _now()})
                continue
            verified, total = verify_citations(op, source_all)
            if total > 0 and verified == 0:
                reg["cannot_express"].append({
                    "finding_ref": ref,
                    "note": f"{op.get('op_type')} rejected: 0/{total} citation quotes verified",
                    "logged_at": _now()})
                continue
            cls, stamp2 = self.call("effect_classify_assist", [{"role": "user", "content":
                "REDESIGN PASS — change-class is workable here but still must be honest.\n"
                + finding_body + "\nOPERATION:\n" + json.dumps(op)
                + "\nProduce the typed EffectClassificationDraft JSON per the schema."}])
            cost += stamp2["cost"]["usd"]
            tr = op.get("tradeoff")
            unranked = bool(tr) and not (tr.get("ranking_basis") or "").strip()
            op_id = f"RD-{len(reg['operations']) + 1:03d}"
            reg["operations"][op_id] = {
                "op_id": op_id, "finding_ref": ref,
                "misalignment_code": finding.get("code"),
                "misalignment_title": finding.get("title"),
                "operation": op,
                "citations_verified": verified, "citations_total": total,
                "draft_classification": cls,
                "status": "returned_tradeoff" if unranked else "needs_review",
                "proposed_at": _now(), "disposition": None,
            }
            op_ids.append(op_id)
        return {"status": "processed", "op_ids": op_ids,
                "cost_usd": round(cost, 6), "processed_at": _now()}

    # ---------- dispositions ----------

    def disposition(self, op_id: str, *, name: str, role: str, action: str,
                    effect_class: str, rationale: str,
                    modified_proposal: Optional[str] = None) -> dict:
        reg = self.register()
        op = reg["operations"].get(op_id)
        if not op:
            raise RefactorError(404, f"unknown operation {op_id}")
        if op["status"] in ("finalized", "rejected"):
            raise RefactorError(409, f"{op_id} already dispositioned ({op['status']})")
        if not (rationale or "").strip():
            raise RefactorError(400, "rationale required")
        if action not in ("accept", "modify", "reject", "return"):
            raise RefactorError(400, "action must be accept | modify | reject | return")
        if op["status"] == "returned_tradeoff" and action in ("accept", "modify"):
            raise RefactorError(403, "P3D.5: this move carries an UNRANKED tradeoff — it cannot "
                                     "be finalized by anyone in review. It goes to the Principal "
                                     "as a proposed Mandate amendment (action: return), or reject it")
        if effect_class in ("change", "unresolved") and role not in ("Principal", "Principal Delegate"):
            raise RefactorError(403, "P3D.4: change-class moves are dispositioned by the Principal "
                                     "or named delegate — a Policy Reviewer may not finalize them here")
        if effect_class not in ("codify", "clarify", "fill_gap", "change", "unresolved"):
            raise RefactorError(400, "invalid effect_class")
        if role not in ("Principal", "Principal Delegate", "Policy Reviewer", "Program Owner"):
            raise RefactorError(403, "unknown review role")
        if action == "modify" and not (modified_proposal or "").strip():
            raise RefactorError(400, "modify requires the modified proposal text")
        op["disposition"] = {"reviewer": {"name": name, "role": role},
                             "action": action, "effect_class": effect_class,
                             "draft_effect_class": op["draft_classification"]["draft_effect_class"],
                             "rationale": rationale, "modified_proposal": modified_proposal,
                             "timestamp": _now()}
        op["status"] = {"accept": "finalized", "modify": "finalized",
                        "reject": "rejected", "return": "returned_tradeoff"}[action]
        self._save(reg)
        self.dl({"type": "disposition",
                 "artifact": f"registers/redesign_operations.json#{op_id}",
                 "artifact_version": "0.1",
                 "decision": f"{action} {op['operation']['op_type']} ({op_id}) as {effect_class} "
                             f"for {op['finding_ref']} "
                             f"[hook: {op['operation'].get('objective_hook', {}).get('objective_id')}]",
                 "rationale": rationale, "decided_by": {"name": name, "role": role}})
        return op

    def backlog_disposition(self, op_id: str, *, name: str, role: str, action: str,
                            rationale: str, objective_id: Optional[str] = None) -> dict:
        reg = self.register()
        item = reg["backlog"].get(op_id)
        if not item:
            raise RefactorError(404, f"{op_id} is not in the imported Redesign Backlog")
        if item["status"] != "undecided":
            raise RefactorError(409, f"{op_id} already {item['status']}")
        if role not in ("Principal", "Principal Delegate"):
            raise RefactorError(403, "Backlog dispositions belong to the Principal (P3D.7)")
        if not (rationale or "").strip():
            raise RefactorError(400, "rationale required")
        if action not in ("adopt", "decline", "defer"):
            raise RefactorError(400, "action must be adopt | decline | defer")
        if action == "adopt":
            m = self._mandate_or_409()
            if objective_id not in {o["objective_id"] for o in m["objectives"]}:
                raise RefactorError(400, "adopt requires objective_id of an ADOPTED objective — "
                                         "the hook rule applies to backlog items too")
            baseline = json.loads((self.gdir / "refactored_baseline.json").read_text())
            src = next((o for o in baseline.get("operation_trace", []) +
                        [op for op in baseline.get("operation_trace", [])]
                        if o["op_id"] == op_id), None)
            # parked ops live in the predecessor register snapshot inside the baseline doc?
            # they are listed by id only; reconstruct minimal record
            rd_id = f"RD-{len(reg['operations']) + 1:03d}"
            reg["operations"][rd_id] = {
                "op_id": rd_id, "finding_ref": f"backlog:{op_id}",
                "misalignment_code": "BACKLOG", "misalignment_title": f"adopted from {op_id}",
                "operation": {"op_type": "INTRODUCE", "targets": [{"item_id": "backlog", "element_ref": op_id}],
                              "proposal": f"Adopted Redesign Backlog item {op_id} — see predecessor "
                                          "operations register for full text",
                              "rationale": rationale,
                              "citations": [], "objective_hook": {"objective_id": objective_id,
                                                                  "how": rationale[:600]}},
                "citations_verified": 0, "citations_total": 0,
                "draft_classification": {"draft_effect_class": "change",
                                         "baseline_reasoning": "parked as change in the refactor pass",
                                         "cells_touched": [{"actor": "?", "activity": "?"}],
                                         "confidence": "high",
                                         "evidentiary_ceiling_notes": None},
                "status": "needs_review", "proposed_at": _now(), "disposition": None}
            item["entered_queue_as"] = rd_id
        item["status"] = {"adopt": "adopted", "decline": "declined", "defer": "deferred"}[action]
        item["disposition"] = {"reviewer": {"name": name, "role": role}, "action": action,
                               "rationale": rationale, "objective_id": objective_id,
                               "timestamp": _now()}
        self._save(reg)
        self.dl({"type": "disposition",
                 "artifact": f"registers/redesign_operations.json#backlog:{op_id}",
                 "artifact_version": "0.1",
                 "decision": f"Backlog item {op_id}: {action}",
                 "rationale": rationale, "decided_by": {"name": name, "role": role}})
        return item

    # ---------- P3D.6 invariants + ratify ----------

    def invariants(self, deferred_objectives: Optional[list[dict]] = None) -> dict:
        m = self._mandate_or_409()
        reg = self.register()
        deferred = {d["objective_id"] for d in (deferred_objectives or [])}
        checks = []
        finalized = [o for o in reg["operations"].values() if o["status"] == "finalized"]
        unhooked = [o["op_id"] for o in finalized
                    if not (o["operation"].get("objective_hook") or {}).get("objective_id")]
        checks.append({"name": "every_finalized_move_hooked",
                       "status": "fail" if unhooked else "pass",
                       "details": f"unhooked finalized moves: {unhooked or 'none'}"})
        served = {(o["operation"].get("objective_hook") or {}).get("objective_id")
                  for o in finalized}
        orphans = [o["objective_id"] for o in m["objectives"]
                   if o["objective_id"] not in served and o["objective_id"] not in deferred]
        checks.append({"name": "no_orphan_objectives",
                       "status": "fail" if orphans else "pass",
                       "details": f"objectives neither served nor explicitly deferred: {orphans or 'none'}"})
        open_items = [o["op_id"] for o in reg["operations"].values()
                      if o["status"] in ("needs_review", "returned_tradeoff")]
        checks.append({"name": "zero_open_dispositions",
                       "status": "fail" if open_items else "pass",
                       "details": f"open (incl. returned-tradeoff moves awaiting Principal): {open_items or 'none'}"})
        undecided = [k for k, v in reg["backlog"].items() if v["status"] == "undecided"]
        checks.append({"name": "backlog_fully_dispositioned",
                       "status": "fail" if undecided else "pass",
                       "details": f"undecided backlog items: {len(undecided)}"})
        unworked = [f["finding_ref"] for f in self.findings()
                    if reg["findings_processed"].get(f["finding_ref"], {}).get("status") != "processed"]
        checks.append({"name": "misalignment_register_fully_worked",
                       "status": "fail" if unworked else "pass",
                       "details": f"unworked findings: {len(unworked)}"})
        report = {"ran_at": _now(), "checks": checks,
                  "pass": all(c["status"] != "fail" for c in checks)}
        (self.rdir / "redesign_invariants.json").write_text(json.dumps(report, indent=2))
        return report

    def ratify(self, *, name: str, role: str, rationale: str,
               deferred_objectives: Optional[list[dict]] = None) -> dict:
        if role != "Program Owner":
            raise RefactorError(403, "ratification is the Program Owner's act (OR-4)")
        if not (rationale or "").strip():
            raise RefactorError(400, "rationale required")
        for d in deferred_objectives or []:
            if not (d.get("rationale") or "").strip():
                raise RefactorError(400, f"deferred objective {d.get('objective_id')} needs the "
                                         "Principal's logged rationale")
        m = self._mandate_or_409()
        report = self.invariants(deferred_objectives)
        if not report["pass"]:
            failing = [c["name"] for c in report["checks"] if c["status"] == "fail"]
            raise RefactorError(409, f"invariants failing: {failing}")
        out = self.gdir / "target_blueprint.json"
        if out.exists():
            raise RefactorError(409, "already ratified — frozen (OR-7)")
        reg = self.register()
        ops = sorted((o for o in reg["operations"].values() if o["status"] == "finalized"),
                     key=lambda o: o["op_id"])
        reviewers = {o["disposition"]["reviewer"]["name"] for o in reg["operations"].values()
                     if o.get("disposition")}
        doc = {"label": "Target Blueprint (redesign)", "program_id": self.program_id,
               "mode": "redesign",
               "based_on": {"refactored_baseline": json.loads(
                                (self.gdir / "refactored_baseline.json").read_text()).get("content_hash"),
                            "ratified_mandate": m["content_hash"]},
               "operation_trace": ops,
               "deferred_objectives": deferred_objectives or [],
               "backlog_dispositions": reg["backlog"],
               "cannot_express_log": reg.get("cannot_express", []),
               "invariants_report": report,
               "disclosures": {
                   "manual_effect_classification": True,
                   "operation_trace_form": "Target = Refactored Blueprint baseline + this ordered trace",
                   "adjudication": ("non_gating_demo_only (single reviewer)" if len(reviewers) <= 1
                                    else f"reviewers: {sorted(reviewers)}")},
               "ratified_by": {"name": name, "role": role},
               "ratified_at": _now(), "rationale": rationale}
        doc["content_hash"] = "sha256:" + hashlib.sha256(
            json.dumps(doc["operation_trace"], sort_keys=True).encode()).hexdigest()
        out.write_text(json.dumps(doc, indent=2))
        self.dl({"type": "ratification", "artifact": "target_blueprint.json",
                 "artifact_version": "1.0",
                 "decision": f"Ratify Target Blueprint (redesign): {len(ops)} moves finalized; "
                             f"{len(deferred_objectives or [])} objectives deferred with rationale",
                 "rationale": rationale, "decided_by": {"name": name, "role": role}})
        return doc

    # ---------- summary ----------

    def summary(self, reg: Optional[dict] = None) -> dict:
        reg = reg or self.register()
        counts = {"needs_review": 0, "returned_tradeoff": 0, "finalized": 0, "rejected": 0}
        for op in reg["operations"].values():
            counts[op["status"]] = counts.get(op["status"], 0) + 1
        total = len(self.findings())
        processed = sum(1 for v in reg["findings_processed"].values()
                        if v.get("status") == "processed")
        inv = None
        ip = self.rdir / "redesign_invariants.json"
        if ip.exists():
            inv = json.loads(ip.read_text())
        return {"mandate": self.mandate(), "hypotheses": self.hypotheses(),
                "misalignments": self.misalignments(),
                "findings_total": total, "findings_processed": processed,
                "findings_errors": [k for k, v in reg["findings_processed"].items()
                                    if v.get("status") == "error"],
                "counts": counts, "operations": reg["operations"],
                "backlog": reg["backlog"],
                "cannot_express": reg.get("cannot_express", []),
                "invariants": inv,
                "ratified": (self.gdir / "target_blueprint.json").exists(),
                "cost_usd": round(sum(v.get("cost_usd", 0)
                                      for v in reg["findings_processed"].values())
                                  + ((self.misalignments() or {}).get("cost_usd", 0)), 4)}
