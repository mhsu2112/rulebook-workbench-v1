import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from workbench.config import load_registry  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def registry():
    return load_registry(REPO / "models.yaml")


def make_response(model="anthropic/claude-opus-4.8", content="ok", cost=0.01, id_="gen-123"):
    return {
        "id": id_,
        "model": model,
        "provider": "TestProvider",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": cost},
    }


MIN_EXTRACTION = {"item_id": "t", "objectives": [], "obligations": [],
                  "definitions": [], "interactions": [], "nothing_in_scope": True}


@pytest.fixture()
def ok_transport():
    """MockTransport that echoes back the requested primary model as served.

    When the prompt carries the structured-output marker (distill_extract in
    the router tests), return a minimal schema-valid extraction so local
    validation passes — these tests exercise routing, not content."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = "ok"
        if "OUTPUT FORMAT (mandatory)" in payload["messages"][-1]["content"]:
            content = json.dumps(MIN_EXTRACTION)
        return httpx.Response(200, json=make_response(model=payload["model"], content=content))
    return httpx.MockTransport(handler)
