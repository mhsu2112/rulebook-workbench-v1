import json

import pytest

from workbench.redesign import Redesigner, charter_successor
from workbench.refactor import RefactorError

SOURCE = ("Each bank shall maintain sufficient collateral pre-positioned at the discount "
          "window to cover projected thirty-day outflows under stress. " * 6)

HYP = {"mandate_id": "mh-1", "program_id": "p2", "version": "0.1", "status": "hypothesis",
       "principal": None,
       "objectives": [
           {"objective_id": "O1", "statement": "Banks can draw liquidity within hours of a run",
            "attribution": {"source": "respondent", "kind": "respondent_view"}, "adoption": None},
           {"objective_id": "O2", "statement": "Compliance burden proportionate to risk",
            "attribution": {"source": "respondent", "kind": "respondent_view"}, "adoption": None},
           {"objective_id": "O3", "statement": "A vague aspiration nobody needs",
            "attribution": {"source": "respondent", "kind": "respondent_view"}, "adoption": None}]}

MIS = {"findings": [{
    "code": "M1", "title": "Run-speed objective unserved",
    "description": "No mechanism achieves hours-scale drawing.",
    "objective_ids": ["O1"], "blueprint_refs": ["frbdw-discount-window"]}]}

RD_OP = {
    "finding_ref": "mis#0",
    "operations": [{
        "op_type": "RECALIBRATE",
        "targets": [{"item_id": "frbdw-discount-window", "element_ref": None}],
        "parameters": "reporting cadence monthly -> daily-on-trigger",
        "proposal": "Recalibrate reporting cadence for run-susceptible institutions.",
        "rationale": "Serves O1 directly.",
        "citations": [{"quote": "cover projected thirty-day outflows under stress"}],
        "objective_hook": {"objective_id": "O1", "how": "cadence is the binding constraint on detection"},
        "tradeoff": {"advances": "O1", "costs": "O2", "ranking_basis": "Mandate ranks O1 > O2"},
    }],
    "cannot_express": None,
}

CLS = {"draft_effect_class": "change",
       "baseline_reasoning": "Baseline requires monthly; this changes it.",
       "cells_touched": [{"actor": "bank", "activity": "reporting", "jurisdiction": "US"}],
       "evidentiary_ceiling_notes": None, "confidence": "high"}


def _mk(tmp_path, responses=None):
    responses = responses or {"misalign_detect": MIS, "redesign_propose": RD_OP,
                              "effect_classify_assist": CLS}
    dl = []

    def call_fn(task_id, messages):
        out = responses[task_id]
        return json.loads(json.dumps(out)), {"cost": {"usd": 0.05}, "model_served": "m",
                                             "timestamp": "t"}

    r = Redesigner(tmp_path, program_id="p2", scope="liquidity redesign",
                   call_fn=call_fn, dl_fn=lambda e: dl.append(e) or "DL-1")
    (tmp_path / "restricted").mkdir(parents=True)
    (tmp_path / "restricted/mandate_hypotheses.json").write_text(json.dumps(HYP))
    (tmp_path / "governed/blueprint").mkdir(parents=True)
    (tmp_path / "governed/corpus_texts").mkdir(parents=True)
    (tmp_path / "governed/corpus_texts/frbdw-discount-window.txt").write_text(SOURCE)
    (tmp_path / "governed/blueprint/frbdw-discount-window.json").write_text(json.dumps(
        {"item_id": "frbdw-discount-window", "nothing_in_scope": False, "objectives": [],
         "obligations": [], "definitions": [], "interactions": []}))
    (tmp_path / "governed/refactored_baseline.json").write_text(json.dumps(
        {"content_hash": "sha256:base", "operation_trace": [],
         "redesign_backlog": ["OP-042"]}))
    (tmp_path / "governed/manifest").mkdir(parents=True)
    (tmp_path / "governed/manifest/manifest.json").write_text(json.dumps(
        {"content_hash": "sha256:man", "items": [{"item_id": "frbdw-discount-window",
                                                  "family": "operational_spec"}]}))
    return r, dl


