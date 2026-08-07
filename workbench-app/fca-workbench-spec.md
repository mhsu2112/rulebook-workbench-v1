# FCA Reporting Workbench — Domain Pack Specification

**Status:** draft v0.1 for review
**Author:** drafted for M. Hsu, 30 July 2026
**Governs:** the FCA/PRA Transaction and Post-Trade Reporting Harmonisation Taskforce build
**Relationship to existing specs:** extends `spec/40-prototype-prd.md` and the Rulebook Consolidation Instruction Set. Where this document and the PRD conflict on the governance core, the PRD governs. This document governs the domain layer only.

---

## 1. Purpose

Build an FCA-specific configuration of the Rulebook Workbench for the Transaction and Post-Trade Reporting Harmonisation Taskforce, capable of supporting the Taskforce's work on **harmonisation, de-duplication and streamlining** across UK MiFIR, UK EMIR and UK SFTR.

**Design constraint, load-bearing throughout:** the Taskforce has made no decision on the priority or sequencing of the three levers. The tool must therefore be sequence-agnostic. It must not encode an ordering, and its most valuable single function is to show the Taskforce **what each candidate ordering costs**.

---

## 2. Evidence base: what the existing run already establishes

The programme `uk-derivatives-reporting` exists in the current Workbench, ratified in refactor mode, with an 18-item frozen manifest covering UK MiFIR, UK EMIR, UK SFTR, the retained RTS/ITS, SUP 17/17A, the FCA and Bank validation-rule guidance, the EU Exit SIs, the PRA Rulebook cross-references and the ESMA legacy material. Four defect-detection runs produced **71 findings**; four have been worked into **7 proposed operations** at a cost of roughly $0.25 per finding.

This run is the strongest argument both *for* the approach and *for* the fork, because it demonstrates each precisely.

### 2.1 What it proves works

The generic D1–D10 taxonomy found real, specific, citable cross-regime divergence in the actual UK corpus:

| Code | Count | Representative finding |
|---|---|---|
| D2 divergent definitions | 11 | `financial counterparty` differs between UK SFTR and the EMIR onshoring SI; `trade repository` differs across families; `compression` differs between RTS 22 and EMIR RTS |
| D3 duplicate provisions | 12 | errors-and-omissions notification duty stated separately in MiFIR, EMIR and SFTR guidance; the clearing-day rule duplicated across EMIR and SFTR RTS |
| D4 undefined material term | 10 | FC/NFC undefined despite driving who reports; `reportable financial instrument` undefined in MiFIR guidance |
| D10 applicability inconsistency | 8 | NFCs in scope under EMIR, out of scope under SFTR; MiFIR disapplied to SFTs while an SFT flag persists in RTS 22 |
| D1 conflicting requirements | 2 | MiFIR "close of the following working day" vs EMIR/SFTR "working day following"; FC-facing-NFC single-side vs both-report default |

The governance behaved correctly under stress. `OP-001` — splitting `financial counterparty` into regime-scoped canonical entries — was drafted `unresolved` and **parked**, because canonicalising across two regimes whose enumerations differ is not meaning-preserving. Two findings landed in `cannot_express`, both because the whitelist can unify the drawing but cannot adjudicate a residual substantive scope question. That is the system refusing to make a policy call by accident, which is the whole point.

### 2.2 What it proves is missing

Set the 71 findings against the burden analysis in the Taskforce questionnaire response. The register contains **no findings at all** on:

- **valuation updates** — approximately 48% of EMIR transaction-level activity volume and 45% of SFTR;
- **position-level reporting** — approximately 38% of EMIR volumes;
- **static and reference data restated on every message**, though GLEIF, ANNA-DSB and the venues publish it;
- **exchange-traded derivatives reported to two destinations on two field sets**;
- **derivable fields** the authorities could compute rather than collect;
- **elements with no articulated supervisory use case**;
- **externally-sourced fields where accountability and control sit apart**;
- the **event-model divergence** (EMIR's NEWT/MODI/CORR/REVI/POSC against MiFIR's absence of an equivalent) as anything more than a single incidental finding on action-type vocabularies.

The reason is structural, not a defect of the run. The manifest contains 18 **instruments**; the extraction atom is *obligations, definitions and interactions* drawn from legal prose. The field tables — RTS 22 Annex I, the EMIR RTS tables, the SFTR RTS tables — are present in the corpus as text, but nothing in the pipeline models a **data element**. A pass that cannot see elements cannot see element-level duplication, and element-level duplication is where the burden lives.

**This is the specification's central conclusion.** The Workbench's method transfers to the FCA problem; its atom does not. Everything below follows from replacing the atom and building the machinery that a field-level model makes possible.

---

