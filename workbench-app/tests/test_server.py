import json
import shutil
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import REPO, make_response
from workbench.server import COMPLETE_MARKER, create_app

MIN_PS = {
    "program_id": "placeholder", "statement_id": "ps-001", "version": "0.1",
    "status": "awaiting_ratification",
    "roles": {"respondent": {"name": "R", "capacity": "sponsor"},
              "program_owner": {"name": "R", "capacity": "Program Owner"},
              "principal": None},
    "interview": {"transcript_ref": "x", "consent": {"notice_given": True, "publication_excerpts": "none"},
                  "answers": [{"answer_id": "A1", "stage": "S1", "question": "q", "verbatim": "v"}]},
    "synthesis": {
        "recommended_mode": {"mode": "refactor", "basis_answer_ids": ["A1"]},
        "scope_sentence": {"text": "Distill X.", "basis_answer_ids": ["A1"]},
        "decision_served": {"text": "WG decides.", "basis_answer_ids": ["A1"]},
        "consumers": [], "success_criteria": [], "non_goals": [],
        "client": {"authority": "Agency", "posture": "advisory", "mutable_core_claims": []},
    },
    "open_items": [
        {"item_id": "OI-1", "description": "Pin the snapshot date", "owner": "Scope Owner", "blocking": True},
        {"item_id": "OI-2", "description": "Non-blocking note", "owner": "Scope Owner", "blocking": False},
    ],
    "ratification": {"status": "awaiting_ratification"},
}


MIN_MH = {
    "mandate_id": "mh-001", "program_id": "placeholder", "version": "0.1",
    "status": "hypothesis", "principal": None,
    "objectives": [{"objective_id": "O1", "statement": "Confidence maintained",
                    "attribution": {"source": "respondent", "kind": "respondent_view"},
                    "adoption": None}],
}


def transport(with_mandate=False):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model = payload["model"]
        last = payload["messages"][-1]["content"]
        if "MandateHypotheses" in last:                     # mandate_synthesis
            content = json.dumps(MIN_MH)
        elif "PurposeStatement" in last:                    # purpose_synthesis
            ps = dict(MIN_PS)
            if with_mandate:
                ps = {**MIN_PS, "mandate_hypotheses_ref": "PENDING"}
            content = json.dumps(ps)
        elif model == "anthropic/claude-sonnet-5":          # intake_interview
            content = "Q1: what is going wrong today? (a) scatter (b) conflicts (c) burden"
        else:
            content = "ok"
        return httpx.Response(200, json=make_response(model=model, content=content))
    return httpx.MockTransport(handler)


@pytest.fixture()
def approot(tmp_path):
    """A temp app root with models.yaml, contracts on the path, and the skill file."""
    shutil.copy(REPO / "models.yaml", tmp_path / "models.yaml")
    skill_dir = tmp_path / "skills" / "purpose-elicitation"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Purpose Elicitation\n(test copy)\n")
    # keep schema resolution working from the temp root
    text = (tmp_path / "models.yaml").read_text().replace(
        "- src/workbench/contracts", f"- {REPO}/src/workbench/contracts").replace(
        "- ../rulebook-workbench/schemas", f"- {REPO.parent}/rulebook-workbench/schemas")
    (tmp_path / "models.yaml").write_text(text)
    return tmp_path


@pytest.fixture()
def client(approot):
    app = create_app(root=approot, transport=transport(), api_key="test-key")
    return TestClient(app)


def test_program_lifecycle(client):
    assert client.get("/api/programs").json() == []
    r = client.post("/api/programs", json={"program_id": "demo-prog"})
    assert r.status_code == 200
    assert client.get("/api/programs").json() == ["demo-prog"]
    assert client.post("/api/programs", json={"program_id": "Bad Slug!"}).status_code == 400


