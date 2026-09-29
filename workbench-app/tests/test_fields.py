"""Field-level comparison (release 3): per-regime field registers from workbooks
and texts, a cross-regime comparison, and field findings in the Defect Register."""
import io
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from test_server import approot, make_response, _ratified_program  # noqa: F401  (fixtures)
from test_xlsx import make_xlsx
from workbench import acquire, fields
from workbench.server import create_app

EMIR = make_xlsx({
    "Overview": [["UK EMIR validation rules"], ["Read the tabs"]],
    "Trade validations": [
        ["", "", "", "Trade level", ""],
        ["Table", "Item", "Field", "NEWT", "MODI"],
        ["1", "1", "Reporting timestamp", "M", "M"],
        ["1", "4", "Counterparty 1 (Reporting counterparty)", "M", "M"],
        ["1", "7", "Nature of the counterparty 1", "M", "C"],
        ["2", "1", "UTI", "M", "M"],
    ],
    "Details": [
        ["Table", "Item", "Field", "Details to be reported", "Format"],
        ["1", "1", "Reporting timestamp", "Date and time of the submission of the report.", "ISO 8601 UTC"],
        ["1", "4", "Counterparty 1 (Reporting counterparty)", "Identifier of the counterparty to the derivative.", "ISO 17442 LEI"],
        ["1", "7", "Nature of the counterparty 1", "Whether counterparty 1 is financial or non-financial.", "F, N, C, O"],
        ["2", "1", "UTI", "Unique transaction identifier.", "Up to 52 alphanumeric characters"],
    ],
})
SFTR = make_xlsx({
    "Loan and collateral": [
        ["", "", "", "", "Trade level"],
        ["", "", "", "", "NEWT (New)"],
        ["Counterparty data"],
        ["1", "Reporting timestamp", "Date and time of submission of the report.", "ISO 8601 UTC", "M"],
        ["3", "Reporting counterparty", "Unique code identifying the reporting counterparty.", "ISO 17442 LEI", "M"],
        ["5", "Nature of the reporting counterparty", "Financial or non-financial.", "F or N", "M"],
        ["9", "Unique Transaction Identifier", "Unique reference assigned to the SFT.", "Up to 52 alphanumeric characters", "M"],
    ],
})
RTS22 = ("ANNEX I Table 2 Details to be reported in transaction reports. "
         "Field 1 Report status: Indication as to whether the transaction report is new or a cancellation. "
         "Field 3 Trading venue transaction identification code: Alphanumerical code assigned by the trading venue. "
         "Field 7 Buyer identification code: Code used to identify the acquirer of the financial instrument. ") * 3

MAPS = {
    "Trade validations": {"is_field_sheet": True, "header_rows": [1, 2], "first_data_row": 3,
                          "columns": {"table": "A", "number": "B", "name": "C"}, "mandatory_columns": ["D", "E"]},
    "Details": {"is_field_sheet": True, "header_rows": [1], "first_data_row": 2,
                "columns": {"table": "A", "number": "B", "name": "C", "definition": "D", "format": "E"},
                "mandatory_columns": []},
    "Loan and collateral": {"is_field_sheet": True, "header_rows": [1, 2], "first_data_row": 4,
                            "columns": {"number": "A", "name": "B", "definition": "C", "format": "D"},
                            "mandatory_columns": ["E"]},
}
PAIRS = {  # what the fake model says matches, by field name
    ("Reporting timestamp", "Reporting timestamp"): (["identical"], False),
    ("Counterparty 1 (Reporting counterparty)", "Reporting counterparty"): (["identical"], False),
    ("Nature of the counterparty 1", "Nature of the reporting counterparty"): (["format_difference", "definition_difference"], True),
    ("UTI", "Unique Transaction Identifier"): (["identical"], False),
}


def fake_model(prompt: str) -> dict:
    if "You are mapping one worksheet" in prompt:
        sheet = prompt.split("SHEET: ")[1].split("\n")[0]
        return MAPS.get(sheet, {"is_field_sheet": False, "columns": {}})
    if "You are building a field register" in prompt:
        return {"fields": [
            {"number": "1", "name": "Report status", "definition": "New or cancellation.",
             "quote": "Field 1 Report status: Indication as to whether the transaction report is new or a cancellation."},
            {"number": "7", "name": "Buyer identification code", "definition": "Acquirer.",
             "quote": "Field 7 Buyer identification code: Code used to identify the acquirer"},
            {"number": "99", "name": "Invented field", "quote": "this sentence is not in the source"}]}
    if "You are comparing reporting fields" in prompt:
        # the prompt lists "ID · name"; answer for every listed pair we know
        ids = {}
        for line in prompt.splitlines():
            line = line.strip().lstrip("- ")
            if " · " in line and line.split(" · ")[0].replace("-", "").isalnum():
                fid, rest = line.split(" · ", 1)
                ids.setdefault(fid, rest.split(" (item")[0].strip())
        a_tag = prompt.split("Below are ")[1].split(" ")[1]
        out = []
        for fa, na in ids.items():
            if not fa.startswith(a_tag.upper()):
                continue
            for fb, nb in ids.items():
                if fb.startswith(a_tag.upper()):
                    continue
                hit = PAIRS.get((na, nb)) or PAIRS.get((nb, na))
                if hit:
                    out.append({"a": fa, "b": fb, "aspects": hit[0], "detail": f"{na} vs {nb}",
                                "changes_obligations": hit[1], "impact_reason": "because"})
        return {"matches": out}
    return {}