## 3. Architecture: domain packs

Per the architecture decision, the FCA build is a **swappable domain pack inside the existing codebase**, not a fork.

### 3.1 What stays in the core, untouched

The governance spine, which is the asset whose credibility the FCA build borrows:

- `router.py` — model routing, diversity constraints (G5), fail-closed privacy (ADR-016), schema-validated structured output, provenance stamps (G4/ADR-015), the cost meter.
- `gates.py` — the ADR-013 waiver taxonomy and the non-waivable minimum (OR-1, OR-4, ADR-012, SCHEMA-RATIFIED).
- `storage.py` — the governed/restricted split and the append-only decision log.
- `manifest.py` — import, canonical hashing, freeze, OR-7 immutability.
- The ratification acts and role checks in `refactor.py` / `redesign.py` — OR-1 routing, OR-4 role gating, P3.3 human classification, P3.8 invariants, OR-8 chartering.
- `crosswalk.py` — the P4.3–P4.5 accountability spine.

### 3.2 What becomes pack-supplied

A domain pack is a declarative bundle plus a small amount of code implementing three interfaces. Proposed layout:

```
src/workbench/packs/
  __init__.py            # registry, load_pack(pack_id)
  base.py                # DomainPack protocol
  generic/               # today's behaviour, extracted verbatim
    taxonomy.py          # D1-D10
    whitelist.py         # the 13 refactor ops + RECALIBRATE
    atom.py              # obligations/definitions/interactions extraction
    prompts.py
  fca_reporting/
    taxonomy.py          # R1-R12 (§5)
    whitelist.py         # + BIND, ADOPT-CANON-DEFINITION, DELEGATE-SOURCE, DERIVE (§6)
    atom.py              # Reporting Element Model (§4)
    canon.py             # CDE / ISO 20022 / identifier registry (§8)
    burden.py            # volume and burden weighting (§11)
    importers/           # field-table and validation-rule ingest
    prompts.py
    seed/                # the pre-worked example (§14)
```

The `DomainPack` protocol:

```python
class DomainPack(Protocol):
    pack_id: str
    pack_version: str

    def taxonomy(self) -> TaxonomySpec: ...          # codes, descriptions, blast-radius order
    def whitelist(self) -> WhitelistSpec: ...        # ops per mode, with per-op constraints
    def atom_schema(self) -> dict: ...               # JSON Schema for one extraction unit
    def extraction_prompt(self, item) -> str: ...
    def detection_prompt(self, scope, items) -> str: ...
    def proposal_prompt(self, finding, ctx) -> str: ...
    def effect_class_dimensions(self) -> list[str]:  # ["*"] generic; regime ids for FCA
        ...
    def invariants(self, program) -> list[Check]: ...  # pack-specific gates
    def exports(self) -> list[ExportSpec]: ...
```

### 3.3 Pack binding is a ratified programme property

A programme's pack is chosen at creation, recorded in the Purpose Statement, and **frozen with the manifest**. Changing a pack after freeze is prohibited under the same reasoning as OR-7: findings, operations and effect classes are all expressed in pack vocabulary, so a pack change silently invalidates the register. The programme summary and every export display `pack_id@pack_version` alongside `registry_version`, and the provenance stamp gains a `pack_version` field.

### 3.4 Migration path

1. Extract today's behaviour into `packs/generic` with no behavioural change; the existing test suite must stay green and the three existing demo programmes must render identically. This is the only step that risks the working app, so it is done first and separately.
2. Add pack resolution to `server.py`, defaulting to `generic` where a programme has no recorded pack.
3. Build `packs/fca_reporting` against the frozen interface.

---

## 4. The atom: the Reporting Element Model

### 4.1 Rationale

An obligation-and-definition model is right for a rulebook whose operative content is prose duties. It is wrong for reporting regimes, whose operative content is a **field set plus a validation rule set plus an event model**. The FCA pack replaces the extraction atom accordingly.

Instruments remain the manifest unit — legal provenance and the mutable-core analysis depend on them. The **blueprint** changes.

### 4.2 Schema

`contracts/reporting_element.schema.json` (abbreviated; full schema in the build):