def test_interview_roundtrip_and_restricted_storage(client, approot):
    client.post("/api/programs", json={"program_id": "p1"})
    r = client.post("/api/programs/p1/interview", json={"message": "clean up AML"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"].startswith("Q1") and body["complete"] is False
    # transcript is in restricted/, never governed/ (ADR-016)
    assert (approot / "programs/p1/restricted/interview.json").exists()
    assert not (approot / "programs/p1/governed/interview.json").exists()
    client.post("/api/programs/p1/interview", json={"message": "mostly scatter"})
    assert len(client.get("/api/programs/p1/interview").json()) == 4


def test_interview_fails_closed_without_zdr(approot):
    app = create_app(root=approot, transport=transport(), api_key="test-key")
    app.state.wb.registry.settings.zdr_pool_available = False
    c = TestClient(app)
    c.post("/api/programs", json={"program_id": "p1"})
    r = c.post("/api/programs/p1/interview", json={"message": "hello"})
    assert r.status_code == 503 and "fail-closed" in r.json()["detail"].lower().replace("_", "-")


def test_synthesize_writes_governed_artifact(client, approot):
    client.post("/api/programs", json={"program_id": "p1"})
    assert client.post("/api/programs/p1/synthesize").status_code == 400  # no transcript yet
    client.post("/api/programs/p1/interview", json={"message": "clean up AML"})
    r = client.post("/api/programs/p1/synthesize")
    assert r.status_code == 200
    doc = json.loads((approot / "programs/p1/governed/purpose_statement.json").read_text())
    assert doc["program_id"] == "p1"
    assert doc["status"] == "awaiting_ratification"
    assert doc["interview"]["transcript_ref"] == "programs/p1/restricted/interview.json"


def test_ratify_blocked_until_open_items_resolved(client, approot):
    client.post("/api/programs", json={"program_id": "p1"})
    client.post("/api/programs/p1/interview", json={"message": "hi"})
    client.post("/api/programs/p1/synthesize")
    ok = {"name": "Mike Hsu", "role": "Program Owner", "rationale": "looks right"}
    assert client.post("/api/programs/p1/ratify", json={**ok, "role": "Reviewer"}).status_code == 403
    assert client.post("/api/programs/p1/ratify", json={**ok, "rationale": "  "}).status_code == 400
    # server-side enforcement: blocking open item -> 409, naming the item
    r = client.post("/api/programs/p1/ratify", json=ok)
    assert r.status_code == 409 and "OI-1" in r.json()["detail"]
    # resolve requires a rationale
    bad = client.post("/api/programs/p1/open-items/OI-1/resolve",
                      json={"name": "Mike Hsu", "role": "Scope Owner", "rationale": " "})
    assert bad.status_code == 400
    assert client.post("/api/programs/p1/open-items/OI-9/resolve",
                       json={"name": "M", "role": "X", "rationale": "r"}).status_code == 404
    # resolve OI-1 (⚖, logged as DL-001)
    r = client.post("/api/programs/p1/open-items/OI-1/resolve",
                    json={"name": "Mike Hsu", "role": "Scope Owner", "rationale": "snapshot pinned 2026-07-18"})
    assert r.status_code == 200
    item = next(i for i in r.json()["open_items"] if i["item_id"] == "OI-1")
    assert item["blocking"] is False and item["resolution"]["decision_log_ref"] == "DL-001"
    assert client.post("/api/programs/p1/open-items/OI-1/resolve",
                       json={"name": "M", "role": "X", "rationale": "again"}).status_code == 409
    # now ratification goes through as DL-002
    r = client.post("/api/programs/p1/ratify", json=ok)
    assert r.status_code == 200 and r.json()["status"] == "ratified"
    assert r.json()["ratification"]["decision_log_ref"] == "DL-002"
    log = [json.loads(l) for l in
           (approot / "programs/p1/governed/decisions.log.jsonl").read_text().splitlines()]
    assert [e["type"] for e in log] == ["disposition", "ratification"]
    assert client.post("/api/programs/p1/ratify", json=ok).status_code == 409  # no double-ratify
    # open items are frozen after ratification
    assert client.post("/api/programs/p1/open-items/OI-2/resolve",
                       json={"name": "M", "role": "X", "rationale": "r"}).status_code == 409


def test_stamps_persisted_with_program_id(client, approot):
    client.post("/api/programs", json={"program_id": "p1"})
    client.post("/api/programs/p1/interview", json={"message": "hi"})
    lines = [json.loads(l) for l in (approot / "runs/stamps.jsonl").read_text().splitlines()]
    assert lines and lines[-1]["task_id"] == "intake_interview" and lines[-1]["program_id"] == "p1"
    m = client.get("/api/models").json()
    assert m["lifetime_calls"] == len(lines) and m["lifetime_usd"] > 0


def test_models_endpoint_and_override_persistence(client, approot):
    r = client.get("/api/models").json()
    assert "intake_interview" in r["tasks"]
    assert r["tasks"]["distill_extract"]["source"] == "default"
    client.post("/api/models/override", json={"task_id": "distill_extract", "model": "openai/gpt-5.6-sol"})
    r2 = client.get("/api/models").json()["tasks"]["distill_extract"]
    assert r2["current_model"] == "openai/gpt-5.6-sol" and r2["source"] == "user_override"
    assert json.loads((approot / "overrides.json").read_text()) == {"distill_extract": "openai/gpt-5.6-sol"}
    client.post("/api/models/override", json={"task_id": "distill_extract", "model": None})
    assert client.get("/api/models").json()["tasks"]["distill_extract"]["source"] == "default"
    assert client.post("/api/models/override", json={"task_id": "nope", "model": "x"}).status_code == 404


def test_ui_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Rulebook Workbench" in r.text


def test_dotenv_loaded_from_root(approot, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    (approot / ".env").write_text("# comment\nOPENROUTER_API_KEY=sk-or-from-file\n")
    app = create_app(root=approot, transport=transport())
    assert app.state.wb.router.api_key == "sk-or-from-file"


def test_dotenv_never_overrides_real_env(approot, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-real-env")
    (approot / ".env").write_text("OPENROUTER_API_KEY=sk-or-from-file\n")
    app = create_app(root=approot, transport=transport())
    assert app.state.wb.router.api_key == "sk-or-real-env"


def test_mandate_hypotheses_written_when_referenced(approot):
    app = create_app(root=approot, transport=transport(with_mandate=True), api_key="test-key")
    c = TestClient(app)
    c.post("/api/programs", json={"program_id": "p1"})
    c.post("/api/programs/p1/interview", json={"message": "redesign liquidity"})
    r = c.post("/api/programs/p1/synthesize")
    assert r.status_code == 200
    doc = r.json()["purpose_statement"]
    assert doc["mandate_hypotheses_ref"] == "programs/p1/restricted/mandate_hypotheses.json"
    mh = json.loads((approot / "programs/p1/restricted/mandate_hypotheses.json").read_text())
    assert mh["status"] == "hypothesis" and mh["program_id"] == "p1"
    assert all(o["adoption"] is None for o in mh["objectives"])  # ADR-006 enforced server-side


def test_no_dangling_mandate_ref_without_seed_material(client, approot):
    client.post("/api/programs", json={"program_id": "p1"})
    client.post("/api/programs/p1/interview", json={"message": "hi"})
    doc = client.post("/api/programs/p1/synthesize").json()["purpose_statement"]
    assert not doc.get("mandate_hypotheses_ref")
    assert not (approot / "programs/p1/restricted/mandate_hypotheses.json").exists()


def test_manifest_import_and_freeze(client, approot):
    import shutil as sh
    (approot / "data").mkdir(exist_ok=True)
    sh.copy(REPO / "data" / "aml-program-rules-slice.json", approot / "data" / "aml-program-rules-slice.json")
    client.post("/api/programs", json={"program_id": "p1"})
    assert client.get("/api/programs/p1/manifest").status_code == 404
    slices = client.get("/api/slices").json()
    assert slices and slices[0]["slice_id"] == "aml-program-rules-slice" and slices[0]["items"] == 42
    r = client.post("/api/programs/p1/manifest/import", json={"slice_id": "aml-program-rules-slice"})
    assert r.status_code == 200 and r.json()["frozen"] is False and len(r.json()["items"]) == 42
    m = client.get("/api/programs/p1/manifest").json()
    assert len(m["gaps"]) == 4  # gap register travels with the import
    # freeze governance
    ok = {"name": "Mike Hsu", "role": "Corpus Steward", "rationale": "census slice reviewed"}
    assert client.post("/api/programs/p1/manifest/freeze", json={**ok, "role": "Reviewer"}).status_code == 403
    assert client.post("/api/programs/p1/manifest/freeze", json={**ok, "rationale": " "}).status_code == 400
    r = client.post("/api/programs/p1/manifest/freeze", json=ok)
    assert r.status_code == 200
    doc = r.json()
    assert doc["frozen"] and doc["content_hash"].startswith("sha256:") and doc["frozen_at"]
    # decision logged
    entries = [json.loads(l) for l in
               (approot / "programs/p1/governed/decisions.log.jsonl").read_text().splitlines()]
    assert entries[-1]["type"] == "manifest_freeze" and doc["content_hash"] in entries[-1]["decision"]
    # immutability (OR-7): no re-import, no re-freeze
    assert client.post("/api/programs/p1/manifest/import", json={"slice_id": "aml-program-rules-slice"}).status_code == 409
    assert client.post("/api/programs/p1/manifest/freeze", json=ok).status_code == 409
    # sha sidecar written
    assert (approot / "programs/p1/governed/manifest/manifest.sha256").read_text().strip() == doc["content_hash"]


def test_canonical_hash_order_independent():
    from workbench.manifest import canonical_hash
    a = [{"item_id": "x", "v": 1}, {"item_id": "y", "v": 2}]
    b = [{"item_id": "y", "v": 2}, {"item_id": "x", "v": 1}]
    assert canonical_hash(a) == canonical_hash(b)
    assert canonical_hash(a) != canonical_hash([{"item_id": "x", "v": 1}])
