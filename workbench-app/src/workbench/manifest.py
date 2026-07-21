"""Frozen Manifest machinery (instruction set P1; PRD M2).

Import a curated corpus slice into a program, then freeze it: a canonical
content hash over the items, a ⚖ decision-log entry, and immutability from
that moment on (scope changes go to the scope-change queue, never silently
into a frozen manifest — OR-7).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import jsonschema


class ManifestError(Exception): ...
class FrozenError(ManifestError): ...


def _schema() -> dict:
    with resources.files("workbench.contracts").joinpath("manifest.schema.json").open() as f:
        return json.load(f)


def canonical_hash(items: list[dict]) -> str:
    """Deterministic content hash: order-independent, whitespace-independent."""
    canon = json.dumps(sorted(items, key=lambda i: i["item_id"]),
                       sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()


def manifest_path(program_dir: str | Path) -> Path:
    return Path(program_dir) / "governed" / "manifest" / "manifest.json"


def load(program_dir: str | Path) -> dict | None:
    p = manifest_path(program_dir)
    return json.loads(p.read_text()) if p.exists() else None


def import_slice(program_dir: str | Path, slice_doc: dict, program_id: str) -> dict:
    """Create/replace the (unfrozen) manifest from a curated slice document."""
    existing = load(program_dir)
    if existing and existing.get("frozen"):
        raise FrozenError("Manifest is frozen (OR-7): new material goes to the scope-change "
                          "queue and takes effect only via a new manifest version")
    items = slice_doc["items"]
    ids = [i["item_id"] for i in items]
    if len(ids) != len(set(ids)):
        dupes = sorted({x for x in ids if ids.count(x) > 1})
        raise ManifestError(f"Duplicate item_ids in slice: {dupes}")
    doc = {
        "program_id": program_id,
        "manifest_version": "0.1",
        "frozen": False,
        "frozen_at": None,
        "content_hash": None,
        "scope_contract_version": slice_doc.get("scope_contract_version"),
        "source_note": slice_doc.get("source_note"),
        "items": items,
    }
    jsonschema.validate(doc, _schema())
    p = manifest_path(program_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2))
    # gap register travels with the import (instruction set P1.6)
    if slice_doc.get("gaps"):
        reg = Path(program_dir) / "governed" / "registers"
        reg.mkdir(parents=True, exist_ok=True)
        (reg / "gaps.json").write_text(json.dumps(slice_doc["gaps"], indent=2))
    return doc


def freeze(program_dir: str | Path) -> dict:
    """Freeze the manifest: hash, timestamp, immutability. Caller logs the ⚖."""
    doc = load(program_dir)
    if doc is None:
        raise ManifestError("No manifest to freeze — import a corpus slice first")
    if doc.get("frozen"):
        raise FrozenError("Already frozen")
    if not doc.get("items"):
        raise ManifestError("Refusing to freeze an empty manifest")
    doc["frozen"] = True
    doc["frozen_at"] = datetime.now(timezone.utc).isoformat()
    doc["content_hash"] = canonical_hash(doc["items"])
    jsonschema.validate(doc, _schema())
    p = manifest_path(program_dir)
    p.write_text(json.dumps(doc, indent=2))
    (p.parent / "manifest.sha256").write_text(doc["content_hash"] + "\n")
    return doc