```jsonc
{
  "element_id":      "emir.rts.t2.f21",        // pack-stable, derived from regime + table + field no.
  "regime":          "UK_EMIR",                 // UK_MIFIR | UK_EMIR | UK_SFTR
  "instrument_ref":  { "item_id": "...", "locator": "Annex I Table 2 field 21" },
  "name":            "Valuation amount",
  "concept":         "valuation.amount",        // pack-assigned concept key — the harmonisation join
  "definition":      { "text": "...", "quote_verified": true, "source_item_id": "..." },
  "format":          { "type": "decimal", "pattern": "...", "code_list": null },
  "code_list_ref":   null,                       // e.g. "ISO4217", "EMIR.ActionType"
  "event_model_ref": "emir.actiontype",          // links to the regime's event taxonomy
  "applicability":   { "condition": "...", "derived_from": ["..."] },
  "reporting_party": "both",                     // both | seller | buyer | FC | venue | CCP | other
  "timing":          { "deadline": "T+1", "basis_quote": "..." },
  "validation_rules": [ { "rule_id": "...", "logic": "...", "source_item_id": "..." } ],
  "supervisory_use_case": {                      // §12
      "status": "absent",                        // stated_instrument | stated_guidance | asserted | absent
      "text": null, "source_item_id": null },
  "volume_weight":   { "share_of_regime_volume": 0.48, "basis": "taskforce_2026_figures",
                       "confidence": "estimate" },
  "external_dependency": { "present": true, "source": "counterparty", "verifiable_by_reporter": false },
  "derivable": { "assessed": true, "from": ["position", "market_data"], "note": "..." }
}
```

### 4.3 Population

Three ingest routes, in descending order of preference. **Every route must produce a verbatim-quoted, machine-checked citation to the legal source; no element enters the blueprint on a model's say-so.**

1. **Structured import.** FCA and Bank validation-rule publications and XML schemas are already tabular or machine-readable. Parse directly into elements. This is the primary route and it is what makes the FCA build cheaper per element than the generic build is per provision.
2. **Table extraction from retained RTS/ITS.** The retained regulations are held in the corpus as XML (`retained-commission-delegated-regulation-eu-2017.xml` and siblings). Annex tables are extractable deterministically; a model is used only to normalise column semantics, and its output is schema-validated and quote-checked against the XML.
3. **Model extraction from prose.** Reserved for applicability conditions, reporting-party allocation and timing, which are stated in narrative articles rather than tables. Same citation discipline as the current `distill` pass.

The `concept` key is the harmonisation join and the single most consequential piece of curation in the build. It is **proposed** by the pack (seeded from CDE where a CDE element exists) and **ratified by a human** before the divergence pass runs. An unratified concept assignment cannot found a divergence finding. This is deliberate: concept assignment is where the analysis could smuggle in a conclusion, so it is made an explicit, logged, reviewable act rather than a model inference.

### 4.4 Coexistence with the prose blueprint

The FCA pack produces **both**: the Reporting Element Model and the existing obligation/definition extraction. They are complementary — the 71 existing findings are real and should not be discarded, and the mutable-core analysis (which findings are fixable at FCA/PRA level versus requiring statutory change) operates on instruments, not elements. Findings may cite either layer; a finding citing both is the most valuable kind, because it ties a burden number to a legal provision someone can amend.

---

## 5. Divergence taxonomy (R-codes)

Replaces D1–D10 within the FCA pack. Each code carries a default lever and a default class; both are defaults the human may override on disposition, and the override is logged.

| Code | Divergence | Lever | Class |
|---|---|---|---|
| **R1** | Same concept, materially divergent definitions across regimes | harmonise | refactor |
| **R2** | Same term, different concepts — false friend | harmonise | refactor |
| **R3** | Same concept, different identifier scheme or code list | harmonise | refactor |
| **R4** | Same lifecycle event, different event model or action-type vocabulary | harmonise | refactor |
| **R5** | Same fact, different validation logic or conditional rule | harmonise | refactor |
| **R6** | Same fact reported by both counterparties — dual-sided duplication | de-duplicate | **redesign** |
| **R7** | Same fact reported to two destinations under two regimes | de-duplicate | **redesign** |
| **R8** | Static or reference data restated though authoritatively published elsewhere | de-duplicate | mixed |
| **R9** | Element derivable by the authority from data it already holds | de-duplicate | **redesign** |
| **R10** | Element with no articulated supervisory use case | de-duplicate | **redesign** |
| **R11** | Externally-sourced element — reporter accountable without control | streamline | governance |
| **R12** | Interpretive ambiguity — no worked example, divergent house views | streamline | refactor |
| **R13** | Requirement assembled only by reading several instruments — navigability | streamline | refactor |
| **R14** | Obsolete, spent or superseded-in-substance element or provision | de-duplicate | refactor |
| **R15** | Gap — obligation implied by structure or supervisory practice but stated nowhere | streamline | **redesign** |

Notes on the design:

