"""Field-level comparison (Distill, release 3): per-regime field registers and a
cross-regime comparison of what each regime makes firms report.

Design agreed 25 September 2026 (field-register step):

1. Field registers. Workbooks (.xlsx) published by the regulators are read
   directly. One small model call per sheet says which columns hold the field
   number, name, definition, format and validation rules, and which hold the
   mandatory/conditional/optional flags; the rows are then read by code, so every
   field in the register is exactly what the workbook says. Sources without a
   workbook (e.g. the MiFIR RTS 22 field table) are read by the model, and a
   field is kept only if its quote is found verbatim in the source.
2. Comparison. For each pair of regimes, likely counterparts are found by the
   words of their names and definitions; the model then decides which really
   record the same data point and how they differ: identical, format, definition,
   validation or applicability. For each difference it also drafts whether
   harmonizing it would change what firms must report.
3. The matches are joined into unified rows. Every row that spans two or more
   regimes becomes a cited finding in the Defect Register (run "defects-fields"),
   so it is worked in Refactor like any other defect; the human effect
   classification there remains the decision (PRD NG2).

Every model call goes through the program's router (stamped, budgeted, pinned
models). Nothing here writes to the official record except the defect run.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from workbench import acquire
from workbench.distill import _norm

RUN_ID = "defects-fields"
BATCH = 20               # fields of one regime per comparison call
CANDIDATES = 8           # counterpart candidates offered per field
TEXT_CHUNK = 120_000     # chars per field_extract call
MAP_ROWS = 28            # rows shown to the model to map a sheet

ASPECTS = ["identical", "format_difference", "definition_difference",
           "validation_conflict", "applicability_difference"]
ASPECT_LABEL = {"identical": "identical", "format_difference": "format differs",
                "definition_difference": "definition differs", "validation_conflict": "validation conflicts",
                "applicability_difference": "applicability differs"}
# worst first; the row takes the code of its worst aspect
SEVERITY = ["validation_conflict", "definition_difference", "format_difference",
            "applicability_difference", "identical"]
CODE = {"validation_conflict": "D1", "definition_difference": "D2", "format_difference": "D2",
        "applicability_difference": "D10", "identical": "D3"}

REGIME_HINTS = [("EMIR", r"\bemir\b|648/2012|148/2013|auth\.0?30|auth\.108"),
                ("SFTR", r"\bsftr\b|2015/2365|2019/356|securities financing"),
                ("MiFIR", r"\bmifir\b|600/2014|2017/590|rts ?22|transaction report")]

STOP = set("the a an of to in for and or on by with is be as at this that which any its it from "
           "where when shall field fields reported report reporting code value".split())

MAP_PROMPT = """You are mapping one worksheet of a regulator's reporting-rules workbook so that
code can read its fields. Program: {program_id}. Regime: {regime}.

Below are the sheet's first rows and a few later rows. Cells are given as
COLUMN=value (spreadsheet column letters; empty cells omitted; long values cut).

Return JSON:
- is_field_sheet: true only if the sheet lists reporting fields one per row
  (a change log, overview or reconciliation-tolerance sheet is false).
- header_rows: the spreadsheet row numbers holding column headings (may be several,
  e.g. a group row "Trade level" over "NEWT (New)"); [] if none.
- first_data_row: the spreadsheet row number of the first field row.
- columns: the LETTER of the column holding each item, or null if absent:
  number (field/item number), name (field name), definition (details to be reported /
  description), format (format and permitted values), validation (validation rules),
  table (table number), section (section name).
- mandatory_columns: letters of every column holding M/C/O/-/N flags per action type
  or level; [] if none.
- note: one short sentence on anything unusual.

SHEET: {sheet}
{rows}"""

EXTRACT_PROMPT = """You are building a field register for {regime} from a legal text, for program
{program_id}. List EVERY reporting field in the text's field tables (for example
"Table 2 — Details to be reported"), in order. Do not invent fields and do not
list fields that are only mentioned in passing.

