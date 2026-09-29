# Rulebook Consolidation Instruction Set

| | |
|---|---|
| **Status** | 0.3 — supersedes 0.2 (dual-mode) and 0.1 (refactor-only), which remain in the statute-distill folder / git history. Versioning per ADR-002: this document does not name product milestones |
| **Layer** | L2 (see `governance/SPEC-HIERARCHY.md`); binds the regulatory profile (`spec/20`) to program execution |
| **Owner** | Mike Hsu |
| **Scope** | Distill (①) → Refactor (②a) **or** Redesign (②b) → Align (③) → Reform support (④). The mode is elected per program in Phase 0 and gates everything downstream |
| **MVP pairing** | Refactor MVP: **BSA/AML**. Redesign MVP: **liquidity**. §14 states what each must prove |
| **Posture** | Assistive workbench with drafting support (ADR-003): AI surfaces, drafts, and cross-checks at scale; named humans make every judgment call, on the record; all drafts are proposals to an Authority, never operative text |
| **Companion documents** | `spec/20-profile-regulatory.md` (operations, `baseline_set_for`) · `scoping-protocol-v0.2.md` (Phase 0 in full detail; currently upstream) · `statutedistill-prd-v0.2.md` (core calculus, pinned via `spec/00`) · `skills/purpose-elicitation/SKILL.md` (the P0.1 interview mechanic) · `schemas/` (artifact contracts) |

---

## 1. In plain English

Every regulated industry lives under a body of rules that no one designed as a whole. Statutes get amended piecemeal. Regulations layer on top of statutes. Agencies add guidance, reporting instructions, examination manuals, FAQs — and enforcement actions imply expectations that appear nowhere in writing. After a few decades the result is what we call a **Legacy Rulebook**: thousands of provisions that each made sense when written but that collectively contain duplications, contradictions, dead references, and requirements scattered across so many documents that no one can find them all. Everyone senses the mess; no one can see it whole.

Think of it as a building assembled over a century by different crews, with no master drawing on file. Before renovating, a sensible owner would first draw the building *as it actually stands* — crooked hallways included. That is step one, **Distill**: AI reads the entire Legacy Rulebook and produces the **Derived Blueprint**, a faithful, higher-level picture of the operating logic actually in force — what the regime is trying to accomplish, who must do what, and how the pieces interact. Faithful means faithful: where the rulebook contradicts itself, the blueprint records the contradiction rather than quietly fixing it. For the first time, the forest is visible, not just the trees.

Step two is where human attention concentrates, and it fixes the *drawing*, not the bricks. It comes in two modes, and every program declares its mode before it starts. **Refactor** is cleanup only: working from the blueprint's recorded flaws, merge duplicates, give each term a single definition, retire dead rules, resolve contradictions — without changing what the law substantively requires. Every proposed fix is labeled with its effect — restates the law, clarifies an ambiguity, fills a gap, or *changes* the law — and in refactor mode, anything in the last category is not acted on: it is set aside on an explicit list. **Redesign** goes further: it starts from a written statement of what the regime is *for* — its objectives, ranked, adopted by the people with authority to hold them — and reshapes the blueprint to serve those objectives. Redesign is openly a policy exercise, so it runs under stricter governance, not looser: every change must name the objective it serves, and every change is decided by a person, never by the tool. In both modes the output is the **Target Blueprint**: the regime, stated coherently.

The two modes are kept honest by sequencing and by labels, not by hope. A redesign program still refactors first — you cannot sensibly redesign a drawing you cannot yet read — and only then reshapes the cleaned blueprint against its stated objectives. And because every move carries an effect label, cleanup claims are checkable: a "pure cleanup" that quietly changes the law will be caught by audit, and a redesign that cannot say which objective a change serves will not pass its gate.

Step three, **Align**, redrafts the operative materials to match the cleaned blueprint. The result is the **Consolidated Rulebook**: every provision connects to a visible purpose in the blueprint, and a complete crosswalk shows where every old provision went — merged, repealed, or retained, each with reasons. Nothing disappears silently. Actual reform — the moment old materials are repealed and new ones take effect — is not a separate shortcut around this process; it happens only *through* it, executed by the authority that owns the rules, with these materials as the working papers.

Two disciplines make the exercise trustworthy. First, the separation between cleanup and policy change is enforced by rule, not by good intentions: the mode is declared up front, policy change is permitted only in redesign mode, and even there only when anchored to an adopted objective and decided by a named person. Second, the paper trail: every statement in every blueprint traces to the specific statute, regulation, or guidance document it came from, and every human judgment is recorded with who decided, what they decided, and why. Anyone — a colleague today, the public later — can check the work.

The rest of this document is the recipe: numbered, precise instructions, so that different teams applying it to different regimes produce comparable and auditable results.

---

## 2. How to read this instruction set

