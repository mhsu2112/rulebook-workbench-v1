"""Document-upload path for source discovery / acquisition.

For sources with no fetchable URL, a user uploads the document: its text enters
the corpus store and the acquirer treats it as acquired ("manual"), without ever
touching the frozen manifest hash (OR-7 — same discipline as url_overrides).
"""
import json

import pytest
from fastapi.testclient import TestClient

from test_server import approot, transport  # noqa: F401  (fixtures)
from test_acquire import corpus_transport
from workbench.acquire import Acquirer, extract_upload, store_upload, UploadError
from workbench.server import create_app

SNAP = "2026-07-18"
TXT = ("This internal supervisory circular sets out the reporting obligation for "
       "covered institutions. " * 8).encode()
HTML = (b"<html><head><script>bad()</script></head><body><h1>Circular 7</h1><p>"
        + b"Covered firms must report within ten business days. " * 8 + b"</p></body></html>")


def test_extract_upload_routes_by_type():
    t, ext = extract_upload("circular.txt", TXT)
    assert ext == "txt" and "reporting obligation" in t
    t2, ext2 = extract_upload("page.html", HTML)
    assert ext2 == "html" and "report within ten business days" in t2 and "bad()" not in t2
    # PDF magic bytes win regardless of a misleading name; a corrupt PDF is a
    # friendly UploadError, not a raw pypdf traceback.
    with pytest.raises(UploadError):
        extract_upload("notes.txt", b"%PDF-1.4 not really")


def test_store_upload_writes_text_raw_and_provenance(tmp_path):
    prov = store_upload(tmp_path, "local-circular-1", "circular.txt", TXT)
    ct = tmp_path / "governed" / "corpus_texts"
    assert (ct / "local-circular-1.txt").read_text().startswith("This internal")
    assert (ct / "uploads" / "local-circular-1.txt").read_bytes() == TXT
    reg = json.loads((ct / "uploads.json").read_text())
    assert reg["local-circular-1"]["sha256"].startswith("sha256:")
    assert prov["chars"] > 100 and prov["bytes"] == len(TXT)


def test_store_upload_rejects_empty_extraction(tmp_path):
    with pytest.raises(UploadError):
        store_upload(tmp_path, "x", "tiny.txt", b"hi")


def test_acquire_marks_uploaded_manual_without_fetch(tmp_path):
    # Upload wins even though the item carries a URL that WOULD 500 if fetched.
    store_upload(tmp_path, "no-url-source", "circular.txt", TXT)
    item = {"item_id": "no-url-source", "family": "guidance", "locator": "Circular 7",
            "url": "https://dead.example/gone", "title": "Circular", "issuer": "CB", "status": "live"}
    acq = Acquirer(tmp_path, snapshot_date=SNAP, manifest_hash="sha256:abc",
                   transport=corpus_transport(fail_ids=["dead.example"]))
    r = acq.acquire([item], limit=5)
    assert r["counts"] == {"fetched": 1, "error": 0, "pending": 0}   # 'manual' counts as acquired
    rec = r["items"]["no-url-source"]
    assert rec["status"] == "manual" and rec["source"] == "uploaded_document"
    assert rec["raw_sha256"].startswith("sha256:")


def _frozen_program(c, pid, item):
    c.post("/api/programs", json={"program_id": pid})
    c.post(f"/api/programs/{pid}/manifest/items", json=item)
    c.post(f"/api/programs/{pid}/policy/ratify",
           json={"name": "M", "role": "Program Owner", "rationale": "r"})
    c.post(f"/api/programs/{pid}/manifest/freeze",
           json={"name": "M", "role": "Corpus Steward", "rationale": "r"})


def test_corpus_upload_satisfies_existing_item(approot):  # noqa: F811
    app = create_app(root=approot, transport=corpus_transport(), api_key="test-key")
    c = TestClient(app)
    _frozen_program(c, "p1", {"item_id": "local-circular-1", "title": "Board Circular 7",
                              "issuer": "Central Bank", "family": "guidance", "status": "live",
                              "locator": "Circular 7/2026 (no public URL)"})
    r = c.post("/api/programs/p1/corpus/upload",
               data={"item_id": "local-circular-1"},
               files={"file": ("circular.txt", TXT, "text/plain")})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "manual" and r.json()["sha256"].startswith("sha256:")
    s = c.get("/api/programs/p1/corpus/status").json()
    assert s["items"]["local-circular-1"]["status"] == "manual"
    assert s["counts"]["fetched"] + s["counts"]["pending"] >= 0 and s["counts"]["pending"] == 0
    # unknown item is rejected
    assert c.post("/api/programs/p1/corpus/upload", data={"item_id": "nope"},
                  files={"file": ("x.txt", TXT, "text/plain")}).status_code == 404


def test_discover_upload_adds_new_source(approot):  # noqa: F811
    app = create_app(root=approot, transport=corpus_transport(), api_key="test-key")
    c = TestClient(app)
    c.post("/api/programs", json={"program_id": "p2"})
    r = c.post("/api/programs/p2/discover/upload",
               data={"title": "Local Board Circular 12", "issuer": "Central Bank",
                     "family": "guidance", "locator": "Circular 12/2026"},
               files={"file": ("c12.txt", TXT, "text/plain")})
    assert r.status_code == 200, r.text
    iid = r.json()["item"]["item_id"]
    assert iid and r.json()["status"] == "manual"
    m = c.get("/api/programs/p2/manifest").json()
    added = [i for i in m["items"] if i["item_id"] == iid][0]
    assert added["issuer"] == "Central Bank" and "uploaded document" in added["note"].lower()
    # empty metadata is rejected (missing/blank title -> 422 from FastAPI or 400 from our guard)
    assert c.post("/api/programs/p2/discover/upload",
                  data={"title": "", "issuer": "x", "family": "guidance"},
                  files={"file": ("y.txt", TXT, "text/plain")}).status_code in (400, 422)


def test_discover_upload_blocked_after_freeze(approot):  # noqa: F811
    app = create_app(root=approot, transport=corpus_transport(), api_key="test-key")
    c = TestClient(app)
    _frozen_program(c, "p3", {"item_id": "seed-1", "title": "Seed", "issuer": "X",
                              "family": "guidance", "status": "live", "locator": "seed"})
    r = c.post("/api/programs/p3/discover/upload",
               data={"title": "Too Late", "issuer": "X", "family": "guidance"},
               files={"file": ("z.txt", TXT, "text/plain")})
    assert r.status_code == 409   # frozen manifest -> new material goes to the scope-change queue
