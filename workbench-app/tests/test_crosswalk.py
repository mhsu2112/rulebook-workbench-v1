import json

import pytest

from workbench.crosswalk import Crosswalker


def _op(op_id, op_type, item_ids, effect_class, pass_="refactor", hook=None, proposal="p"):
    op = {"op_id": op_id, "operation": {"op_type": op_type,
          "targets": [{"item_id": i, "element_ref": None} for i in item_ids],
          "proposal": proposal, "citations": []},
          "disposition": {"effect_class": effect_class, "action": "accept",
                          "rationale": f"{op_type} rationale", "reviewer": {"name": "R", "role": "Policy Reviewer"}}}
    if hook:
        op["operation"]["objective_hook"] = {"objective_id": hook, "how": "serves"}
    return op


def _prog(tmp_path, *, mode="refactor", items, target_trace, baseline_trace=None):
    g = tmp_path / "governed"
    (g / "manifest").mkdir(parents=True)
    (g / "manifest/manifest.json").write_text(json.dumps(
        {"content_hash": "sha256:man", "items": items}))
    (g / "target_blueprint.json").write_text(json.dumps(
        {"content_hash": "sha256:tb", "mode": mode, "operation_trace": target_trace}))
    if baseline_trace is not None:
        (g / "refactored_baseline.json").write_text(json.dumps(
            {"content_hash": "sha256:base", "operation_trace": baseline_trace}))
    return Crosswalker(tmp_path, "p1")


ITEMS = [{"item_id": "a", "family": "regA", "title": "A"},
         {"item_id": "b", "family": "regA", "title": "B"},
         {"item_id": "c", "family": "regB", "title": "C"},
         {"item_id": "d", "family": "regB", "title": "D"}]


def test_dispositions_derived_from_trace(tmp_path):
    trace = [_op("OP-001", "MERGE", ["a", "b"], "codify"),
             _op("OP-002", "REPEAL", ["c"], "codify")]
    cw = _prog(tmp_path, items=ITEMS, target_trace=trace).build()
    disp = {l["item_id"]: l["disposition"] for l in cw["legacy"]}
    assert disp == {"a": "subsumed", "b": "subsumed", "c": "repealed", "d": "retained"}
    assert cw["counts"] == {"subsumed": 2, "repealed": 1, "retained": 1}
    # every provision appears exactly once (OR-5)
    assert len(cw["legacy"]) == len(ITEMS)


def test_reverse_and_introductions(tmp_path):
    trace = [_op("OP-001", "MERGE", ["a", "b"], "codify"),
             _op("OP-003", "INTRODUCE", ["a"], "fill_gap")]
    cw = _prog(tmp_path, items=ITEMS, target_trace=trace).build()
    fams = {f["family"]: f for f in cw["reverse"]}
    assert fams["regA"]["source_count"] == 2
    assert "OP-001" in fams["regA"]["operations"]
    assert len(cw["introductions"]) == 1 and cw["introductions"][0]["op_id"] == "OP-003"


def test_refactor_audit_flags_change_class(tmp_path):
    # a change-class op somehow finalized in refactor mode -> audit FAIL
    trace = [_op("OP-001", "MERGE", ["a"], "change")]
    cw = _prog(tmp_path, items=ITEMS, target_trace=trace).build()
    a = {c["name"]: c for c in cw["audit"]["checks"]}
    assert a["no_unlogged_change_in_refactor"]["status"] == "fail"
    assert cw["audit"]["pass"] is False


def test_refactor_audit_passes_clean(tmp_path):
    trace = [_op("OP-001", "MERGE", ["a", "b"], "codify"),
             _op("OP-002", "CANONICALIZE-DEFINITION", ["c"], "clarify")]
    cw = _prog(tmp_path, items=ITEMS, target_trace=trace).build()
    a = {c["name"]: c for c in cw["audit"]["checks"]}
    assert a["no_unlogged_change_in_refactor"]["status"] == "pass"
    assert a["operation_targets_resolve"]["status"] == "pass"
    assert a["every_operation_classified"]["status"] == "pass"


def test_redesign_change_is_permitted_but_audited(tmp_path):
    base = [_op("OP-001", "MERGE", ["a"], "codify", pass_="refactor")]
    tgt = [_op("RD-001", "RECALIBRATE", ["b"], "change", pass_="redesign", hook="O1")]
    cw = _prog(tmp_path, mode="redesign", items=ITEMS,
               target_trace=tgt, baseline_trace=base).build()
    a = {c["name"]: c for c in cw["audit"]["checks"]}
    assert "change_content_traces_to_principal" in a
    assert a["change_content_traces_to_principal"]["status"] == "pass"
    assert cw["audit"]["pass"] is True
    # composed trace: both passes present
    assert cw["trace_size"] == 2
    passes = {o for l in cw["legacy"] for o in [op["pass"] for op in l["operations"]]}
    assert passes == {"refactor", "redesign"}
    # the RECALIBRATE with hook shows in introductions? no — only INTRODUCE. check hook path via reverse
    assert any(l["item_id"] == "b" and l["operations"][0]["effect_class"] == "change"
               for l in cw["legacy"])


def test_dangling_target_fails_integrity(tmp_path):
    trace = [_op("OP-001", "MERGE", ["a", "ZZZ"], "codify")]
    cw = _prog(tmp_path, items=ITEMS, target_trace=trace).build()
    a = {c["name"]: c for c in cw["audit"]["checks"]}
    assert a["operation_targets_resolve"]["status"] == "fail"
    assert cw["dangling_targets"][0]["item_id"] == "ZZZ"


def test_retained_bucket_challenge_warns(tmp_path):
    trace = [_op("OP-001", "MERGE", ["a"], "codify")]  # 1 of 4 touched -> 75% retained
    cw = _prog(tmp_path, items=ITEMS, target_trace=trace).build()
    a = {c["name"]: c for c in cw["audit"]["checks"]}
    assert a["retained_bucket_challenge"]["status"] == "warn"


def test_render_and_no_target_error(tmp_path):
    trace = [_op("OP-001", "MERGE", ["a", "b"], "codify"),
             _op("OP-002", "REPEAL", ["c"], "codify")]
    cwr = _prog(tmp_path, items=ITEMS, target_trace=trace)
    html = cwr.render()
    assert "Crosswalk" in html and "subsumed" in html and "repealed" in html
    assert "working paper" in html
    # a program with no target blueprint errors
    empty = Crosswalker(tmp_path / "nope", "x")
    with pytest.raises(FileNotFoundError):
        empty.build()
