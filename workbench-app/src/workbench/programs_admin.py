"""Per-program administration: archive and safe rename (spec/54 §2.4).

Governance posture: **archive, never destroy.** "Delete" moves a program into
`programs/_archive/` (hidden from the list, restorable); the append-only
decision log is never removed. Rename is non-trivial because a program_id
appears in the folder name, in governed artifacts, and in runs/stamps.jsonl —
so it is done here as one careful operation, repointing stamps by EXACT match
(never substring — the lesson from the `-p2` rename).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
ARCHIVE_DIR = "_archive"


class AdminError(Exception): ...


def programs_root(root: str | Path) -> Path:
    return Path(root) / "programs"


def list_active(root: str | Path) -> list[str]:
    base = programs_root(root)
    if not base.is_dir():
        return []
    # Names starting with "_" (e.g. _archive) are infrastructure, not programs.
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("_"))


def list_archived(root: str | Path) -> list[str]:
    base = programs_root(root) / ARCHIVE_DIR
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def archive(root: str | Path, pid: str) -> dict:
    base = programs_root(root)
    src = base / pid
    if not src.is_dir():
        raise AdminError(f"Unknown program '{pid}'")
    arc = base / ARCHIVE_DIR
    arc.mkdir(exist_ok=True)
    dest = arc / pid
    if dest.exists():
        raise AdminError(f"An archived program named '{pid}' already exists")
    src.rename(dest)
    return {"program_id": pid, "archived": True}


def restore(root: str | Path, pid: str) -> dict:
    base = programs_root(root)
    src = base / ARCHIVE_DIR / pid
    if not src.is_dir():
        raise AdminError(f"No archived program '{pid}'")
    dest = base / pid
    if dest.exists():
        raise AdminError(f"An active program named '{pid}' already exists")
    src.rename(dest)
    return {"program_id": pid, "archived": False}


def _repoint_program_id(pdir: Path, new_id: str) -> None:
    """Rewrite program_id in the governed/restricted artifacts that carry it."""
    targets = [
        pdir / "governed" / "purpose_statement.json",
        pdir / "governed" / "manifest" / "manifest.json",
        pdir / "restricted" / "mandate_hypotheses.json",
    ]
    for t in targets:
        if t.exists():
            try:
                doc = json.loads(t.read_text())
            except ValueError:
                continue
            if isinstance(doc, dict) and doc.get("program_id"):
                doc["program_id"] = new_id
                t.write_text(json.dumps(doc, indent=2))


def _repoint_stamps(root: Path, old_id: str, new_id: str) -> int:
    """Repoint runs/stamps.jsonl entries by EXACT program_id match. Returns count."""
    stamps = Path(root) / "runs" / "stamps.jsonl"
    if not stamps.exists():
        return 0
    out, n = [], 0
    for line in stamps.read_text().splitlines():
        if not line.strip():
            out.append(line)
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        if rec.get("program_id") == old_id:      # EXACT, never substring
            rec["program_id"] = new_id
            n += 1
            out.append(json.dumps(rec))
        else:
            out.append(line)
    stamps.write_text("\n".join(out) + ("\n" if out else ""))
    return n


def rename(root: str | Path, old_id: str, new_id: str, *, by: str = "Program Owner") -> dict:
    base = programs_root(root)
    if not (base / old_id).is_dir():
        raise AdminError(f"Unknown program '{old_id}'")
    new_id = new_id.strip()
    if not SLUG.match(new_id):
        raise AdminError("New name must be a lowercase slug (a-z, 0-9, -, _), 2–64 chars")
    if new_id == old_id:
        raise AdminError("New name is the same as the current one")
    if (base / new_id).exists() or (base / ARCHIVE_DIR / new_id).exists():
        raise AdminError(f"A program named '{new_id}' already exists")

    (base / old_id).rename(base / new_id)
    pdir = base / new_id
    _repoint_program_id(pdir, new_id)
    n = _repoint_stamps(root, old_id, new_id)

    # Log the rename in the (moved) decision log — append-only, so it records
    # the identity change without rewriting any prior entry.
    log = pdir / "governed" / "decisions.log.jsonl"
    if log.exists():
        entry = {
            "entry_id": f"DL-{sum(1 for _ in log.read_text().splitlines() if _.strip()) + 1:03d}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "other",
            "artifact": "program",
            "decided_by": {"name": by, "role": "Program Owner"},
            "decision": f"Rename program '{old_id}' → '{new_id}'",
            "rationale": f"Program renamed; {n} provenance stamp(s) repointed by exact match.",
        }
        with log.open("a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    return {"program_id": new_id, "renamed_from": old_id, "stamps_repointed": n}
