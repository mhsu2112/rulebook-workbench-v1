"""Per-program model policy (spec/55 §4).

Which model runs each task is a *decision*, not a running toggle. Each program
carries a policy artifact: provisional (Recommended) by default, freely editable
while provisional, then **locked** by a ratification that writes a decision-log
entry. After locking it is read-only — "which model ran" becomes provenance, not
a live choice — and can only change by an explicit, logged re-open. The router
reads a program's ratified overrides at call time (as program-scoped overrides),
so the ledger's provenance flows from the policy that was decided.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import presets as presets_mod


class PolicyError(Exception): ...
class PolicyLocked(PolicyError): ...


def policy_path(program_dir: str | Path) -> Path:
    return Path(program_dir) / "governed" / "model_policy.json"


def default_policy(program_id: str) -> dict:
    return {"program_id": program_id, "preset": "recommended", "lab": None,
            "overrides": {}, "status": "provisional",
            "ratified_by": None, "ratified_at": None, "rationale": None, "hash": None}


def load(program_dir: str | Path, program_id: str) -> dict:
    p = policy_path(program_dir)
    if p.exists():
        return json.loads(p.read_text())
    return default_policy(program_id)


def save(program_dir: str | Path, doc: dict) -> dict:
    p = policy_path(program_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2))
    return doc


def _guard_unlocked(doc: dict) -> None:
    if doc.get("status") == "ratified":
        raise PolicyLocked("Model policy is locked — re-open it before changing models")


def set_preset(program_dir, program_id, registry, preset: str, lab=None) -> tuple[dict, list]:
    doc = load(program_dir, program_id)
    _guard_unlocked(doc)
    overrides, notes = presets_mod.resolve_preset(registry, preset, lab)
    doc.update({"preset": preset, "lab": lab, "overrides": overrides})
    save(program_dir, doc)
    return doc, notes


def set_override(program_dir, program_id, task_id: str, model) -> dict:
    doc = load(program_dir, program_id)
    _guard_unlocked(doc)
    if model is None:
        doc["overrides"].pop(task_id, None)
    else:
        doc["overrides"][task_id] = model
    doc["preset"] = "custom"
    doc["lab"] = None
    save(program_dir, doc)
    return doc


def _hash(doc: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps({"overrides": doc.get("overrides", {}), "pinned": doc.get("pinned_models") or {}},
                   sort_keys=True).encode()).hexdigest()


def effective_overrides(doc: dict) -> dict:
    """What the router should use for this program. A ratified policy pins the exact
    model IDs it resolved to at lock time, so later changes to the app-wide defaults
    (models.yaml, presets) never silently change a locked program. Older policies
    locked before pinning existed carry no pins and keep following the defaults."""
    if doc.get("status") == "ratified" and doc.get("pinned_models"):
        return dict(doc["pinned_models"])
    return dict(doc.get("overrides") or {})


def ratify(program_dir, program_id, name: str, rationale: str,
           resolved_models: dict | None = None) -> dict:
    doc = load(program_dir, program_id)
    if doc.get("status") == "ratified":
        raise PolicyError("Model policy is already locked")
    if resolved_models:
        doc["pinned_models"] = dict(sorted(resolved_models.items()))
    doc["status"] = "ratified"
    doc["ratified_by"] = {"name": name, "role": "Program Owner"}
    doc["ratified_at"] = datetime.now(timezone.utc).isoformat()
    doc["rationale"] = rationale
    doc["hash"] = _hash(doc)
    save(program_dir, doc)
    return doc


def reopen(program_dir, program_id) -> dict:
    doc = load(program_dir, program_id)
    doc["status"] = "provisional"
    doc.pop("pinned_models", None)
    doc["ratified_by"] = None
    doc["ratified_at"] = None
    doc["hash"] = None
    save(program_dir, doc)
    return doc
