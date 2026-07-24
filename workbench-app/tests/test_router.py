import json

import httpx
import pytest

from conftest import make_response
from workbench.router import (
    BudgetExceededError,
    DiversityViolationError,
    MissingAPIKeyError,
    ModelRouter,
    SensitiveTaskPolicyError,
    StructuredOutputError,
    UpstreamError,
)

MSGS = [{"role": "user", "content": "hello"}]


def router(registry, transport, **kw):
    kw.setdefault("api_key", "test-key")
    kw.setdefault("sleep", lambda s: None)
    return ModelRouter(registry=registry, transport=transport, **kw)


def test_resolution_order(registry, ok_transport):
    r = router(registry, ok_transport,
               program_overrides={"render_prose": "openai/gpt-5.6-luna"},
               user_overrides={"render_prose": "mistralai/mistral-medium-3.5",
                               "claim_verify": "openai/gpt-5.6-luna"})
    assert r.resolve("render_prose").source == "program_override"
    assert r.resolve("render_prose").model == "openai/gpt-5.6-luna"
    assert r.resolve("claim_verify").source == "user_override"
    assert r.resolve("distill_extract").source == "default"


def test_unknown_task_rejected(registry, ok_transport):
    with pytest.raises(KeyError):
        router(registry, ok_transport).call("ad_hoc_call", MSGS)


def test_missing_key_fails(registry, ok_transport, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    r = ModelRouter(registry=registry, transport=ok_transport, api_key=None)
    with pytest.raises(MissingAPIKeyError):
        r.call("render_prose", MSGS)


def test_sensitive_fails_closed_without_zdr_pool(registry, ok_transport):
    registry.settings.zdr_pool_available = False
    r = router(registry, ok_transport)
    with pytest.raises(SensitiveTaskPolicyError):
        r.call("intake_interview", MSGS)
    assert r.run_records == []  # no network, no record


def test_sensitive_sets_zdr_and_deny(registry):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=make_response(model=captured["model"]))

    r = router(registry, httpx.MockTransport(handler))
    r.call("intake_interview", MSGS)
    assert captured["provider"] == {"data_collection": "deny", "zdr": True}


def test_diversity_violation_blocks_call(registry, ok_transport):
    r = router(registry, ok_transport)
    r.call("distill_extract", MSGS)  # anthropic used for the primary run
    with pytest.raises(DiversityViolationError):
        r.user_overrides["second_census"] = "anthropic/claude-sonnet-5"
        r.call("second_census", MSGS)


def test_diversity_compares_actual_run_not_default(registry, ok_transport):
    r = router(registry, ok_transport,
               program_overrides={"distill_extract": "openai/gpt-5.6-sol"})
    r.call("distill_extract", MSGS)  # actually ran on openai
    with pytest.raises(DiversityViolationError):
        r.call("second_census", MSGS)  # default openai now collides
    # anthropic also stays forbidden (defect_detect's resolved default) —
    # a third family is required
    r.user_overrides["second_census"] = "anthropic/claude-opus-4.8"
    with pytest.raises(DiversityViolationError):
        r.call("second_census", MSGS)
    r.user_overrides["second_census"] = "mistralai/mistral-medium-3.5"
    out, stamp = r.call("second_census", MSGS)
    assert stamp["model_served"].startswith("mistralai/")


def test_provenance_stamp_complete_and_costed(registry, ok_transport):
    r = router(registry, ok_transport)
    _, stamp = r.call("claim_verify", MSGS)
    for key in ("app_commit", "registry_version", "prompt_hash", "input_hash",
                "output_hash", "fallback_history", "resolution_source"):
        assert key in stamp
    assert stamp["cost"]["usd"] == 0.01
    assert r.spent_usd == pytest.approx(0.01)


def test_budget_hard_stop(registry, ok_transport):
    r = router(registry, ok_transport, budget_usd=0.015)
    r.call("render_prose", MSGS)
    r.call("render_prose", MSGS)  # crosses the budget
    with pytest.raises(BudgetExceededError):
        r.call("render_prose", MSGS)


def test_retry_then_success(registry):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json=make_response())

    r = router(registry, httpx.MockTransport(handler))
    _, stamp = r.call("render_prose", MSGS)
    assert calls["n"] == 3 and stamp["request_id"] == "gen-123"


def test_client_error_no_retry(registry):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    with pytest.raises(UpstreamError):
        router(registry, httpx.MockTransport(handler)).call("render_prose", MSGS)
    assert calls["n"] == 1


def _structured_registry(registry, tmp_path):
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
    (tmp_path / "toy.schema.json").write_text(json.dumps(schema))
    registry.settings.contracts_dirs = [str(tmp_path)]
    registry.tasks["render_prose"].structured_output = "toy.schema.json"
    return registry


