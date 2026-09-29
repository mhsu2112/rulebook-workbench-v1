"""Spreadsheet sources: regulators publish field-level reporting rules as .xlsx
workbooks. The fetcher and the upload path both read them (standard library
only), rendering each row with its column headings so a citation can quote it."""
import io
import json
import zipfile

import httpx

from workbench.acquire import (Acquirer, extract_text, extract_upload, xlsx_sheets,
                               xlsx_to_text, zip_kind)

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def make_xlsx(sheets: dict[str, list[list]], *, date_cells=()) -> bytes:
    """A minimal but valid workbook. Strings go to sharedStrings (like Excel);
    numbers stay numeric; cells listed in date_cells get a date style."""
    shared: list[str] = []

    def sidx(s):
        if s not in shared:
            shared.append(s)
        return shared.index(s)

    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w")
    names = list(sheets)
    z.writestr("[Content_Types].xml", "<Types/>")
    z.writestr("xl/workbook.xml", f'<workbook {NS} {RNS}><sheets>' + "".join(
        f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names)) + "</sheets></workbook>")
    z.writestr("xl/_rels/workbook.xml.rels",
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
                   f'<Relationship Id="rId{i + 1}" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(names)))
               + "</Relationships>")
    z.writestr("xl/styles.xml", f'<styleSheet {NS}><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
    for i, n in enumerate(names):
        rows = []
        for r, row in enumerate(sheets[n], start=1):
            cells = []
            for c, v in enumerate(row):
                if v is None or v == "":
                    continue
                ref = f"{chr(65 + c)}{r}"
                if isinstance(v, (int, float)):
                    style = ' s="1"' if (n, ref) in date_cells else ""
                    cells.append(f'<c r="{ref}"{style}><v>{v}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="s"><v>{sidx(v)}</v></c>')
            rows.append(f'<row r="{r}">' + "".join(cells) + "</row>")
        z.writestr(f"xl/worksheets/sheet{i + 1}.xml", f'<worksheet {NS}><sheetData>' + "".join(rows) + "</sheetData></worksheet>")
    z.writestr("xl/sharedStrings.xml", f'<sst {NS}>' + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")
    z.close()
    return buf.getvalue()


RULES = make_xlsx({
    "Overview": [["Validation rules for UK EMIR reporting"], ["Updated", 45762]],
    "Trade validations": [
        ["", "", "", "Trade level", "", "Position level", ""],
        ["Table", "Item", "Field", "NEWT", "MODI", "NEWT", "MODI"],
        [1, 1, "Reporting timestamp", "M", "M", "M", "C"],
        [1, 2, "Report submitting entity ID", "M", "O", "M", "M"],
    ],
}, date_cells={("Overview", "B2")})


def test_zip_kind_tells_workbooks_from_word_files():
    assert zip_kind(RULES) == "xlsx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w/>")
    assert zip_kind(buf.getvalue()) == "docx"
    assert zip_kind(b"%PDF-1.7") is None


def test_sheets_read_in_order_with_values():
    sheets = xlsx_sheets(RULES)
    assert [s["name"] for s in sheets] == ["Overview", "Trade validations"]
    tv = sheets[1]["rows"]
    assert tv[2][:3] == ["1", "1", "Reporting timestamp"]
    assert sheets[0]["rows"][1] == ["Updated", "2025-04-15"]       # date-styled serial → ISO date


def test_rows_carry_their_headings_and_row_numbers():
    t = xlsx_to_text(RULES)
    assert "=== Sheet: Trade validations ===" in t
    # repeated sub-headings are told apart by the merged group row above them
    assert "Columns: Table | Item | Field | Trade level · NEWT | Trade level · MODI | Position level · NEWT" in t
    assert "Row 3: Table: 1 | Item: 1 | Field: Reporting timestamp | Trade level · NEWT: M" in t
    assert "Position level · MODI: C" in t
    assert "Row 4: Table: 1 | Item: 2 | Field: Report submitting entity ID" in t


def test_fetcher_routes_a_workbook_by_its_contents(tmp_path):
    ct, raw = extract_text("application/octet-stream", "https://x/rules", RULES)
    assert raw == "xlsx" and "Reporting timestamp" in ct

    def handler(request):
        return httpx.Response(200, content=RULES, headers={
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
    acq = Acquirer(tmp_path, snapshot_date="2026-07-18", manifest_hash="sha256:x",
                   transport=httpx.MockTransport(handler))
    item = {"item_id": "uk-emir-validation-rules", "family": "guidance",
            "url": "https://www.fca.org.uk/publication/fca/uk-emir-validation-rules-2026.xlsx"}
    r = acq.acquire([item], limit=5)
    rec = r["items"]["uk-emir-validation-rules"]
    assert rec["status"] == "fetched" and rec["raw_ext"] == "xlsx"
    d = tmp_path / "governed" / "corpus_texts"
    assert (d / "uk-emir-validation-rules.xlsx").read_bytes() == RULES
    assert "Report submitting entity ID" in (d / "uk-emir-validation-rules.txt").read_text()


def test_legacy_xls_is_a_clear_error(tmp_path):
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600

    def handler(request):
        return httpx.Response(200, content=ole, headers={"content-type": "application/vnd.ms-excel"})
    acq = Acquirer(tmp_path, snapshot_date="2026-07-18", manifest_hash="sha256:x",
                   transport=httpx.MockTransport(handler))
    r = acq.acquire([{"item_id": "old", "family": "guidance", "url": "https://x/old.xls"}], limit=5)
    assert r["items"]["old"]["status"] == "error"
    assert "legacy Office file" in json.dumps(r["items"]["old"]["errors"])


def test_upload_accepts_a_workbook_whatever_its_name():
    text, ext = extract_upload("SFTR reporting fields.xlsx", RULES)
    assert ext == "xlsx" and "Trade level · NEWT: M" in text
    text2, ext2 = extract_upload("download", RULES)       # no extension: sniffed
    assert ext2 == "xlsx"
