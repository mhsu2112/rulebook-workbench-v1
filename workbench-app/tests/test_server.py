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
    # freeze is gated on a locked model policy (spec/55) — it 409s until locked
    assert client.post("/api/programs/p1/manifest/freeze", json=ok).status_code == 409
    client.post("/api/programs/p1/policy/ratify", json={"name": "Mike Hsu", "role": "Program Owner", "rationale": "recommended is fine"})
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


def test_build_corpus_in_app(client):
    client.post("/api/programs", json={"program_id": "gsl"})
    # no manifest yet -> 404
    assert client.get("/api/programs/gsl/manifest").status_code == 404
    # add a source from scratch (creates the manifest)
    r = client.post("/api/programs/gsl/manifest/items", json={
        "item_id": "12-cfr-1266", "title": "FHLBank advances", "issuer": "FHFA",
        "family": "regulation", "locator": "12 CFR 1266", "status": "live",
        "evidence_role": "binding_authority", "url": "https://example.gov/x"})
    assert r.status_code == 200 and len(r.json()["items"]) == 1 and r.json()["frozen"] is False
    # required-field validation
    bad = client.post("/api/programs/gsl/manifest/items", json={
        "item_id": "x", "title": "", "issuer": "Y", "family": "f", "locator": "L"})
    assert bad.status_code == 400 and "Missing required" in bad.json()["detail"]
    # duplicate id rejected
    dup = client.post("/api/programs/gsl/manifest/items", json={
        "item_id": "12-cfr-1266", "title": "dup", "issuer": "Z", "family": "f", "locator": "L"})
    assert dup.status_code == 400 and "already in the manifest" in dup.json()["detail"]
    # add a second, then remove it
    client.post("/api/programs/gsl/manifest/items", json={
        "item_id": "12-usc-1430", "title": "Advances (statute)", "issuer": "Congress",
        "family": "statute", "locator": "12 U.S.C. 1430"})
    assert len(client.get("/api/programs/gsl/manifest").json()["items"]) == 2
    rm = client.delete("/api/programs/gsl/manifest/items/12-usc-1430")
    assert rm.status_code == 200 and len(rm.json()["items"]) == 1
    # freeze (policy locked first), then adds/removes are refused (OR-7)
    client.post("/api/programs/gsl/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "ok"})
    client.post("/api/programs/gsl/manifest/freeze",
                json={"name": "M", "role": "Corpus Steward", "rationale": "assembled in-app"})
    frozen_add = client.post("/api/programs/gsl/manifest/items", json={
        "item_id": "late", "title": "t", "issuer": "i", "family": "f", "locator": "L"})
    assert frozen_add.status_code == 409


def discover_transport():
    """Serves BOTH the OpenRouter model call (source_candidates JSON) and the
    catalog/verification GETs the discovery endpoint fans out to."""
    ecfr = {"results": [
        {"hierarchy": {"title": "12", "part": "1266"},
         "headings": {"part": "PART 1266—FEDERAL HOME LOAN BANK ADVANCES",
                      "chapter": "CHAPTER XII—FEDERAL HOUSING FINANCE AGENCY"}},
    ]}
    model_out = {"candidates": [
        {"title": "FHLBank Act — advances", "issuer": "Congress", "family": "statute",
         "usc_locator": "12 U.S.C. 1430", "rationale": "statutory basis for advances"},
    ]}

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/chat/completions" in u:
            model = json.loads(request.content)["model"]
            return httpx.Response(200, json=make_response(model=model, content=json.dumps(model_out)))
        if "/api/search/v1/results" in u:
            return httpx.Response(200, json=ecfr)
        if "federalregister.gov" in u:
            return httpx.Response(200, json={"results": []})
        if "uscode.house.gov" in u:
            return httpx.Response(200, text="<p>" + "advances to members " * 40 + "</p>")
        if "/api/versioner/" in u:
            return httpx.Response(200, content=b"<DIV>" + b"x" * 800 + b"</DIV>")
        return httpx.Response(500, text="unexpected " + u)
    return httpx.MockTransport(handler)


def test_discover_proposes_without_mutating_manifest(approot):
    app = create_app(root=approot, transport=discover_transport(), api_key="test-key")
    client = TestClient(app)
    client.post("/api/programs", json={"program_id": "gsl"})

    r = client.post("/api/programs/gsl/discover", json={"terms": "fhlbank advances"})
    assert r.status_code == 200
    body = r.json()
    ids = {c["proposed_item_id"] for c in body["candidates"]}
    assert "12-cfr-1266" in ids            # catalog lane (eCFR search)
    assert "12-usc-1430" in ids            # model lane, verified against uscode
    assert all("verified" in c for c in body["candidates"])

    # Discovery mutated nothing: there is still no manifest.
    assert client.get("/api/programs/gsl/manifest").status_code == 404

    # Accepting a candidate is the human's act -> it flows through add_item.
    cand = next(c for c in body["candidates"] if c["proposed_item_id"] == "12-cfr-1266")
    add = client.post("/api/programs/gsl/manifest/items", json={
        "item_id": cand["proposed_item_id"], "title": cand["title"], "issuer": cand["issuer"],
        "family": cand["family"], "locator": cand["locator"], "status": cand["status"],
        "evidence_role": cand["evidence_role"], "url": cand["url"]})
    assert add.status_code == 200
    assert len(client.get("/api/programs/gsl/manifest").json()["items"]) == 1

    # Re-running discovery now drops the just-added source (deduped).
    r2 = client.post("/api/programs/gsl/discover", json={"terms": "fhlbank advances"})
    ids2 = {c["proposed_item_id"] for c in r2.json()["candidates"]}
    assert "12-cfr-1266" not in ids2


def test_discover_refused_when_frozen(approot):
    app = create_app(root=approot, transport=discover_transport(), api_key="test-key")
    client = TestClient(app)
    client.post("/api/programs", json={"program_id": "gsl"})
    client.post("/api/programs/gsl/manifest/items", json={
        "item_id": "12-usc-1430", "title": "t", "issuer": "Congress", "family": "statute",
        "locator": "12 U.S.C. 1430"})
    client.post("/api/programs/gsl/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "ok"})
    client.post("/api/programs/gsl/manifest/freeze",
                json={"name": "M", "role": "Corpus Steward", "rationale": "pin it"})
    r = client.post("/api/programs/gsl/discover", json={"terms": "advances"})
    assert r.status_code == 409 and "frozen" in r.json()["detail"].lower()


def test_synthesize_refuses_to_unratify(client, approot):
    """Regression: re-running synthesize on a RATIFIED purpose must not silently
    overwrite it back to awaiting_ratification (which hides the Corpus tab and
    every downstream tab). The ratified governed artifact is protected."""
    client.post("/api/programs", json={"program_id": "p1"})
    client.post("/api/programs/p1/interview", json={"message": "clean up AML"})
    client.post("/api/programs/p1/synthesize")
    # resolve the one blocking open item, then ratify
    client.post("/api/programs/p1/open-items/OI-1/resolve",
                json={"name": "Mike Hsu", "role": "Scope Owner", "rationale": "pinned"})
    r = client.post("/api/programs/p1/ratify",
                    json={"name": "Mike Hsu", "role": "Program Owner", "rationale": "looks right"})
    assert r.status_code == 200
    ps = approot / "programs/p1/governed/purpose_statement.json"
    assert json.loads(ps.read_text())["status"] == "ratified"
    # Re-synthesizing is now blocked and the file is untouched.
    again = client.post("/api/programs/p1/synthesize")
    assert again.status_code == 409 and "ratified" in again.json()["detail"].lower()
    assert json.loads(ps.read_text())["status"] == "ratified"       # still ratified — not clobbered
    # And the overview still shows the Corpus tab (and downstream readiness intact).
    assert client.get("/api/programs/p1/overview").json()["tabs"]["corpus"] is True


import io as _io
import zipfile as _zip


def test_archive_and_restore(client):
    client.post("/api/programs", json={"program_id": "arch1"})
    assert "arch1" in client.get("/api/programs").json()
    r = client.post("/api/programs/arch1/archive")
    assert r.status_code == 200 and r.json()["archived"] is True
    assert "arch1" not in client.get("/api/programs").json()          # hidden from active list
    assert "arch1" in client.get("/api/programs/archived").json()     # but restorable
    assert client.post("/api/programs/arch1/restore").status_code == 200
    assert "arch1" in client.get("/api/programs").json()


def test_rename_repoints_id_and_stamps(client, approot):
    client.post("/api/programs", json={"program_id": "oldname"})
    client.post("/api/programs/oldname/interview", json={"message": "clean up AML"})  # writes a stamp
    client.post("/api/programs/oldname/synthesize")                                    # writes purpose w/ program_id
    r = client.post("/api/programs/oldname/rename", json={"new_id": "newname"})
    assert r.status_code == 200 and r.json()["program_id"] == "newname"
    progs = client.get("/api/programs").json()
    assert "newname" in progs and "oldname" not in progs
    # program_id rewritten inside the artifact
    ps = json.loads((approot / "programs/newname/governed/purpose_statement.json").read_text())
    assert ps["program_id"] == "newname"
    # provenance stamps repointed by exact match
    stamps = (approot / "runs/stamps.jsonl").read_text()
    assert '"program_id": "newname"' in stamps and '"program_id": "oldname"' not in stamps
    # collision + bad-slug rejected
    client.post("/api/programs", json={"program_id": "taken"})
    assert client.post("/api/programs/newname/rename", json={"new_id": "taken"}).status_code == 400
    assert client.post("/api/programs/newname/rename", json={"new_id": "Bad Slug"}).status_code == 400


def test_rename_exact_match_no_substring_bleed(client, approot):
    # A program whose id is a SUBSTRING sibling must not be touched by the rename.
    client.post("/api/programs", json={"program_id": "liq"})
    client.post("/api/programs", json={"program_id": "liq-p2"})
    client.post("/api/programs/liq/interview", json={"message": "hi"})     # stamp for 'liq'
    client.post("/api/programs/liq-p2/interview", json={"message": "hi"})  # stamp for 'liq-p2'
    client.post("/api/programs/liq/rename", json={"new_id": "liquidity"})
    stamps = (approot / "runs/stamps.jsonl").read_text()
    assert '"program_id": "liquidity"' in stamps          # renamed one moved
    assert '"program_id": "liq-p2"' in stamps             # sibling untouched (no substring bleed)


def test_program_package_zip(client, approot):
    client.post("/api/programs", json={"program_id": "pkg1"})
    client.post("/api/programs/pkg1/manifest/items", json={
        "item_id": "12-cfr-1266", "title": "Advances", "issuer": "FHFA",
        "family": "regulation", "locator": "12 CFR 1266"})
    r = client.get("/api/programs/pkg1/package")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = _zip.ZipFile(_io.BytesIO(r.content))
    names = z.namelist()
    assert "pkg1-package/index.html" in names
    assert "pkg1-package/manifest.csv" in names
    assert "pkg1-package/MANIFEST.txt" in names
    assert any(n.startswith("pkg1-package/governed/") for n in names)
    # manifest.csv actually carries the item
    assert b"12-cfr-1266" in z.read("pkg1-package/manifest.csv")


def test_discover_questions_endpoint(client):
    client.post("/api/programs", json={"program_id": "q1"})
    client.post("/api/programs/q1/interview", json={"message": "clean up AML"})
    client.post("/api/programs/q1/synthesize")
    r = client.post("/api/programs/q1/discover/questions")
    assert r.status_code == 200 and "questions" in r.json()


def test_preset_endpoints(client):
    pr = client.get("/api/models/presets").json()
    assert [p["id"] for p in pr["presets"]] == ["recommended", "cost", "open", "lab"]
    assert pr["active"]["preset"] == "recommended"
    # apply lab-first: anthropic
    r = client.post("/api/models/preset", json={"preset": "lab", "lab": "anthropic"})
    assert r.status_code == 200
    body = r.json()
    assert body["overrides"]["distill_extract"].startswith("anthropic/")
    assert not body["overrides"]["second_census"].startswith("anthropic/")   # independence
    assert any("independent" in n for n in body["notes"])
    # now the models endpoint reports it as active
    assert client.get("/api/models").json()["active_preset"] == {"preset": "lab", "lab": "anthropic"}
    # a single manual override flips it to 'custom'
    client.post("/api/models/override", json={"task_id": "blueprint_summary", "model": "openai/gpt-5.6-luna"})
    assert client.get("/api/models").json()["active_preset"]["preset"] == "custom"
    # recommended clears everything
    client.post("/api/models/preset", json={"preset": "recommended"})
    assert client.get("/api/models").json()["active_preset"]["preset"] == "recommended"
    # bad preset / missing lab rejected
    assert client.post("/api/models/preset", json={"preset": "nope"}).status_code == 400
    assert client.post("/api/models/preset", json={"preset": "lab"}).status_code == 400


def test_model_policy_lifecycle(client, approot):
    client.post("/api/programs", json={"program_id": "pol1"})
    # defaults to provisional Recommended
    p = client.get("/api/programs/pol1/policy").json()
    assert p["status"] == "provisional" and p["preset"] == "recommended" and p["overrides"] == {}
    # set a strategy (provisional) — writes per-program overrides
    r = client.post("/api/programs/pol1/policy", json={"preset": "lab", "lab": "anthropic"})
    assert r.status_code == 200
    doc = r.json()["policy"]
    assert doc["preset"] == "lab" and doc["overrides"]["distill_extract"].startswith("anthropic/")
    # a manual dial makes it Customized
    client.post("/api/programs/pol1/policy/override", json={"task_id": "blueprint_summary", "model": "openai/gpt-5.6-luna"})
    assert client.get("/api/programs/pol1/policy").json()["preset"] == "custom"
    # lock requires Program Owner + rationale, and logs a decision
    assert client.post("/api/programs/pol1/policy/ratify", json={"name": "M", "role": "Reviewer", "rationale": "x"}).status_code == 403
    assert client.post("/api/programs/pol1/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": " "}).status_code == 400
    lk = client.post("/api/programs/pol1/policy/ratify", json={"name": "Mike Hsu", "role": "Program Owner", "rationale": "locked for the run"})
    assert lk.status_code == 200 and lk.json()["status"] == "ratified" and lk.json()["hash"].startswith("sha256:")
    entries = [json.loads(l) for l in (approot / "programs/pol1/governed/decisions.log.jsonl").read_text().splitlines()]
    assert entries[-1]["type"] == "ratification" and entries[-1]["artifact"] == "model_policy.json"
    # locked → changes refused until re-opened
    assert client.post("/api/programs/pol1/policy", json={"preset": "cost"}).status_code == 409
    assert client.post("/api/programs/pol1/policy/override", json={"task_id": "blueprint_summary", "model": None}).status_code == 409
    # re-open (logged) then editable again
    ro = client.post("/api/programs/pol1/policy/reopen", json={"name": "Mike Hsu", "role": "Program Owner", "rationale": "revisiting"})
    assert ro.status_code == 200 and ro.json()["status"] == "provisional"
    assert client.post("/api/programs/pol1/policy", json={"preset": "cost"}).status_code == 200


def test_freeze_gated_on_locked_policy(client, approot):
    client.post("/api/programs", json={"program_id": "g2"})
    client.post("/api/programs/g2/manifest/items", json={
        "item_id": "12-cfr-1266", "title": "t", "issuer": "FHFA", "family": "regulation", "locator": "12 CFR 1266"})
    ok = {"name": "M", "role": "Corpus Steward", "rationale": "reviewed"}
    assert client.post("/api/programs/g2/manifest/freeze", json=ok).status_code == 409   # policy not locked
    client.post("/api/programs/g2/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "ok"})
    assert client.post("/api/programs/g2/manifest/freeze", json=ok).status_code == 200


def test_policy_drives_provenance(client, approot):
    # A program's ratified policy actually changes which model the router serves.
    client.post("/api/programs", json={"program_id": "prov1"})
    client.post("/api/programs/prov1/policy", json={"preset": "lab", "lab": "openai"})
    client.post("/api/programs/prov1/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "ok"})
    client.post("/api/programs/prov1/interview", json={"message": "hi"})   # intake_interview runs under policy
    stamps = [json.loads(l) for l in (approot / "runs/stamps.jsonl").read_text().splitlines() if l.strip()]
    mine = [s for s in stamps if s.get("program_id") == "prov1" and s["task_id"] == "intake_interview"]
    assert mine and mine[-1]["model_requested"].startswith("openai/")   # policy, not the anthropic default


def test_ledger_endpoint(client, approot):
    client.post("/api/programs", json={"program_id": "led1"})
    client.post("/api/programs/led1/interview", json={"message": "clean up AML"})   # provenance + transcript
    client.post("/api/programs/led1/synthesize")
    client.post("/api/programs/led1/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "ok"})
    # purpose ledger: has the interview conversation + intake provenance
    lp = client.get("/api/programs/led1/ledger/purpose").json()
    assert lp["phase"] == "purpose"
    assert any(m["role"] == "user" for m in lp["conversation"])
    assert any(m["task"] == "intake_interview" for m in lp["models"])
    # the model-policy lock decision is filed under setup, not purpose
    assert not any(d["artifact"] == "model_policy.json" for d in lp["decisions"])
    ls = client.get("/api/programs/led1/ledger/setup").json()
    assert any(d.get("artifact") == "model_policy.json" for d in ls["decisions"])
    # overview is program-wide
    lo = client.get("/api/programs/led1/ledger/overview").json()
    assert len(lo["decisions"]) >= 1 and lo["conversation"]


def test_corpus_url_override(client, approot):
    client.post("/api/programs", json={"program_id": "uk1"})
    # a source with no fetchable locator/url (like a UK statute the planner can't map)
    client.post("/api/programs/uk1/manifest/items", json={
        "item_id": "uk-emir", "title": "UK EMIR (onshored)", "issuer": "UK", "family": "statute",
        "locator": "(no locator — human to supply)"})
    client.post("/api/programs/uk1/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "ok"})
    client.post("/api/programs/uk1/manifest/freeze", json={"name": "M", "role": "Corpus Steward", "rationale": "r"})
    # acquire → the item errors with a clear "no source URL" message (not a blank)
    client.post("/api/programs/uk1/corpus/acquire", json={"limit": 4})
    st = client.get("/api/programs/uk1/corpus/status").json()
    assert st["items"]["uk-emir"]["status"] == "error"
    assert "no source URL" in (st["items"]["uk-emir"]["errors"] or [""])[-1]
    # set a URL override (does not touch the frozen manifest)
    r = client.post("/api/programs/uk1/corpus/url-override", json={"item_id": "uk-emir", "url": "https://www.legislation.gov.uk/eur/2012/648"})
    assert r.status_code == 200 and r.json()["overrides"] == 1
    assert (approot / "programs/uk1/governed/corpus_texts/url_overrides.json").exists()
    # unknown item rejected
    assert client.post("/api/programs/uk1/corpus/url-override", json={"item_id": "nope", "url": "x"}).status_code == 404


def test_corpus_set_aside_source(client, approot):
    client.post("/api/programs", json={"program_id": "ex1"})
    client.post("/api/programs/ex1/manifest/items", json={
        "item_id": "good", "title": "Fetchable", "issuer": "X", "family": "regulation", "locator": "12 CFR 1"})
    client.post("/api/programs/ex1/manifest/items", json={
        "item_id": "nofetch", "title": "Reference only", "issuer": "Y", "family": "guidance",
        "locator": "(no locator — human to supply)"})
    client.post("/api/programs/ex1/policy/ratify", json={"name": "M", "role": "Program Owner", "rationale": "ok"})
    client.post("/api/programs/ex1/manifest/freeze", json={"name": "M", "role": "Corpus Steward", "rationale": "r"})
    # set aside requires a reason
    assert client.post("/api/programs/ex1/corpus/exclude", json={"item_id": "nofetch"}).status_code == 400
    assert client.post("/api/programs/ex1/corpus/exclude", json={"item_id": "ghost", "reason": "x"}).status_code == 404
    r = client.post("/api/programs/ex1/corpus/exclude", json={"item_id": "nofetch", "reason": "reference-only, no fetchable doc"})
    assert r.status_code == 200 and r.json()["excluded"] is True
    # status shows it excluded (not error); decision logged
    st = client.get("/api/programs/ex1/corpus/status").json()
    assert st["counts"]["excluded"] == 1 and st["items"]["nofetch"]["status"] == "excluded"
    entries = [json.loads(l) for l in (approot / "programs/ex1/governed/decisions.log.jsonl").read_text().splitlines()]
    assert entries[-1]["artifact"] == "corpus" and "Set aside" in entries[-1]["decision"]
    # completeness: overview now requires only the 1 active source, not 2
    ov = client.get("/api/programs/ex1/overview").json()
    corpus_stage = next(s for s in ov["stages"] if s["key"] == "corpus")
    assert "1 sources" in corpus_stage["metric"]
    # restore
    assert client.post("/api/programs/ex1/corpus/exclude", json={"item_id": "nofetch", "undo": True}).status_code == 200
    assert client.get("/api/programs/ex1/corpus/status").json()["counts"]["excluded"] == 0
