import json
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import REPO, make_response
from test_server import MIN_PS, approot  # noqa: F401  (fixture)
from workbench.distill import Distiller, verify_citations
from workbench.server import create_app

SOURCE = ("Each bank shall develop, implement, and maintain an effective anti-money "
          "laundering program reasonably designed to assure compliance. The program "
          "shall be approved by the board of directors. " * 5)

GOOD_EX = {
    "item_id": "x", "nothing_in_scope": False,
    "objectives": [],
    "obligations": [{
        "obligation_id": "OB-1", "actor": "bank", "modality": "must",
        "action": "develop, implement, and maintain an effective AML program",
        "trigger": None, "threshold": None, "exceptions": [],
        "citations": [{"quote": "Each bank shall develop, implement, and maintain an effective anti-money laundering program"}],
    }],
    "definitions": [{"term": "program", "definition": "(undefined here)",
                     "citations": [{"quote": "maintain an effective anti-money laundering program"}]}],
    "interactions": [], "notes": None,
}

BAD_EX = json.loads(json.dumps(GOOD_EX))
BAD_EX["obligations"][0]["citations"] = [{"quote": "This sentence appears nowhere in the source."}]
BAD_EX["definitions"][0]["citations"] = [{"quote": "Neither does this fabricated one."}]

DEFECTS = {"findings": [{
    "code": "D4", "title": "Undefined material term: program",
    "description": "The term 'program' is used but never defined.",
    "locations": [{"item_id": "31-cfr-1022", "quote": "maintain an effective anti-money laundering program"}],
}]}


def test_verify_citations_sets_flags():
    ex = json.loads(json.dumps(GOOD_EX))
    v, t = verify_citations(ex, SOURCE)
    assert (v, t) == (2, 2)
    assert all(c["verified"] for c in ex["obligations"][0]["citations"])
    ex2 = json.loads(json.dumps(BAD_EX))
    v2, t2 = verify_citations(ex2, SOURCE)
    assert (v2, t2) == (0, 2)


def test_verify_normalizes_whitespace_and_quotes():
    ex = {"citations": [{"quote": "Each  bank\nshall develop,   implement,"}]}
    v, t = verify_citations(ex, SOURCE)
    assert (v, t) == (1, 1)


def _mk_distiller(tmp_path, responses):
    """responses: dict task_id -> python object to return"""
    calls = []

    def call_fn(task_id, messages):
        calls.append((task_id, messages[-1]["content"]))
        out = responses[task_id]
        return json.loads(json.dumps(out)) if isinstance(out, (dict, list)) else out, \
            {"cost": {"usd": 0.02}}

    d = Distiller(tmp_path, program_id="p1", scope="AML program-establishment obligations",
                  manifest_hash="sha256:abc", call_fn=call_fn)
    (tmp_path / "governed/corpus_texts").mkdir(parents=True, exist_ok=True)
    return d, calls


def _write_text(tmp_path, iid, text=SOURCE):
    (tmp_path / f"governed/corpus_texts/{iid}.txt").write_text(text)


def test_extract_records_and_rejects_bad_citations(tmp_path):
    d, calls = _mk_distiller(tmp_path, {"distill_extract": GOOD_EX})
    _write_text(tmp_path, "31-cfr-1022")
    items = [{"item_id": "31-cfr-1022", "family": "regulation_fincen", "title": "MSB",
              "issuer": "FinCEN", "locator": "31 CFR 1022", "status": "live"}]
    r = d.run(items, limit=5)
    assert r["counts"]["extracted"] == 1
    saved = json.loads((tmp_path / "governed/blueprint/31-cfr-1022.json").read_text())
    assert saved["obligations"][0]["citations"][0]["verified"] is True
    rec = r["items"]["31-cfr-1022"]
    assert rec["citations_verified"] == 2 and rec["citations_total"] == 2
    # bad citations -> rejected as error, file for that item not overwritten
    d2, _ = _mk_distiller(tmp_path, {"distill_extract": BAD_EX})
    _write_text(tmp_path, "bad-item")
    r2 = d2.run([{**items[0], "item_id": "bad-item"}], limit=5)
    assert r2["items"]["bad-item"]["status"] == "error"
    assert "citation verification failed" in r2["items"]["bad-item"]["errors"][0]
    assert not (tmp_path / "governed/blueprint/bad-item.json").exists()