def fake_call(task, msgs):
    return fake_model(msgs[0]["content"]), {"cost": {"usd": 0.01}}


def _program(tmp_path):
    ct = tmp_path / "governed" / "corpus_texts"
    ct.mkdir(parents=True)
    for iid, data in (("uk-emir-validation-rules", EMIR), ("uk-sftr-validation-rules", SFTR)):
        (ct / f"{iid}.xlsx").write_bytes(data)
        (ct / f"{iid}.txt").write_text(acquire.xlsx_to_text(data))
    (ct / "rts-22-2017-590.txt").write_text(RTS22)
    items = [{"item_id": "uk-emir-validation-rules", "title": "UK EMIR Validation Rules"},
             {"item_id": "uk-sftr-validation-rules", "title": "UK SFTR validation rules"},
             {"item_id": "rts-22-2017-590", "title": "Commission Delegated Regulation (EU) 2017/590 (RTS 22)"},
             {"item_id": "fsma-2000", "title": "FSMA 2000"}]
    return fields.FieldComparer(tmp_path, program_id="p", scope="Harmonize reporting", manifest_hash="sha256:m",
                                items=items, call_fn=fake_call)


def test_workbook_registers_read_by_code_after_one_mapping_call_per_sheet(tmp_path):
    fc = _program(tmp_path)
    assert fc.default_selection() == {"uk-emir-validation-rules": "EMIR", "uk-sftr-validation-rules": "SFTR"}
    cands = {c["item_id"]: c for c in fc.candidates()}
    assert cands["rts-22-2017-590"]["kind"] == "text" and cands["rts-22-2017-590"]["suggested_regime"] == "MiFIR"
    fc.set_sources(fc.default_selection())
    r = fc.build(limit=5)
    assert r["per_regime"] == {"EMIR": 4, "SFTR": 4}
    st = fc.state()
    e = [f for f in st["fields"].values() if f["regime"] == "EMIR"]
    # the same field on two sheets is one field: validation-sheet row cited, details sheet fills in
    cp = next(f for f in e if f["number"] == "4")
    assert cp["sheet"] == "Trade validations" and cp["row"] == 4
    assert cp["definition"].startswith("Identifier of the counterparty") and cp["format"] == "ISO 17442 LEI"
    assert cp["also"] == [{"sheet": "Details", "row": 3}]
    assert cp["flags"] == {"Trade level / NEWT": "M", "Trade level / MODI": "M"}
    assert all(f["verified"] for f in st["fields"].values())            # every quote is the text line of its row
    s = next(f for f in st["fields"].values() if f["regime"] == "SFTR" and f["number"] == "3")
    assert s["section"] == "Counterparty data" and s["quote"].startswith("Row 5:")
    assert st["sources"]["uk-emir-validation-rules"]["sheets"][0]["is_field_sheet"] is False


def test_text_register_keeps_only_verified_fields(tmp_path):
    fc = _program(tmp_path)
    fc.set_sources({"rts-22-2017-590": "MiFIR"})
    fc.build(limit=5)
    st = fc.state()
    names = sorted(f["name"] for f in st["fields"].values())
    assert names == ["Buyer identification code", "Report status"]
    assert st["sources"]["rts-22-2017-590"]["dropped_unverified"] == 1
    with pytest.raises(fields.FieldError):
        fc.set_sources({"nope": "X"})
    with pytest.raises(fields.FieldError):
        fc.set_sources({"rts-22-2017-590": "bad/regime"})


