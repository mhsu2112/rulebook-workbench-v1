# Specification Hierarchy

| | |
|---|---|
| **Status** | 0.1 — adopted at repo creation (ADR-001) |
| **Purpose** | Make the document set one executable, internally consistent system: which layer defines what, which document wins a conflict, and where domain variation is allowed |

## The layer model

```
L0  CORE CALCULUS          primitives (15) · effect classes · invariants ·
                           normative flags & disposition machine · claim-level
                           verification
                           Source: StatuteDistill PRD §§7–10 (pinned upstream).
                           Index: spec/00-core-calculus.md
        │  profiles may SELECT a subset and EXTEND via declared mappings;
        │  they may never redefine core semantics
        ▼
L1  DOMAIN PROFILES        criminal (spec/10 → PRD, reference implementation)
                           regulatory (spec/20 — operation subset, extensions
                           incl. RECALIBRATE, baseline_set_for, product boundary)
        ▼
L2  PROGRAM INSTRUCTIONS   spec/30-instruction-set.md — modes, phases, gates,
                           roles, routing tables. Binds a profile to a program.
        ▼
L3  INTERFACE MECHANICS    skills/ (elicitation protocols) and schemas/ (typed
                           artifact contracts). Implement L2 steps; may add
                           conduct detail, never new governance authority.
```

## Precedence rules

1. Within a layer, the document named above is authoritative for that layer's
   subject matter.
2. Across layers, the *lower-numbered* layer wins on semantics (a profile
   cannot redefine an effect class; an instruction set cannot redefine a
   profile's operation), and the *higher-numbered* layer wins on procedure
   (the PRD does not dictate phase gates for regulatory programs).
3. Across repositories: StatuteDistill PRD controls L0 and the criminal L1
   profile. This repository controls the regulatory L1 profile and everything
   at L2–L3 for regulatory programs.
4. Conflicts are never resolved silently — STOP and file an ADR
   (see AGENTS.md rule 1).

## Standing conflict resolutions

- **Operative-text boundary (ADR-003).** The PRD's non-goal "producing
  operative legal text" (NG2) stands *and* Phase 4 stands: Phase 4 produces
  **proposed consolidated drafts** — advisory working papers for an Authority —
  never operative instruments. The workbench's product boundary is
  *analytical workbench + drafting support*; promulgation is the Authority's
  act (instruction set Phase 5). Any statement implying the workbench issues
  operative text is a defect.
- **Primitive-set extension (ADR-004).** The core set remains fifteen.
  The regulatory profile SELECTS the domain-applicable subset (excluding
  criminal-specific primitives such as `ASSIGN-MENS-REA`) and EXTENDS via
  declared mapping: `RECALIBRATE` is a domain specialization of `REGRADE`
  (same arity pattern, same highest normative load, same routing). Profile
  extensions are recorded in spec/20 §2 with their core mapping or an explicit
  justification as a new primitive; unmapped ad-hoc operations are prohibited.
- **Versioning (ADR-002).** Documents carry semver headers; the "v1" product
  milestone name appears only in README/ADRs. No document calls itself v1.