- **R8 is deliberately "mixed."** Ceasing to collect a field that GLEIF already publishes removes a duty (redesign) unless the regime's own text already treats the external source as authoritative (refactor). The classification is made per finding, by a human, and the split is itself informative.
- **R11 is a governance finding, not an operation candidate.** It produces no blueprint move. It populates a register addressed to the authorities about where accountability and control have come apart. Suppressing it into the operation pipeline would misrepresent it.
- **R14 subsumes generic D6 and D8** because in a reporting context "superseded but not revoked" and "obsolete" behave identically: a field nobody uses that firms still populate.
- Generic D5 (dangling reference) and D7 (scattered requirement) both map onto R13, since in a reporting context each is a navigability failure. Generic D9 (gap) is retained as **R15**, defaulting to redesign class, because a reporting gap is almost always a policy question rather than a drafting oversight.

### 5.1 Default blast-radius order

Retained from the current implementation's logic and extended: `R2, R1, R3, R4, R5` → `R14, R8` → `R6, R7, R9, R10` → `R13, R12` → `R11, R15`.

**This order is a default, not a policy.** Under §10 it applies only when the Taskforce has not elected a Work Order, and when it applies it is labelled in every export as *a default the Taskforce did not elect*.

---

## 6. Operation whitelist extensions

### 6.1 New refactor-class operations

**`BIND`** — assert that element *A* in regime X and element *B* in regime Y denote the same concept, and record the canonical concept entry both map to, **without altering either regime's text**. This is the crosswalk relation promoted to a first-class move. It is the only harmonisation operation that is provably meaning-preserving for every regime simultaneously, because it changes no regime's obligation set — it changes only what the authorities publish about the relationship between them. `BIND` is the workhorse of a harmonisation pass and its absence is the clearest gap in the current whitelist.

Constraints: requires a ratified concept key; requires a canon hook (§8) or an explicit `canon_absent` justification; must state, per regime, what remains different after binding (format, code list, applicability) — a `BIND` that conceals residual divergence is worse than no `BIND`.

**`ADOPT-CANON-DEFINITION`** — a specialisation of `CANONICALIZE-DEFINITION` where the canonical target is a published external standard (CDE, ISO 20022) rather than one regime's text. This matters for legitimacy: adopting the CDE definition of a valuation amount is binding to an international standard, whereas picking EMIR's definition over MiFIR's is adjudicating between two UK regimes. The first is plausibly refactor-class; the second usually is not.

Constraints: `canon_ref` mandatory and must resolve in the ratified Canon register; per-regime effect class mandatory (§7); where adoption changes any regime's obligation set, OR-1 parks it exactly as today.

### 6.2 New redesign-class operations

**`DELEGATE-SOURCE`** — move a reporting duty to the party holding the authoritative record: CCP, trading venue, ARM, or a reference-data utility such as GLEIF, ANNA-DSB or the DSB. Requires an objective hook, a named recipient, and an explicit statement of what supervisory capability is gained or lost.

**`DERIVE`** — the authority computes an element from data it already holds rather than collecting it. Requires an objective hook, the derivation inputs, and a statement of which regime's data the derivation depends on.

Both are squarely redesign-class, both require a Principal and a ratified Mandate under existing P0.9 governance, and neither is expressible today. They are the two moves the Taskforce burden analysis actually recommends, which is a good reason to be able to represent them precisely rather than as free text.

### 6.3 Retained operations

All 13 existing refactor operations and `RECALIBRATE` are retained with unchanged semantics. `SUBSTITUTE-TERM` remains strictly meaning-preserving. `INTRODUCE` remains ADR-005 constrained in refactor mode.

---

## 7. Per-regime effect classification

### 7.1 The problem

`refactor.py` requires a single `effect_class` per operation from `{codify, clarify, fill_gap, change, unresolved}`, and OR-1 blocks `change`/`unresolved` from finalising in a refactor pass. With one corpus this is exactly right. With three co-equal regimes it is under-determined: adopting a canonical definition may be `codify` for EMIR, `clarify` for SFTR and `change` for MiFIR, and a single label must either lose that information or overstate the disruption.

`OP-001` in the existing run is precisely this case, and the model resolved it by drafting `unresolved` — honest, but it discards the fact that the operation is harmless for two of the three regimes.

### 7.2 The change

Effect class becomes a **vector over the regimes the operation touches**:

```jsonc
"effect_class": {
  "UK_EMIR":  { "class": "codify",  "rationale": "...", "classified_by": {...} },
  "UK_SFTR":  { "class": "clarify", "rationale": "...", "classified_by": {...} },
  "UK_MIFIR": { "class": "change",  "rationale": "...", "classified_by": {...} }
}
```