For each field return: number (as written, e.g. "7"), name, definition (the
text's own description, verbatim or trimmed, at most 400 characters), format
(format and standards, at most 200 characters, or null), and quote: a VERBATIM
span of at most 300 characters copied exactly from the text that contains the
field's name. Quotes are machine-checked; a field whose quote is not found is
dropped. If this part of the text holds no field table, return an empty list.

Return JSON: {{"fields": [...]}}

===== TEXT ({part}) =====
{text}"""

MATCH_PROMPT = """You are comparing reporting fields across regimes for program {program_id}.

RATIFIED SCOPE: {scope}

Below are {n} {a} fields. Under each are candidate {b} fields found by shared
words. For each {a} field, decide which candidates (if any) record the SAME data
point about the same transaction or party. Candidates that are merely related
(a different data point on the same topic) are NOT matches. A field may match
more than one candidate, or none.

For each match give:
- a, b: the field ids.
- aspects: one or more of identical (same meaning, format and rules),
  format_difference (same meaning, different format, code list or precision),
  definition_difference (materially different definition or population),
  validation_conflict (validation rules that cannot both be satisfied by one value,
  or require contradictory content), applicability_difference (mandatory in one
  regime, conditional/optional in the other, for the comparable action types).
  "identical" is never combined with another aspect.
- detail: one or two sentences, precise about what differs (quote the rule if short).
- changes_obligations: true if harmonizing the two would change what some firm
  must report (a value, a format it must use, or whether it must report the
  field); false if it would only remove duplication or align presentation.
  This is a DRAFT for a human reviewer, not a decision.
- impact_reason: one sentence.

Return JSON: {{"matches": [...]}}. Fields with no counterpart are simply left out.

===== FIELDS =====
{fields}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except ValueError:
        return default


def guess_regime(item: dict) -> Optional[str]:
    hay = " ".join(str(item.get(k) or "") for k in ("item_id", "title", "locator", "url")).lower()
    for name, pat in REGIME_HINTS:
        if re.search(pat, hay):
            return name
    return None


def _col(letter: Optional[str]) -> Optional[int]:
    if not letter or not isinstance(letter, str) or not re.fullmatch(r"[A-Za-z]{1,3}", letter.strip()):
        return None
    return acquire._col_index(letter.strip().upper())


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP and len(w) > 1}


def _acronyms(name: str) -> set[str]:
    """'Unique Transaction Identifier (UTI)' -> {'uti'}; 'UTI' -> {'uti'}."""
    out = {m.lower() for m in re.findall(r"\b[A-Z]{2,6}\b", name or "")}
    words = re.findall(r"[A-Za-z]+", re.sub(r"\(.*?\)", " ", name or ""))
    if 2 <= len(words) <= 6:
        out.add("".join(w[0] for w in words).lower())
    return out


def _sim(a: dict, b: dict) -> float:
    na, nb = _tokens(a.get("name", "")), _tokens(b.get("name", ""))
    acr = 0.5 if _acronyms(a.get("name", "")) & _acronyms(b.get("name", "")) else 0.0
    da, db = _tokens((a.get("definition") or "")[:300]), _tokens((b.get("definition") or "")[:300])
    j = lambda x, y: (len(x & y) / len(x | y)) if (x or y) else 0.0
    exact = 1.0 if _norm(a.get("name", "")) == _norm(b.get("name", "")) else 0.0
    return 0.55 * j(na, nb) + 0.3 * j(da, db) + 0.15 * j(na, db | nb) + exact + acr


