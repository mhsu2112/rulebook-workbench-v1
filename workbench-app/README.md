# workbench-app

Code repository for the Rulebook Workbench prototype — the M0 walking
skeleton per `../rulebook-workbench/spec/40-prototype-prd.md` (which governs;
this README is operational only).

## What exists at M0

- **Model router** (`src/workbench/router.py`): the single OpenRouter
  integration. Per-task model selection from `models.yaml` with resolution
  order program-override → user-toggle → default; model-diversity
  enforcement against *actually-used* runs (G5); fail-closed privacy for
  sensitive tasks (ADR-016); schema-validated structured outputs; a
  provenance stamp on every call, itself schema-validated (G4/ADR-015);
  retries + cross-model fallbacks; per-program cost meter with hard stop.
- **Gate catalogue seed** (`src/workbench/gates.py`): the ADR-013 waiver
  taxonomy with the nonwaivable minimum (OR-1, OR-4, ADR-012,
  SCHEMA-RATIFIED) — and no generic waive function anywhere.
- **Storage** (`src/workbench/storage.py`): the governed/restricted store
  split with automatic .gitignore coverage, and the schema-validated
  append-only decision log.
- **Base contracts** (`src/workbench/contracts/`): provenance stamp,
  decision-log entry, frozen manifest, gate rule (the ADR-015 M0 set).
- **Tests**: 20 offline tests (mocked transport). `make check` must be green.

## Setup

```
pip install -e ".[dev]"
make check                 # offline test suite
cp .env.example .env       # add your OPENROUTER_API_KEY
make smoke                 # one live routed, stamped call (~fractions of a cent)
make models                # verify models.yaml IDs against the live catalog
```

## Layout

```
models.yaml                task registry (D4 assignments, verified 2026-07-18)
src/workbench/             router, gates, storage, config, contracts/
tests/                     offline suite
scripts/                   smoke.py (live call), check_models.py (catalog check)
programs/                  created at runtime; restricted/ stores are gitignored
```

## Milestone status

**M0 — complete** (2026-07-18): router, gates, storage, contracts; live smoke
call verified by the owner.

**M1 — built, live checks pending:** the web app (`make app`, then open
http://localhost:8000). Program creation → interview chat (skill runs
verbatim as system prompt, D5; transcripts stored in `restricted/`, ADR-016)
→ typed Purpose Statement synthesis (schema-enforced structured output) →
⚖ ratification with rationale, written to the append-only decision log.
Model Settings tab = the per-task toggle (overrides persisted, stamped, and
diversity-checked at call time). 27 offline tests green.

M1 exit items needing a live key on the owner's machine:
- [ ] `make evals` — the ADR-011 eval suite (12 refactor-applicable cases,
      model-played personas, judged transcripts; results land in `evals-out/`)
- [ ] One real interview run end-to-end in the browser, ratified

Next: M2 (manifest import + freeze for the AML program-rules corpus).