def test_extract_requires_acquired_text_and_resumes(tmp_path):
    d, _ = _mk_distiller(tmp_path, {"distill_extract": GOOD_EX})
    items = [{"item_id": "missing", "family": "f"}]
    r = d.run(items, limit=5)
    assert r["items"]["missing"]["status"] == "error"
    assert "no acquired text" in r["items"]["missing"]["errors"][0]
    r2 = d.run(items, limit=5)   # errors not retried by default
    assert r2["processed"] == 0
    _write_text(tmp_path, "missing")
    r3 = d.run(items, limit=5, retry_errors=True)
    assert r3["counts"]["extracted"] == 1


def test_focus_pass_for_oversized_texts(tmp_path):
    big = SOURCE * 400  # > FOCUS_LIMIT
    responses = {"distill_focus": SOURCE, "distill_extract": GOOD_EX}
    d, calls = _mk_distiller(tmp_path, responses)
    _write_text(tmp_path, "big-item", big)
    r = d.run([{"item_id": "big-item", "family": "statute"}], limit=1)
    assert r["counts"]["extracted"] == 1
    tasks = [t for t, _ in calls]
    assert "distill_focus" in tasks and tasks[-1] == "distill_extract"
    assert r["items"]["big-item"]["focused"] is True


def test_ceiling_notes_for_evidence_and_horizon(tmp_path):
    d, calls = _mk_distiller(tmp_path, {"distill_extract": GOOD_EX})
    _write_text(tmp_path, "enf-1")
    _write_text(tmp_path, "prop-1")
    d.run([{"item_id": "enf-1", "family": "enforcement_index", "evidence_role": "enforcement_evidence"},
           {"item_id": "prop-1", "family": "reform_proposal", "evidence_role": "reform_proposal"}], limit=5)
    prompts = [p for t, p in calls if t == "distill_extract"]
    assert any("may NOT establish an operative duty" in p for p in prompts)
    assert any("never anchors a current-law claim" in p for p in prompts)


def test_defect_run_writes_register_and_verifies_quotes(tmp_path):
    d, _ = _mk_distiller(tmp_path, {"distill_extract": GOOD_EX, "defect_detect": DEFECTS})
    _write_text(tmp_path, "31-cfr-1022")
    items = [{"item_id": "31-cfr-1022", "family": "regulation_fincen"}]
    d.run(items, limit=5)
    out = d.detect_defects(items, family="regulation_fincen")
    assert out["findings"][0]["code"] == "D4"
    assert out["findings"][0]["locations"][0]["verified"] is True
    reg = json.loads((tmp_path / "governed/registers/defects.json").read_text())
    assert "defects-regulation_fincen" in reg["runs"]
    # cross pass writes a second run
    d.detect_defects(items, family=None)
    reg2 = json.loads((tmp_path / "governed/registers/defects.json").read_text())
    assert "defects-cross" in reg2["runs"]


def _mk_app(approot, ratified=True):  # noqa: F811
    (approot / "data").mkdir(exist_ok=True)
    shutil.copy(REPO / "data" / "aml-program-rules-slice.json",
                approot / "data" / "aml-program-rules-slice.json")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        last = payload["messages"][-1]["content"]
        if "Phase 2 distillation" in last:
            content = json.dumps(GOOD_EX)
        elif "defect detection" in last:
            content = json.dumps(DEFECTS)
        else:
            content = json.dumps(GOOD_EX)
        return httpx.Response(200, json=make_response(model=payload["model"], content=content))

    app = create_app(root=approot, transport=httpx.MockTransport(handler), api_key="test-key")
    c = TestClient(app)
    c.post("/api/programs", json={"program_id": "p1"})
    ps = json.loads(json.dumps(MIN_PS))
    ps["program_id"] = "p1"
    ps["status"] = "ratified" if ratified else "awaiting_ratification"
    (approot / "programs/p1/governed/purpose_statement.json").write_text(json.dumps(ps))
    return c


def test_endpoints_gated_on_frozen_manifest_and_ratified_ps(approot):  # noqa: F811
    c = _mk_app(approot, ratified=False)
    assert c.get("/api/programs/p1/blueprint").status_code == 404  # no manifest yet
    c.post("/api/programs/p1/manifest/import", json={"slice_id": "aml-program-rules-slice"})
    c.post("/api/programs/p1/manifest/freeze", json={"name": "M", "role": "Corpus Steward", "rationale": "r"})
    r = c.get("/api/programs/p1/blueprint")
    assert r.status_code == 409 and "not ratified" in r.json()["detail"]