- **OR-1 applies on the maximum**, ordering `codify < clarify < fill_gap < change < unresolved`. If any regime is `change` or `unresolved`, the operation parks. Governance strictness is unchanged.
- **P3.3 is unchanged**: every entry in the vector is a human classification. The model's draft vector is retained beside it for audit.
- The parked item now carries the information the Taskforce most needs: *this move is free for EMIR and SFTR and costs a policy decision only for MiFIR.* That sentence is the difference between an intractable list and a workable agenda.
- The generic pack declares `effect_class_dimensions() -> ["*"]`, keeping today's single-label behaviour; the storage format is the vector in both cases, with `"*"` as the sole key for single-corpus packs.

### 7.3 New invariant

`per_regime_obligation_preservation` — for each regime independently, every element in that regime's pre-operation set is either preserved, or bound to a canonical entry that preserves its obligation, or explicitly disposed of by a finalised operation whose effect class for **that** regime is not `change`. Any residue fails the invariant and blocks ratification under P3.8. This is the multi-corpus analogue of OR-5 and it is the technical heart of "harmonisation without policy change."

---

## 8. The Canon register

### 8.1 Purpose

Redesign gets its legitimacy from a ratified Mandate and a named Principal. Harmonisation needs a legitimacy source too — otherwise canonicalising across regimes is just picking a winner — but it does not need a Principal, because the choice can be referred to a published external standard rather than to anyone's policy preference.

The Canon is that source. `Mandate : redesign :: Canon : harmonise`, but factual rather than normative.

### 8.2 Contents

Seeded, versioned, ratifiable:

- **CPMI-IOSCO Critical Data Elements (CDE)** — the primary canon for OTC derivatives.
- **ISO 20022** element definitions where the regimes' schemas already reference them.
- **Identifier schemes:** LEI (GLEIF), UPI (DSB), UTI, ISIN (ANNA), MIC, and the relevant ISO code lists.
- **Event and action-type models** where a standard exists.

Each entry: `canon_id`, `standard`, `version`, `definition_text`, `source_url`, `authority`, `status ∈ {published, draft, superseded}`, and `uk_adoption_status` recording whether UK instruments already reference it.

### 8.3 Governance

- The Canon is **ratified as a whole, with a version**, by the Program Owner, before any harmonisation operation may hook to it. Adding an entry mid-programme creates a new Canon version and is logged.
- Every `BIND` and `ADOPT-CANON-DEFINITION` carries `canon_ref`. Hookless harmonisation operations **cannot enter review** — the direct analogue of P3D.4's objective-hook rule.
- Where no canon entry exists, the operation records `canon_absent` with a justification, and the finding is automatically flagged for the Parked Questions register. **This is expected to be common for SFTR**, since CDE coverage of securities financing transactions is materially thinner than for OTC derivatives. That is a real and useful finding, not a build problem: it says the Taskforce cannot harmonise parts of SFTR by reference to an existing standard, and must either commission one or take a policy decision.

---

## 9. Burden and volume weighting

Every finding carries an estimated impact vector so that orderings can be compared on more than finding counts.

```jsonc
"impact": {
  "volume_share": { "UK_EMIR": 0.48, "UK_SFTR": 0.45, "UK_MIFIR": null },
  "burden_vector": { "sourcing": 0.30, "quality_recon": 0.18, "interpretation": 0.12,
                     "technology": 0.05, "back_reporting": 0.02 },
  "basis": "taskforce_2026_volumes | cross_firm_estimate | firm_supplied | unknown",
  "confidence": "estimate"
}
```

Three disciplines, all non-negotiable:

1. **Provenance is mandatory.** `basis` and `confidence` are required fields. A figure without a basis cannot be stored.
2. **Estimates are visibly estimates.** Every export renders estimated figures distinctly from sourced ones, and the comparator reports its results separately for sourced-only and estimate-inclusive inputs. The Taskforce is going to argue about these numbers; the tool's job is to make the argument tractable, not to win it.
3. **Firms can overwrite.** The register accepts firm-supplied figures against the same element ids, which is the natural path from "one member's estimate" to "the Taskforce's evidence base."

The initial burden distribution is seeded from the questionnaire response's estimated allocation and is labelled as such.

---

## 10. The Work Order

### 10.1 Election

At programme chartering, the Taskforce elects an ordering over the three levers — or declines to.

```jsonc
"work_order": {
  "status": "elected | default_applied",
  "sequence": ["harmonise", "de-duplicate", "streamline"],
  "rationale": "...",
  "elected_by": { "name": "...", "role": "Program Owner" },
  "version": 1
}
```

- Elected orders are ratified and logged like any other decision, and are versioned — a Taskforce that changes its mind produces a v2 with a rationale, and the register records which operations were finalised under which version.
- If no election is made, the §5.1 blast-radius default applies and `status` is `default_applied`, rendered in every export as *"default ordering; not elected by the Taskforce."* Silence never looks like a decision.

### 10.2 Dependency warnings, not blocks

