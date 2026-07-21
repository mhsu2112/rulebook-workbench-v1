# Rulebook Workbench

**The Foundry's system for consolidating and redesigning regulatory rulebooks:
Legacy Rulebook → Derived Blueprint → Target Blueprint → Consolidated Rulebook.**

This repository is the *governing materials* for the workbench — specifications,
program instructions, interface mechanics (skills), data contracts (schemas),
and their evaluation suites. It is the single place where terminology, operations,
and governance rules are kept mutually consistent.

## What lives where

| Path | Contents | Controls |
|---|---|---|
| `governance/SPEC-HIERARCHY.md` | The layer model: which document governs what, and how conflicts resolve | Everything in this repo |
| `governance/DECISIONS.md` | Append-only ADR log; every cross-document conflict resolution is recorded here | — |
| `spec/00-core-calculus.md` | Index of the portable core (primitives, effect classes, invariants, normative-flag machinery), pinned to its upstream source | Core semantics |
| `spec/10-profile-criminal.md` | Pointer to the criminal-law reference implementation (StatuteDistill / DC CCRC) | Criminal profile |
| `spec/20-profile-regulatory.md` | The regulatory domain profile: operation subset + extensions, `baseline_set_for`, product boundary | Regulatory profile |
| `spec/30-instruction-set.md` | The dual-mode program instructions (Phases 0–5) | Program execution |
| `spec/40-prototype-prd.md` | PRD for the workbench app prototype (per-task model routing via a single OpenRouter integration) | Prototype product scope |
| `skills/purpose-elicitation/` | The Phase 0 interview mechanic | P0.1 / P0.9 seeding |
| `schemas/` | Typed data contracts (Purpose Statement, Mandate) | Artifact structure |
| `evals/` | Behavioral test cases for skills and, later, pipeline stages | Regression gates |

## Relationship to other repositories

- **`04-policy-sludge-code/statute-distill_lex-allium`** — the research and
  reference-implementation repository: the StatuteDistill PRD, the DC CCRC
  criminal-law reference implementation, and the BSA/AML corpus/census work.
  This repo *imports* its core calculus (pinned; see `spec/00`) and does not
  modify it. The BSA/AML census remains there until the refactor MVP formally
  adopts it under a frozen manifest.
- **Engine code** (parsers, graph store, `baseline_set_for` implementation,
  T0–T8 build) is *not* in this repo. It belongs in a dedicated code
  repository with its own `pyproject.toml`, tests, and `make check`, created
  at T0. Keeping governing materials and engine code separate means spec
  iteration never breaks builds and vice versa.

## Versioning convention (resolves the "v1"/"v0.2" confusion)

- **Documents** carry semantic versions in their headers (`0.3`, `1.0`), bumped
  on substantive change, with superseded versions retained in git history —
  not as parallel files.
- **The product milestone** ("workbench v1" = dual-mode: refactor + redesign)
  is named only here in the README and in `governance/DECISIONS.md` (ADR-002).
  Documents never call themselves "v1."
- Program-generated artifacts (Scope Contracts, manifests, blueprints) are
  versioned per the instruction set and stamped with contract version +
  manifest hash.

## Status

Scaffolded 2026-07-18 in response to the Codex cross-review (see
`governance/DECISIONS.md` ADR-001–ADR-010 for what was adopted and how).
Current MVP pairing: refactor MVP on BSA/AML; redesign MVP on liquidity.
