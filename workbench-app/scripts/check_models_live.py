"""Live check: does every configured model answer under the account's privacy settings?

Sends one tiny request to every model named in models.yaml (each task's default
and its fallbacks) through OpenRouter, with the same provider restrictions the
router uses PLUS zero-data-retention forced on. This mirrors an account that has
"ZDR for all requests" switched on, so a model that passes here will not be
refused mid-pipeline because of the privacy policy.

  .venv/bin/python scripts/check_models_live.py              # configured models
  .venv/bin/python scripts/check_models_live.py --catalog    # + optional catalog models

Requires OPENROUTER_API_KEY (read from .env). Cost: a fraction of a cent in total.
Exit code 0 = every Workbench task still has its default model; 1 otherwise.
(Tasks in the developer eval harness, phase: eval, are reported but never fail the check.)
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from workbench.config import load_registry  # noqa: E402

PROMPT = "Reply with the single word OK."


@dataclass
class Result:
    model: str
    ok: bool
    detail: str = ""
    provider: str = ""
    cost: float = 0.0
    tasks_default: list[str] = field(default_factory=list)
    tasks_fallback: list[str] = field(default_factory=list)


def models_by_role(registry, include_catalog: bool = False) -> dict[str, dict[str, list[str]]]:
    """model -> {"default": [task ids], "fallback": [task ids]}"""
    out: dict[str, dict[str, list[str]]] = {}
    for tid, t in registry.tasks.items():
        out.setdefault(t.default_model, {"default": [], "fallback": []})["default"].append(tid)
        for fb in t.fallbacks:
            out.setdefault(fb, {"default": [], "fallback": []})["fallback"].append(tid)
    if include_catalog:
        for m in getattr(registry.settings, "catalog", None) or []:
            out.setdefault(m, {"default": [], "fallback": []})
    return out


def probe(client: httpx.Client, base_url: str, api_key: str, model: str,
          data_collection: str, retries: int = 2, sleep=time.sleep) -> tuple[bool, str, str, float]:
    """One tiny request; transient failures (429 / 5xx / network) are retried."""
    for attempt in range(retries + 1):
        ok, detail, provider, cost, transient = _probe_once(client, base_url, api_key, model, data_collection)
        if ok or not transient or attempt == retries:
            return ok, (detail + " (transient — re-run later)" if transient and not ok else detail), provider, cost
        sleep(3 * (attempt + 1))
    return False, "unreachable", "", 0.0


def _probe_once(client: httpx.Client, base_url: str, api_key: str, model: str,
                data_collection: str) -> tuple[bool, str, str, float, bool]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 512,          # headroom for reasoning models
        "temperature": 0,
        "provider": {"data_collection": data_collection, "zdr": True},
        "usage": {"include": True},
    }
    try:
        r = client.post(f"{base_url}/chat/completions", json=payload,
                        headers={"Authorization": f"Bearer {api_key}"})
    except (httpx.TransportError, httpx.TimeoutException) as e:
        return False, f"network error: {e}", "", 0.0, True
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", "") or r.text
        except ValueError:
            msg = r.text
        return False, f"HTTP {r.status_code}: {msg[:160]}", "", 0.0, (r.status_code == 429 or r.status_code >= 500)
    try:
        data = r.json()
    except ValueError:
        return False, "malformed response", "", 0.0, True
    if not data.get("choices"):
        e = data.get("error") or {}
        err = e.get("message", "no choices returned")
        code = e.get("code")
        transient = code == 429 or (isinstance(code, int) and code >= 500) or "rate-limit" in str(err)
        return False, str(err)[:160], "", 0.0, transient
    cost = float((data.get("usage") or {}).get("cost") or 0.0)
    return True, "answered", data.get("provider", ""), cost, False


def run(registry, api_key: str, include_catalog: bool = False,
        transport: Optional[httpx.BaseTransport] = None, sleep=time.sleep) -> tuple[list[Result], list[str], list[str]]:
    roles = models_by_role(registry, include_catalog)
    results: list[Result] = []
    with httpx.Client(transport=transport, timeout=httpx.Timeout(90.0, connect=15.0)) as client:
        for model in sorted(roles):
            ok, detail, provider, cost = probe(client, registry.settings.base_url, api_key,
                                               model, registry.settings.data_collection, sleep=sleep)
            results.append(Result(model, ok, detail, provider, cost,
                                  roles[model]["default"], roles[model]["fallback"]))
    passed = {r.model for r in results if r.ok}
    degraded, blocked = [], []
    for tid, t in registry.tasks.items():
        if t.phase == "eval":          # developer eval harness only; not used in the Workbench UI
            continue
        if t.default_model in passed:
            continue
        (degraded if any(fb in passed for fb in t.fallbacks) else blocked).append(tid)
    return results, degraded, blocked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--catalog", action="store_true", help="also probe the optional catalog models")
    args = ap.parse_args()

    from workbench.server import load_dotenv
    import os
    load_dotenv(REPO)
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not set — add it to .env first.")
        return 2

    registry = load_registry(REPO / "models.yaml")
    print(f"Endpoint: {registry.settings.base_url}   (zero-data-retention forced on for every probe)\n")
    results, degraded, blocked = run(registry, key, include_catalog=args.catalog)

    for r in results:
        role = ("default for " + ", ".join(r.tasks_default)) if r.tasks_default else \
               ("fallback for " + ", ".join(r.tasks_fallback)) if r.tasks_fallback else "catalog option"
        mark = "ok     " if r.ok else "REFUSED"
        extra = f"via {r.provider}" if r.ok else r.detail
        print(f"{mark}  {r.model:<36} {extra}")
        print(f"         {role}")
    total = sum(r.cost for r in results)
    print(f"\nSpent: ${total:.5f}")

    if blocked:
        print("\nBLOCKED — no working model at all for: " + ", ".join(blocked))
    if degraded:
        print("DEGRADED — default refused, running on a fallback: " + ", ".join(degraded))
    if not blocked and not degraded:
        failed_fb = [r.model for r in results if not r.ok]
        if failed_fb:
            print("\nAll tasks have their default model. Refused fallbacks (update models.yaml when convenient): "
                  + ", ".join(failed_fb))
        else:
            print("\nAll configured models answered under zero-data-retention.")
        return 0
    print("\nUpdate models.yaml (or the account's provider settings) before relying on the tasks above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