class FieldError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class FieldComparer:
    """Builds field registers and compares them. `call_fn(task, messages)` is the
    server's stamped, budgeted router call; this class adds no model access."""

    def __init__(self, program_dir: str | Path, *, program_id: str, scope: str, manifest_hash: str,
                 items: list[dict], call_fn: Callable):
        self.pdir = Path(program_dir)
        self.g = self.pdir / "governed"
        self.program_id, self.scope, self.manifest_hash = program_id, scope, manifest_hash
        self.items = {i["item_id"]: i for i in items}
        self.call = call_fn
        self.path = self.g / "registers" / "fields.json"

    # ---------------------------------------------------------------- state

    def state(self) -> dict:
        st = _load(self.path)
        if not st or st.get("manifest_hash") != self.manifest_hash:
            st = {"manifest_hash": self.manifest_hash, "sources": {}, "fields": {}, "pairs": {},
                  "rows": [], "summary": None, "created_at": _now()}
        return st

    def _save(self, st: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(st, indent=2))

    def _raw_xlsx(self, iid: str) -> Optional[bytes]:
        d = self.g / "corpus_texts"
        for p in (d / f"{iid}.xlsx", d / "uploads" / f"{iid}.xlsx"):
            if p.exists():
                return p.read_bytes()
        return None

    def _text(self, iid: str) -> str:
        p = self.g / "corpus_texts" / f"{iid}.txt"
        return p.read_text() if p.exists() else ""

    # ---------------------------------------------------------------- sources

    def candidates(self) -> list[dict]:
        """Every current source, with what the field step would do with it."""
        st = self.state()
        out = []
        for iid, it in self.items.items():
            has_text = bool(self._text(iid))
            kind = "workbook" if self._raw_xlsx(iid) else ("text" if has_text else None)
            sel = st["sources"].get(iid)
            out.append({"item_id": iid, "title": it.get("title", ""), "family": it.get("family"),
                        "kind": kind, "suggested_regime": guess_regime(it),
                        "chars": len(self._text(iid)) if has_text else 0,
                        "selected": bool(sel), "regime": (sel or {}).get("regime"),
                        "status": (sel or {}).get("status"), "fields": (sel or {}).get("fields"),
                        "errors": (sel or {}).get("errors")})
        return out

    def default_selection(self) -> dict:
        return {c["item_id"]: c["suggested_regime"] for c in self.candidates()
                if c["kind"] == "workbook" and c["suggested_regime"]}

    def set_sources(self, selection: dict) -> dict:
        """selection: {item_id: regime or null}. Changing the set of sources or a
        regime clears the comparison (it no longer describes these registers)."""
        st = self.state()
        if self._refactor_started():
            raise FieldError(409, "Refactor has already worked field-level findings; the field sources can no "
                                  "longer change in this program")
        changed = False
        for iid, regime in selection.items():
            if iid not in self.items:
                raise FieldError(404, f"No source '{iid}' in the corpus")
            regime = (regime or "").strip() or None
            cur = st["sources"].get(iid)
            if regime is None:
                if cur:
                    st["sources"].pop(iid)
                    changed = True
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._-]{0,23}", regime):
                raise FieldError(400, f"'{regime}' is not a usable regime name (letters, digits, spaces; up to 24)")
            kind = "workbook" if self._raw_xlsx(iid) else "text"
            if kind == "text" and not self._text(iid):
                raise FieldError(409, f"'{iid}' has no captured text yet — capture it on the Corpus step first")
            if not cur or cur.get("regime") != regime:
                st["sources"][iid] = {"regime": regime, "kind": kind, "status": "pending"}
                changed = True
        if changed:
            keep = set(st["sources"])
            st["fields"] = {k: v for k, v in st["fields"].items() if v["item_id"] in keep
                            and st["sources"][v["item_id"]]["status"] == "built"
                            and st["sources"][v["item_id"]]["regime"] == v["regime"]}
            for iid, s in st["sources"].items():
                if s["status"] == "built" and not any(f["item_id"] == iid for f in st["fields"].values()):
                    s["status"] = "pending"
            self._reset_comparison(st)
        self._save(st)
        return st

    def _reset_comparison(self, st: dict) -> None:
        st["pairs"], st["rows"], st["summary"] = {}, [], None
        st.pop("defects_written_at", None)

    # ---------------------------------------------------------------- build registers

    def build(self, *, limit: int = 4, retry_errors: bool = False) -> dict:
        st = self.state()
        if not st["sources"]:
            raise FieldError(409, "Choose the field sources first")
        done = 0
        for iid, src in sorted(st["sources"].items()):
            if src["status"] == "built" or (src["status"] == "error" and not retry_errors):
                continue
            if done >= limit:
                break
            done += 1
            try:
                fields, cost, meta = (self._build_workbook(iid, src) if src["kind"] == "workbook"
                                      else self._build_text(iid, src))
                for f in list(st["fields"]):
                    if st["fields"][f]["item_id"] == iid:
                        st["fields"].pop(f)
                if not fields:
                    raise FieldError(422, "no reporting fields were found in this source")
                self._number(st, fields, src["regime"])
                src.update({"status": "built", "fields": len(fields), "cost_usd": round(cost, 6),
                            "built_at": _now(), "errors": None, **meta})
            except Exception as e:  # noqa: BLE001 — per-source resilience
                src.update({"status": "error", "errors": [f"{type(e).__name__}: {getattr(e, 'detail', str(e))[:600]}"]})
            self._reset_comparison(st)
            self._save(st)
        return self.status(st)

    def _number(self, st: dict, fields: list[dict], regime: str) -> None:
        tag = re.sub(r"[^A-Za-z0-9]", "", regime).upper()[:8] or "X"
        taken = {int(k.rsplit("-", 1)[1]) for k in st["fields"] if k.rsplit("-", 1)[0] == tag}
        n = max(taken, default=0)
        for f in fields:
            n += 1
            fid = f"{tag}-{n:03d}"
            st["fields"][fid] = {"field_id": fid, "regime": regime, **f}

    def _build_workbook(self, iid: str, src: dict) -> tuple[list[dict], float, dict]:
        data = self._raw_xlsx(iid)
        text = self._text(iid)
        sheets = acquire.xlsx_sheets(data)
        fields, cost, maps = [], 0.0, []
        for sh in sheets:
            rows = sh["rows"]
            if not any(rows) or sh["hidden"]:
                continue
            shown = self._rows_for_map(rows)
            out, stamp = self.call("field_map", [{"role": "user", "content": MAP_PROMPT.format(
                program_id=self.program_id, regime=src["regime"], sheet=sh["name"], rows=shown)}])
            cost += stamp["cost"]["usd"]
            m = {"sheet": sh["name"], "is_field_sheet": bool(out.get("is_field_sheet")),
                 "columns": out.get("columns") or {}, "mandatory_columns": out.get("mandatory_columns") or [],
                 "header_rows": out.get("header_rows") or [], "first_data_row": out.get("first_data_row"),
                 "note": out.get("note")}
            maps.append(m)
            if m["is_field_sheet"]:
                fields += self._read_sheet(iid, sh, m, text)
        return self._merge(fields), cost, {"sheets": maps}

    @staticmethod
    def _merge(fields: list[dict]) -> list[dict]:
        """One workbook can list the same field on several sheets (e.g. validation
        rules on one, details and format on another). Fields with the same table,
        number and name are one field: the first row is its citation, the others
        fill in what it lacks and are kept as further rows."""
        out, seen = [], {}
        for f in fields:
            key = (f.get("table") or "", f.get("number") or "", _norm(f["name"])) if f.get("number") else None
            if key is None or key not in seen:
                if key is not None:
                    seen[key] = f
                out.append(f)
                continue
            base = seen[key]
            for k in ("definition", "format", "validation", "section"):
                if not base.get(k) and f.get(k):
                    base[k] = f[k]
            if not base.get("flags") and f.get("flags"):
                base["flags"] = f["flags"]
            base.setdefault("also", []).append({"sheet": f["sheet"], "row": f["row"]})
        return out

    @staticmethod
    def _rows_for_map(rows: list[list[str]]) -> str:
        picks = list(range(min(MAP_ROWS, len(rows))))
        for extra in (len(rows) // 2, len(rows) - 1):
            if extra >= MAP_ROWS and extra not in picks:
                picks.append(extra)
        lines = []
        for i in picks:
            cells = [f"{acquire._xl_col(k)}={x[:90]}" for k, x in enumerate(rows[i]) if x]
            if cells:
                lines.append(f"Row {i + 1}: " + " ; ".join(cells))
        return "\n".join(lines)

    def _read_sheet(self, iid: str, sh: dict, m: dict, text: str) -> list[dict]:
        rows = sh["rows"]
        cols = {k: _col(v) for k, v in (m["columns"] or {}).items()}
        name_c = cols.get("name")
        if name_c is None:
            return []
        first = m["first_data_row"]
        first = int(first) if isinstance(first, (int, float)) or (isinstance(first, str) and first.isdigit()) else 1
        # flag-column labels: header rows above, merged (group) cells carried rightwards
        mand = [c for c in (_col(x) for x in m["mandatory_columns"]) if c is not None]
        labels = {c: [] for c in mand}
        for hr in sorted(int(x) for x in m["header_rows"] if str(x).isdigit()):
            if not 1 <= hr <= len(rows):
                continue
            cur = ""
            row = rows[hr - 1]
            for k in range(max(mand, default=-1) + 1):
                v = re.sub(r"\s+", " ", row[k]).strip() if k < len(row) else ""
                if len(v) > 40:          # an instruction sentence above the codes, not a label
                    v = ""
                cur = v or cur
                if k in labels and cur:
                    labels[k].append(cur)
        h, heads = acquire.sheet_headings(rows)       # to rebuild the cited text line exactly
        hay = _norm(text)
        cell = lambda row, c: (row[c].strip() if c is not None and c < len(row) else "")
        out, section = [], None
        for n in range(max(first, 1) - 1, 0, -1):     # a section heading just above the first field
            filled = [x for x in rows[n - 1] if x]
            if len(filled) == 1 and len(filled[0]) <= 120:
                section = filled[0]
                break
            if len(filled) > 1:
                break
        for n in range(max(first, 1), len(rows) + 1):
            row = rows[n - 1]
            filled = [x for x in row if x]
            if not filled:
                continue
            name = cell(row, name_c)
            if len(filled) == 1 and not name:
                section = filled[0][:120]              # a heading row inside the table
                continue
            if not name or len(name) > 200:
                continue
            number = cell(row, cols.get("number"))
            if cols.get("number") is not None and not number:
                if len(filled) <= 2:
                    section = name[:120]
                continue
            flags = {" / ".join(labels.get(c) or [acquire._xl_col(c)]): cell(row, c) for c in mand if cell(row, c)}
            line = acquire.row_line(n, row, heads) if n > h + 1 else ""
            quote = line[:350]
            out.append({
                "item_id": iid, "sheet": sh["name"], "row": n,
                "table": cell(row, cols.get("table")) or None, "number": number or None,
                "section": cell(row, cols.get("section")) or section,
                "name": name, "definition": cell(row, cols.get("definition"))[:1500] or None,
                "format": cell(row, cols.get("format"))[:600] or None,
                "validation": cell(row, cols.get("validation"))[:1500] or None,
                "flags": flags, "quote": quote,
                "verified": bool(quote) and _norm(quote) in hay})
        return out

    def _build_text(self, iid: str, src: dict) -> tuple[list[dict], float, dict]:
        text = self._text(iid)
        hay = _norm(text)
        fields, cost, dropped = [], 0.0, 0
        parts = [text[i:i + TEXT_CHUNK] for i in range(0, len(text), TEXT_CHUNK)] or [""]
        for k, part in enumerate(parts):
            out, stamp = self.call("field_extract", [{"role": "user", "content": EXTRACT_PROMPT.format(
                regime=src["regime"], program_id=self.program_id, part=f"part {k + 1} of {len(parts)}", text=part)}])
            cost += stamp["cost"]["usd"]
            for f in out.get("fields") or []:
                q = (f.get("quote") or "").strip()
                if not q or _norm(q) not in hay or not (f.get("name") or "").strip():
                    dropped += 1
                    continue
                fields.append({"item_id": iid, "sheet": None, "row": None, "table": None,
                               "number": (str(f.get("number")) if f.get("number") is not None else None),
                               "section": None, "name": f["name"].strip()[:200],
                               "definition": (f.get("definition") or "")[:1500] or None,
                               "format": (f.get("format") or "")[:600] or None, "validation": None,
                               "flags": {}, "quote": q[:350], "verified": True})
        return fields, cost, {"dropped_unverified": dropped}

    # ---------------------------------------------------------------- compare

    def regimes(self, st: dict) -> list[str]:
        regs = {}
        for f in st["fields"].values():
            regs[f["regime"]] = regs.get(f["regime"], 0) + 1
        return sorted(regs, key=lambda r: (-regs[r], r))

    def plan(self, st: dict) -> dict:
        """The comparison work: for each pair of regimes, batches of the larger
        regime's fields. Deterministic, so a paused comparison resumes exactly."""
        regs = self.regimes(st)
        out = {}
        for i in range(len(regs)):
            for j in range(i + 1, len(regs)):
                a, b = regs[i], regs[j]
                ids = sorted(k for k, f in st["fields"].items() if f["regime"] == a)
                out[f"{a}|{b}"] = [ids[k:k + BATCH] for k in range(0, len(ids), BATCH)]
        return out

    def _candidates_for(self, st: dict, fid: str, b: str) -> list[str]:
        f = st["fields"][fid]
        pool = [(k, _sim(f, g)) for k, g in st["fields"].items() if g["regime"] == b]
        pool.sort(key=lambda x: -x[1])
        return [k for k, s in pool[:CANDIDATES] if s > 0.05]

    @staticmethod
    def _brief(fid: str, f: dict) -> str:
        bits = [f"{fid} · {f['name']}"]
        if f.get("number"):
            bits.append(f"(item {f['number']}{', ' + f['section'] if f.get('section') else ''})")
        s = " ".join(bits)
        if f.get("definition"):
            s += f"\n    definition: {f['definition'][:380]}"
        if f.get("format"):
            s += f"\n    format: {f['format'][:200]}"
        if f.get("validation"):
            s += f"\n    validation: {f['validation'][:300]}"
        if f.get("flags"):
            vals = list(f["flags"].values())
            s += "\n    required: " + ", ".join(f"{v}×{vals.count(v)}" for v in sorted(set(vals)))
        return s

    def compare(self, *, limit: int = 3, retry_errors: bool = False) -> dict:
        st = self.state()
        pending_build = [i for i, s in st["sources"].items() if s["status"] != "built"]
        if pending_build:
            raise FieldError(409, "Build every selected field register first")
        if len(self.regimes(st)) < 2:
            raise FieldError(409, "The comparison needs field registers for at least two regimes")
        if self._refactor_started():
            raise FieldError(409, "Refactor has already worked field-level findings; the comparison is closed")
        plan = self.plan(st)
        done = 0
        for pair, batches in plan.items():
            a, b = pair.split("|")
            rec = st["pairs"].setdefault(pair, {"batches": {}})
            for k, ids in enumerate(batches):
                br = rec["batches"].get(str(k))
                if br and (br["status"] == "done" or (br["status"] == "error" and not retry_errors)):
                    continue
                if done >= limit:
                    break
                done += 1
                try:
                    rec["batches"][str(k)] = self._match_batch(st, a, b, ids)
                except Exception as e:  # noqa: BLE001
                    rec["batches"][str(k)] = {"status": "error",
                                              "errors": [f"{type(e).__name__}: {getattr(e, 'detail', str(e))[:600]}"]}
                self._save(st)
        if self._comparison_complete(st, plan):
            self._assemble(st)
            self._write_defects(st)
            self._save(st)
        return self.status(st)

    def _match_batch(self, st: dict, a: str, b: str, ids: list[str]) -> dict:
        blocks, allowed = [], {}
        for fid in ids:
            cands = self._candidates_for(st, fid, b)
            allowed[fid] = set(cands)
            blocks.append(self._brief(fid, st["fields"][fid]) + "\n  candidates:\n" + (
                "\n".join("    - " + self._brief(c, st["fields"][c]).replace("\n    ", "\n        ") for c in cands)
                or "    (none)"))
        out, stamp = self.call("field_match", [{"role": "user", "content": MATCH_PROMPT.format(
            program_id=self.program_id, scope=self.scope, n=len(ids), a=a, b=b,
            fields="\n\n".join(blocks))}])
        matches = []
        for m in out.get("matches") or []:
            fa, fb = m.get("a"), m.get("b")
            if fa not in allowed or fb not in st["fields"] or st["fields"][fb]["regime"] != b:
                continue
            aspects = [x for x in (m.get("aspects") or []) if x in ASPECTS] or ["definition_difference"]
            if "identical" in aspects and len(aspects) > 1:
                aspects = [x for x in aspects if x != "identical"]
            matches.append({"a": fa, "b": fb, "aspects": aspects, "detail": (m.get("detail") or "")[:1200],
                            "changes_obligations": bool(m.get("changes_obligations")),
                            "impact_reason": (m.get("impact_reason") or "")[:600],
                            "outside_candidates": fb not in allowed[fa]})
        return {"status": "done", "fields": ids, "matches": matches, "cost_usd": round(stamp["cost"]["usd"], 6),
                "at": _now()}

    def _comparison_complete(self, st: dict, plan: dict) -> bool:
        return bool(plan) and all(
            (st["pairs"].get(p) or {}).get("batches", {}).get(str(k), {}).get("status") == "done"
            for p, batches in plan.items() for k in range(len(batches)))

    # ---------------------------------------------------------------- assemble

    def _assemble(self, st: dict) -> None:
        matches = [m for rec in st["pairs"].values() for br in rec["batches"].values()
                   if br.get("status") == "done" for m in br["matches"]]
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for m in matches:
            parent[find(m["a"])] = find(m["b"])
        groups: dict[str, list[str]] = {}
        order = sorted(st["fields"], key=lambda k: (self.regimes(st).index(st["fields"][k]["regime"]), k))
        for fid in order:
            groups.setdefault(find(fid), []).append(fid)
        rows = []
        for members in sorted(groups.values(), key=lambda ms: order.index(ms[0])):
            ms = set(members)
            rel = [m for m in matches if m["a"] in ms and m["b"] in ms]
            aspects = {x for m in rel for x in m["aspects"]}
            worst = next((x for x in SEVERITY if x in aspects), None)
            regs = []
            for fid in members:
                r = st["fields"][fid]["regime"]
                if r not in regs:
                    regs.append(r)
            rows.append({"row_id": f"FR-{len(rows) + 1:03d}", "name": st["fields"][members[0]]["name"],
                         "members": members, "regimes": regs, "relation": worst if len(regs) > 1 else "single_regime",
                         "aspects": [x for x in SEVERITY if x in aspects],
                         "changes_obligations": any(m["changes_obligations"] for m in rel),
                         "matches": rel})
        st["rows"] = rows
        by = {}
        for r in rows:
            by[r["relation"]] = by.get(r["relation"], 0) + 1
        multi = [r for r in rows if len(r["regimes"]) > 1]
        st["summary"] = {"fields": len(st["fields"]), "rows": len(rows), "cross_regime_rows": len(multi),
                         "relationships": len(matches), "by_relation": by,
                         "hard_conflicts": sum(1 for r in multi if r["relation"] == "validation_conflict"),
                         "changes_obligations": sum(1 for r in multi if r["changes_obligations"] and r["relation"] != "identical"),
                         "no_change": sum(1 for r in multi if not r["changes_obligations"] or r["relation"] == "identical"),
                         "cost_usd": round(sum(br.get("cost_usd") or 0 for rec in st["pairs"].values()
                                               for br in rec["batches"].values()), 4),
                         "assembled_at": _now()}

    def findings(self, st: dict) -> list[dict]:
        out = []
        for r in st["rows"]:
            if len(r["regimes"]) < 2:
                continue
            rel = r["relation"]
            fs = [st["fields"][m] for m in r["members"]]
            names = "; ".join(f"{f['regime']} {('item ' + f['number'] + ' ') if f.get('number') else ''}“{f['name']}”" for f in fs)
            sent = lambda x: x.strip() + ("" if x.strip().endswith((".", "!", "?")) else ".")
            details = " ".join(sent(m["detail"]) for m in r["matches"] if m["detail"].strip())
            if rel == "identical":
                impact = ("Removing the duplication would not change what firms report: the regimes ask for the "
                          "same value in the same form.")
            else:
                reasons = " ".join(sent(m["impact_reason"]) for m in r["matches"] if m["impact_reason"].strip())
                impact = (("Draft view: harmonizing this WOULD change what some firms must report. " if r["changes_obligations"]
                           else "Draft view: harmonizing this would NOT change what firms must report. ") + reasons)
            title = f"{r['name']}: {ASPECT_LABEL.get(rel, rel)} across {', '.join(r['regimes'])}"
            out.append({
                "code": CODE.get(rel, "D2"), "title": title[:250],
                "description": (f"Field-level comparison, row {r['row_id']}. Fields: {names}. {details} {impact}").strip(),
                "locations": [{"item_id": f["item_id"], "quote": (f.get("quote") or "")[:800] or None,
                               "verified": bool(f.get("verified"))} for f in fs],
                "field_row": r["row_id"], "relation": rel,
                "firm_impact": "changes_obligations" if (r["changes_obligations"] and rel != "identical") else "no_change"})
        return out

    def _write_defects(self, st: dict) -> None:
        dpath = self.g / "registers" / "defects.json"
        reg = _load(dpath) or {"manifest_hash": self.manifest_hash, "runs": {}}
        reg.setdefault("runs", {})
        fs = self.findings(st)
        reg["runs"][RUN_ID] = {"detected_at": _now(),
                               "scope_label": "field level: " + ", ".join(self.regimes(st)),
                               "cost_usd": (st.get("summary") or {}).get("cost_usd", 0.0), "findings": fs}
        dpath.parent.mkdir(parents=True, exist_ok=True)
        dpath.write_text(json.dumps(reg, indent=2))
        st["defects_written_at"] = _now()

    def _refactor_started(self) -> bool:
        ops = _load(self.g / "registers" / "operations.json") or {}
        return any(str(k).startswith(RUN_ID + "#") for k in (ops.get("findings_processed") or {}))

    # ---------------------------------------------------------------- read

    def status(self, st: Optional[dict] = None) -> dict:
        st = st or self.state()
        plan = self.plan(st) if st["fields"] else {}
        total = sum(len(b) for b in plan.values())
        done = sum(1 for p, b in plan.items() for k in range(len(b))
                   if (st["pairs"].get(p) or {}).get("batches", {}).get(str(k), {}).get("status") == "done")
        errs = sum(1 for p, b in plan.items() for k in range(len(b))
                   if (st["pairs"].get(p) or {}).get("batches", {}).get(str(k), {}).get("status") == "error")
        per_regime = {}
        for f in st["fields"].values():
            per_regime[f["regime"]] = per_regime.get(f["regime"], 0) + 1
        return {"sources": self.candidates(), "selected": st["sources"], "per_regime": per_regime,
                "fields": len(st["fields"]),
                "compare": {"pairs": list(plan), "batches_total": total, "batches_done": done, "batches_error": errs},
                "summary": st.get("summary"), "defects_written_at": st.get("defects_written_at"),
                "refactor_started": self._refactor_started(),
                "rows_preview": [{k: r[k] for k in ("row_id", "name", "regimes", "relation", "changes_obligations")}
                                 | {"fields": [f"{st['fields'][m]['regime']}: {st['fields'][m]['name']}" for m in r["members"]]}
                                 for r in st["rows"] if len(r["regimes"]) > 1][:400]}

    def estimate_work(self, st: Optional[dict] = None) -> dict:
        """Rough size of the remaining model work, per task: (prompt chars,
        expected completion tokens). The server prices it from past calls."""
        st = st or self.state()
        est = {"field_map": [0, 0], "field_extract": [0, 0], "field_match": [0, 0]}
        for iid, s in st["sources"].items():
            if s["status"] == "built":
                continue
            if s["kind"] == "workbook":
                data = self._raw_xlsx(iid)
                n = sum(1 for sh in acquire.xlsx_sheets(data) if any(sh["rows"]) and not sh["hidden"]) if data else 0
                est["field_map"][0] += n * 9000
                est["field_map"][1] += n * 400
            else:
                chars = len(self._text(iid))
                est["field_extract"][0] += chars + 2000
                est["field_extract"][1] += max(1500, chars // 25)
        if st["fields"] and all(s["status"] == "built" for s in st["sources"].values()):
            plan = self.plan(st)
            for p, batches in plan.items():
                for k, ids in enumerate(batches):
                    if (st["pairs"].get(p) or {}).get("batches", {}).get(str(k), {}).get("status") == "done":
                        continue
                    est["field_match"][0] += len(ids) * (1 + CANDIDATES) * 700 + 3000
                    est["field_match"][1] += len(ids) * 180
        elif st["sources"]:
            # registers not built yet: size the comparison from typical field counts
            n = max(1, len(st["sources"]))
            guess = 150 * n
            est["field_match"][0] += (guess // BATCH + 1) * (BATCH * (1 + CANDIDATES) * 700 + 3000)
            est["field_match"][1] += guess * 180
        return est


# ---------------------------------------------------------------- export

def register_xlsx(st: dict, program_id: str, banner: Optional[str] = None) -> bytes:
    from workbench.xlsx_write import write_workbook
    regs = []
    for f in st["fields"].values():
        if f["regime"] not in regs:
            regs.append(f["regime"])
    regs.sort()
    fields = st["fields"]
    label = lambda fid: (f"{fid} · {('item ' + fields[fid]['number'] + ' · ') if fields[fid].get('number') else ''}"
                         f"{fields[fid]['name']}")
    s = st.get("summary") or {}
    readme = [["Field Register", program_id]]
    if banner:
        readme.append(["", banner])
    readme += [
        ["What this is", "Every reporting field of each regime, read from the regulators' own workbooks (or, where there is "
                         "none, from the legal text with machine-checked quotes), and how the regimes' fields line up."],
        ["Fields", s.get("fields", len(fields))],
        ["Unified rows", s.get("rows", "")], ["Rows spanning two or more regimes", s.get("cross_regime_rows", "")],
        ["Classified relationships", s.get("relationships", "")], ["Hard validation conflicts", s.get("hard_conflicts", "")],
        ["Draft: would change what firms report", s.get("changes_obligations", "")],
        ["How to read it", "‘Unified rows’ has one row per data point; the regime columns name the field that records it in each "
                           "regime. ‘Changes obligations’ is a model's DRAFT for reviewers; the decision is the human effect "
                           "classification in Refactor. Each regime sheet cites the source, sheet and row of every field."],
    ]
    unified = [["Row", "Data point", "Regimes", "Relation", "Changes what firms report (draft)", "Defect code"]
               + [f"{r} field(s)" for r in regs] + ["What differs", "Why (draft impact)"]]
    for r in st.get("rows") or []:
        rel = r["relation"]
        unified.append([r["row_id"], r["name"], ", ".join(r["regimes"]), ASPECT_LABEL.get(rel, rel.replace("_", " ")),
                        ("" if len(r["regimes"]) < 2 else ("no" if rel == "identical" else r["changes_obligations"])),
                        CODE.get(rel, "") if len(r["regimes"]) > 1 else ""]
                       + ["\n".join(label(m) for m in r["members"] if fields[m]["regime"] == g) for g in regs]
                       + [" ".join(m["detail"] for m in r["matches"] if m["detail"]),
                          " ".join(m["impact_reason"] for m in r["matches"] if m["impact_reason"])])
    rels = [["Regimes", "Field", "Counterpart", "How they differ", "Detail", "Changes what firms report (draft)", "Why"]]
    for pair, rec in sorted((st.get("pairs") or {}).items()):
        for br in rec.get("batches", {}).values():
            for m in br.get("matches") or []:
                rels.append([pair.replace("|", " · "), label(m["a"]), label(m["b"]),
                             ", ".join(ASPECT_LABEL.get(x, x) for x in m["aspects"]), m["detail"],
                             False if m["aspects"] == ["identical"] else m["changes_obligations"], m["impact_reason"]])
    sheets = [("Read me", readme, [34, 110]), ("Unified rows", unified, None), ("Relationships", rels, None)]
    for g in regs:
        rows = [["Field id", "Table", "Item", "Section", "Field", "Definition", "Format", "Validation rules",
                 "Required (by action type)", "Source", "Sheet", "Row", "Quote verified"]]
        for fid in sorted(k for k, f in fields.items() if f["regime"] == g):
            f = fields[fid]
            flags = f.get("flags") or {}
            rows.append([fid, f.get("table"), f.get("number"), f.get("section"), f["name"], f.get("definition"),
                         f.get("format"), f.get("validation"),
                         "; ".join(f"{k}: {v}" for k, v in flags.items())[:2000], f["item_id"], f.get("sheet"),
                         f.get("row"), bool(f.get("verified"))])
        sheets.append((f"{g} fields", rows, [10, 7, 7, 22, 30, 50, 34, 50, 34, 26, 20, 6, 9]))
    return write_workbook(sheets)
