"""A small .xlsx writer (standard library only), for downloads such as the Field
Register. Text cells are inline strings; the first row of each sheet is a bold,
frozen, filterable heading row; columns get sensible widths."""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

_CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
       '<Default Extension="xml" ContentType="application/xml"/>'
       '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
       '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
       '{sheets}</Types>')
_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<fonts count="2"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/></font></fonts>'
           '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
           '<fill><patternFill patternType="solid"><fgColor rgb="FFE4EFED"/><bgColor indexed="64"/></patternFill></fill></fills>'
           '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
           '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
           '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
           '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
           '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
           '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
           '</styleSheet>')


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _clean(v) -> str:
    s = "" if v is None else str(v)
    # XML 1.0 forbids most control characters
    return "".join(ch for ch in s if ch in "\t\n\r" or ord(ch) >= 32)[:32000]


def _sheet_xml(rows: list[list], widths: list[int] | None) -> str:
    ncol = max((len(r) for r in rows), default=1)
    if not widths:
        widths = []
        for c in range(ncol):
            longest = max((len(_clean(r[c])) for r in rows[:200] if c < len(r)), default=8)
            widths.append(max(8, min(60, longest + 2)))
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    out = []
    for r_i, row in enumerate(rows, start=1):
        cells = []
        for c_i, v in enumerate(row):
            if v is None or v == "":
                continue
            ref = f"{_col(c_i)}{r_i}"
            style = 1 if r_i == 1 else 0
            if isinstance(v, bool):
                cells.append(f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{"yes" if v else "no"}</t></is></c>')
            elif isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}" s="{style}"><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(_clean(v))}</t></is></c>')
        out.append(f'<row r="{r_i}">' + "".join(cells) + "</row>")
    last = f"{_col(ncol - 1)}{max(1, len(rows))}"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>' + "".join(out) + '</sheetData>'
            + (f'<autoFilter ref="A1:{last}"/>' if len(rows) > 1 else "") + '</worksheet>')


def write_workbook(sheets: list[tuple[str, list[list], list[int] | None]]) -> bytes:
    """sheets: [(name, rows, column widths or None)]; rows[0] is the heading row."""
    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    names = []
    for name, _, _ in sheets:
        n = "".join(ch for ch in name if ch not in "[]:*?/\\")[:31] or "Sheet"
        while n in names:
            n = n[:28] + f"_{len(names)}"
        names.append(n)
    z.writestr("[Content_Types].xml", _CT.format(sheets="".join(
        f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(len(sheets)))))
    z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
               '</Relationships>')
    z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
               + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names))
               + '</sheets>'
               + '</workbook>')
    z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                         for i in range(len(sheets)))
               + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
               '</Relationships>')
    z.writestr("xl/styles.xml", _STYLES)
    for i, (_, rows, widths) in enumerate(sheets):
        z.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet_xml(rows, widths))
    z.close()
    return buf.getvalue()
