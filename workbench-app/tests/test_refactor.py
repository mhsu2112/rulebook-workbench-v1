import json

import pytest

from workbench.refactor import RefactorError, Refactorer, route

SOURCE = ("Each bank shall develop, implement, and maintain an effective anti-money "
          "laundering program reasonably designed to assure compliance. The program "
          "shall be approved by the board of directors. " * 5)

PROPOSAL = {
    "finding_ref": "defects-x#0",
    "operations": [{
        "op_type": "CANONICALIZE-DEFINITION",
        "targets": [{"item_id": "item-a", "element_ref": "program"}],
        "parameters": "canonical: the AML program per 31 CFR 1022.210",
        "proposal": "Adopt one canonical definition of 'program' across both instruments.",
        "rationale": "D2 divergence between item-a and item-b.",
        "citations": [{"quote": "maintain an effective anti-money laundering program"}],
    }],
    "cannot_express": None,
}

CLASSIFICATION = {
    "draft_effect_class": "clarify",
    "baseline_reasoning": "Both sources state the duty; wording differs without substantive divergence.",
    "cells_touched": [{"actor": "bank", "activity": "AML program", "jurisdiction": "US"}],
    "evidentiary_ceiling_notes": None,
    "confidence": "medium",
}

FINDING = {"code": "D2", "title": "Divergent definitions: program",
           "description": "Two definitions of 'program'.",
           "locations": [{"item_id": "item-a", "quote": "x"}, {"item_id": "item-b", "quote": "y"}]}


