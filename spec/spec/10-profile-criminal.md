# Criminal-Law Profile — Pointer

| | |
|---|---|
| **Status** | 0.1 |
| **Layer** | L1 |
| **Source of truth** | StatuteDistill PRD v0.2 (entire document) — the DC CCRC reference implementation |

The criminal-law profile is the reference implementation and lives upstream in
`statute-distill_lex-allium`. This repo does not restate it. Its role here:

- It is the **existence proof** for the method (the CCRC's ~70 reports as a
  hand-authored divergence log; M0 validation of the fifteen-primitive basis).
- Its artifacts (as-built/intended specs, authority graph, gold findings) are
  the model for the regulatory profile's artifact shapes.
- Divergences between how the regulatory profile (spec/20) and the criminal
  profile handle a shared concept MUST be intentional and ADR-logged, not
  accidental.
