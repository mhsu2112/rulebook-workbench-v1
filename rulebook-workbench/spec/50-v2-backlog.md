# 50 — v2 Backlog (candidates, not commitments)

**Status:** Draft 0.1 · 2026-07-19
**Audience:** Foundry working group (non-technical intro; per-item notes get more precise)
**Rule of the road:** Nothing here is adopted. Any item that touches governance
(gates, roles, stores, provenance) requires an ADR in `governance/DECISIONS.md`
before implementation. Items that are purely convenience features do not.

## Introduction (for non-technical readers)

The v1 workbench proves the method end-to-end: interview → ratified Purpose
Statement → frozen corpus → acquisition → distillation with verified citations →
defect register. This file is the holding pen for what v1 deliberately left out.
It has two sources: (A) ideas adapted from a May 2026 Microsoft Research /
Cornell paper whose problem is a close cousin of ours, and (B) features
requested by the Program Owner from using the prototype. Each item notes what it
would give us, what it would cost, and whether it needs a governance decision
first.

---

## Part A — From the AI-assisted systematization paper

**Source:** Agarwal, D., Sheng, E., Atalla, C., Garcia-Gathright, J., Mozannar,
H., Washington, H., Chouldechova, A., Barocas, S., Wallach, H., *AI-Assisted
Systematization for Evaluating GenAI Systems*, arXiv:2605.26001v1 (25 May 2026).

The paper formalizes "systematization": turning a fuzzy background concept into
an explicit, structured, auditable spec *before* measuring anything — the same
move our distillation makes on rulebooks, and the same failure mode (skipping
the explicit step) that our diagram forbids. Key difference to respect: they
systematize contested concepts with **no authoritative text**, so their specs
are grounded in literature and simulated judgment. We distill **positive law**,
where an authoritative text exists — our OR-3 verbatim-citation discipline is
stricter than anything in their pipeline and must not be loosened by any import
below.

### A1. Blueprint self-audit worksheet (highest value)

Adapt their six-attribute validation worksheet (clarity, operationalizability,
granularity, provenance, completeness, salience — each with structured questions
and a 1–5 rubric) into a **P2.7 "blueprint self-audit" pass** run against the
Derived Blueprint itself.

- Gap it closes: the defect register (D1–D10) audits the *source corpus*;
  citation verification audits *quote fidelity*; nothing audits *the quality of
  our own extraction as an artifact*. The paper's headline empirical finding is
  that **internal inconsistency is the main failure mode of AI-assisted
  systematization** — a term defined one way and used another, heterogeneous
  definition formats within one spec. That defect could arise inside our
  blueprint today and nothing would catch it.
- Shape: a new audit task (model-assisted, human-dispositioned) + a small typed
  `blueprint_audit.schema.json`; findings land in a register like defects do.
- Governance: new artifact type → needs an ADR. Provenance attribute is nearly
  free (stamps, registers); clarity/consistency checks are the new work.

### A2. Information recoverability for the second census (C-ADV2)

The Purpose Statement already commits to an independent, model-diversity-enforced
second extraction pass, but v1 never specified how to *compare* the two censuses
beyond eyeballing. The paper's metric — annotate a shared sample under both
specs and measure how well one predicts the other, with asymmetry revealing
which is coarser — is a principled answer.

- v2 shape (lightweight adaptation, not their full logistic-regression rig):
  align obligations across the two censuses; report unmatched elements,
  modality disagreements (must/should/may flips), and threshold mismatches; emit
  a convergence summary the working group can defend.
- Governance: comparison report is advisory input to human reconciliation; no
  new gate. ADR to fix the comparison method before first use (pre-registration
  discipline, per P2.6/ADR-009).

### A3. Delphi-style simulated panel — redesign mode only

Their multi-agent phase 2 (diverse simulated expert personas propose phenomena;
a moderator merges across rounds) maps onto the hardest part of the ②b path:
generating **candidate design objectives** for a Target Blueprint (liquidity).

- Fits existing machinery: panel output lands as MandateHypotheses — attributed,
  `adoption: null` always, ratified only by humans (ADR-006). The Foundry
  working group is the real panel; the simulated one drafts material for them to
  react to.
- Caution from the paper's own results: the multi-agent version did **not**
  produce better specs than a direct single prompt — its advantage was
  auditability. Build this for governance traceability, not for quality claims.
  Their limitations section also concedes simulated experts are no substitute
  for real stakeholders; ours would be labeled accordingly.