def _ratify_mandate(r, discard_o3=True):
    return r.ratify_mandate(
        name="Principal P", role="Principal",
        decisions=[{"objective_id": "O1", "action": "adopt", "rationale": "core"},
                   {"objective_id": "O2", "action": "amend", "rationale": "sharpen",
                    "amended_statement": "Burden proportionate to marginal risk reduction"},
                   {"objective_id": "O3", "action": "discard", "rationale": "not adopted"}],
        ranking=["O1", "O2"], constraints=["13(3) emergency lending limits are a statutory floor"],
        rationale="adopted after review")


def test_mandate_requires_principal_and_full_disposition(tmp_path):
    r, dl = _mk(tmp_path)
    with pytest.raises(RefactorError) as e:
        r.ratify_mandate(name="M", role="Program Owner", decisions=[], ranking=[],
                         constraints=[], rationale="x")
    assert e.value.status == 403
    with pytest.raises(RefactorError) as e2:
        r.ratify_mandate(name="P", role="Principal",
                         decisions=[{"objective_id": "O1", "action": "adopt", "rationale": "r"}],
                         ranking=["O1"], constraints=[], rationale="x")
    assert "silence adopts nothing" in e2.value.detail
    m = _ratify_mandate(r)
    assert [o["objective_id"] for o in m["objectives"]] == ["O1", "O2"]
    assert m["objectives"][1]["statement"].startswith("Burden proportionate to marginal")
    assert m["objectives"][0]["policy_choice"]["adopted_by"]["role"] == "Principal"
    assert dl and dl[0]["type"] == "ratification"
    with pytest.raises(RefactorError):        # frozen
        _ratify_mandate(r)


def test_redesign_pass_gated_on_mandate(tmp_path):
    r, _ = _mk(tmp_path)
    with pytest.raises(RefactorError) as e:
        r.detect_misalignments()
    assert "MUST NOT run on hypotheses" in e.value.detail
    _ratify_mandate(r)
    mis = r.detect_misalignments()
    assert mis["findings"][0]["code"] == "M1"


def test_hookless_and_hypothesis_hooked_moves_returned(tmp_path):
    bad = json.loads(json.dumps(RD_OP))
    bad["operations"][0]["objective_hook"] = {"objective_id": "O3", "how": "discarded objective"}
    bad["operations"].append(json.loads(json.dumps(RD_OP["operations"][0])))
    bad["operations"][1]["objective_hook"] = None
    r, _ = _mk(tmp_path, responses={"misalign_detect": MIS, "redesign_propose": bad,
                                    "effect_classify_assist": CLS})
    _ratify_mandate(r)
    r.detect_misalignments()
    out = r.propose(limit=5)
    assert out["operations"] == {}
    notes = " | ".join(x["note"] for x in out["cannot_express"])
    assert "not an adopted objective" in notes and "missing" in notes


def test_unranked_tradeoff_returns_and_cannot_finalize(tmp_path):
    op = json.loads(json.dumps(RD_OP))
    op["operations"][0]["tradeoff"]["ranking_basis"] = None
    r, _ = _mk(tmp_path, responses={"misalign_detect": MIS, "redesign_propose": op,
                                    "effect_classify_assist": CLS})
    _ratify_mandate(r)
    r.detect_misalignments()
    out = r.propose(limit=5)
    op_id = list(out["operations"])[0]
    assert out["operations"][op_id]["status"] == "returned_tradeoff"
    with pytest.raises(RefactorError) as e:
        r.disposition(op_id, name="P", role="Principal", action="accept",
                      effect_class="change", rationale="I rank them myself")
    assert "P3D.5" in e.value.detail


def test_change_class_requires_principal(tmp_path):
    r, dl = _mk(tmp_path)
    _ratify_mandate(r)
    r.detect_misalignments()
    out = r.propose(limit=5)
    op_id = list(out["operations"])[0]
    with pytest.raises(RefactorError) as e:
        r.disposition(op_id, name="M", role="Policy Reviewer", action="accept",
                      effect_class="change", rationale="fine")
    assert "Principal" in e.value.detail
    op = r.disposition(op_id, name="Principal P", role="Principal", action="accept",
                       effect_class="change", rationale="ranked tradeoff; serves O1")
    assert op["status"] == "finalized"
    assert any("hook: O1" in d["decision"] for d in dl)


