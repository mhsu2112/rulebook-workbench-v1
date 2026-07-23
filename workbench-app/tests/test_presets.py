"""Tests for model presets — especially that a preset can NEVER waive the
independence (must-differ-family) or privacy (sensitive→eligible) guarantees.
"""
from workbench import presets
from workbench.presets import family


def test_recommended_is_no_overrides(registry):
    assign, notes = presets.resolve_preset(registry, "recommended")
    assert assign == {} and notes == []
    assert presets.detect_active(registry, {}) == {"preset": "recommended", "lab": None}


def test_lab_first_keeps_independence(registry):
    for lab in ("anthropic", "openai", "google"):
        assign, notes = presets.resolve_preset(registry, "lab", lab)
        # second census must differ in family from the extractor & defect detector
        ex_fam = family(assign.get("distill_extract") or registry.task("distill_extract").default_model)
        df_fam = family(assign.get("defect_detect") or registry.task("defect_detect").default_model)
        assert family(assign["second_census"]) not in {ex_fam, df_fam}, lab
        # the effect-classifier must not be the family that drafts the operations
        op_fam = family(assign.get("operation_propose") or registry.task("operation_propose").default_model)
        assert family(assign["effect_classify_assist"]) != op_fam, lab
        # heavy reasoning actually runs on the chosen lab
        assert family(assign["distill_extract"]) == ({"anthropic": "anthropic", "openai": "openai", "google": "google"}[lab])


def test_lab_first_anthropic_moves_checks_off_anthropic(registry):
    assign, notes = presets.resolve_preset(registry, "lab", "anthropic")
    assert family(assign["distill_extract"]) == "anthropic"
    assert family(assign["second_census"]) != "anthropic"
    assert family(assign["effect_classify_assist"]) != "anthropic"
    assert any("independent" in n for n in notes)


def test_open_weight_keeps_sensitive_on_eligible_default(registry):
    assign, notes = presets.resolve_preset(registry, "open")
    # sensitive transcript tasks must NOT be routed to open-weight families
    for tid in ("intake_interview", "purpose_synthesis", "mandate_synthesis"):
        assert tid not in assign, tid                      # kept on eligible default
    assert any("privacy-eligible" in n for n in notes)
    # non-sensitive heavy tasks do go open, and independence still holds
    assert family(assign["second_census"]) not in {family(assign["distill_extract"]), family(assign["defect_detect"])}


def test_cost_optimized_independence_holds(registry):
    assign, _ = presets.resolve_preset(registry, "cost")
    assert family(assign["second_census"]) not in {family(assign["distill_extract"]), family(assign["defect_detect"])}
    assert family(assign["effect_classify_assist"]) != family(assign["operation_propose"])


def test_detect_active_roundtrips(registry):
    for preset, lab in [("cost", None), ("open", None), ("lab", "anthropic"),
                        ("lab", "openai"), ("lab", "google")]:
        assign, _ = presets.resolve_preset(registry, preset, lab)
        assert presets.detect_active(registry, assign) == {"preset": preset, "lab": lab}
    # a single manual tweak off a preset reads as 'custom'
    assign, _ = presets.resolve_preset(registry, "cost")
    assign["distill_extract"] = "anthropic/claude-opus-4.8"
    assert presets.detect_active(registry, assign)["preset"] == "custom"


def test_lab_first_requires_valid_lab(registry):
    import pytest
    with pytest.raises(ValueError):
        presets.resolve_preset(registry, "lab", None)