- Governance: ADR required (new task family + persona provenance rules).

### A4. Inclusion/exclusion criteria on taxonomy values

Their spec slots carry per-value definitions with inclusion criteria, exclusion
criteria, and examples. Our D1–D10 defect codes and (M4) effect classes are
one-line definitions. Tighten each into **definition + inclusion criteria +
exclusion criteria + one worked example**. Their qualitative findings document
exactly what goes wrong when value definitions are loose or heterogeneous —
inconsistent application by both models and humans.

- Cheap, high leverage; mostly spec-writing, little code.
- Governance: taxonomy change → versioned spec edit + ADR note.

### A5. Caution to keep, not a feature: small artifacts win

Their expert evaluators found the multi-agent system's hundred-page discussion
logs *less* auditable in practice than shorter artifacts — more provenance on
paper, less in reach. This vindicates v1's small-typed-artifact bias (decision
log entries, stamps, registers) over transcript-dumping. Hold that line as v2
grows; any new artifact should be summarizable on one screen.

---

## Part B — Program Owner feature requests (from v1 use)

### B1. Multi-user login + per-user OpenRouter keys

Let other working-group members sign in and use the workbench with their own
OpenRouter API keys.

- Security/privacy requirements (fail-closed, per ADR-016 spirit): keys stored
  server-side encrypted at rest, never logged, never echoed to the UI, never in
  provenance stamps or exports; per-user spend budgets; key deletion on account
  removal.
- Governance upside: v1 gates trust a *claimed* name (the ratify dialog asks who
  you are). Real authentication makes OR-4 and reviewer-independence (ADR-012)
  **enforceable** — the server can actually know the ratifier is the Program
  Owner and that the M4 reviewer differs from the proposer. This is the
  strongest reason to build login, beyond multi-user convenience.
- Governance: ADR required (role model becomes real; decision-log entries gain
  authenticated identity).

### B2. Manual vs. auto-approve toggle for distillation batches

v1 requires a click per batch. Add a per-program election: **manual** (review
each batch before the next runs) or **automatic** (run to completion, stopping
only on errors or budget).

- Distillation is not itself a ⚖ decision point (extraction is machine work,
  verified by code), so auto mode does not bypass any gate — ratification,
  disposition, and freeze remain human-only either way.
- The election should still be recorded (a decision-log entry naming who chose
  auto mode and the budget cap), so an audit can see the corpus was distilled
  unattended.
- Include a hard budget ceiling and an error-rate circuit breaker (e.g., pause
  if >20% of items in a run fail citation verification).

### B2b. Review workspace, not a side pane (Program Owner field report, 2026-07-20)

In v1, the substantive work of Phases 2–3 — reading extractions, weighing
defect findings, dispositioning operations — is smooshed into the right-hand
pane, while the broad middle panel sits idle outside the interview. The
disposition decision is the highest-judgment act in the whole workflow, and it
currently happens in the least space.

v2 requirement: blueprint and refactor/redesign work gets the full width — the
middle panel or a dedicated screen per operation/finding — structured as a
**unified review workspace**:

- the object under review (proposal, draft classification, citations) on one
  side, with the underlying source texts and extractions openable in place;
- a **scratchpad/context panel** where the reviewer can look things up before
  dispositioning: search the corpus, open any item's text at the cited span,
  run an ad-hoc query ("where else does this term appear?", "what does the
  baseline say for MSBs?") — against the governed corpus first, and optionally
  a routed model call for context (clearly stamped as advisory, never entering
  the artifact);
- the disposition form last, so the workflow reads: consider → investigate →
  decide, all in one place.

Without this, reviewers toggle between the workbench and an external browser,
and the context that actually drove a disposition never enters the record.
With it, scratchpad activity can optionally be attached to the disposition as
evidence ("reviewer consulted items X, Y") — which turns the workspace into a
provenance improvement, not just a comfort. Pairs with B2a (the two together
are the Phase-3 operator experience); scratchpad model calls are ordinary
routed tasks (stamped, budgeted). Notes/queries are working material, not
governed artifacts — no ADR needed unless attached-as-evidence is built, which
touches the disposition record schema (small ADR).

### B2c. Grouped dispositions without grouped judgment (Program Owner field report, 2026-07-20)

Hand-dispositioning the AML operation queue (123 findings) is excessively
laborious when many findings are similar. Three mechanisms, in descending
order of safety — the first two are spec-consistent as written; the third
requires an instruction-set amendment and is NOT recommended:

1. **Many-findings-per-operation (build this).** Operations should carry
   `finding_refs[]`: one MERGE resolves five D3 duplicates; one
   CANONICALIZE-DEFINITION resolves a D2 cluster and its D4 satellites. One
   disposition per *operation* then legitimately settles several defects with
   zero fidelity loss — every finding stays traceable to the move that
   resolved it. Requires a clustering step at proposal time (code heuristics
   on shared terms/items first; model assist optional) whose cluster
   membership is reviewer-visible, never silent.
2. **Sampled batch-finalize for codify (build this).** The routing table
   already says codify = "eligible to finalize; sampled human review (rate:
   open parameter)". Implement it as written: fix and log the sample rate
   (§15 open parameter — needs its ADR), reviewer inspects the sample,
   batch record names the rate, the sampled ops, and the reviewer.
