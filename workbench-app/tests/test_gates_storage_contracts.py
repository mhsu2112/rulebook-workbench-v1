import json
from importlib import resources

import jsonschema
import pytest

from workbench import gates, storage


# ---------------- gates (ADR-013) ----------------

def test_catalogue_validates_against_contract():
    gates.validate_catalogue()


def test_nonwaivable_rules_cannot_be_waived():
    for rule in gates.CORE_RULES:
        if rule.waiver_policy is gates.WaiverPolicy.NONWAIVABLE:
            with pytest.raises(gates.NonwaivableError):
                gates.waive(rule, by_name="Anyone", by_role="Program Owner", rationale="please")


def test_adr013_minimum_nonwaivable_set_present():
    nonwaivable = {r.rule_id for r in gates.CORE_RULES
                   if r.waiver_policy is gates.WaiverPolicy.NONWAIVABLE}
    assert {"OR-1", "OR-4", "ADR-012", "SCHEMA-RATIFIED"} <= nonwaivable


def test_waivable_rule_produces_logged_record():
    rule = next(r for r in gates.CORE_RULES if r.rule_id == "P1-SECOND-CENSUS")
    rec = gates.waive(rule, by_name="Mike Hsu", by_role="Program Owner", rationale="budget-gated")
    assert rec["type"] == "waiver" and rec["rationale"] == "budget-gated"
    with pytest.raises(PermissionError):
        gates.waive(rule, by_name="X", by_role="Distillation Lead", rationale="nope")
    with pytest.raises(ValueError):
        gates.waive(rule, by_name="Mike Hsu", by_role="Program Owner", rationale="  ")


# ---------------- storage (ADR-016) ----------------

def test_store_split_and_gitignore(tmp_path):
    pdir = storage.init_program(tmp_path, "demo")
    assert (pdir / "governed").is_dir() and (pdir / "restricted").is_dir()
    assert storage.GITIGNORE_LINE in (tmp_path / ".gitignore").read_text()
    storage.init_program(tmp_path, "demo2")  # idempotent, no duplicate line
    assert (tmp_path / ".gitignore").read_text().count(storage.GITIGNORE_LINE) == 1


def test_decision_log_append_and_validation(tmp_path):
    pdir = storage.init_program(tmp_path, "demo")
    entry = {
        "entry_id": "DL-001", "timestamp": "2026-07-18T00:00:00Z", "type": "ratification",
        "decided_by": {"name": "Mike Hsu", "role": "Program Owner"},
        "decision": "Ratify X", "rationale": "because",
    }
    storage.append_decision(pdir, entry)
    assert storage.read_decisions(pdir) == [entry]
    with pytest.raises(jsonschema.ValidationError):
        storage.append_decision(pdir, {"entry_id": "nope"})
    assert len(storage.read_decisions(pdir)) == 1  # invalid entry never landed


# ---------------- contracts (ADR-015 base set) ----------------

def test_all_base_contracts_are_valid_json_schemas():
    names = ["provenance_stamp", "decision_log_entry", "manifest", "gate_rule"]
    for name in names:
        with resources.files("workbench.contracts").joinpath(f"{name}.schema.json").open() as f:
            schema = json.load(f)
        jsonschema.Draft202012Validator.check_schema(schema)


def test_manifest_contract_accepts_minimal_frozen_manifest():
    with resources.files("workbench.contracts").joinpath("manifest.schema.json").open() as f:
        schema = json.load(f)
    doc = {
        "program_id": "aml-program-rules-refactor-demo",
        "manifest_version": "0.1", "frozen": True,
        "frozen_at": "2026-07-18T00:00:00Z", "content_hash": "sha256:abc",
        "items": [{"item_id": "31cfr1020.210", "title": "AML program requirements (banks)",
                    "issuer": "FinCEN", "family": "program_rules", "status": "live",
                    "locator": "31 CFR 1020.210"}],
    }
    jsonschema.validate(doc, schema)