The pack computes, from the Reporting Element Model, a dependency graph: a de-duplication finding on elements *E* depends on any harmonisation finding whose canonical concept covers an element in *E*. **This is computable only because the atom is field-level** — you cannot derive it from prose.

Where the elected order works a finding ahead of its dependencies, the workbench does not refuse. It:

1. surfaces the affected findings and the specific dependencies violated;
2. requires an acknowledged override with a rationale, logged as a decision;
3. marks every operation finalised under an override as `provisional_under_override`, and lists them in the ratification report.

This is the "down-payment, not substitute" discipline from the questionnaire response applied inside the tool. The Taskforce may sequence however it wishes; it may not do so without the cost being recorded.

---

## 11. The Sequence Comparator

The feature that justifies the build. Run the divergence pass **once**, then evaluate every candidate ordering against the same register.

### 11.1 Inputs

The finding register, where each finding *f* carries: `code`, `lever(f)`, `class(f)`, `elements(f)`, `depends_on(f)`, `impact(f)`.

### 11.2 Model

For an ordering *O* = (L₁, L₂, L₃) over levers, and for each phase *i*:

- **Resolvable(i)** = { *f* : lever(*f*) = Lᵢ, and every *d* ∈ depends_on(*f*) is resolved in a phase ≤ *i* }
- **Blocked(i)** = { *f* : lever(*f*) = Lᵢ, and some *d* ∈ depends_on(*f*) falls in a phase > *i* } — findings that must either wait or proceed under override
- **Parked(i)** = { *f* ∈ Resolvable(i) : class(*f*) = redesign } while the programme is in refactor mode — the policy questions this phase surfaces
- **Rework(i)** = | { operations finalised in phases *j* < *i* whose touched elements are re-canonicalised by a finding resolved in phase *i* } | — the count of work that must be redone because a later phase changed a definition an earlier phase relied on
- **Coverage(i)** = Σ volume_share over Resolvable(i), computed twice: sourced figures only, and estimate-inclusive

### 11.3 Outputs

For each of the six orderings (and any custom order the user enters):

| Metric | Meaning for the Taskforce |
|---|---|
| Total rework | work that must be done twice under this order |
| Phase-1 coverage | share of reporting volume addressed before the first decision point |
| Blocked count | findings that cannot be worked in their nominated phase |
| Parked-by-phase curve | when the policy questions surface — early enough to act on, or too late |
| Override burden | how many acknowledged overrides the order requires |
| Statutory-layer share | how much of the order's value depends on changes outside FCA/PRA competence |

The last row matters disproportionately. The existing programme already records that the onshored statutory framework sits **outside the mutable core** — only the FCA/PRA rulebook, retained technical standards and reporting guidance are administratively amendable. An ordering whose early value depends on statutory change is slower in practice regardless of how it scores analytically, and the comparator should say so.

### 11.4 Honesty requirements

- Where dependencies cannot be computed (elements not yet modelled, concept keys unratified), the comparator reports **coverage of its own analysis** and names what it could not assess. Silent truncation would make a partial register look like a complete one.
- The comparator ranks; it does not choose. Output is a comparison table plus the assumptions behind it, addressed to the Taskforce for decision.

---

## 12. The supervisory use-case register

Every element carries `supervisory_use_case.status ∈ {stated_instrument, stated_guidance, asserted, absent}`. Status `absent` automatically raises an **R10** finding.

This turns a rhetorical argument — *where the authorities cannot articulate a supervisory use case, that absence is itself a finding* — into a standing, machine-checkable register, and it puts the burden of articulation on the authority, in a form that can be published.

Handle with care in the FCA-facing framing. The register is a prompt for articulation, not an accusation: the natural presentation is *"these elements have no use case stated in the instruments or guidance we ingested; supervisors may well have one, and recording it here is cheap."* A supervisor who fills it in has improved the corpus. A supervisor who cannot has told the Taskforce something important.

---

## 13. Exports

Beyond the existing derived-blueprint, crosswalk and target-blueprint exports:

1. **Divergence Register** — all findings, filterable by regime pair, lever, class, concept, volume share. The primary analytical artefact.
2. **Parked Questions Register** — first-class, standalone, not buried inside `target_blueprint.json`. For each parked item: the divergence, the regimes affected, the per-regime effect class, the decision required, who must make it (FCA/PRA administratively, or HMT/Parliament by SI), and the volume at stake. For a Taskforce session this is arguably the primary deliverable.
3. **Sequence Comparison** — §11 output.
4. **Canon Coverage Report** — which concepts have a canon entry, which do not, and what that implies for harmonising by reference rather than by adjudication.
5. **Accountability Register** — the R11 findings: where reporting accountability and data control sit apart.