3. **Cluster-review for clarify/fill_gap (do not build without an ADR).**
   The spec demands per-instance ⚖ disposition for these classes, for cause:
   effect class is per-instance — the one real change-class move hides in
   the cluster of ten similar-looking clarifies. Instead: **template
   dispositions** — reviewer multi-selects individually-inspected ops,
   confirms class per op (pre-filled from draft), writes ONE shared
   rationale; system emits N individual decision-log entries. Judgment stays
   per-instance; only the typing is batched.

Also a UI truth v1 under-communicates: parked (change/unresolved) operations
need no disposition — the Redesign Backlog is a legitimate resting state.
The mandatory queue is needs_review + the codify sample only. Pairs with
B2a/B2b as the Phase-3 throughput story.

### B2d. Primary actions belong at the top (Program Owner field report, 2026-07-20)

The finalize/ratify button sits below a very long scroll of disposition
cards; reaching it means scrolling past everything. General rule for v2:
phase-level actions (run invariants, ratify/certify, propose batch) live in a
**sticky header or action bar** that stays visible while the queue scrolls
beneath it, with a progress indicator ("14 of 41 dispositioned") and
jump-to-section links (needs review / eligible / parked). Subsumed by B2b's
workspace redesign if that lands first; listed separately so it isn't lost.

### B3. Document attachments during the purpose interview

Let the respondent attach documents (memos, org charts, prior reports) during
the Phase 0 back-and-forth, for the interviewer to draw on.

- Privacy: attachments are interview material → they belong in the `restricted/`
  store (ADR-016): gitignored, excluded from exports, consent rules apply.
- Provenance: any Purpose Statement claim derived from an attachment needs a
  basis reference (attachment id + location), same as `basis_answer_ids` —
  otherwise attachments become an unauditable side channel into a governed
  artifact. Needs a small schema extension → ADR.
- Practical: text extraction limits, size caps, and a visible list of what the
  interviewer was shown.

### B4. Progress / "thinking" indicator

Long operations (synthesis, distillation batches, defect runs) currently show a
static message. Add live progress: per-item status streaming (queued → focusing
→ extracting → verifying → done), elapsed time, and running cost.

- Pure UX; no governance implications; no ADR needed.
- Implementation note: server-sent events or polling a job-status endpoint;
  also the natural foundation for B2's auto mode (the stream is how you watch
  an unattended run).

### B2a. Distillation UX overhaul — fewer clicks, visible machinery (Program Owner field report, 2026-07-20)

Direct feedback after running the full AML distillation: the click-and-wait
loop (batch → wait on a static message → click again → hunt for what changed)
is way too long, and the interface says too little about what is happening
under the hood. Requirement, stated as outcomes rather than mechanisms: a full
corpus should distill with one or two decisions, not a dozen clicks; the
operator should be able to walk away and be told when something finished,
failed, or needs them; and at any moment the screen should answer "what is it
doing right now, what has it done, what did it cost so far."

This bundles and prioritizes three existing items into one build:
- **B2** (auto mode) supplies the fewer-clicks half — run-to-completion with a
  budget cap, an error circuit breaker, and the election logged.
- **B4** (progress stream) supplies the visibility half — per-item status
  (queued → focusing → extracting → verifying), elapsed time, running cost.
- **B5** (per-item jobs) is the plumbing both stand on.
Also implied: browser/desktop notification on completion or first error, and a
"what changed since I last looked" affordance (the v1 register diff is
invisible unless you know where to look — the defect-cards-at-the-bottom
episode was this same defect in another costume).