def test_extract_flow_via_api(approot):  # noqa: F811
    c = _mk_app(approot, ratified=True)
    c.post("/api/programs/p1/manifest/import", json={"slice_id": "aml-program-rules-slice"})
    c.post("/api/programs/p1/manifest/freeze", json={"name": "M", "role": "Corpus Steward", "rationale": "r"})
    # fake acquisition for two items
    ct = approot / "programs/p1/governed/corpus_texts"
    ct.mkdir(parents=True, exist_ok=True)
    (ct / "31-cfr-1022.txt").write_text(SOURCE)
    (ct / "31-cfr-1020.txt").write_text(SOURCE)
    b = c.get("/api/programs/p1/blueprint").json()
    assert b["counts"] == {"extracted": 0, "error": 0, "pending": 42}
    r = c.post("/api/programs/p1/blueprint/extract", json={"limit": 2}).json()
    assert r["processed"] == 2
    # the two with texts extract; order follows manifest, so pick from results
    statuses = {k: v["status"] for k, v in r["items"].items()}
    assert list(statuses.values()).count("extracted") + list(statuses.values()).count("error") == 2
    ex = c.get("/api/programs/p1/blueprint/extraction/31-cfr-1022")
    if ex.status_code == 200:
        assert ex.json()["obligations"][0]["citations"][0]["verified"] is True


def test_bare_string_citations_normalized_and_verified(tmp_path):
    """Regression: FINRA items failed schema validation because the model
    returned citations as bare strings; shape must not kill an extraction."""
    ex = json.loads(json.dumps(GOOD_EX))
    ex["obligations"][0]["citations"] = [
        "Each bank shall develop, implement, and maintain an effective anti-money laundering program"]
    d, _ = _mk_distiller(tmp_path, {"distill_extract": ex})
    _write_text(tmp_path, "str-cite")
    r = d.run([{"item_id": "str-cite", "family": "sro_finra"}], limit=1)
    assert r["items"]["str-cite"]["status"] == "extracted"
    saved = json.loads((tmp_path / "governed/blueprint/str-cite.json").read_text())
    c = saved["obligations"][0]["citations"][0]
    assert c["quote"].startswith("Each bank") and c["verified"] is True


def test_uncited_claims_rejected(tmp_path):
    ex = json.loads(json.dumps(GOOD_EX))
    ex["obligations"][0]["citations"] = []
    ex["definitions"] = []
    d, _ = _mk_distiller(tmp_path, {"distill_extract": ex})
    _write_text(tmp_path, "uncited")
    r = d.run([{"item_id": "uncited", "family": "f"}], limit=1)
    assert r["items"]["uncited"]["status"] == "error"
    assert "zero citations" in r["items"]["uncited"]["errors"][0]


def test_reconcile_evicts_stale_empty_and_heals_register(tmp_path):
    """Regression: an undead server left (a) a ∅-extraction written from a
    block page whose source has since been re-fetched for real, and (b) a
    register entry contradicting a good extraction file."""
    import os, time
    d, _ = _mk_distiller(tmp_path, {"distill_extract": GOOD_EX})
    # (a) stale ∅ whose source was re-acquired AFTER the extraction was written
    (tmp_path / "governed/blueprint").mkdir(parents=True, exist_ok=True)
    (tmp_path / "governed/blueprint/stale.json").write_text(json.dumps(
        {"item_id": "stale", "nothing_in_scope": True, "objectives": [], "obligations": [],
         "definitions": [], "interactions": [], "notes": "CAPTCHA page"}))
    (tmp_path / "governed/corpus_texts/stale.txt").write_text(SOURCE * 6)
    now = time.time()
    os.utime(tmp_path / "governed/blueprint/stale.json", (now - 600, now - 600))
    os.utime(tmp_path / "governed/corpus_texts/stale.txt", (now, now))
    # (a2) legitimately-empty extraction of an UNCHANGED source must be kept
    (tmp_path / "governed/corpus_texts/legit-empty.txt").write_text(SOURCE * 6)
    (tmp_path / "governed/blueprint/legit-empty.json").write_text(json.dumps(
        {"item_id": "legit-empty", "nothing_in_scope": True, "objectives": [], "obligations": [],
         "definitions": [], "interactions": [], "notes": "out of scope, correctly"}))
    os.utime(tmp_path / "governed/corpus_texts/legit-empty.txt", (now - 600, now - 600))
    # (b) good file, contradictory register entry
    _write_text(tmp_path, "good")
    good = json.loads(json.dumps(GOOD_EX)); good["item_id"] = "good"
    (tmp_path / "governed/blueprint/good.json").write_text(json.dumps(good))
    reg = {"manifest_hash": "sha256:abc", "items": {
        "good": {"status": "extracted", "obligations": 0, "definitions": 0,
                 "nothing_in_scope": True, "citations_verified": 0, "citations_total": 0},
        "gone": {"status": "extracted"}}}
    (tmp_path / "governed/blueprint/extraction_register.json").write_text(json.dumps(reg))
    items = [{"item_id": "stale", "family": "f"}, {"item_id": "good", "family": "f"},
             {"item_id": "gone", "family": "f"}, {"item_id": "legit-empty", "family": "f"}]
    out = d.reconcile(items)
    assert "stale" not in out["items"]                       # evicted -> pending
    assert not (tmp_path / "governed/blueprint/stale.json").exists()
    assert out["items"]["legit-empty"]["status"] == "extracted"   # ∅ of unchanged source kept
    assert (tmp_path / "governed/blueprint/legit-empty.json").exists()
    assert out["items"]["good"]["obligations"] == 1          # healed from file
    assert out["items"]["good"]["citations_verified"] == 2
    assert "gone" not in out["items"]                        # no file -> pending


