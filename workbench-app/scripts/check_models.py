"""Verify every model ID in models.yaml exists in the live OpenRouter catalog (D4 hygiene)."""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from workbench.config import load_registry  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    registry = load_registry(REPO / "models.yaml")
    configured = set()
    for t in registry.tasks.values():
        configured.add(t.default_model)
        configured.update(t.fallbacks)
    catalog = {m["id"] for m in httpx.get(
        f"{registry.settings.base_url}/models", timeout=30).json()["data"]}
    missing = sorted(configured - catalog)
    for m in sorted(configured):
        print(("MISSING  " if m in missing else "ok       ") + m)
    if missing:
        print(f"\n{len(missing)} configured model(s) not in the current catalog — update models.yaml")
        return 1
    print(f"\nAll {len(configured)} configured models present in catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