Priority: promoted to the top of Part B. The v1 experience proved the
governance pipeline; this is the main thing standing between the prototype and
something a working-group member could operate unassisted.

### B5. Per-item extraction jobs with live progress (from Codex review, 2026-07-19)

v1 runs a batch synchronously behind one static message; a failure surfaces
only at the end. v2: queue each item as a job, poll status per item (queued →
focusing → extracting → verifying), targeted per-item retry. Pairs with B4's
progress stream; no governance implications.

### B6. Derived Blueprint finalization gate (from Codex review, 2026-07-19)

assemble() is a live view over per-item files; the governing spec describes a
versioned composite artifact. Add an explicit ⚖ "finalize Derived Blueprint"
step: assembles the composite, hashes it, records a decision-log entry, and
downstream passes (refactor/redesign) read the frozen composite rather than
the live view. Mirrors the manifest-freeze pattern (OR-7). ADR required.

### B7. No-terminal operation (Program Owner request, 2026-07-20)

Everything today — install, start, restart, repairs — runs through terminal
commands the Program Owner pastes into Claude Code. v2 should not require a
terminal at all for normal operation: launch the workbench like an ordinary
application (double-clickable app or menu-bar item that starts/stops the
server and opens the browser), update it the same way, and surface
health/restart in the UI rather than in `make` targets.

- Options, in rising order of effort: a clickable launcher script → a menu-bar
  wrapper around the server (start/stop/status/logs) → a packaged desktop app
  (e.g., the server bundled with its own runtime, no Python setup).
- The launcher should absorb what the Makefile learned the hard way: clear the
  port before starting, always run the code that is on disk, verify the served
  build, and show these checks as a green/red status rather than shell output.
- Pairs with B1 (login) and B2a (fewer clicks): together they are the
  "operable by a non-technical working-group member, end to end" story.
- No governance implications; no ADR needed.

### B9. Model catalog — proper wiring (Program Owner request, 2026-07-21)

v1 added open-weight models (`nvidia/nemotron-4-340b-instruct`,
`moonshotai/kimi-k2`, `qwen/qwen3-235b-a22b`) to the per-task toggle as a
config-driven `catalog` list, so they are *selectable*. What's deferred is the
wiring that makes them *safely routable*:

- **Slug verification.** The catalog slugs are hand-entered. `make models` /
  `scripts/check_models.py` verifies IDs against the live OpenRouter catalog;
  v2 should verify the catalog too (not just task defaults/fallbacks) and flag
  any slug that no longer resolves, in the UI rather than only on the CLI.
- **Per-provider eligibility, surfaced at toggle time.** The router already
  enforces the no-training/ZDR provider preference at call time and fails
  sensitive tasks closed when no eligible provider exists (ADR-016). But the
  toggle does not yet *show* which models are ZDR/no-training eligible, so a
  user can pick an open-weight model for a sensitive task (interview,
  synthesis) and only discover the fail-closed at run time. v2: mark each
  catalog model's eligibility per task in the dropdown (e.g., grey out or badge
  "not eligible for sensitive tasks"), and explain the block inline.
- **Capability/cost metadata.** Show context window, structured-output
  reliability, and price class next to each model, so the toggle is an informed
  choice rather than a name. (Some models reject rich JSON schemas — the Azure
  lesson; the registry should carry a per-model structured-output flag and the
  router should prefer schema-in-prompt for models that need it.)
- **Diversity-family registration.** New families (`nvidia`, `moonshotai`,
  `qwen`) widen the pool the C-ADV2 second-census diversity rule can draw from;
  confirm the family-prefix extraction handles them and document the enlarged
  diversity set.
- Governance: no new gate; this hardens existing ADR-016 enforcement and makes
  it visible. A short ADR note if the registry schema gains per-model
  eligibility/capability fields.

### B10. Parking lot (captured, not yet scoped)

- Export bundle for working-group review (governed artifacts only, restricted
  store excluded, consented excerpts flagged) — partially specced in v1 PRD.
- Public/read-only mode for the eventual publication path.

---

## Suggested sequencing (advisory)

Cheap-and-sharp first: **A4** (taxonomy criteria) and **B4** (progress UI) are
small. **A1** (self-audit) before the first working-group demo if possible — it
answers the obvious skeptical question "who audits *your* artifact?". **B2**
naturally rides along with B4. **B1** (login) is the largest lift and the
gateway to real multi-user governance; **A2** lands with the second census;
**A3** waits for the liquidity redesign phase (M4+).