- **MUST / MUST NOT** are hard requirements. A phase gate containing a MUST cannot be passed while it is unmet, except by a written waiver from the Program Owner recorded in the **Decision Log**.
- **SHOULD** is the default; deviation is permitted but MUST be logged with a reason.
- **MAY** is discretionary.
- Instructions are numbered `P<phase>.<step>` (e.g., P2.4) and are intended to be executed in order within a phase unless marked parallelizable.
- Named artifacts appear in **bold** at first definition and are indexed in §12.
- **⚖** marks a decision point that only the named human role may take. AI output at a ⚖ point is a *proposal*, never a disposition.
- Each phase specifies: *Purpose · Entry criteria · Inputs · Instructions · Outputs · Exit gate · Decision points.*

---

## 3. Definitions

| Term | Definition |
|---|---|
| **Legacy Rulebook** | The complete in-scope stock of operative materials at the pinned snapshot date: statutes, regulations, reporting instructions, guidance, handbooks/manuals, and (as evidence only) enforcement actions. |
| **Derived Blueprint** | The as-built specification distilled from the Legacy Rulebook: regime objectives, actors, obligations, definitions, and interactions — *including* its recorded inconsistencies. Descriptive, never aspirational. |
| **Mode** | The per-program election, made in Phase 0 and recorded in the Purpose Statement: `refactor` (cleanup only; substantive requirements unchanged) or `redesign` (substantive change permitted, anchored to a ratified Mandate). |
| **Purpose Statement** | The Phase 0 artifact produced by the purpose-elicitation interview: mode, one-sentence scope, the decision the output supports, consumers, client and mutable core, success criteria, and explicit non-goals. Typed per `schemas/purpose_statement.schema.json`; anchors everything downstream. |
| **Mandate Hypotheses** | Interview-derived, *non-authoritative* candidate objectives, rankings, and constraints, each attributed to its source (ADR-006). Input to P0.9; never a source of authority. |
| **Ratified Mandate** | Redesign mode only: the register of regime objectives created in the Principal-led P0.9 process — each objective stated, ranked, adopted by an identity-verified Principal, with fixed constraints listed. Typed per `schemas/mandate.schema.json`. The sole source of authority for `change`-class moves. |
| **Refactored Blueprint** | The intermediate object in redesign mode: the Derived Blueprint after the refactor pass, before objective-driven reshaping. In refactor mode it *is* the Target Blueprint. |
| **Target Blueprint** | The blueprint after the elected mode's work is complete: contradictions resolved, one definition per term, dead rules retired — and, in redesign mode, reshaped to serve the Mandate. The reference object all downstream drafting must connect to. |
| **Misalignment Register** | Redesign mode only: the typed, cited list of gaps between the Refactored Blueprint and the Mandate (see taxonomy, P3D.2). The redesign analog of the Defect Register. |
| **Objective hook** | The Mandate objective a redesign move serves. Every `change`-class move MUST carry one; the drafting analog is the blueprint hook (P4.2). |
| **Consolidated Rulebook** | Redrafted operative materials organized by, and traceable to, the Target Blueprint. |
| **Defect** | A typed, cited flaw recorded during distillation (see taxonomy, P2.5). |
| **Effect class** | The label attached to every refactoring move: `codify` (restates what the law already requires) · `clarify` (resolves ambiguity without changing substance) · `fill_gap` (states explicitly what was implied but nowhere stated) · `change` (alters what the law requires). |
| **Redesign Backlog** | In refactor mode: the parked list of all `change`-class findings the program refuses to act on, held for a future redesign program. In redesign mode: the intake queue feeding P3D. |
| **Crosswalk** | The two-way provision-level mapping: every legacy provision → its disposition (subsumed / repealed / retained-with-reasons); every consolidated provision → its sources and its Target Blueprint element. |
| **Scope Contract** | The frozen, versioned statement of what is in and out: purpose, actors × obligations, jurisdictions, snapshot date, evidence policy, boundaries (per `scoping-protocol-v0.2.md`). |
| **Frozen Manifest** | The deterministic, hashed list of every document in the Legacy Rulebook, with per-item status and evidence-role metadata. |
| **Normative flag / disposition** | Per PRD §9: a typed marker (`policy_choice`, `doctrinal_ambiguity`, `institutional_discretion`, …) on any finding requiring human judgment, plus a routing state (`needs_review` → `reviewer_accepted / rejected / modified`) with reviewer, timestamp, and rationale. |
| **Decision Log** | The append-only record of every ⚖ decision, waiver, and scope change across all phases. |

---

## 4. Roles

| Role | Responsibility | Notes |
|---|---|---|
| **Program Owner** | Owns the program; grants waivers; ratifies the Target Blueprint; final ⚖ authority | One named person |
| **Scope Owner** | Owns the Scope Contract and the scope-change queue | May be same person as Program Owner in a pilot |
| **Distillation Lead** | Runs Phases 1–2; accountable for fidelity of the Derived Blueprint | |
| **Policy Reviewer(s)** | Disposition `clarify` and `fill_gap` findings; adjudicate fidelity samples | Domain experts; ≥1 independent of the Distillation Lead |
| **Corpus Steward** | Maintains the domain catalog and manifest post-freeze; runs status monitors | Per `scoping-protocol-v0.2.md` §8 |
| **Principal(s)** | Redesign mode only: the person(s) or body whose objectives constitute the Mandate, and who disposition `change`-class moves | The workbench never supplies objectives; it elicits and records them. Legitimacy lives here |
| **Authority / Client** | The body with legal power over the instruments; executes Phase 5 | The Foundry's posture is advisory: it produces the working papers, not the legal acts |