def test_comparison_builds_unified_rows_and_defect_findings(tmp_path):
    fc = _program(tmp_path)
    fc.set_sources({"uk-emir-validation-rules": "EMIR", "uk-sftr-validation-rules": "SFTR", "rts-22-2017-590": "MiFIR"})
    with pytest.raises(fields.FieldError):
        fc.compare()                                   # registers not built yet
    fc.build(limit=5)
    r = fc.compare(limit=1)
    assert r["compare"]["batches_done"] == 1 and r["summary"] is None
    r = fc.compare(limit=10)
    assert r["compare"]["batches_done"] == r["compare"]["batches_total"] == 3
    s = r["summary"]
    assert s["fields"] == 10 and s["cross_regime_rows"] == 4 and s["rows"] == 6
    assert s["by_relation"] == {"identical": 3, "definition_difference": 1, "single_regime": 2}
    st = fc.state()
    ts = next(row for row in st["rows"] if row["name"] == "Reporting timestamp")
    assert ts["regimes"] == ["EMIR", "SFTR"] and ts["relation"] == "identical"
    nat = next(row for row in st["rows"] if row["name"].startswith("Nature"))
    assert nat["aspects"] == ["definition_difference", "format_difference"]     # worst first

    reg = json.loads((tmp_path / "governed/registers/defects.json").read_text())
    fs = reg["runs"]["defects-fields"]["findings"]
    assert len(fs) == 4
    by = {f["field_row"]: f for f in fs}
    nat = next(f for f in fs if f["relation"] == "definition_difference")
    assert nat["code"] == "D2" and nat["firm_impact"] == "changes_obligations"
    assert "WOULD change" in nat["description"]
    uti = next(f for f in fs if f["title"].startswith("UTI"))
    assert uti["code"] == "D3" and uti["firm_impact"] == "no_change"
    assert all(loc["verified"] for f in fs for loc in f["locations"])
    assert len(by) == 4

    # other defect runs are kept, and the Refactor lock holds once field findings are worked
    reg["runs"]["defects-cross"] = {"findings": []}
    (tmp_path / "governed/registers/defects.json").write_text(json.dumps(reg))
    (tmp_path / "governed/registers/operations.json").write_text(json.dumps(
        {"findings_processed": {"defects-fields#0": {"status": "processed"}}}))
    with pytest.raises(fields.FieldError):
        fc.set_sources({"rts-22-2017-590": None})


def test_register_workbook_round_trips(tmp_path):
    fc = _program(tmp_path)
    fc.set_sources({"uk-emir-validation-rules": "EMIR", "uk-sftr-validation-rules": "SFTR"})
    fc.build(limit=5)
    fc.compare(limit=10)
    data = fields.register_xlsx(fc.state(), "p", banner="EXPLORATION — test")
    sheets = {s["name"]: s["rows"] for s in acquire.xlsx_sheets(data)}
    assert list(sheets) == ["Read me", "Unified rows", "Relationships", "EMIR fields", "SFTR fields"]
    assert sheets["Unified rows"][0][:4] == ["Row", "Data point", "Regimes", "Relation"]
    assert any("EXPLORATION" in " ".join(r) for r in sheets["Read me"])
    assert len(sheets["EMIR fields"]) == 5 and sheets["EMIR fields"][1][0] == "EMIR-001"


# ---------------------------------------------------------------- through the API

def _transport():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        out = fake_model(payload["messages"][-1]["content"])
        return httpx.Response(200, json=make_response(model=payload["model"], content=json.dumps(out)))
    return httpx.MockTransport(handler)


def test_field_endpoints(approot):  # noqa: F811
    c = TestClient(create_app(root=approot, transport=_transport(), api_key="test-key"))
    _ratified_program(c, approot, "fx")
    for iid, title in (("uk-emir-validation-rules", "UK EMIR Validation Rules"),
                       ("uk-sftr-validation-rules", "UK SFTR validation rules")):
        c.post("/api/programs/fx/manifest/items", json={"item_id": iid, "title": title, "issuer": "FCA",
                                                         "family": "reporting_instruction", "locator": title})
    assert c.get("/api/programs/fx/fields").status_code == 409          # corpus not frozen
    c.post("/api/programs/fx/policy/ratify", json={"name": "O", "role": "Program Owner", "rationale": "ok"})
    c.post("/api/programs/fx/manifest/freeze", json={"name": "O", "role": "Program Owner", "rationale": "ok"})
    ct = approot / "programs/fx/governed/corpus_texts"
    ct.mkdir(parents=True, exist_ok=True)
    for iid, data in (("uk-emir-validation-rules", EMIR), ("uk-sftr-validation-rules", SFTR)):
        (ct / f"{iid}.xlsx").write_bytes(data)
        (ct / f"{iid}.txt").write_text(acquire.xlsx_to_text(data))

    st = c.get("/api/programs/fx/fields").json()
    assert st["default_selection"] == {"uk-emir-validation-rules": "EMIR", "uk-sftr-validation-rules": "SFTR"}
    assert "estimate" in st
    r = c.post("/api/programs/fx/fields/sources", json={"sources": st["default_selection"]})
    assert r.status_code == 200 and len(r.json()["selected"]) == 2
    assert c.post("/api/programs/fx/fields/compare", json={}).status_code == 409
    r = c.post("/api/programs/fx/fields/build", json={"limit": 5}).json()
    assert r["per_regime"] == {"EMIR": 4, "SFTR": 4}
    r = c.post("/api/programs/fx/fields/compare", json={"limit": 10}).json()
    assert r["summary"]["cross_regime_rows"] == 4 and r["defects_written_at"]
    stamps = [json.loads(l) for l in (approot / "runs/stamps.jsonl").read_text().splitlines() if l.strip()]
    assert {"field_map", "field_match"} <= {s["task_id"] for s in stamps}
    x = c.get("/api/programs/fx/fields/register.xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    docx = c.get("/api/programs/fx/blueprint/defects/register.docx")
    assert docx.status_code == 200
    body = zipfile.ZipFile(io.BytesIO(docx.content)).read("word/document.xml").decode()
    assert "Field-level comparison" in body
