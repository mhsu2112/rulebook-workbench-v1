"""Which configured models have newer releases? (report only — changes nothing)

Collects every model ID the Workbench names — task defaults and fallbacks and the
selector catalog in models.yaml, plus the preset line-ups in presets.py — and
compares each with the live OpenRouter catalog. A newer release is a model from the
same provider and the same line (the ID with its version numbers ignored, e.g.
anthropic/claude-opus-5.5 and anthropic/claude-opus-6 are one line; ...-sol and
...-sol-pro are two) that was published more recently.

  .venv/bin/python scripts/model_updates.py        (or: make models-updates)

Then edit models.yaml / presets.py, run `make models-live` (confirms each new
model answers under zero-data-retention) and the test suite. Programs whose model
policy is already locked keep the exact models they pinned at lock time.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from workbench import presets  # noqa: E402
from workbench.config import load_registry  # noqa: E402

_VERSION = re.compile(r"\d+(?:[.\-]\d+)*")


def line_of(model_id: str) -> str:
    """Provider + name with every version number replaced by '#'."""
    return _VERSION.sub("#", model_id.split(":")[0])


def configured_models(registry) -> dict[str, set[str]]:
    """model id -> where it is used (task defaults, fallbacks, catalog, presets)."""
    where: dict[str, set[str]] = {}
    def add(m, tag):
        if m:
            where.setdefault(m, set()).add(tag)
    for tid, t in registry.tasks.items():
        add(t.default_model, f"default:{tid}")
        for fb in t.fallbacks:
            add(fb, f"fallback:{tid}")
    for m in registry.settings.catalog or []:
        add(m, "selector")
    for lab, tiers in presets.LAB.items():
        for tier, m in tiers.items():
            add(m, f"preset lab-first:{lab}/{tier}")
    for m in presets.OPEN:
        add(m, "preset open-weight")
    for m in set(presets.COST.values()):
        add(m, "preset cost")
    return where


def find_updates(where: dict[str, set[str]], catalog: list[dict]) -> tuple[list[dict], list[str]]:
    by_id = {m["id"]: m for m in catalog}
    updates, missing = [], []
    for mid in sorted(where):
        cur = by_id.get(mid)
        if cur is None:
            missing.append(mid)
            continue
        line = line_of(mid)
        newer = [m for m in catalog
                 if ":" not in m["id"] and m["id"] != mid and line_of(m["id"]) == line
                 and m.get("created", 0) > cur.get("created", 0)]
        if newer:
            newer.sort(key=lambda m: -m.get("created", 0))
            updates.append({"current": mid, "used_in": sorted(where[mid]), "newer": newer})
    return updates, missing


def _price(m: dict) -> str:
    p = m.get("pricing") or {}
    try:
        return f"${float(p.get('prompt', 0)) * 1e6:.2f}/${float(p.get('completion', 0)) * 1e6:.2f} per M tokens"
    except (TypeError, ValueError):
        return ""


def main() -> int:
    registry = load_registry(REPO / "models.yaml")
    try:
        catalog = httpx.get(f"{registry.settings.base_url}/models", timeout=30).json()["data"]
    except Exception as e:  # noqa: BLE001
        print(f"Could not reach the OpenRouter catalog: {e}")
        return 2
    where = configured_models(registry)
    updates, missing = find_updates(where, catalog)
    print(f"Checked {len(where)} configured models against {len(catalog)} catalog entries.\n")
    for u in updates:
        print(f"NEWER  {u['current']}")
        print(f"       used in: {', '.join(u['used_in'])}")
        for m in u["newer"]:
            print(f"       -> {m['id']:44} released {date.fromtimestamp(m.get('created', 0))}  {_price(m)}")
        print()
    for mid in missing:
        print(f"GONE   {mid} — no longer in the catalog; replace it (used in: {', '.join(sorted(where[mid]))})")
    if not updates and not missing:
        print("Everything configured is the newest release in its line.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