Every export carries the manifest hash, pack version, Canon version, Work Order version and status, and the estimate/sourced split.

---

## 14. The seeded pre-worked example

Modelled on `aml-program-rules-refactor-demo` and the `liquidity-refactor-p1` / `liquidity-redesign-p2` pair, the FCA pack ships with a fully worked, ratified example programme so that a first-time user sees the method rather than an empty screen.

### 14.1 Subject: the lifecycle event model

**`uk-reporting-lifecycle-demo`** — one concept family taken end to end across all three regimes: how a trade's lifecycle events are represented. EMIR's NEWT / MODI / CORR / REVI / POSC action-type taxonomy, SFTR's equivalent, and MiFIR's absence of a clean counterpart.

Chosen because it is: genuinely cross-regime (all three); already evidenced in the existing run (`defects-regulation#1`, divergent action-type vocabularies for terminating a cleared contract); small enough to model exhaustively at field level; a case where firms demonstrably maintain parallel translation logic for economically identical events; and one where the canon question is live and interesting — CDE covers some of this and not all of it.

### 14.2 Contents

- A curated element slice: every lifecycle-event-related element from the three regimes' field tables, fully populated per §4.2, with verified citations.
- Ratified concept assignments, with the interview-style rationale visible.
- A Canon slice covering the CDE event elements, with the SFTR gaps explicit.
- A divergence register of R1–R5 findings on the slice, plus at least one R6/R7 to show a redesign-class finding parking correctly.
- Proposed operations including at least one `BIND`, one `ADOPT-CANON-DEFINITION`, one operation with a **mixed per-regime effect vector** that parks on the maximum rule, and one `cannot_express` entry.
- A ratified Target Blueprint with a populated Parked Questions register.
- A **Sequence Comparison over the slice**, showing all six orderings scored — the single screen that most directly demonstrates the tool's value to a Taskforce that has not yet decided.
- A chartered `uk-reporting-lifecycle-demo-p2` redesign successor, unratified, with the Mandate open and the Principal marked OPEN — showing exactly where the policy questions go and who must answer them.

### 14.3 Status and labelling

The demo is built from the real UK corpus and real citations. Every burden and volume figure in it is labelled as an estimate with its basis. The programme is marked `demonstration` throughout and its ratifications are attributed to a demo owner, so nothing in it can be mistaken for an FCA position or for a Taskforce output.

---

## 15. Build plan

Effort is one experienced engineer, calendar weeks, with model costs negligible against labour (the existing run suggests roughly $0.25 per finding worked).

### 15.1 Full build

| Milestone | Work | Weeks |
|---|---|---|
| **A** | Extract `packs/generic` from current code, no behaviour change; existing tests green; three existing demos render identically | 2 |
| **B** | Reporting Element Model schema; field-table and validation-rule importers; XML annex extraction; concept-key ratification UI | 3 |
| **C** | R-taxonomy; `BIND` / `ADOPT-CANON-DEFINITION` / `DELEGATE-SOURCE` / `DERIVE`; per-regime effect vectors; the `per_regime_obligation_preservation` invariant | 2 |
| **D** | Canon register: seed, versioning, ratification, hook enforcement, coverage report | 1.5 |
| **E** | Work Order election; dependency graph; override machinery; Sequence Comparator | 2 |
| **F** | Burden weighting; supervisory use-case register; the five exports | 1.5 |
| **G** | Seeded lifecycle demo, built and ratified end to end; FCA-facing UI copy | 2 |
| | **Total** | **14** |

### 15.2 The September constraint

Fourteen weeks from 30 July lands in early November. The Taskforce session is in September. The full build does not fit, and pretending otherwise would be the most damaging thing this specification could do.

**Proposed September subset — approximately five weeks:**

- **C** in full, applied to the *existing* prose-based blueprint rather than to a complete element model. The R-taxonomy and the new operations work on the corpus already frozen and distilled; the 71 findings are re-coded into R-codes, which is cheap and immediately more legible to a reporting audience.
- **D** partial: CDE only, no ISO 20022 element mapping, coverage report included.
- **B** narrowed to a **hand-curated element slice for lifecycle events only** — perhaps 60–100 elements, populated semi-manually with verified citations. No general importer.
- **E** implemented against that slice, which is enough for a real Sequence Comparison because dependencies within one concept family are computable.
- **G** narrowed: the seeded demo *is* the slice.
- **A** deferred: build the FCA pack as a branch, extract the generic pack afterwards. This carries known rework and should be stated as a deliberate debt rather than discovered later.

