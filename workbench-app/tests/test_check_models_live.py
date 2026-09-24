"""Offline tests for scripts/check_models_live.py (no network: MockTransport)."""
import importlib.util
import json
import sys

import httpx

from conftest import REPO
from workbench.config import load_registry

_spec = importlib.util.spec_from_file_location("check_models_live", REPO / "scripts" / "check_models_live.py")
live = importlib.util.module_from_spec(_spec)
sys.modules["check_models_live"] = live
_spec.loader.exec_module(live)


def _transport(refuse: set[str], seen: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if body["model"] in refuse:
            return httpx.Response(404, json={"error": {"message": "No endpoints found matching your data policy"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}],
                                         "provider": "TestProv", "usage": {"cost": 0.00001}})
    return httpx.MockTransport(handler)


def test_every_probe_forces_zdr_and_no_training():
    reg = load_registry(REPO / "models.yaml")
    seen: list[dict] = []
    results, degraded, blocked = live.run(reg, "k", transport=_transport(set(), seen), sleep=lambda s: None)
    assert results and all(r.ok for r in results) and not degraded and not blocked
    assert all(b["provider"]["zdr"] is True for b in seen)
    assert all(b["provider"]["data_collection"] == reg.settings.data_collection for b in seen)
    assert all("models" not in b for b in seen)          # no silent model fallback inside a probe
    configured = {t.default_model for t in reg.tasks.values()} | {f for t in reg.tasks.values() for f in t.fallbacks}
    assert {b["model"] for b in seen} == configured


def test_refused_default_is_degraded_or_blocked():
    reg = load_registry(REPO / "models.yaml")
    tid, task = next((k, t) for k, t in reg.tasks.items() if t.fallbacks)
    # refuse only this task's default -> it runs degraded on a fallback
    _, degraded, blocked = live.run(reg, "k", transport=_transport({task.default_model}, []), sleep=lambda s: None)
    assert tid in degraded and tid not in blocked
    # refuse everything -> every task blocked
    everything = {t.default_model for t in reg.tasks.values()} | {f for t in reg.tasks.values() for f in t.fallbacks}
    _, degraded, blocked = live.run(reg, "k", transport=_transport(everything, []), sleep=lambda s: None)
    product_tasks = {k for k, t in reg.tasks.items() if t.phase != "eval"}
    assert set(blocked) == product_tasks and not degraded


def test_transient_429_is_retried_then_passes():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate-limited upstream"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}], "provider": "P"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        ok, detail, _, _ = live.probe(c, "https://x", "k", "m/one", "deny", sleep=lambda s: None)
    assert ok and calls["n"] == 2


def test_policy_refusal_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404, json={"error": {"message": "No endpoints found matching your data policy"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        ok, detail, _, _ = live.probe(c, "https://x", "k", "m/one", "deny", sleep=lambda s: None)
    assert not ok and calls["n"] == 1 and "data policy" in detail