One person MAY hold several roles in a pilot, except: the Policy Reviewer adjudicating a fidelity sample MUST NOT be the person who produced the sampled distillation.

---

## 5. Operating rules (cross-cutting; apply in every phase)

- **OR-1 — Mode-gated change control.** A move whose effect class is `change` MUST NOT be finalized in refactor mode — it is recorded in full (operation, evidence, citations) and parked in the **Redesign Backlog**. In redesign mode a `change`-class move may be finalized only if it (a) carries an objective hook into the ratified Mandate, (b) receives a recorded human disposition by the Principal or their named delegate, and (c) survives the P3D tradeoff rule. There is no third mode and no mid-program mode switch without a new Purpose Statement and Program Owner sign-off in the Decision Log.
- **OR-2 — Single path to reform.** No consolidated text may be drafted except from the ratified Target Blueprint. The diagram's arrow ④ (Reform) is the *output* of ① + ②a + ③, never an independent workstream. Direct legacy-provision editing is prohibited.
- **OR-3 — Full traceability.** Every blueprint statement, defect, refactoring move, and drafted provision MUST carry citations to documents in the Frozen Manifest, at claim level (per PRD §10) — not merely "a citation exists."
- **OR-4 — Humans decide.** Every finding carrying a normative flag reaches `final` only through a recorded human disposition. No exceptions, including in pilots.
- **OR-5 — Nothing disappears silently.** Every legacy provision must appear in the Crosswalk with exactly one disposition. An unexplained absence is a gate-blocking error.
- **OR-6 — Public-grade by default.** Outputs are internal for now but MUST be produced to a standard that survives later publication without rework: complete citations, logged decisions, reproducible runs stamped with Scope Contract version + manifest hash.
- **OR-7 — Frozen scope.** After manifest freeze, newly discovered materials enter the scope-change queue and take effect only via a new manifest version. They MUST NOT be silently added to a run in progress.
- **OR-8 — Redesign builds on a refactored substrate.** Redesign operations MUST target the Refactored Blueprint, never the raw Derived Blueprint or legacy text. You cannot redesign a drawing you cannot yet read; the refactor pass is not optional in redesign mode.

---

## 6. Phase 0 — Scope the regime

**Purpose.** Elect the target regime and freeze what "the whole rulebook" means, so completeness is measurable rather than rhetorical.
**Entry criteria.** A candidate regime (e.g., liquidity) and a Program Owner.
**Inputs.** Domain knowledge; any existing domain catalog.

**Instructions.** Phase 0 executes the scoping turns T0–T8 of `scoping-protocol-v0.2.md`, which governs in full. The load-bearing steps, restated so this document stands alone:

- **P0.1** Run the **purpose-elicitation interview** (`skills/purpose-elicitation/SKILL.md`). The user arrives with a topic label ("clean up AML," "modernize liquidity"); a topic label is not a purpose. The interview elicits, one question at a time: the symptom vs. aspiration picture, change tolerance (the mode discriminator), client and mutable core, consumers and the decision the output supports, boundaries, snapshot, and success criteria — and synthesizes them into a draft **Purpose Statement** (typed per schema: verbatim answers separated from synthesized conclusions; mode recommendation citing its supporting answer IDs; open items classified blocking / non-blocking) containing a proposed mode. Compound initiatives are decomposed per ADR-007 — one refactor program with a chartered redesign successor, one redesign program with its gated refactor subprogram, or separate programs by instrument tier or Authority — never a blended mode. The verbatim interview log is retained as an *internal evidentiary transcript*; the ratification and publication artifact carries only consented excerpts (ADR-010). ⚖ (Program Owner) The mode election and the Purpose Statement are ratified by a human; the interview proposes, it does not decide. The election drives dead-stock policy, the role of enforcement materials, the completeness standard, and which Phase 3 pass runs.
- **P0.2** Write the one-sentence scope: *"Distill ⟨obligation family⟩ for ⟨actors & activities⟩ under ⟨jurisdictions & authorities⟩ at ⟨snapshot date⟩ to produce ⟨outputs⟩, using ⟨permitted source roles⟩, treating ⟨adjacent regimes⟩ as boundaries."* If it takes two sentences, it is two projects; split now.
- **P0.3** Fix the time-and-status policy: the pinned snapshot date; explicit treatment of proposed, delayed, stayed, vacated, withdrawn, and superseded material.
- **P0.4** Classify anticipated source families into amendability tiers: **mutable core** (what the Authority can amend — the only tier Phase 3–4 operations may target) · **fixed constraints** (e.g., statutes, absent legislation — distilled as invariants) · **coordination layer** · **evidence layer**. A scope whose mutable core is empty is dead on arrival; stop and re-scope.
- **P0.5** Build the actors × obligations matrix; mark each cell core / boundary / excluded.
- **P0.6** Set the legal perimeter (issuers via delegation sweep, jurisdictions, SROs, adjacent regimes) and the closure policy (which citation edges expand scope).
- **P0.7** Set the evidence policy: per source family, its legal role, its evidentiary ceiling (notably: enforcement actions evidence applied expectations but MUST NOT independently establish an operative duty; proposed rules MUST NOT anchor current-law claims), and its disposition.
- **P0.8** Run the adversarial kill tests (protocol Tier 1) on the elected scope before proceeding.
- **P0.9** *(redesign mode only)* **Mandate ratification — a Principal-led process, distinct from the interview (ADR-006).** Inputs: the **Mandate Hypotheses** from P0.1 — attributed, non-authoritative candidate framings, which the interview may collect from any respondent. In P0.9, with identity and authority verified, the Principal(s): adopt, amend, or discard each candidate objective, stated in outcome terms (not in terms of existing instruments); rank them, forced through pairwise tradeoff questions ("where objectives A and B conflict, which yields?"); fix constraints (statutory floors, treaty obligations, constitutional limits); and take attribution — each adopted objective carries a `policy_choice` normative flag with the Principal's recorded adoption. Hypotheses from non-Principal respondents are NEVER promoted to "adopted" by default, by silence, or by the workbench. The **Ratified Mandate** is versioned and frozen; amendments go through the Principal, logged. A redesign program without a Ratified Mandate MUST NOT pass this gate — that is the definition of a grand vision with no connecting pieces.