def test_backlog_must_be_dispositioned_and_hook_rule_applies(tmp_path):
    r, _ = _mk(tmp_path)
    _ratify_mandate(r)
    r.detect_misalignments()
    out = r.propose(limit=5)
    op_id = list(out["operations"])[0]
    r.disposition(op_id, name="P", role="Principal", action="accept",
                  effect_class="change", rationale="ok")
    rep = r.invariants()
    assert not rep["pass"]
    assert any(c["name"] == "backlog_fully_dispositioned" and c["status"] == "fail"
               for c in rep["checks"])
    with pytest.raises(RefactorError):        # adopt without objective -> refused
        r.backlog_disposition("OP-042", name="P", role="Principal", action="adopt",
                              rationale="want it", objective_id="O9")
    with pytest.raises(RefactorError):        # wrong role
        r.backlog_disposition("OP-042", name="M", role="Policy Reviewer", action="decline",
                              rationale="no")
    r.backlog_disposition("OP-042", name="P", role="Principal", action="defer",
                          rationale="next cycle")
    rep2 = r.invariants([{"objective_id": "O2", "rationale": "phase 2"}])
    assert rep2["pass"]


def test_ratify_produces_redesign_target_blueprint(tmp_path):
    r, _ = _mk(tmp_path)
    _ratify_mandate(r)
    r.detect_misalignments()
    out = r.propose(limit=5)
    op_id = list(out["operations"])[0]
    r.disposition(op_id, name="P", role="Principal", action="accept",
                  effect_class="change", rationale="ok")
    r.backlog_disposition("OP-042", name="P", role="Principal", action="decline",
                          rationale="not aligned")
    with pytest.raises(RefactorError):        # O2 orphan without deferral
        r.ratify(name="Mike", role="Program Owner", rationale="done")
    doc = r.ratify(name="Mike", role="Program Owner", rationale="done",
                   deferred_objectives=[{"objective_id": "O2", "rationale": "phase 2 scope"}])
    assert doc["label"] == "Target Blueprint (redesign)"
    assert doc["based_on"]["ratified_mandate"].startswith("sha256:")
    assert doc["deferred_objectives"][0]["objective_id"] == "O2"
    with pytest.raises(RefactorError):
        r.ratify(name="Mike", role="Program Owner", rationale="again")


def test_charter_successor_requires_ratified_predecessor(tmp_path):
    pred = tmp_path / "p1"; succ = tmp_path / "p2"
    (pred / "governed").mkdir(parents=True)
    with pytest.raises(RefactorError) as e:
        charter_successor(pred, succ, pred_id="p1", succ_id="p2")
    assert "OR-8" in e.value.detail
    # minimal ratified predecessor
    g = pred / "governed"
    for d in ("manifest", "blueprint", "corpus_texts"):
        (g / d).mkdir()
    (g / "manifest/manifest.json").write_text(json.dumps({"content_hash": "sha256:m", "items": []}))
    (g / "blueprint/extraction_register.json").write_text(json.dumps({"items": {}}))
    (g / "corpus_texts/x.txt").write_text("text")
    (g / "target_blueprint.json").write_text(json.dumps(
        {"content_hash": "sha256:tb", "redesign_backlog": ["OP-007"], "operation_trace": []}))
    (pred / "restricted").mkdir()
    (pred / "restricted/mandate_hypotheses.json").write_text(json.dumps(HYP))
    (g / "purpose_statement.json").write_text(json.dumps(
        {"program_id": "p1", "statement_id": "ps-p1", "version": "0.1", "status": "ratified",
         "synthesis": {"recommended_mode": {"mode": "refactor", "basis_answer_ids": []},
                       "scope_sentence": {"text": "Scope."}},
         "open_items": [], "ratification": {"status": "ratified"}}))
    out = charter_successor(pred, succ, pred_id="p1", succ_id="p2")
    assert out["hypotheses_transferred"] is True
    ps2 = json.loads((succ / "governed/purpose_statement.json").read_text())
    assert ps2["synthesis"]["recommended_mode"]["mode"] == "redesign"
    assert ps2["status"] == "awaiting_ratification"          # Mike ratifies it in-app
    assert (succ / "governed/refactored_baseline.json").exists()
    assert (succ / "governed/corpus_texts/x.txt").exists()