def _mk(tmp_path, responses=None, mode="refactor", classification=None):
    responses = responses or {"operation_propose": PROPOSAL,
                              "effect_classify_assist": classification or CLASSIFICATION}
    calls, dl = [], []

    def call_fn(task_id, messages):
        calls.append((task_id, messages[-1]["content"]))
        return json.loads(json.dumps(responses[task_id])), {"cost": {"usd": 0.05}}

    r = Refactorer(tmp_path, program_id="p1", scope="AML program obligations",
                   mode=mode, manifest_hash="sha256:abc", call_fn=call_fn,
                   dl_fn=lambda e: dl.append(e) or "DL-%03d" % len(dl))
    (tmp_path / "governed/corpus_texts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "governed/blueprint").mkdir(parents=True, exist_ok=True)
    for iid in ("item-a", "item-b"):
        (tmp_path / f"governed/corpus_texts/{iid}.txt").write_text(SOURCE)
        (tmp_path / f"governed/blueprint/{iid}.json").write_text(json.dumps(
            {"item_id": iid, "nothing_in_scope": False, "objectives": [],
             "obligations": [], "definitions": [{"term": "program", "definition":
                 "definition " + iid, "citations": []}], "interactions": []}))
    (tmp_path / "governed/registers").mkdir(parents=True, exist_ok=True)
    (tmp_path / "governed/registers/defects.json").write_text(json.dumps(
        {"runs": {"defects-x": {"findings": [FINDING]}}}))
    return r, calls, dl


def test_propose_verifies_citations_and_routes(tmp_path):
    r, calls, _ = _mk(tmp_path)
    out = r.propose(limit=5)
    assert out["findings_processed"] == 1
    ops = list(out["operations"].values())
    assert len(ops) == 1
    op = ops[0]
    assert op["status"] == "needs_review"          # clarify -> needs_review (P3.4)
    assert op["citations_verified"] == 1
    assert [t for t, _ in calls] == ["operation_propose", "effect_classify_assist"]


def test_routing_table():
    assert route("codify") == "eligible"
    assert route("clarify") == "needs_review"
    assert route("fill_gap") == "needs_review"
    assert route("change") == "parked"
    assert route("unresolved") == "parked"


def test_change_class_parks_automatically(tmp_path):
    cls = dict(CLASSIFICATION, draft_effect_class="change")
    r, _, _ = _mk(tmp_path, classification=cls)
    out = r.propose(limit=5)
    assert list(out["operations"].values())[0]["status"] == "parked"


def test_all_fabricated_citations_reject_proposal(tmp_path):
    bad = json.loads(json.dumps(PROPOSAL))
    bad["operations"][0]["citations"] = [{"quote": "this sentence is nowhere in the sources"}]
    r, _, _ = _mk(tmp_path, responses={"operation_propose": bad,
                                       "effect_classify_assist": CLASSIFICATION})
    out = r.propose(limit=5)
    assert out["operations"] == {}
    assert any("0/1 citation quotes verified" in x["note"] for x in out["cannot_express"])


def test_disposition_gates(tmp_path):
    r, _, dl = _mk(tmp_path)
    r.propose(limit=5)
    op_id = list(r.register()["operations"])[0]
    with pytest.raises(RefactorError) as e:
        r.disposition(op_id, name="M", role="Corpus Steward", action="accept",
                      effect_class="clarify", rationale="r")
    assert e.value.status == 403                    # wrong role
    with pytest.raises(RefactorError):
        r.disposition(op_id, name="M", role="Policy Reviewer", action="accept",
                      effect_class="clarify", rationale="  ")   # no rationale
    # OR-1: human classifies as change -> accept forbidden
    with pytest.raises(RefactorError) as e2:
        r.disposition(op_id, name="M", role="Policy Reviewer", action="accept",
                      effect_class="change", rationale="looks fine to me")
    assert "OR-1" in e2.value.detail
    # park as change is the honest path
    op = r.disposition(op_id, name="M", role="Policy Reviewer", action="park",
                       effect_class="change", rationale="new duty; belongs to redesign")
    assert op["status"] == "parked"
    assert op["disposition"]["draft_effect_class"] == "clarify"   # both records kept (NG2)
    assert len(dl) == 1                                            # P3.6 logged
    with pytest.raises(RefactorError):                             # no double disposition… parked can be re-dispositioned?
        r.disposition("OP-999", name="M", role="Policy Reviewer", action="accept",
                      effect_class="codify", rationale="r")


def test_accept_finalizes_and_logs(tmp_path):
    r, _, dl = _mk(tmp_path)
    r.propose(limit=5)
    op_id = list(r.register()["operations"])[0]
    op = r.disposition(op_id, name="M", role="Policy Reviewer", action="accept",
                       effect_class="clarify", rationale="definition divergence is verbal only")
    assert op["status"] == "finalized"
    assert op["disposition"]["effect_class"] == "clarify"
    assert dl and "accept CANONICALIZE-DEFINITION" in dl[0]["decision"]


def test_ratify_gates_and_artifact(tmp_path):
    r, _, dl = _mk(tmp_path)
    r.propose(limit=5)
    op_id = list(r.register()["operations"])[0]
    with pytest.raises(RefactorError) as e:
        r.ratify(name="Mike", role="Program Owner", rationale="ship it")
    assert "zero_open_dispositions" in e.value.detail
    r.disposition(op_id, name="M", role="Policy Reviewer", action="accept",
                  effect_class="clarify", rationale="ok")
    with pytest.raises(RefactorError):
        r.ratify(name="Mike", role="Policy Reviewer", rationale="not my call")
    doc = r.ratify(name="Mike", role="Program Owner", rationale="pass complete")
    assert doc["label"] == "Target Blueprint"
    assert len(doc["operation_trace"]) == 1
    assert doc["disclosures"]["manual_effect_classification"] is True
    assert "non_gating_demo_only" in doc["disclosures"]["adjudication"]
    with pytest.raises(RefactorError) as e2:      # OR-7: frozen
        r.ratify(name="Mike", role="Program Owner", rationale="again")
    assert "OR-7" in e2.value.detail


def test_redesign_mode_label(tmp_path):
    r, _, _ = _mk(tmp_path, mode="redesign")
    r.propose(limit=5)
    op_id = list(r.register()["operations"])[0]
    r.disposition(op_id, name="M", role="Policy Reviewer", action="reject",
                  effect_class="clarify", rationale="not needed")
    doc = r.ratify(name="Mike", role="Program Owner", rationale="baseline certified")
    assert "Refactored Blueprint" in doc["label"]


def test_blast_radius_ordering(tmp_path):
    r, _, _ = _mk(tmp_path)
    d = {"runs": {"defects-a": {"findings": [
            dict(FINDING, code="D5", title="dangling"),
            dict(FINDING, code="D2", title="divergent"),
            dict(FINDING, code="D9", title="gap")]}}}
    (tmp_path / "governed/registers/defects.json").write_text(json.dumps(d))
    codes = [f["code"] for f in r.findings()]
    assert codes == ["D2", "D5", "D9"]   # definitions first, gaps last


# ---------------- API-level flow ----------------

import httpx
import shutil
from fastapi.testclient import TestClient
from conftest import REPO, make_response
from test_server import MIN_PS, approot  # noqa: F401
from workbench.server import create_app

GOOD_EX = {
    "item_id": "x", "nothing_in_scope": False, "objectives": [],
    "obligations": [{"obligation_id": "OB-1", "actor": "bank", "modality": "must",
                     "action": "maintain an AML program", "trigger": None, "threshold": None,
                     "exceptions": [], "citations": [{"quote": "Each bank shall develop, implement, and maintain an effective anti-money laundering program"}]}],
    "definitions": [], "interactions": [], "notes": None,
}


def _api_app(approot):  # noqa: F811
    (approot / "data").mkdir(exist_ok=True)
    shutil.copy(REPO / "data" / "aml-program-rules-slice.json",
                approot / "data" / "aml-program-rules-slice.json")

    slice_items = json.load(open(REPO / "data" / "aml-program-rules-slice.json"))["items"]
    first_iid = slice_items[0]["item_id"]
    api_proposal = json.loads(json.dumps(PROPOSAL))
    api_proposal["operations"][0]["targets"] = [{"item_id": first_iid, "element_ref": None}]
    api_proposal["operations"][0]["citations"] = [
        {"quote": "maintain an effective anti-money laundering program"}]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        last = payload["messages"][-1]["content"]
        if "OperationProposal" in last:
            content = json.dumps(api_proposal)
        elif "EffectClassificationDraft" in last:
            content = json.dumps(dict(CLASSIFICATION, draft_effect_class="codify"))
        elif "BlueprintExecutiveSummary" in last:
            content = json.dumps({"headline": "A layered regime.", "how_to_read": "trace + tables",
                                  "regime_shape": [{"heading": "H1", "text": "t", "refs": []},
                                                   {"heading": "H2", "text": "t", "refs": []}],
                                  "highlights": [{"point": "p", "refs": ["OP-001"]},
                                                 {"point": "p2", "refs": ["OP-001"]},
                                                 {"point": "p3", "refs": ["OP-001"]}],
                                  "tensions": [{"point": "parked", "refs": ["OP-001"]}],
                                  "caveats": "advisory"})
        else:
            content = json.dumps(GOOD_EX)
        return httpx.Response(200, json=make_response(model=payload["model"], content=content))

    app = create_app(root=approot, transport=httpx.MockTransport(handler), api_key="test-key")
    c = TestClient(app)
    c.post("/api/programs", json={"program_id": "p1"})
    ps = json.loads(json.dumps(MIN_PS))
    ps["program_id"] = "p1"; ps["status"] = "ratified"
    (approot / "programs/p1/governed/purpose_statement.json").write_text(json.dumps(ps))
    c.post("/api/programs/p1/manifest/import", json={"slice_id": "aml-program-rules-slice"})
    c.post("/api/programs/p1/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "r"})
    c.post("/api/programs/p1/manifest/freeze", json={"name": "M", "role": "Corpus Steward", "rationale": "r"})
    return c


def test_api_refactor_gated_on_phase2(approot):  # noqa: F811
    c = _api_app(approot)
    r = c.get("/api/programs/p1/refactor")
    assert r.status_code == 409 and "Phase 2 gate" in r.json()["detail"]


def test_api_refactor_full_flow(approot):  # noqa: F811
    c = _api_app(approot)
    # fake a complete Phase 2: extraction file + register entry per item, texts, defects
    man = c.get("/api/programs/p1/manifest").json()
    gov = approot / "programs/p1/governed"
    (gov / "blueprint").mkdir(parents=True, exist_ok=True)
    (gov / "corpus_texts").mkdir(parents=True, exist_ok=True)
    src = ("Each bank shall develop, implement, and maintain an effective anti-money "
           "laundering program reasonably designed to assure compliance. " * 10)
    for it in man["items"]:
        iid = it["item_id"]
        (gov / f"corpus_texts/{iid}.txt").write_text(src)
        ex = json.loads(json.dumps(GOOD_EX)); ex["item_id"] = iid
        (gov / f"blueprint/{iid}.json").write_text(json.dumps(ex))
    (gov / "registers").mkdir(exist_ok=True)
    finding = dict(FINDING)
    finding["locations"] = [{"item_id": man["items"][0]["item_id"], "quote": "q"}]
    (gov / "registers/defects.json").write_text(json.dumps(
        {"runs": {"defects-x": {"findings": [finding]}}}))
    # summary now reachable (reconcile heals the register from the files)
    s = c.get("/api/programs/p1/refactor").json()
    assert s["findings_total"] == 1
    r = c.post("/api/programs/p1/refactor/propose", json={"limit": 5}).json()
    ops = list(r["operations"].values())
    assert len(ops) == 1 and ops[0]["status"] == "eligible"   # codify
    op_id = ops[0]["op_id"]
    # OR-1 via API
    bad = c.post(f"/api/programs/p1/refactor/operations/{op_id}/disposition",
                 json={"name": "M", "role": "Policy Reviewer", "action": "accept",
                       "effect_class": "change", "rationale": "r"})
    assert bad.status_code == 403 and "OR-1" in bad.json()["detail"]
    ok = c.post(f"/api/programs/p1/refactor/operations/{op_id}/disposition",
                json={"name": "M", "role": "Policy Reviewer", "action": "accept",
                      "effect_class": "codify", "rationale": "baseline requires it"})
    assert ok.status_code == 200
    rat = c.post("/api/programs/p1/refactor/ratify",
                 json={"name": "Mike", "role": "Program Owner", "rationale": "done"})
    assert rat.status_code == 200
    doc = rat.json()
    assert doc["label"] == "Target Blueprint" and len(doc["operation_trace"]) == 1
    # decision log got the disposition + ratification entries
    log = (gov / "decisions.log.jsonl").read_text().splitlines()
    assert sum(1 for line in log if "OP-001" in line) == 1
    assert any("Ratify Target Blueprint" in line for line in log)


def test_target_blueprint_render_and_summary(approot):  # noqa: F811
    c = _api_app(approot)
    # no target blueprint yet -> 409
    assert c.get("/api/programs/p1/target-blueprint/render").status_code == 409
    # build a complete refactor pass and ratify
    man = c.get("/api/programs/p1/manifest").json()
    gov = approot / "programs/p1/governed"
    (gov / "blueprint").mkdir(parents=True, exist_ok=True)
    (gov / "corpus_texts").mkdir(parents=True, exist_ok=True)
    src = ("Each bank shall develop, implement, and maintain an effective anti-money "
           "laundering program reasonably designed to assure compliance. " * 10)
    for it in man["items"]:
        (gov / f"corpus_texts/{it['item_id']}.txt").write_text(src)
        ex = json.loads(json.dumps(GOOD_EX)); ex["item_id"] = it["item_id"]
        (gov / f"blueprint/{it['item_id']}.json").write_text(json.dumps(ex))
    (gov / "registers").mkdir(exist_ok=True)
    finding = dict(FINDING); finding["locations"] = [{"item_id": man["items"][0]["item_id"], "quote": "q"}]
    (gov / "registers/defects.json").write_text(json.dumps({"runs": {"defects-x": {"findings": [finding]}}}))
    r = c.post("/api/programs/p1/refactor/propose", json={"limit": 5}).json()
    op_id = list(r["operations"])[0]
    c.post(f"/api/programs/p1/refactor/operations/{op_id}/disposition",
           json={"name": "M", "role": "Policy Reviewer", "action": "accept",
                 "effect_class": "codify", "rationale": "baseline requires it"})
    c.post("/api/programs/p1/refactor/ratify",
           json={"name": "Mike", "role": "Program Owner", "rationale": "done"})
    # now the target blueprint renders
    tr = c.get("/api/programs/p1/target-blueprint/render")
    assert tr.status_code == 200
    assert "Target Blueprint" in tr.text
    assert "operation-trace form" in tr.text
    assert "Ratified scope" in tr.text
    # summary generation (handler returns GOOD_EX shape for non-summary; add summary content)
    s = c.post("/api/programs/p1/target-blueprint/summarize")
    assert s.status_code == 200
    assert s.json()["_provenance"]["advisory"] is True
