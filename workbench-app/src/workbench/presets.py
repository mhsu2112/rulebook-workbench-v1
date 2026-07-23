"""Model presets (spec/54 follow-on): one-click strategies that bulk-set the
per-task model overrides the router already reads.

Four presets a non-technical user can reason about:
  • recommended       — the curated defaults (no overrides)
  • cost              — cheapest capable model per task
  • open              — prefer the open-weight catalog (Nemotron/Kimi/Qwen)
  • lab:<anthropic|openai|google> — one house, everywhere it's allowed

A preset is NOT a mode — it just writes user_overrides in bulk. Non-waivable
guarantees still hold and are enforced HERE, not merely at call time:
  • independence: any task with a must_differ_family_from rule (second census),
    plus the effect-classifier by design, is kept off the family it must differ
    from — moved to an allowed family, with a note.
  • privacy: a sensitive task (transcripts) is only ever assigned to a
    ZDR-capable major-lab family; otherwise it keeps its privacy-eligible
    default, with a note. (The router's fail-closed remains the backstop.)
"""
from __future__ import annotations

from typing import Optional


def family(model_id: str) -> str:
    return (model_id or "").split("/")[0]


# ZDR-capable major closed labs — the only families a preset will route a
# sensitive (transcript-bearing) task to.
ELIGIBLE_SENSITIVE = {"anthropic", "openai", "google"}

# Per-lab model choices. Anthropic has no distinct cheap tier → Sonnet serves.
# NOTE: google/gemini-3.1-pro slug should be confirmed with `make models`.
LAB = {
    "anthropic": {"strong": "anthropic/claude-opus-4.8", "mid": "anthropic/claude-sonnet-5", "cheap": "anthropic/claude-sonnet-5"},
    "openai":    {"strong": "openai/gpt-5.6-sol",        "mid": "openai/gpt-5.6-sol",        "cheap": "openai/gpt-5.6-luna"},
    "google":    {"strong": "google/gemini-3.1-pro",     "mid": "google/gemini-3.1-pro",     "cheap": "google/gemini-3.1-flash-lite"},
}
ALT_LAB = {"anthropic": "openai", "openai": "anthropic", "google": "anthropic"}

OPEN = ["moonshotai/kimi-k2", "qwen/qwen3-235b-a22b", "nvidia/nemotron-4-340b-instruct"]

# Visible, preset-controlled tasks and their complexity tier.
TIER = {
    "purpose_synthesis": "heavy", "mandate_synthesis": "heavy", "distill_extract": "heavy",
    "defect_detect": "heavy", "operation_propose": "heavy", "redesign_propose": "heavy",
    "misalign_detect": "heavy", "source_discovery": "heavy", "second_census": "heavy",
    "effect_classify_assist": "heavy",
    "intake_interview": "conversational", "discovery_questions": "conversational",
    "blueprint_summary": "light", "target_summary": "light",
}
# Pure plumbing / eval — hidden from the selector, left on their defaults.
HIDDEN = {"distill_focus", "claim_verify", "render_prose", "eval_respondent", "eval_judge"}

COST = {"heavy": "anthropic/claude-sonnet-5",
        "conversational": "google/gemini-3.1-flash-lite",
        "light": "google/gemini-3.1-flash-lite"}

# Open-weight assignment chosen so the independence tasks land on a family
# distinct from the tasks they must differ from (kimi≠qwen≠nemotron).
OPEN_MAP = {
    "distill_extract": "qwen/qwen3-235b-a22b", "defect_detect": "moonshotai/kimi-k2",
    "second_census": "nvidia/nemotron-4-340b-instruct",
    "operation_propose": "qwen/qwen3-235b-a22b", "effect_classify_assist": "nvidia/nemotron-4-340b-instruct",
    "redesign_propose": "moonshotai/kimi-k2", "misalign_detect": "qwen/qwen3-235b-a22b",
    "source_discovery": "nvidia/nemotron-4-340b-instruct",
    "purpose_synthesis": "moonshotai/kimi-k2", "mandate_synthesis": "moonshotai/kimi-k2",
    "intake_interview": "qwen/qwen3-235b-a22b", "discovery_questions": "qwen/qwen3-235b-a22b",
    "blueprint_summary": "moonshotai/kimi-k2", "target_summary": "qwen/qwen3-235b-a22b",
}