**Outputs.** **Purpose Statement** (ratified, incl. mode) + internal evidentiary transcript; **Scope Contract** v1.0 (versioned); consumer roster; amendability-tier table; **Mandate Hypotheses** and, in redesign mode, the **Ratified Mandate**; opening entries in the **Decision Log** (scope elections carry `institutional_discretion` flags).
**Exit gate.** Purpose Statement and mode ratified by Program Owner ⚖; Scope Contract approved by Scope Owner ⚖; kill tests passed; every Tier-1 question answered in writing; in redesign mode, Ratified Mandate adopted by identity-verified Principal(s) ⚖.

---

## 7. Phase 1 — Assemble the Legacy Rulebook

**Purpose.** Turn the Scope Contract into a complete, deduplicated, citable corpus with a frozen manifest.
**Entry criteria.** Phase 0 gate passed.
**Inputs.** Scope Contract; domain catalog (create or extend it if absent).

**Instructions.**

- **P1.1** Census every in-scope source family against its declared completeness class (`census` · `official_index_census` · `curated_set` · `sample`), each with a written acceptance criterion. Record per item: identifier, title, issuer, date, status, URL/locator, family, applicability (actor / activity / effective interval).
- **P1.2** Resolve status: mark superseded, rescinded, expired, stayed, and vacated items per the P0.3 policy. Capture archived copies of anything at risk of deletion at the source.
- **P1.3** Deduplicate: detect exact and near-duplicate instruments; merge with a logged merge report.
- **P1.4** Apply the evidence policy (P0.7) as per-family defaults; log per-item overrides individually.
- **P1.5** Run adversarial completeness checks: **(a)** consumer question banks (~20 canonical questions per declared consumer; each must be answerable from the corpus or produce a scope amendment / explicit boundary); **(b)** an independent second census by a different model, team, or method, diffed against the first — MANDATORY for a domain's first contract. Every diff line is adjudicated ⚖ (Distillation Lead), not averaged.
- **P1.6** Record unresolved gaps in a **Gap Register** with acceptance tests and a named owner.
- **P1.7** Freeze: emit the **Frozen Manifest** with content hash. Stamp all downstream artifacts with Scope Contract version + manifest hash.

**Outputs.** Frozen Manifest; Gap Register; census diff report; catalog updates.
**Exit gate.** Both adversarial checks run and adjudicated; every family meets its acceptance criterion or has a Gap Register entry; manifest hash recorded.

---

## 8. Phase 2 — ① Distill: Legacy Rulebook → Derived Blueprint

**Purpose.** Recover the as-built operating logic at forest level, faithfully — flaws included. Distillation is identical in both modes: the Derived Blueprint is descriptive regardless of what the program later does with it.
**Entry criteria.** Phase 1 gate passed.
**Inputs.** Frozen Manifest corpus; actors × obligations matrix.

**Instructions.**

- **P2.1** Partition the regime into **obligation families** (e.g., for liquidity: quantitative ratio requirements; internal risk-management requirements; reporting; disclosure; supervisory expectations). The partition is a proposal ratified ⚖ by the Distillation Lead and becomes the blueprint's spine.
- **P2.2** For each family, extract into the canonical schema:
  - *stated objective(s)* — quoted where the sources state them; where only inferable, marked `inferred` with the inference's basis cited;
  - *actors and applicability* — who is covered, with thresholds and effective intervals;
  - *obligations as element tables* — who / must do what / when / at what threshold / with what exceptions / evidenced how;
  - *definitions* — every defined term, every definition of it, and every material undefined term;
  - *interactions* — cross-references, delegation chains, and dependencies between families.
