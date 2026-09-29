# Regulatory Domain Profile

| | |
|---|---|
| **Status** | 0.1 |
| **Layer** | L1 (see governance/SPEC-HIERARCHY.md) |
| **Governs** | How the core calculus applies to regulatory corpora (statutes + regulations + reporting instructions + guidance + manuals + enforcement evidence) — the profile used by spec/30 and both MVPs |
| **Key ADRs** | ADR-003 (product boundary), ADR-004 (operations), ADR-005 (`fill_gap`/`INTRODUCE`), ADR-008 (`baseline_set_for`) |

## 1. Product boundary (ADR-003)

The workbench is an **analytical workbench with drafting support**. It
produces: derived/target blueprints, registers, crosswalks, and *proposed*
consolidated drafts — advisory working papers addressed to an Authority.
It never produces operative legal text; promulgation, repeal, and issuance
are the Authority's acts (instruction set, Phase 5). This preserves PRD
non-goal NG2 while permitting Phase 4.

## 2. Operation set (ADR-004)

### 2.1 Selected core primitives

| Family | Selected | Regulatory reading |
|---|---|---|
| Structure | `MERGE` · `SPLIT` · `INTRODUCE`* · `REPEAL` · `RELOCATE` | Instruments and provisions instead of offenses |
| Terminology | `CANONICALIZE-DEFINITION` · `DEFINE-TERM` · `SUBSTITUTE-TERM` | Unchanged semantics |
| Liability | `NORMALIZE-ELEMENTS` · `FACTOR-EXCEPTION` | Elements = who/must/what/when/threshold/exception tables |
| General Part | `ELEVATE-GENERAL-RULE` · `RESOLVE-CROSS-REFERENCE` | "General part" = definitions/appliability sections shared across instruments |

*`INTRODUCE` is selected but usage-constrained in the refactor pass — §2.3.

### 2.2 Exclusions and extensions

- **Excluded (criminal-specific):** `ASSIGN-MENS-REA` (no mens-rea layer in
  regulatory obligations as modeled) and `RELATE-OFFENSE` as named; its
  relational function is carried by a typed `RELATE-OBLIGATION` edge
  (`specializes` / `shares_term` / `coordinates_with`) — a rename-level
  mapping, same semantics, recorded here per the L1 contract.
- **Extension by specialization:** **`RECALIBRATE`** ⊂ `REGRADE`. Adjusts a
  quantitative or scoping parameter of an existing obligation: threshold,
  ratio level, frequency, deadline, applicability line. Same profile as its
  parent: highest normative load, per-instance effect classification, and
  (per spec/30) Principal-level disposition. `REGRADE`'s penalty-class
  semantics do not carry over; only its role as "the parameter-changing,
  maximally normative move" does.
- No other operations exist in this profile. A needed move that cannot be
  expressed is a logged finding and a proposed ADR — never an ad-hoc edit.

### 2.3 The `fill_gap` / `INTRODUCE` rule (ADR-005)

In the **refactor pass**, `INTRODUCE` may carry effect class `fill_gap` only
when `baseline_set_for` (§3) establishes that the duty *already exists* for
the relevant (actor, activity, jurisdiction, as-of) cell — e.g., stated in a
controlling instrument the blueprint had only implicitly captured — and the
operation merely makes it explicit. Every instance is human-reviewed.
Where the baseline does not establish the duty, the honest effect class is
`change` (or `unresolved` where the baseline itself is indeterminate), and
the move parks to the Redesign Backlog. In the **redesign pass**, `INTRODUCE`
operates freely under `change`-class governance (objective hook + Principal
disposition).

## 3. `baseline_set_for` — the regulatory authority baseline (ADR-008)

Effect classification's safety claim — that `clarify`, `fill_gap`, and
`change` are distinguishable — cannot rest on a structural diff. The profile
therefore defines a baseline resolver, the regulatory analog of the PRD §8
case-law authority graph:

```
baseline_set_for(target, actor, activity, jurisdiction, as_of_date)
  → the set of provisions/expectations operative for that cell, each tagged:
```

| Resolution axis | What it must resolve |
|---|---|
| Hierarchy & delegation | Statute → regulation → instruction/guidance chains; which issuer had authority, via which delegation |
| Applicability | Actor class, activity, sector, size thresholds, effective intervals |
| Status controls | Amendments, supersession, rescission, expiry — and litigation status: stays, injunctions, vacaturs (the confident-falsehood class of error) |
| Evidentiary ceiling | Per source role: operative law · authoritative interpretation · nonbinding guidance · enforcement evidence. Enforcement evidence NEVER independently establishes an operative duty; proposed rules never anchor current-law claims |
| Live conflicts | Where two unresolved live sources conflict for the same cell, the baseline returns *both*, marked conflicting — it does not adjudicate |

Classification rule: an operation's effect class is computed by comparing its
output against `baseline_set_for` for every cell it touches. `codify` = the
baseline already requires it; `clarify` = the baseline supports it but
ambiguously; `fill_gap` = per §2.3; `change` = the baseline requires
something else or nothing. An indeterminate baseline yields `unresolved`,
which routes like `change` (park or Principal), never like `clarify`.

**Implementation status:** specification only. The resolver is built in the
engine repository (with the schema/invariant set from
`scoping-protocol-v0.2.md` §9 as its spec). Until it exists, Phase 3 effect
classification is performed by humans applying this section's rules, with the
claim-level verifier records as evidence — and that manual posture is a
stated limitation in any output.

## 4. Corpus machinery (imported)

Scope contracts, censuses, evidence-policy axes, adversarial completeness
(C-ADV1/C-ADV2), catalog maintenance: governed by `scoping-protocol-v0.2.md`
(currently in the statute-distill repo; candidate for relocation here — open
item in DECISIONS.md backlog). The instruction set's Phases 0–1 bind to it.