def test_blueprint_render_endpoint(approot):  # noqa: F811
    c = _mk_app(approot, ratified=True)
    c.post("/api/programs/p1/manifest/import", json={"slice_id": "aml-program-rules-slice"})
    c.post("/api/programs/p1/manifest/freeze", json={"name": "M", "role": "Corpus Steward", "rationale": "r"})
    gov = approot / "programs/p1/governed"
    (gov / "corpus_texts").mkdir(parents=True, exist_ok=True)
    (gov / "corpus_texts/31-cfr-1022.txt").write_text(SOURCE)
    (gov / "blueprint").mkdir(parents=True, exist_ok=True)
    ex = json.loads(json.dumps(GOOD_EX)); ex["item_id"] = "31-cfr-1022"
    ex["obligations"][0]["citations"][0]["verified"] = True
    (gov / "blueprint/31-cfr-1022.json").write_text(json.dumps(ex))
    r = c.get("/api/programs/p1/blueprint/render")
    assert r.status_code == 200
    assert "Derived Blueprint" in r.text
    assert "develop, implement, and maintain" in r.text   # obligation rendered
    assert "✓" in r.text                                   # verification mark
    assert "source of truth" in r.text                     # provenance footer


MIN_SUMMARY = {
    "headline": "A layered AML regime.",
    "how_to_read": "Families, then element tables; the tables are the artifact.",
    "regime_shape": [{"heading": "Statutory spine", "text": "BSA delegates to FinCEN.", "refs": ["31-usc-5311"]},
                     {"heading": "Program rules", "text": "Per-sector program rules.", "refs": ["31-cfr-1022"]}],
    "highlights": [{"point": "The MSB program rule is the dense node.", "refs": ["31-cfr-1022"]},
                   {"point": "Definitions diverge.", "refs": ["D2"]},
                   {"point": "Exam manual carries expectations.", "refs": ["ffiec-man-cp-01"]}],
    "tensions": [{"point": "Agent-allocation vs sole responsibility.", "refs": ["defects-regulation_fincen#0"]}],
    "caveats": "Advisory reading guide; enforcement items evidence expectations only.",
}


def test_summary_generated_and_rendered_as_advisory(approot):  # noqa: F811
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        last = payload["messages"][-1]["content"]
        if "BlueprintExecutiveSummary" in last:
            assert "Do NOT resolve" in last          # fidelity rule extends to the summary
            content = json.dumps(MIN_SUMMARY)
        else:
            content = json.dumps(GOOD_EX)
        return httpx.Response(200, json=make_response(model=payload["model"], content=content))

    (approot / "data").mkdir(exist_ok=True)
    shutil.copy(REPO / "data" / "aml-program-rules-slice.json",
                approot / "data" / "aml-program-rules-slice.json")
    app = create_app(root=approot, transport=httpx.MockTransport(handler), api_key="k")
    c = TestClient(app)
    c.post("/api/programs", json={"program_id": "p1"})
    ps = json.loads(json.dumps(MIN_PS)); ps["program_id"] = "p1"; ps["status"] = "ratified"
    (approot / "programs/p1/governed/purpose_statement.json").write_text(json.dumps(ps))
    c.post("/api/programs/p1/manifest/import", json={"slice_id": "aml-program-rules-slice"})
    c.post("/api/programs/p1/manifest/freeze", json={"name": "M", "role": "Corpus Steward", "rationale": "r"})
    r = c.post("/api/programs/p1/blueprint/summarize")
    assert r.status_code == 200
    assert r.json()["_provenance"]["advisory"] is True
    html_out = c.get("/api/programs/p1/blueprint/render").text
    assert "ADVISORY ORIENTATION" in html_out
    assert "the table wins" in html_out
    assert "Agent-allocation vs sole responsibility." in html_out
