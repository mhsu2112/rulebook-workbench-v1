"""Explorations (release 2, ADR-019): branches never touch the official record."""
import hashlib
import io
import json
import zipfile

from test_server import client, approot, transport, MIN_PS  # noqa: F401  (fixtures)
from test_server import _docx_text


def _tree_hash(d):
    h = hashlib.sha256()
    for f in sorted(p for p in d.rglob("*") if p.is_file() and "explorations" not in p.parts):
        h.update(str(f.relative_to(d)).encode()); h.update(f.read_bytes())
    return h.hexdigest()


def _official(client, pid):
    client.post("/api/programs", json={"program_id": pid})
    client.post(f"/api/programs/{pid}/interview", json={"message": "clean up AML"})
    client.post(f"/api/programs/{pid}/synthesize")


def test_branch_is_isolated_from_the_official_record(client, approot):
    _official(client, "ex1")
    pdir = approot / "programs" / "ex1"
    before = _tree_hash(pdir)

    imp = client.get("/api/programs/ex1/explorations/impact?answer_id=A1").json()
    assert imp["restart"] == "purpose" and imp["stage"] == "S1"

    r = client.post("/api/programs/ex1/explorations", json={
        "name": "Different problem", "answer_id": "A1", "new_answer": "something else",
        "by_name": "Tester", "by_role": "Policy Reviewer"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["program_id"] == "ex1~x-a" and b["branch_id"] == "a"
    assert (pdir / "explorations" / "a" / "branch.json").exists()
    turns = json.loads((pdir / "explorations" / "a" / "restricted" / "interview.json").read_text())
    assert "[EXPLORATION A]" in turns[-1]["content"] and "something else" in turns[-1]["content"]

    # the branch is a working program under its own address
    o = client.get("/api/programs/ex1~x-a/overview").json()
    assert o["exploration"]["branch_id"] == "a"
    assert client.post("/api/programs/ex1~x-a/synthesize").status_code == 200
    r = client.post("/api/programs/ex1~x-a/open-items/OI-1/resolve",
                    json={"name": "Tester", "role": "Scope Owner", "rationale": "fine"})
    assert r.status_code == 200
    r = client.post("/api/programs/ex1~x-a/ratify",
                    json={"name": "Tester", "role": "Program Owner", "rationale": "what if"})
    assert r.status_code == 200
    log = client.get("/api/programs/ex1~x-a/overview").json()["decisions"]
    assert [d["entry_id"] for d in log] == ["EX-A-001", "EX-A-002"]
    assert log[-1]["type"] == "exploration_ratification" and all(d["exploration"] == "a" for d in log)

    # the official record did not move, and its packages carry nothing from the branch
    assert _tree_hash(pdir) == before
    assert client.get("/api/programs/ex1/overview").json()["decisions"] == []
    for q in ("", "?share=true"):
        z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/programs/ex1/package{q}").content))
        assert not any("explorations" in n for n in z.namelist())
        assert all(b"something else" not in z.read(n) for n in z.namelist())

    # branch documents are marked
    doc = _docx_text(client.get("/api/programs/ex1~x-a/purpose/statement.docx").content)
    assert "EXPLORATION" in doc
    cover = zipfile.ZipFile(io.BytesIO(client.get("/api/programs/ex1~x-a/package").content))
    assert b"not part of the official record" in cover.read("ex1~x-a-package/index.html")


def test_branch_spend_listing_and_staleness(client, approot):
    _official(client, "ex2")
    client.post("/api/programs/ex2/explorations", json={"answer_id": "A1", "new_answer": "other"})
    client.post("/api/programs/ex2~x-a/synthesize")                   # a paid call inside the branch
    stamps = [json.loads(l) for l in (approot / "runs" / "stamps.jsonl").read_text().splitlines() if l.strip()]
    assert any(s["program_id"] == "ex2~x-a" for s in stamps)
    bud = client.get("/api/budget?pid=ex2").json()
    rows = {p["program_id"]: p for p in bud["programs"]}
    assert rows["ex2~x-a"]["exploration"] and rows["ex2~x-a"]["parent"] == "ex2"
    assert [x["program_id"] for x in bud["program"]["explorations"]] == ["ex2~x-a"]

    lst = client.get("/api/programs/ex2/explorations").json()
    assert len(lst) == 1 and lst[0]["stale"] is False and lst[0]["spend_usd"] > 0
    client.post("/api/programs/ex2/open-items/OI-1/resolve", json={"name": "O", "role": "Scope Owner", "rationale": "x"})
    assert client.get("/api/programs/ex2/explorations").json()[0]["stale"] is True

    cmp_ = client.get("/api/programs/ex2/explorations/a/compare").json()
    assert set(cmp_) == {"official", "branch", "branch_info"}

    # guards
    assert client.post("/api/programs/ex2~x-a/explorations", json={"answer_id": "A1", "new_answer": "y"}).status_code == 400
    assert client.post("/api/programs/ex2/explorations", json={"answer_id": "A1", "new_answer": "v"}).status_code == 400
    assert client.post("/api/programs/ex2/explorations", json={"answer_id": "NOPE", "new_answer": "y"}).status_code == 404
    assert client.get("/api/programs/ex2~x-zz/overview").status_code == 404

    client.post("/api/programs/ex2/explorations/a/archive", json={"name": "O", "role": "Program Owner"})
    assert client.get("/api/programs/ex2/explorations").json() == []
    assert len(client.get("/api/programs/ex2/explorations?archived=true").json()) == 1


def test_promotion_creates_a_new_official_program(client, approot):
    _official(client, "ex3")
    client.post("/api/programs/ex3/explorations", json={"answer_id": "A1", "new_answer": "other"})
    client.post("/api/programs/ex3~x-a/synthesize")
    client.post("/api/programs/ex3~x-a/open-items/OI-1/resolve", json={"name": "T", "role": "Scope Owner", "rationale": "x"})
    client.post("/api/programs/ex3~x-a/ratify", json={"name": "T", "role": "Program Owner", "rationale": "y"})

    body = {"new_program_id": "ex3-alt", "name": "Owner", "role": "Policy Reviewer", "rationale": "adopt it"}
    assert client.post("/api/programs/ex3/explorations/a/promote", json=body).status_code == 403
    body["role"] = "Program Owner"
    r = client.post("/api/programs/ex3/explorations/a/promote", json=body)
    assert r.status_code == 200, r.text
    assert "ex3-alt" in client.get("/api/programs").json()

    new = client.get("/api/programs/ex3-alt/overview").json()
    assert [d["entry_id"] for d in new["decisions"]] == ["DL-001"]
    assert "promoting Exploration A" in new["decisions"][0]["decision"]
    ps = client.get("/api/programs/ex3-alt/purpose").json()
    assert ps["status"] == "awaiting_ratification" and ps["program_id"] == "ex3-alt"
    g = approot / "programs" / "ex3-alt" / "governed"
    assert (g / "exploration_history.jsonl").exists() and (g / "promoted_from.json").exists()
    assert not (approot / "programs" / "ex3-alt" / "branch.json").exists()

    parent = client.get("/api/programs/ex3/overview").json()["decisions"]
    assert len(parent) == 1 and "promoted to a new official program, ex3-alt" in parent[0]["decision"]
    assert client.post("/api/programs/ex3/explorations/a/promote", json={**body, "new_program_id": "ex3-alt2"}).status_code == 409


# ---------------------------------------------------------------- source explorations (addendum 1)

def _frozen_program(client, approot, pid):
    from test_server import _ratified_program
    _ratified_program(client, approot, pid)
    for iid in ("rts-22", "emir-rts-2013"):
        client.post(f"/api/programs/{pid}/manifest/items", json={
            "item_id": iid, "title": iid.upper(), "issuer": "FCA", "family": "regulation", "locator": iid})
    client.post(f"/api/programs/{pid}/policy/ratify", json={"name": "O", "role": "Program Owner", "rationale": "ok"})
    doc = client.post(f"/api/programs/{pid}/manifest/freeze",
                      json={"name": "O", "role": "Program Owner", "rationale": "complete"}).json()
    g = approot / "programs" / pid / "governed"
    bp = g / "blueprint"
    bp.mkdir(parents=True, exist_ok=True)
    reg = {"manifest_hash": doc["content_hash"], "items": {}}
    for iid in ("rts-22", "emir-rts-2013"):
        (bp / f"{iid}.json").write_text(json.dumps({"item_id": iid, "obligations": [{"action": "report"}], "definitions": []}))
        reg["items"][iid] = {"status": "extracted", "obligations": 1, "cost_usd": 0.5, "manifest_hash": doc["content_hash"]}
    (bp / "extraction_register.json").write_text(json.dumps(reg))
    (g / "registers").mkdir(exist_ok=True)
    (g / "registers" / "defects.json").write_text(json.dumps({"manifest_hash": doc["content_hash"], "runs": {"defects-cross": {"findings": [{}]}}}))
    (g / "blueprint_summary.json").write_text("{}")
    return doc


def test_source_exploration_keeps_purpose_and_reopens_corpus(client, approot):
    _frozen_program(client, approot, "sx1")
    pdir = approot / "programs" / "sx1"
    before = _tree_hash(pdir)

    imp = client.get("/api/programs/sx1/explorations/impact?kind=sources").json()
    assert imp["kind"] == "sources" and imp["restart"] == "corpus" and imp["per_source_usd"] == 0.5
    assert any("Purpose Statement" in r for r in imp["reused"])

    assert client.post("/api/programs/sx1/explorations", json={"kind": "sources", "note": " "}).status_code == 400
    r = client.post("/api/programs/sx1/explorations", json={
        "kind": "sources", "name": "Field-level sources", "note": "Add the FCA validation-rules workbook",
        "by_name": "Mike", "by_role": "Program Owner"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["program_id"] == "sx1~x-a" and b["restart"] == "corpus"
    assert b["changed"]["official_items"] == ["rts-22", "emir-rts-2013"]

    # Purpose stays ratified; the corpus is a draft; per-source extractions came along
    assert client.get("/api/programs/sx1~x-a/purpose").json()["status"] == "ratified"
    m = client.get("/api/programs/sx1~x-a/manifest").json()
    assert m["frozen"] is False and len(m["items"]) == 2
    bg = pdir / "explorations" / "a" / "governed"
    assert (bg / "blueprint" / "rts-22.json").exists()
    assert not (bg / "registers" / "defects.json").exists()

    # replace a source: drop the pre-REFIT standard, add the workbook, re-freeze
    assert client.delete("/api/programs/sx1~x-a/manifest/items/emir-rts-2013").status_code == 200
    assert client.post("/api/programs/sx1~x-a/manifest/items", json={
        "item_id": "uk-emir-validation-rules", "title": "UK EMIR Validation Rules", "issuer": "FCA",
        "family": "reporting_instruction", "locator": "FCA/BoE validation rules",
        "url": "https://www.fca.org.uk/publication/fca/uk-emir-validation-rules-2026.xlsx"}).status_code == 200
    r = client.post("/api/programs/sx1~x-a/manifest/freeze", json={"name": "Mike", "role": "Program Owner", "rationale": "new sources"})
    assert r.status_code == 200, r.text
    new_hash = r.json()["content_hash"]
    reg = json.loads((bg / "blueprint" / "extraction_register.json").read_text())
    assert reg["manifest_hash"] == new_hash and set(reg["items"]) == {"rts-22"}
    assert reg["items"]["rts-22"]["manifest_hash"] == new_hash
    assert (bg / "blueprint" / "rts-22.json").exists() and not (bg / "blueprint" / "emir-rts-2013.json").exists()
    assert not (bg / "blueprint_summary.json").exists()
    bpv = client.get("/api/programs/sx1~x-a/blueprint")
    assert bpv.status_code == 200, bpv.text                 # the distiller accepts the carried register
    log = client.get("/api/programs/sx1~x-a/overview").json()["decisions"]
    assert log[-1]["entry_id"] == "EX-A-001" and log[-1]["type"] == "manifest_freeze"

    # the official program did not move
    assert _tree_hash(pdir) == before
    lst = client.get("/api/programs/sx1/explorations").json()
    assert lst[0]["kind"] == "sources" and lst[0]["metrics"]["sources_in_use"] == 2


def test_source_exploration_guards_and_promotion(client, approot):
    from test_server import _ratified_program
    _ratified_program(client, approot, "sx2")
    r = client.post("/api/programs/sx2/explorations", json={"kind": "sources", "note": "add a workbook"})
    assert r.status_code == 409 and "not frozen" in r.json()["detail"]
    assert client.get("/api/programs/sx2/explorations/impact").status_code == 400
    assert client.post("/api/programs/sx2/explorations", json={"kind": "other"}).status_code == 400

    _frozen_program(client, approot, "sx3")
    client.post("/api/programs/sx3/explorations", json={"kind": "sources", "note": "add a workbook"})
    r = client.post("/api/programs/sx3/explorations/a/promote", json={
        "new_program_id": "sx3-fields", "name": "O", "role": "Program Owner", "rationale": "better sources"})
    assert r.status_code == 200, r.text
    new = client.get("/api/programs/sx3-fields/overview").json()
    assert "changed sources" in new["decisions"][0]["decision"]
