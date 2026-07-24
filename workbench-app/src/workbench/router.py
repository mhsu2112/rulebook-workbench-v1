"""The model router: single OpenRouter integration, per-task model selection.

PRD spec/40 §6. Enforces: resolution order (program override → user toggle →
default), model-diversity constraints against actually-used models (G5),
fail-closed privacy for sensitive tasks (ADR-016), schema-validated
structured outputs, provenance stamps on every call (G4), and a per-program
cost meter with hard stop.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from typing import Any, Callable, Optional

import httpx
import jsonschema

from .config import Registry, TaskConfig

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class RouterError(Exception): ...
class MissingAPIKeyError(RouterError): ...
class SensitiveTaskPolicyError(RouterError):
    """A sensitive task found no policy-eligible provider. Fails closed — never relax privacy silently."""
class DiversityViolationError(RouterError): ...
class StructuredOutputError(RouterError): ...
class BudgetExceededError(RouterError): ...
class UpstreamError(RouterError): ...


def _sha(data: Any) -> str:
    if not isinstance(data, (bytes, bytearray)):
        data = json.dumps(data, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _extract_json(text: str) -> Any:
    """Parse a JSON object from model output, tolerating markdown fences and
    surrounding prose."""
    t = text.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            return json.loads(t[start:end + 1])
        raise ValueError("no JSON object found in model output")


def _stamp_schema() -> dict:
    with resources.files("workbench.contracts").joinpath("provenance_stamp.schema.json").open() as f:
        return json.load(f)


@dataclass
class Resolution:
    model: str
    source: str  # program_override | user_override | default


@dataclass
class ModelRouter:
    registry: Registry
    api_key: Optional[str] = None
    program_overrides: dict[str, str] = field(default_factory=dict)
    user_overrides: dict[str, str] = field(default_factory=dict)
    budget_usd: Optional[float] = None
    transport: Optional[httpx.BaseTransport] = None  # injectable for tests
    sleep: Callable[[float], None] = time.sleep
    max_attempts: int = 3

    run_records: list[dict] = field(default_factory=list)
    spent_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self._stamp_schema = _stamp_schema()

    # ---------------- resolution & constraints ----------------

    @staticmethod
    def family(model_id: str) -> str:
        """Interim family notion: provider prefix (ADR-017f notes its limits)."""
        return model_id.split("/")[0]

    def resolve(self, task_id: str) -> Resolution:
        self.registry.task(task_id)  # existence check
        if task_id in self.program_overrides:
            return Resolution(self.program_overrides[task_id], "program_override")
        if task_id in self.user_overrides:
            return Resolution(self.user_overrides[task_id], "user_override")
        return Resolution(self.registry.task(task_id).default_model, "default")

    def used_model_for(self, task_id: str) -> Optional[str]:
        for rec in reversed(self.run_records):
            if rec["task_id"] == task_id:
                return rec["model_served"]
        return None

    def _forbidden_families(self, task: TaskConfig) -> set[str]:
        out: set[str] = set()
        for other_id in task.must_differ_family_from:
            used = self.used_model_for(other_id)
            # Compare against the run actually performed; fall back to that
            # task's resolved model only if it has not run yet.
            target = used or self.resolve(other_id).model
            out.add(self.family(target))
        return out

    def _check_diversity(self, task_id: str, task: TaskConfig, model: str) -> list[str]:
        forbidden = self._forbidden_families(task)
        if self.family(model) in forbidden:
            raise DiversityViolationError(
                f"Task '{task_id}' must differ in family from {task.must_differ_family_from}; "
                f"'{model}' matches a forbidden family {sorted(forbidden)}"
            )
        return [m for m in task.fallbacks if self.family(m) not in forbidden]

    # ---------------- the single integration ----------------

    def call(self, task_id: str, messages: list[dict], *, input_ref: Any = None) -> tuple[Any, dict]:
        task = self.registry.task(task_id)

        # Fail closed BEFORE any network activity (ADR-016).
        if task.sensitive and not self.registry.settings.zdr_pool_available:
            raise SensitiveTaskPolicyError(
                f"Sensitive task '{task_id}': no ZDR/no-training-eligible provider pool available; refusing to call"
            )
        if not self.api_key:
            raise MissingAPIKeyError("OPENROUTER_API_KEY not set")
        if self.budget_usd is not None and self.spent_usd >= self.budget_usd:
            raise BudgetExceededError(
                f"Program budget ${self.budget_usd:.2f} exhausted (${self.spent_usd:.4f} spent); "
                "hard stop — Program Owner acknowledgment required to lift"
            )

        res = self.resolve(task_id)
        fallbacks = self._check_diversity(task_id, task, res.model)

        payload: dict[str, Any] = {
            "model": res.model,
            "messages": messages,
            **task.params,
            "provider": {"data_collection": self.registry.settings.data_collection},
            "usage": {"include": True},
        }
        if fallbacks:
            payload["models"] = [res.model, *fallbacks]
        if task.sensitive:
            payload["provider"]["zdr"] = True

        schema = None
        if task.structured_output:
            # Provider-side strict schemas reject anything richer than their
            # dialect (observed live: Azure requires additionalProperties:false
            # throughout). So: embed the schema in the prompt, validate
            # LOCALLY, and repair once — per PRD §6.2. No response_format.
            schema = json.loads(self.registry.resolve_schema_path(task.structured_output).read_text())
            fmt = ("\n\n===== OUTPUT FORMAT (mandatory) =====\n"
                   "Respond with ONLY a single JSON object — no markdown fences, no "
                   "commentary — that validates against this JSON Schema:\n"
                   + json.dumps(schema))
            messages = list(messages)
            if messages and messages[-1].get("role") == "user":
                messages[-1] = {**messages[-1], "content": messages[-1]["content"] + fmt}
            else:
                messages.append({"role": "user", "content": fmt})
            payload["messages"] = messages

        data = self._post(payload)
        content = data["choices"][0]["message"]["content"]
        finish = data["choices"][0].get("finish_reason") or ""
        usages = [data.get("usage") or {}]
        repair_attempts = 0

        output: Any = content
        if schema is not None:
            while True:
                try:
                    output = _extract_json(content)
                    jsonschema.validate(output, schema)
                    break
                except (json.JSONDecodeError, jsonschema.ValidationError, ValueError) as e:
                    if repair_attempts >= 1:
                        # The failed calls still burned real tokens — count them
                        # against the budget even though no artifact results.
                        self.spent_usd += sum(float(u.get("cost", 0.0)) for u in usages)
                        import jsonschema as _js
                        if isinstance(e, _js.ValidationError):
                            detail = (f"[{e.validator}] at $.{'.'.join(str(x) for x in e.absolute_path)}: "
                                      f"{e.message[:400]}")
                        else:
                            detail = f"[{type(e).__name__}] {str(e)[:400]}"
                        if finish == "length":
                            detail += (f" — the model's output was truncated at the token limit; "
                                       f"raise max_tokens for task '{task_id}'")
                        raise StructuredOutputError(
                            f"Task '{task_id}': model output failed schema validation after a repair "
                            f"attempt and may not enter an artifact: {detail}"
                        ) from e
                    repair_attempts += 1
                    repair = dict(payload)
                    if finish == "length":
                        # Output was cut off at the token limit — re-run the ORIGINAL
                        # request with more room, rather than asking the model to
                        # "fix" a truncated JSON blob (which just truncates again).
                        repair["max_tokens"] = min(int(payload.get("max_tokens") or 4096) * 2, 64000)
                    else:
                        repair["messages"] = messages + [
                            {"role": "assistant", "content": content},
                            {"role": "user", "content": "That output failed JSON Schema validation:\n"
                             + str(e)[:1500] + "\nReturn ONLY the corrected JSON object — no fences, no commentary."},
                        ]
                    data2 = self._post(repair)
                    content = data2["choices"][0]["message"]["content"]
                    finish = data2["choices"][0].get("finish_reason") or ""
                    usages.append(data2.get("usage") or {})

        usage = {
            "prompt_tokens": sum(int(u.get("prompt_tokens", 0)) for u in usages),
            "completion_tokens": sum(int(u.get("completion_tokens", 0)) for u in usages),
            "cost": sum(float(u.get("cost", 0.0)) for u in usages),
        }
        model_served = data.get("model", res.model)
        stamp = {
            "task_id": task_id,
            "model_requested": res.model,
            "model_served": model_served,
            "provider": data.get("provider", "openrouter"),
            "params": task.params,
            "request_id": data.get("id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "app_commit": os.environ.get("WORKBENCH_COMMIT", "dev"),
            "registry_version": self.registry.registry_version,
            "prompt_hash": _sha(messages),
            "skill_version": task.skill_version,
            "fallback_history": [] if model_served == res.model else [res.model],
            "input_hash": _sha(input_ref if input_ref is not None else messages),
            "output_hash": _sha(content),
            "resolution_source": res.source,
            "repair_attempts": repair_attempts,
            "cost": {
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
                "usd": float(usage.get("cost", 0.0)),
            },
        }
        jsonschema.validate(stamp, self._stamp_schema)  # dogfood ADR-015 at every call
        self.run_records.append(stamp)
        self.spent_usd += stamp["cost"]["usd"]
        return output, stamp

    def _post(self, payload: dict) -> dict:
        url = f"{self.registry.settings.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last: Exception | None = None
        # Large distillation calls (e.g. the cross-corpus defect pass: ~70k input
        # tokens plus a big structured-output generation) can run well past a
        # minute. A short read timeout there surfaces as a "stuck" request that
        # eventually fails, so allow a generous read window while keeping connect
        # fast to fail quickly on a genuinely unreachable endpoint.
        timeout = httpx.Timeout(300.0, connect=15.0)
        for attempt in range(self.max_attempts):
            try:
                with httpx.Client(transport=self.transport, timeout=timeout) as client:
                    r = client.post(url, json=payload, headers=headers)
                if r.status_code >= 500:
                    last = UpstreamError(f"HTTP {r.status_code}: {r.text[:200]}")
                elif r.status_code >= 400:
                    raise UpstreamError(f"HTTP {r.status_code}: {r.text[:500]}")
                else:
                    try:
                        data = r.json()
                    except ValueError:
                        # HTTP 200 with a malformed/truncated JSON body is a
                        # provider failure, not a value — retry like a 5xx.
                        last = UpstreamError(f"HTTP 200 with malformed JSON body: {r.text[:200]}")
                        self.sleep(2 ** attempt)
                        continue
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
                    if not content:
                        # Null/empty content (e.g., reasoning tokens exhausted the
                        # limit before any final text). A degenerate response is a
                        # failure, not a value — retry like a 5xx.
                        last = UpstreamError("provider returned empty/null message content")
                    else:
                        return data
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last = e
            self.sleep(2**attempt)
        raise UpstreamError(f"OpenRouter call failed after {self.max_attempts} attempts: {last}")
