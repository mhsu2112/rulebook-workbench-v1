"""Offline tests for scripts/model_updates.py."""
import importlib.util
import sys

from conftest import REPO

_spec = importlib.util.spec_from_file_location("model_updates", REPO / "scripts" / "model_updates.py")
mu = importlib.util.module_from_spec(_spec)
sys.modules["model_updates"] = mu
_spec.loader.exec_module(mu)


def test_line_of_ignores_versions_only():
    assert mu.line_of("anthropic/claude-opus-5.5") == mu.line_of("anthropic/claude-opus-6")
    assert mu.line_of("openai/gpt-6-sol") != mu.line_of("openai/gpt-6-sol-pro")
    assert mu.line_of("google/gemini-3.5-flash-lite") == mu.line_of("google/gemini-4-flash-lite")
    assert mu.line_of("google/gemini-3.5-flash-lite") != mu.line_of("google/gemini-3.8-flash")
    assert mu.line_of("mistralai/mistral-medium-3-5") == mu.line_of("mistralai/mistral-medium-3.1")


def test_find_updates_reports_newer_same_line_and_gone():
    catalog = [
        {"id": "anthropic/claude-opus-5.5", "created": 100},
        {"id": "anthropic/claude-opus-6", "created": 200},
        {"id": "anthropic/claude-opus-5", "created": 50},          # older: not reported
        {"id": "anthropic/claude-opus-6:batch", "created": 300},   # variant: ignored
        {"id": "openai/gpt-6-sol", "created": 100},
        {"id": "openai/gpt-6-sol-pro", "created": 400},            # different line
    ]
    where = {"anthropic/claude-opus-5.5": {"default:x"}, "openai/gpt-6-sol": {"default:y"},
             "google/gemini-9-ghost": {"selector"}}
    updates, missing = mu.find_updates(where, catalog)
    assert [u["current"] for u in updates] == ["anthropic/claude-opus-5.5"]
    assert [m["id"] for m in updates[0]["newer"]] == ["anthropic/claude-opus-6"]
    assert missing == ["google/gemini-9-ghost"]


def test_configured_models_covers_defaults_catalog_and_presets():
    from workbench.config import load_registry
    reg = load_registry(REPO / "models.yaml")
    where = mu.configured_models(reg)
    assert any(t.startswith("default:") for tags in where.values() for t in tags)
    assert any("selector" in tags for tags in where.values())
    assert any(any(t.startswith("preset") for t in tags) for tags in where.values())