- **P2.3** **Fidelity rule (cardinal).** Where sources conflict, record *both sides verbatim with citations*. The Derived Blueprint MUST NOT resolve, harmonize, or paper over anything. A "clean-looking" Derived Blueprint is a defect in the distillation, not a virtue of the regime.
- **P2.4** Emit claim-level verification records for every extracted statement (claim, source span, quoted vs. paraphrased, authority type, as-of validity, verifier status per PRD §10). `contradicted` or `unverified` above threshold blocks the gate.
- **P2.5** Populate the **Defect Register**. Fixed taxonomy (extend only by logged amendment to this instruction set):

  | Code | Defect type |
  |---|---|
  | D1 | Conflicting requirements (two sources impose incompatible duties) |
  | D2 | Divergent definitions (one term, multiple materially different definitions) |
  | D3 | Duplicate provisions (same duty stated in multiple instruments) |
  | D4 | Undefined material term |
  | D5 | Dead or dangling reference |
  | D6 | Superseded-in-substance but never revoked |
  | D7 | Scattered requirement (one obligation assembled only by reading N instruments) |
  | D8 | Obsolete/archaic provision (references extinct entities, products, technology) |
  | D9 | Gap (obligation implied by structure or enforcement but stated nowhere) |
  | D10 | Applicability inconsistency (scope/threshold mismatch across instruments) |

  Each entry: code, location(s), verbatim excerpts, citations, and *no proposed fix* — fixes belong to Phase 3.
- **P2.6** **Two-frame fidelity audit (ADR-009).** *(a) Precision frame — output→source:* sample blueprint statements and adjudicate each against its cited sources. *(b) Recall frame — source→output:* sample corpus provisions from the Frozen Manifest and check that each is represented in (or deliberately excluded from) the blueprint — output-side sampling alone cannot estimate recall. Both samples are stratified (obligation family × source role × legal hierarchy × status), with the sample seed derived deterministically from the manifest hash, and thresholds fixed *before* the pilot (rates and thresholds: **open parameters**, §15). Adjudication is by Policy Reviewers independent of the producer; disagreements are logged, not silently corrected.

**Outputs.** **Derived Blueprint** (versioned; structured store is the source of truth, human-readable rendering derived from it); **Defect Register**; verification records; fidelity audit report.
**Exit gate.** Audit thresholds met; zero uncited blueprint statements; every D-entry cited; Distillation Lead attests fidelity ⚖.

---

## 9. Phase 3 — ②a Refactor / ②b Redesign: Derived Blueprint → Target Blueprint

Phase 3 has two passes. **The refactor pass (P3.1–P3.7) runs in both modes** — per OR-8, redesign happens on a cleaned drawing or not at all. The **redesign pass (P3D.1–P3D.7) runs in redesign mode only**, after the refactor pass. Both modes end at ratification (P3.8).

### 9A. Refactor pass (both modes)

**Purpose.** Fix the drawing, not the bricks: resolve the Defect Register at blueprint level without changing what the law requires. In refactor mode this is the whole of Phase 3 and where human attention concentrates.
**Entry criteria.** Phase 2 gate passed.
**Inputs.** Derived Blueprint; Defect Register.

**Instructions.**

- **P3.1** **Operation whitelist (refactor pass).** Every refactoring move MUST be expressed as one of, or a composition of, the regulatory profile's selected operations (`spec/20` §2): `MERGE` · `SPLIT` · `REPEAL` · `RELOCATE` · `CANONICALIZE-DEFINITION` · `DEFINE-TERM` · `SUBSTITUTE-TERM` (strictly meaning-preserving) · `NORMALIZE-ELEMENTS` · `FACTOR-EXCEPTION` · `ELEVATE-GENERAL-RULE` · `RESOLVE-CROSS-REFERENCE` · `RELATE-OBLIGATION` — plus `INTRODUCE`, permitted in this pass only under the ADR-005 rule (see P3.4). Free-form edits are prohibited: if a needed move cannot be expressed, that is a finding about the profile — log it and propose an ADR; do not improvise.
- **P3.2** Work the Defect Register in order of blast radius (definitions before obligations before cross-references SHOULD be the default order). For each defect, propose candidate operation(s), each carrying: operands, evidence, citations, and effect class.
- **P3.3** **Effect classification (ADR-008).** Classify each operation per-instance by comparing its output against `baseline_set_for(target, actor, activity, jurisdiction, as_of)` for every cell it touches (`spec/20` §3) — legal hierarchy, applicability, status controls, and evidentiary ceilings resolved, not a structural diff against blueprint text. The same operation type can carry different classes in different contexts. An indeterminate baseline yields `unresolved`, routed like `change`. Until the resolver is implemented, classification is performed by humans applying `spec/20` §3, with verifier records as evidence, and that manual posture is disclosed in outputs.
- **P3.4** **Routing table (the enforcement of OR-1):**

  | Effect class | Refactor pass handling (both modes) |
  |---|---|
  | `codify` | Eligible to finalize; sampled human review (rate: open parameter) |
  | `clarify` | `needs_review` — Policy Reviewer disposition required per instance ⚖ |
  | `fill_gap` | `needs_review` ⚖ — finalizable (incl. via `INTRODUCE`) only when `baseline_set_for` establishes the duty already exists and the move merely makes it explicit (ADR-005), with a written rationale; otherwise the honest class is `change` — park |
  | `change` / `unresolved` | MUST NOT finalize in the refactor pass, in either mode. Park to Redesign Backlog, fully documented — in redesign mode the Backlog feeds P3D.7 within the same program |