def test_structured_output_schema_embedded_not_response_format(registry, tmp_path):
    registry = _structured_registry(registry, tmp_path)
    captured = {}

    def good(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=make_response(model="google/gemini-3.1-flash-lite",
                                                      content='```json\n{"x": 1}\n```'))

    out, stamp = router(registry, httpx.MockTransport(good)).call("render_prose", MSGS)
    assert out == {"x": 1}                       # fences tolerated
    assert "response_format" not in captured     # never rely on provider strict mode
    assert "OUTPUT FORMAT (mandatory)" in captured["messages"][-1]["content"]
    assert '"required": ["x"]' in captured["messages"][-1]["content"]
    assert stamp["repair_attempts"] == 0


def test_structured_output_repairs_once_then_succeeds(registry, tmp_path):
    registry = _structured_registry(registry, tmp_path)
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        content = '{"x": "not-an-int"}' if calls["n"] == 1 else '{"x": 1}'
        return httpx.Response(200, json=make_response(model="google/gemini-3.1-flash-lite",
                                                      content=content, cost=0.01))

    out, stamp = router(registry, httpx.MockTransport(flaky)).call("render_prose", MSGS)
    assert out == {"x": 1} and calls["n"] == 2
    assert stamp["repair_attempts"] == 1
    assert stamp["cost"]["usd"] == pytest.approx(0.02)  # both attempts costed


def test_structured_output_fails_after_repair(registry, tmp_path):
    registry = _structured_registry(registry, tmp_path)
    calls = {"n": 0}

    def bad(request):
        calls["n"] += 1
        return httpx.Response(200, json=make_response(model="google/gemini-3.1-flash-lite",
                                                      content='{"x": "not-an-int"}'))

    with pytest.raises(StructuredOutputError):
        router(registry, httpx.MockTransport(bad)).call("render_prose", MSGS)
    assert calls["n"] == 2  # initial + one repair, then hard stop


def test_null_content_retried_then_succeeds(registry):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            resp = make_response()
            resp["choices"][0]["message"]["content"] = None  # degenerate response
            return httpx.Response(200, json=resp)
        return httpx.Response(200, json=make_response(content="finally"))

    out, _ = router(registry, httpx.MockTransport(handler)).call("render_prose", MSGS)
    assert out == "finally" and calls["n"] == 3


def test_persistent_null_content_raises(registry):
    def handler(request: httpx.Request) -> httpx.Response:
        resp = make_response()
        resp["choices"][0]["message"]["content"] = None
        return httpx.Response(200, json=resp)

    with pytest.raises(UpstreamError, match="empty/null"):
        router(registry, httpx.MockTransport(handler)).call("render_prose", MSGS)


def test_malformed_200_body_retried(registry):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, text="<html>gateway hiccup, not json</html>")
        payload = json.loads(request.content)
        return httpx.Response(200, json=make_response(model=payload["model"]))

    r = router(registry, httpx.MockTransport(handler))
    out, stamp = r.call("render_prose", MSGS)
    assert out == "ok" and calls["n"] == 2


def test_failed_structured_output_still_charged(registry):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(200, json=make_response(model=payload["model"],
                                                      content="not json at all", cost=0.5))

    r = router(registry, httpx.MockTransport(handler))
    with pytest.raises(StructuredOutputError):
        r.call("distill_extract", MSGS)
    assert r.spent_usd == 1.0   # primary + repair attempt both counted


def test_structured_output_retries_with_more_tokens_on_truncation(registry, tmp_path):
    """A truncated (finish_reason=length) JSON blob should trigger a RE-RUN with
    doubled max_tokens, not a same-cap 'repair' that just truncates again."""
    registry = _structured_registry(registry, tmp_path)
    calls = {"n": 0, "max_tokens": []}

    def handler(request):
        calls["n"] += 1
        calls["max_tokens"].append(json.loads(request.content).get("max_tokens"))
        if calls["n"] == 1:
            r = make_response(model="google/gemini-3.1-flash-lite", content='{"x": 1', cost=0.01)  # cut off
            r["choices"][0]["finish_reason"] = "length"
            return httpx.Response(200, json=r)
        return httpx.Response(200, json=make_response(model="google/gemini-3.1-flash-lite", content='{"x": 1}', cost=0.01))

    out, stamp = router(registry, httpx.MockTransport(handler)).call("render_prose", MSGS)
    assert out == {"x": 1} and calls["n"] == 2
    assert calls["max_tokens"][1] == calls["max_tokens"][0] * 2   # doubled on the retry
    assert stamp["repair_attempts"] == 1
