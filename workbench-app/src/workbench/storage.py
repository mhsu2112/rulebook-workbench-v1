"""Program workspace storage: the ADR-016 governed/restricted split and the
append-only decision log."""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import jsonschema

GITIGNORE_LINE = "programs/*/restricted/"


def _entry_schema() -> dict:
    with resources.files("workbench.contracts").joinpath("decision_log_entry.schema.json").open() as f:
        return json.load(f)


def init_program(root: str | Path, program_id: str) -> Path:
    """Create programs/<id>/{governed,restricted} under root and ensure the
    root .gitignore excludes every restricted store."""
    root = Path(root)
    pdir = root / "programs" / program_id
    (pdir / "governed").mkdir(parents=True, exist_ok=True)
    (pdir / "restricted").mkdir(parents=True, exist_ok=True)

    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    if GITIGNORE_LINE not in lines:
        lines.append(GITIGNORE_LINE)
        gi.write_text("\n".join(lines) + "\n")
    return pdir


def _branch(program_dir: str | Path) -> dict | None:
    """The branch.json of an exploration folder (programs/<pid>/explorations/<xid>), else None."""
    p = Path(program_dir)
    if p.parent.name != "explorations" or not (p / "branch.json").exists():
        return None
    try:
        return json.loads((p / "branch.json").read_text())
    except ValueError:
        return None


def next_entry_id(program_dir: str | Path) -> str:
    """The next id in this log: DL-### for a program, EX-<X>-### inside an exploration,
    so a branch decision can never be quoted as an official DL number."""
    b = _branch(program_dir)
    prefix = f"EX-{b['branch_id'].upper()}" if b else "DL"
    return f"{prefix}-{len(read_decisions(program_dir)) + 1:03d}"


def append_decision(program_dir: str | Path, entry: dict) -> None:
    """Validate and append one entry to the program's append-only decision log.

    Inside an exploration (ADR-019) every entry is stamped with the branch, and a
    ratification is recorded as exploration_ratification: it unlocks the branch's
    later steps but is never an official ratification."""
    b = _branch(program_dir)
    if b:
        entry = dict(entry)
        entry["exploration"] = b["branch_id"]
        if entry.get("type") == "ratification":
            entry["type"] = "exploration_ratification"
        eid = str(entry.get("entry_id", ""))
        if eid.startswith("DL-"):
            entry["entry_id"] = f"EX-{b['branch_id'].upper()}-" + eid[3:]
    jsonschema.validate(entry, _entry_schema())
    log = Path(program_dir) / "governed" / "decisions.log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_decisions(program_dir: str | Path) -> list[dict]:
    log = Path(program_dir) / "governed" / "decisions.log.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
