# Core Calculus — Index (pinned upstream)

| | |
|---|---|
| **Status** | 0.1 |
| **Layer** | L0 (see governance/SPEC-HIERARCHY.md) |
| **Source of truth** | StatuteDistill PRD v0.2 §§7–10 (`statute-distill_lex-allium/statutedistill-prd-v0.2.md`), pinned |
| **Rule** | This file is an index, not a copy. It exists so this repo's documents can cite core concepts stably without duplicating (and drifting from) the PRD. Change the PRD, then bump the pin here — never fork the content. |

## What the core defines (and profiles may not redefine)

- **The fifteen primitives** (PRD §7.2): Structure — `MERGE` · `SPLIT` ·
  `INTRODUCE` · `REPEAL` · `RELOCATE` · `RELATE-OFFENSE`; Terminology —
  `CANONICALIZE-DEFINITION` · `DEFINE-TERM` · `SUBSTITUTE-TERM`; Liability —
  `NORMALIZE-ELEMENTS` · `ASSIGN-MENS-REA` · `FACTOR-EXCEPTION`; Penalty —
  `REGRADE`; General Part — `ELEVATE-GENERAL-RULE` · `RESOLVE-CROSS-REFERENCE`.
  Each carries operands, arity, inverse, scope, triggering diagnostics, and
  normative load.
- **Effect classes** (PRD §7.3): `codify` · `clarify` · `fill_gap` · `change` —
  determined per-instance by diffing against an authority baseline, never
  per-operation-type.
- **Invariants** (PRD §7.4) and the compiler-pass pipeline: diagnose → operate
  → validate → classify.
- **Normative flag machinery** (PRD §9): typed kind × disposition state, with
  reviewer identity, timestamp, rationale.
- **Claim-level verification** (PRD §10): claim, source span, support type,
  authority type, as-of validity, verifier status.

## What profiles may do (L1 contract)

- **SELECT** the subset of primitives applicable to their domain, with the
  exclusion list stated.
- **EXTEND** by declared mapping to a core primitive (specialization) or, with
  explicit justification, as a new primitive proposed upstream via ADR.
- **PARAMETERIZE** the baseline function their effect classification uses
  (criminal: statute + case-law authority graph, PRD §8; regulatory:
  `baseline_set_for`, spec/20 §3).
- Never: alter effect-class semantics, weaken the normative-flag gate, or
  reclassify a primitive's normative load downward.