PRESETS = ("recommended", "cost", "open", "lab")
LABS = ("anthropic", "openai", "google")


def _base(preset: str, lab: Optional[str]) -> dict:
    out: dict = {}
    for tid, tier in TIER.items():
        if preset == "recommended":
            continue
        if preset == "cost":
            out[tid] = COST[tier]
        elif preset == "open":
            out[tid] = OPEN_MAP.get(tid, OPEN[0])
        elif preset == "lab":
            key = "strong" if tier == "heavy" else "mid" if tier == "conversational" else "cheap"
            out[tid] = LAB[lab][key]
    return out


def _alternate(preset: str, lab: Optional[str], forbidden: set) -> Optional[str]:
    """An allowed-family model suited to the preset, avoiding `forbidden` families."""
    if preset == "lab":
        # try the designated alternate lab, then any other lab.
        for cand_lab in [ALT_LAB[lab]] + [l for l in LABS if l != lab]:
            m = LAB[cand_lab]["strong"]
            if family(m) not in forbidden:
                return m
    if preset == "open":
        for m in OPEN:
            if family(m) not in forbidden:
                return m
    if preset == "cost":
        for m in ("openai/gpt-5.6-luna", "google/gemini-3.1-flash-lite", "anthropic/claude-sonnet-5"):
            if family(m) not in forbidden:
                return m
    # last resort: any lab strong model not forbidden
    for l in LABS:
        if family(LAB[l]["strong"]) not in forbidden:
            return LAB[l]["strong"]
    return None


def resolve_preset(registry, preset: str, lab: Optional[str] = None) -> tuple[dict, list]:
    """Return (overrides, notes) for a preset, enforcing independence + privacy."""
    if preset == "lab" and lab not in LABS:
        raise ValueError("Lab-first requires a lab (anthropic | openai | google)")
    assign = _base(preset, lab)
    notes: list[str] = []

    def fam_of(tid: str) -> str:
        return family(assign.get(tid) or (registry.task(tid).default_model if tid in registry.tasks else ""))

    # Enforce independence (hard must_differ rules + the effect-classifier by design).
    for tid in list(assign):
        if tid not in registry.tasks:
            continue
        task = registry.task(tid)
        forbidden = {fam_of(o) for o in task.must_differ_family_from}
        if tid == "effect_classify_assist":
            forbidden.add(fam_of("operation_propose"))  # must not grade its own drafter
        forbidden.discard("")
        if forbidden and family(assign[tid]) in forbidden:
            alt = _alternate(preset, lab, forbidden)
            if alt:
                assign[tid] = alt
                notes.append(f"{tid}: kept independent — moved off {sorted(forbidden)} to {alt}")

    # Enforce privacy: sensitive tasks only on ZDR-capable major labs, else default.
    for tid in list(assign):
        if tid in registry.tasks and registry.task(tid).sensitive \
                and family(assign[tid]) not in ELIGIBLE_SENSITIVE:
            del assign[tid]
            notes.append(f"{tid}: sensitive (transcripts) — kept on the privacy-eligible default")

    return assign, notes


def detect_active(registry, overrides: dict) -> dict:
    """Which preset (if any) the current overrides correspond to. 'custom' once a
    single dial is changed off a preset; 'recommended' when there are none."""
    overrides = overrides or {}
    if not overrides:
        return {"preset": "recommended", "lab": None}
    for preset, lab in [("cost", None), ("open", None),
                        ("lab", "anthropic"), ("lab", "openai"), ("lab", "google")]:
        assign, _ = resolve_preset(registry, preset, lab)
        if assign == overrides:
            return {"preset": preset, "lab": lab}
    return {"preset": "custom", "lab": None}
