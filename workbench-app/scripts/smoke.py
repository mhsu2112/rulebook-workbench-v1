"""Live M0 smoke test: one routed, stamped call through OpenRouter.

Requires OPENROUTER_API_KEY in the environment (see .env.example).
Usage: make smoke
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from workbench.config import load_registry
from workbench.server import load_dotenv
from workbench.router import ModelRouter

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO)


def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set — copy .env.example to .env and fill it in.")
        return 1
    registry = load_registry(REPO / "models.yaml")
    router = ModelRouter(registry=registry, budget_usd=0.25)
    out, stamp = router.call(
        "render_prose",
        [{"role": "user", "content": "Reply with exactly: WORKBENCH M0 OK"}],
    )
    print("response:", out)
    print("stamp:")
    print(json.dumps(stamp, indent=2))
    print(f"\nspent: ${router.spent_usd:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
