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