- **P3.5** Conflict-resolution rule: where two live sources conflict (D1/D2), newest-wins applies only where supersession is *explicit* in the sources. Otherwise the conflict is not resolvable by refactoring — classify any proposed resolution honestly (usually `change`) and route accordingly.
- **P3.6** Record every disposition in the Decision Log: reviewer, timestamp, accepted / rejected / modified, rationale.
- **P3.7** Run structural invariants on the emerging blueprint: referential integrity (no dangling refs) · definitional uniqueness (one canonical definition per term) · no orphan obligations (every obligation connects to a stated or inferred objective) · applicability consistency. Violations block progression absent a logged exception.

*Refactor-pass exit.* Every Defect Register entry resolved-by-operation or parked; zero open `needs_review` states; invariants pass. In **refactor mode**, proceed directly to P3.8. In **redesign mode**, ⚖ (Program Owner) certify the result as the **Refactored Blueprint** (versioned, frozen — it is the redesign pass's fixed baseline and the object all effect-class diffs in P3D and P4 run against), then proceed to P3D.

### 9B. Redesign pass (redesign mode only)

**Purpose.** Reshape the cleaned blueprint to serve the Mandate. This is openly a policy exercise under explicit governance — the pass answers "what are we for?" with the Principal's adopted answers, never the workbench's.
**Entry criteria.** Refactored Blueprint certified; Ratified Mandate in force (P0.9). Throughout this pass, "Mandate" means the *Ratified* Mandate — hypotheses confer no authority.
**Inputs.** Refactored Blueprint; Ratified Mandate; Redesign Backlog.

**Instructions.**

- **P3D.1** Re-confirm the Mandate against what distillation revealed. If the as-built regime surprised the Principal(s) — objectives served that nobody named, named objectives the regime never served — the Mandate MAY be amended now, by the Principal, logged. After this step it is frozen for the pass.
- **P3D.2** Evaluate the Refactored Blueprint against each Mandate objective and populate the **Misalignment Register**. Fixed taxonomy (extend only by logged amendment to this instruction set):

  | Code | Misalignment type |
  |---|---|
  | M1 | Objective unserved or underserved (no blueprint mechanism advances it) |
  | M2 | Provision serves no Mandate objective (candidate for repeal or renewed justification) |
  | M3 | Burden disproportionate to the objective served (mechanism costs more than its contribution warrants) |
  | M4 | Objectives conflict as implemented (mechanism advances one objective by defeating a higher-ranked one) |
  | M5 | Objective served only indirectly or fragilely (works by accident of drafting, not by design) |

  Each entry cites the blueprint element(s) and the objective(s) concerned. M-entries are *findings*, not decisions.
- **P3D.3** **Operation whitelist (redesign pass).** All refactor-pass operations, now permitted to carry `change` class — `INTRODUCE` unconstrained by the ADR-005 rule — plus `RECALIBRATE` (adjust a threshold, parameter, scope line, or frequency; a declared domain specialization of the core's `REGRADE` per `spec/20` §2.2, inheriting its highest normative load). Free-form edits remain prohibited; whitelist gaps are logged findings and proposed ADRs.
- **P3D.4** Work the Misalignment Register and the Redesign Backlog. Every proposed move carries: operation(s), operands, effect class, **objective hook** (the Mandate objective it serves), evidence, and a normative flag. **Routing: every `change`-class move is `needs_review` to the Principal or named delegate ⚖ — nothing in the redesign pass auto-finalizes.** A move with no objective hook cannot even enter review.
- **P3D.5** **Tradeoff rule.** A move that advances objective A at cost to objective B MUST cite the Mandate's ranking. If the Mandate does not rank A against B, the workbench MUST NOT resolve the conflict — the question returns to the Principal as a proposed Mandate amendment (P3D.1 reopens, logged). The tool surfaces tradeoffs; it never prices them.
- **P3D.6** Run invariants: all P3.7 checks, plus — every `change`-class move has an objective hook and a Principal disposition; every Mandate objective is either served by the blueprint or explicitly deferred with the Principal's logged rationale (no orphan objectives); no unlogged divergence from the Refactored Blueprint (diff audit).
- **P3D.7** Disposition the remaining Redesign Backlog: each parked item is adopted (becomes a P3D.4 move), declined (with rationale), or deferred. The Backlog MUST be empty of undispositioned items at gate.

### 9C. Ratification (both modes)

- **P3.8** ⚖ (Program Owner; in redesign mode, jointly with the Principal) Ratify the **Target Blueprint**; version it; freeze it.

**Outputs.** Target Blueprint (ratified, versioned); Refactored Blueprint and Misalignment Register (redesign mode); Redesign Backlog (refactor mode: parked for a future program; redesign mode: fully dispositioned); complete operation log with effect classes, objective hooks, and dispositions.
**Exit gate.** Refactor-pass exit met; in redesign mode, P3D.6 invariants pass and P3D.7 backlog is clear; ratification recorded.

---

## 10. Phase 4 — ③ Align: Target Blueprint → Consolidated Rulebook drafts

**Purpose.** Redraft the operative materials so they implement the Target Blueprint, with total provision-level accountability.
**Entry criteria.** Phase 3 gate passed (ratified Target Blueprint).
**Inputs.** Target Blueprint; Frozen Manifest; amendability tiers (P0.4).

**Instructions.**

- **P4.1** Plan the consolidated instrument set: organized by the Target Blueprint's structure (obligation families), not by historical accretion or issuing-agency convenience. Drafting targets only the **mutable core** tier; fixed-constraint materials are implemented as invariants the drafts must satisfy, never as text to rewrite.
- **P4.2** Draft each consolidated instrument. Every provision MUST carry a **blueprint hook** — the Target Blueprint element it implements. A provision with no hook is a deviation (P4.4).
- **P4.3** Build the **Crosswalk** as drafting proceeds, not after: legacy → consolidated (each legacy provision: `subsumed` at ⟨destination⟩ / `repealed` with reason / `retained` with reason — large `retained` buckets SHOULD be challenged as triage avoidance) and consolidated → legacy (each drafted provision: its source provisions and blueprint hook).
- **P4.4** Maintain a **Deviation Register**: any drafted text not derivable from the Target Blueprint, and any blueprint element not implemented in the drafts. Deviations are permitted only with a logged ⚖ disposition; the register ships with the drafts — deviations are *visible by construction*.
- **P4.5** Run drafting invariants: no dangling cross-references; one defined term, one definition, used consistently; every legacy provision appears in the Crosswalk exactly once (OR-5); **effect-class audit** — a diff of the drafts against the baseline (refactor mode: the Derived Blueprint; redesign mode: the Refactored Blueprint) MUST surface no `change`-class content that lacks a logged P3/P3D operation with disposition. In refactor mode this is the check that cleanup claims are true; in redesign mode it is the check that every policy change is one the Principal actually decided.
- **P4.6** Independent review, scoped by mode. *Refactor mode:* reviewers answer one question — *"was anything substantive lost or distorted?"* — using the consumer question banks from P1.5 against the drafts; policy merits are explicitly out of scope. *Redesign mode:* the same fidelity review, **plus** a merits review of the changed elements only — reviewers receive the change list with objective hooks and rationales, and assess whether each drafted change faithfully implements its dispositioned P3D move (not whether they agree with the Mandate; contesting the Mandate is the Principal's forum, not this review). These scoped questions become the public-consultation templates when the work goes public.

**Outputs.** **Consolidated Rulebook drafts**; **Crosswalk**; Deviation Register; review report.
**Exit gate.** Crosswalk complete both directions; Deviation Register fully dispositioned; invariants and effect-class audit pass; review findings resolved or logged.

---

## 11. Phase 5 — ④ Reform: cutover support

**Purpose.** Enable the Authority to retire the Legacy Rulebook and adopt the Consolidated Rulebook — and to keep it clean afterward. The Foundry's role here is advisory: it produces the working papers; the Authority performs the legal acts.
**Entry criteria.** Phase 4 gate passed; an engaged Authority (or a working-group decision to package for advocacy).
**Inputs.** All Phase 4 outputs; amendability tiers.

**Instructions.**

- **P5.1** Map the legal vehicle per instrument tier: what the Authority can repeal/reissue administratively (guidance, manuals), what requires rulemaking (regulations), what requires legislation (statutes). Flag every item needing counsel's review — this instruction set is not legal advice.
- **P5.2** Propose a tranche plan: early, visible quick wins (repeal of plainly dead stock — D6/D8 items with `codify`-safe repeals) before the main simultaneous issue-and-repeal, to build momentum and trust.
- **P5.3** Assemble the **Cutover Package**: issue-and-repeal schedule; published Crosswalk; in refactor mode, the Redesign Backlog published as the honest list of policy questions deliberately not decided; in redesign mode, the Mandate and the change list with objective hooks published as the honest account of what *was* decided and why; consultation notice scoped per P4.6; FAQ. Note that redesign-mode cutover of regulations engages notice-and-comment on the merits — the Authority's process timeline differs materially from refactor-mode cutover, and the tranche plan (P5.2) SHOULD sequence refactor-derived quick wins ahead of change-bearing instruments.
- **P5.4** Specify the **maintenance regime** (the "no new sludge" rules): amendments are made in place to consolidated instruments, never as standalone circulars; every new instrument states its objective and its blueprint hook; the Target Blueprint is maintained as the living spec, under a named steward, with a periodic review cycle; a single repository with version history.
- **P5.5** Hand over catalog stewardship (P1 assets) with monitors for status changes (rescissions, vacaturs, new issuances) feeding the scope-change queue.

**Outputs.** Cutover Package; maintenance-regime specification; stewardship handover.
**Exit gate.** Package delivered; the Authority's adoption, adaptation, or declination of the maintenance regime recorded in the Decision Log.

---

## 12. Artifact registry

| Artifact | Produced in | Consumed by | Notes |
|---|---|---|---|
| Purpose Statement (incl. mode) | P0.1 | all phases | The anchor; ratified by Program Owner |
| Scope Contract | P0 | all phases | Versioned; changes only via scope-change queue |
| Mandate Hypotheses | P0.1 | P0.9 | Attributed, non-authoritative (ADR-006) |
| Ratified Mandate | P0.9 *(redesign)* | P3D, P4.6, P5.3 | Adopted by identity-verified Principal(s); versioned; amendments logged |
| Evidentiary transcript | P0.1 | audit (internal) | Access-controlled; publication only via consented excerpts (ADR-010) |
| Frozen Manifest (+hash) | P1 | P2–P5 | Stamps every run |
| Gap Register | P1 | P2, P5 | Open items carry acceptance tests |
| Derived Blueprint | P2 | P3; refactor-mode diffs in P4 | Descriptive; never edited after gate — refactoring produces a *new* object |
| Defect Register | P2 | P3 | Fix-free by rule |
| Verification records | P2–P4 | gates | Claim-level, per PRD §10 |
| Refactored Blueprint | P3 *(redesign)* | P3D; redesign-mode diffs in P4 | The redesign pass's frozen baseline |
| Misalignment Register | P3D.2 *(redesign)* | P3D.4 | Findings, not decisions |
| Target Blueprint | P3 | P4–P5 | Ratified + frozen; the living spec post-cutover |
| Redesign Backlog | P3 | P3D.7 *(redesign)* or a future program *(refactor)* | Never silently dropped |
| Consolidated Rulebook drafts | P4 | P5 | Blueprint hooks mandatory |
| Crosswalk | P4 | P5; public | Two-way; complete |
| Deviation Register | P4 | P5 | Visible by construction |
| Cutover Package | P5 | Authority | Advisory deliverable |
| Decision Log | all | audit | Append-only |

---

## 13. Program metrics

Reported at every gate; the program is auditable or it is nothing:

- instrument and provision counts, before → after; % of stock repealed / subsumed / retained;
- Defect Register: entries found, resolved, parked, by type;
- fidelity: precision/recall from P2.6; citation-integrity rate; zero-tolerance count of unlogged `change`-class content found at P4.5;
- coverage: % of provisions with blueprint hooks (target: 100%); Crosswalk completeness (target: 100%);
- redesign mode only: % of `change`-class moves with objective hooks and Principal dispositions (target: 100%); Mandate coverage (every objective served or explicitly deferred); Misalignment Register closure by type;
- usability: time-to-find on the consumer question banks, Legacy vs. Consolidated;
- process: open `needs_review` age; Decision Log completeness.

---

## 14. The MVP pairing — what each program must prove

**Refactor MVP — BSA/AML.** The largest, most accreted corpus in the portfolio, with the census work already underway. It must prove the *scale* claims: that a complete, adversarially-checked census is achievable (P1); that distillation is faithful at volume (P2.6 metrics); that the refactor pass genuinely contains itself — a Redesign Backlog full of well-documented parked items is a success condition, not a failure; and that the Crosswalk and effect-class audit hold up under the heaviest load. It deliberately takes no policy exposure.

**Redesign MVP — liquidity.** A compact, coherent regime with a live "what are we for?" question. It must prove the *governance* claims: that the purpose-elicitation interview and Mandate elicitation (P0.1, P0.9) can produce objectives sharp enough to hook changes to; that the refactor-then-redesign sequencing inside one program works (OR-8); that the tradeoff rule (P3D.5) genuinely returns unpriced conflicts to the Principal instead of resolving them; and that the published change-list-with-objective-hooks is a persuasive artifact for a working-group audience — the "connecting pieces" thesis, demonstrated.

The pairing is deliberate: each MVP stresses the half of the workbench the other doesn't, and together they exercise every phase and both routing tables.

---

## 15. Open parameters (to set during iteration / at pilot kickoff)

1. P2.6 sampling rates and precision/recall gate thresholds for both audit frames (per ADR-009, fixed before the pilot).
2. P3.4 sampled-review rate for `codify`-class moves.
3. Obligation-family partition granularity (P2.1) for each MVP corpus.
4. Whether the second census (P1.5b) is mandatory for every contract or only a domain's first.
5. Names against roles (§4) for each MVP — in particular, who plays Principal for the liquidity redesign (a real official? the working group as a proxy? Mike as stand-in for prototyping?). The redesign MVP's credibility turns on this; per ADR-006, a stand-in Principal makes every Mandate entry a hypothesis and the MVP output must say so.
6. Rendering formats: whether blueprints get an Allium view from day one or after the pilots.
7. The Mandate's granularity — how many objectives is too many (a 40-objective Mandate ranks nothing), and whether rankings are total or only pairwise-on-conflict.
8. Delegation table for P3D.4 dispositions: which change types the Principal may delegate, and to whom.
9. Whether the redesign pass may begin before the refactor pass fully gates (strict sequence as drafted) or may overlap family-by-family (faster, riskier).
10. Evidentiary-transcript retention period and consent mechanics (ADR-010).
11. Whether `scoping-protocol-v0.2.md` relocates into this repo (as spec/05) or stays upstream with a pin.

*(Resolved since 0.2: the former `fill_gap` open item — closed by ADR-005.)*