What this produces for September is not a tool the FCA can run. It is **a worked divergence register for lifecycle events across the three regimes, with a sequence comparison, produced by an inspectable and re-runnable method.** That is a stronger thing to bring to a Taskforce than a half-built application, and it is honest about what exists.

### 15.3 Sequencing note

Milestone A is the only step that risks the currently working application. If the September subset proceeds on a branch, A should be scheduled immediately afterwards and before any further FCA work, so the debt does not compound.

---

## 16. Governance invariants

### 16.1 Preserved unchanged

OR-1 (change-class moves cannot finalise in a refactor pass), OR-4 (role-gated dispositions and ratifications), OR-5 (provision coverage), OR-7 (frozen manifest immutability), OR-8 (successor charters from a certified baseline), ADR-003 (advisory blueprint moves, never operative text), ADR-005 (constrained INTRODUCE in refactor mode), ADR-015 (schema-validated provenance), ADR-016 (fail-closed privacy), P0.9 (Mandate adoption only by an identity-asserted Principal), P3.3 (human effect classification), P3D.4/P3D.5 (objective hooks, unranked tradeoffs returned to the Principal), P3D.7 (backlog fully dispositioned), P3.8 (invariants before ratification).

### 16.2 Added

- **PACK-FROZEN** — pack id and version are frozen with the manifest; a pack change after freeze is prohibited.
- **CONCEPT-RATIFIED** — a divergence finding may not rest on an unratified concept assignment.
- **CANON-HOOKED** — `BIND` and `ADOPT-CANON-DEFINITION` require a resolving `canon_ref` or a logged `canon_absent` justification.
- **PER-REGIME-PRESERVATION** — §7.3.
- **WORK-ORDER-DISCLOSED** — a default ordering is labelled as such in every export.
- **OVERRIDE-LOGGED** — operations finalised against a dependency violation are marked provisional and listed at ratification.

### 16.3 Non-waivable additions

`CONCEPT-RATIFIED` and `PER-REGIME-PRESERVATION` join the non-waivable minimum. The first prevents the analysis from smuggling in its conclusion; the second is the entire basis of the claim that harmonisation changes no firm's obligations. Neither can be waived by any role.

---

## 17. Risks and open questions

1. **Machine-readability of the UK post-onshoring artefacts.** The build's efficiency case rests on the FCA and Bank validation rules and schemas being parseable. This must be verified before committing to Milestone B; if the UK versions are less structured than the ESMA originals, B lengthens materially. **Verify first.**
2. **Canon coverage for SFTs.** CDE was built for OTC derivatives. Expect substantial `canon_absent` on SFTR. This is a finding, not a failure, but it changes the harmonise/redesign split for SFTR and should be surfaced to the Taskforce early rather than discovered at ratification.
3. **ADR-003 pressure.** A field-level model invites drafting the target schema. The pack proposes blueprint moves addressed to an authority; it does not write technical standards. This boundary will be tested and should be restated in the UI, not only in the specification.
4. **Concept-key curation is the critical path.** It is the one step that cannot be automated without compromising the result, and it is where the analysis could be accused of assuming its conclusion. Budget human time for it explicitly and make the ratification record legible.
5. **Burden figures will be contested.** The Taskforce contains firms with their own cost accounting. The estimate/sourced split and the firm-overwrite path are the design response; they should be prominent from the first demonstration, not added under pressure.
6. **Mode election for the real programme.** The existing `uk-derivatives-reporting` programme is ratified in **refactor** mode, with non-goals explicitly declining to recommend obligation reductions. R6, R7, R9 and R10 findings will therefore all park. That is correct and intended — but it means the FCA-facing framing must be clear that the de-duplication lever's obligational half is a *successor programme with a named Principal*, not something this programme delivers.

---

## Appendix A — mapping the existing 71 findings to R-codes

Provided for the re-coding exercise in Milestone C. Generic → FCA pack:

| Generic | FCA | Note |
|---|---|---|
| D2 divergent definitions | R1, or R2 where the term is a false friend | 11 findings; `financial counterparty` and `trade repository` are the clearest R1 cases |
| D3 duplicate provisions | R7 where cross-destination; R14 where restatement | 12 findings |
| D4 undefined material term | R1 with `definition_absent` | 10 findings |
| D5 dangling reference | R13 | 10 findings |
| D6 superseded not revoked | R14 | 3 findings |
| D7 scattered requirement | R13 | 6 findings |
| D8 obsolete | R14 | 5 findings |
| D9 gap | R15 | 4 findings |
| D10 applicability inconsistency | R5 where validation-rule level; R1 where definitional | 8 findings |
| D1 conflicting requirements | R1 or R5 by nature of the conflict | 2 findings |

Re-coding is a human act with a logged rationale per finding; the mapping above is a starting proposal, not an automatic conversion.
