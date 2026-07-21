"""Gate rules and the ADR-013 waiver taxonomy. There is no generic waiver."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from importlib import resources

import jsonschema


class WaiverPolicy(str, Enum):
    NONWAIVABLE = "nonwaivable"
    PROGRAM_OWNER_WAIVABLE = "program_owner_waivable"
    DEVIATION_ONLY = "deviation_only"


class NonwaivableError(Exception): ...


@dataclass(frozen=True)
class GateRule:
    rule_id: str
    description: str
    waiver_policy: WaiverPolicy
    responsible_role: str
    failure_message: str
    phase: str | None = None

    def as_contract(self) -> dict:
        d = asdict(self)
        d["waiver_policy"] = self.waiver_policy.value
        return d


# The M0 core catalogue. Grows per milestone (ADR-013); the nonwaivable set
# below is the ADR-013 minimum and MUST NOT shrink.
CORE_RULES: list[GateRule] = [
    GateRule(
        "OR-1", "Mode-gated change control: change-class moves finalize only per mode rules",
        WaiverPolicy.NONWAIVABLE, "system",
        "A change-class move cannot be finalized outside redesign-mode governance.", "P3",
    ),
    GateRule(
        "OR-4", "Human disposition of every normative finding",
        WaiverPolicy.NONWAIVABLE, "system",
        "A finding with an open normative flag cannot reach final status.", None,
    ),
    GateRule(
        "ADR-012", "Reviewer independence: two-person rules need two verified identities",
        WaiverPolicy.NONWAIVABLE, "system",
        "A solo-operated audit is non_gating_demo_only and cannot satisfy this gate.", "P2",
    ),
    GateRule(
        "SCHEMA-RATIFIED", "Ratified artifacts must validate against their contracts",
        WaiverPolicy.NONWAIVABLE, "system",
        "An artifact that fails contract validation cannot be ratified.", None,
    ),
    GateRule(
        "P1-SECOND-CENSUS", "C-ADV2 second census on a domain's first executed contract",
        WaiverPolicy.PROGRAM_OWNER_WAIVABLE, "Program Owner",
        "Second census not run; Program Owner may waive with logged rationale.", "P1",
    ),
    GateRule(
        "P2-FIDELITY-THRESHOLDS", "Fidelity audit thresholds fixed before the audit runs",
        WaiverPolicy.DEVIATION_ONLY, "Distillation Lead",
        "Audit thresholds must be pre-registered; post-hoc thresholds are a logged deviation.", "P2",
    ),
]


def _gate_schema() -> dict:
    with resources.files("workbench.contracts").joinpath("gate_rule.schema.json").open() as f:
        return json.load(f)


def validate_catalogue(rules: list[GateRule] | None = None) -> None:
    schema = _gate_schema()
    for r in rules or CORE_RULES:
        jsonschema.validate(r.as_contract(), schema)


def waive(rule: GateRule, *, by_name: str, by_role: str, rationale: str) -> dict:
    """Waive a single rule. Raises for nonwaivable rules — no generic override exists."""
    if rule.waiver_policy is WaiverPolicy.NONWAIVABLE:
        raise NonwaivableError(f"Gate rule {rule.rule_id} is nonwaivable: {rule.failure_message}")
    if not rationale.strip():
        raise ValueError("A waiver requires a rationale")
    if rule.waiver_policy is WaiverPolicy.PROGRAM_OWNER_WAIVABLE and by_role != "Program Owner":
        raise PermissionError(f"Gate rule {rule.rule_id} is waivable only by the Program Owner")
    return {
        "type": "waiver" if rule.waiver_policy is WaiverPolicy.PROGRAM_OWNER_WAIVABLE else "gate_exception",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decided_by": {"name": by_name, "role": by_role},
        "decision": f"Waive gate rule {rule.rule_id}",
        "rationale": rationale,
    }
