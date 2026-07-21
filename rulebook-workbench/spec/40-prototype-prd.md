# PRD — Workbench Prototype ("the app")

| | |
|---|---|
| **Status** | 0.2 — incorporates the Codex review of 0.1 under the MVP-speed lens of ADR-012–017: spec conflicts resolved, one-way doors closed, productionization parked visibly |
| **Owner** | Mike Hsu |
| **What this specifies** | The first working software prototype of the Rulebook Workbench: a web application that runs programs under `spec/30-instruction-set.md`, with per-task AI model selection through a single OpenRouter integration |
| **What this is not** | Production software, a public service, or the engine's final architecture. Code lives in its own repository (per ADR-001); this PRD is that repository's founding document |
| **Governed by** | `governance/SPEC-HIERARCHY.md` (this is an L3-adjacent product spec: it implements L2 procedure and L3 mechanics in software and may add engineering detail, never new governance authority) |
| **Companion documents** | `spec/30-instruction-set.md` · `spec/20-profile-regulatory.md` · `skills/purpose-elicitation/SKILL.md` · `schemas/` |

---

## 1. In plain English

The documents in this repository describe a disciplined way to clean up a
tangled body of regulation: interview the sponsor until the purpose is sharp,
assemble every relevant document, distill the whole pile into a readable
blueprint, fix the blueprint under strict rules, and redraft the materials to
match — with a paper trail at every step and a named human making every
judgment call. So far, that method exists on paper. The prototype turns it
into a tool you can actually sit down and use: a screen where the interview
happens, where the document pile is visible and frozen, where the blueprint
and its recorded flaws can be browsed with every statement linked to its
source, and where the review queue puts each pending judgment in front of
the right person with an Accept / Reject / Modify button and a required
rationale box.

AI does the heavy lifting throughout — reading thousands of pages,
extracting obligations, spotting contradictions, drafting proposals. But
"AI" is not one thing. Some models are excellent conversationalists but
mediocre at digesting a 400-page examination manual; some are painstaking
readers but slow and expensive; some are cheap and fast, which is exactly
what you want when the task is checking ten thousand citations rather than
writing prose. A workbench that used one model for everything would overpay
for the easy tasks and underperform on the hard ones. So the prototype
assigns each kind of task its own default model — one for the intake
interview, another for distillation, another for verification — and lets the
user change any of those assignments from a settings panel, per task or per
program.

The practical question is how to reach many different models — built by
different companies, with different billing and different interfaces —
without building and maintaining a separate integration for each. The answer
is a switchboard service called **OpenRouter**: one account, one API key,
one uniform way of making requests, and behind it hundreds of models from
dozens of providers. The workbench tells the switchboard which model it
wants *for each individual request*; switching the distillation step from
one company's model to another's becomes a one-line settings change rather
than an engineering project. (One clarification of the natural reading of
"a single request": a program is not one giant AI call — a distillation run
may involve hundreds of calls. "Single" here means a single *integration*:
one vendor relationship, one key, one code path, through which every call to
every model flows.)

There is a methodological payoff too, beyond convenience. Our own protocol
requires an independent second census "by a different model, team, or
method," and treats which-model-said-what as evidence. Because every AI call
goes through the switchboard, the prototype can *enforce* that independence
— refusing to run a second-opinion check on the same model family that
produced the first opinion — and it stamps every AI-produced artifact with
exactly which model, at which settings, produced it. The audit trail the
method promises extends down into the machinery.

---

## 2. The direct answer to the motivating question

**Can the multi-model toggle be set up with a single OpenRouter API
integration? Yes.** OpenRouter exposes one OpenAI-compatible endpoint
(`https://openrouter.ai/api/v1`) with one API key; the model is chosen
per-request via the `model` field (e.g., `anthropic/claude-…`,
`openai/gpt-…`, `google/gemini-…`), with an optional `models` fallback array
tried in priority order when the primary fails, provider-routing preferences
(including zero-data-retention and no-training filters), and per-model
structured-output support. The prototype therefore needs exactly one
external AI dependency and one secret to manage. What it is *not* is one
request per program: each task step issues its own request(s); the router
(§5) decides which model each one goes to.

---

## 3. Goals / non-goals

### Goals

- **G1 — Run a refactor vertical slice (ADR-014).** One program (the
  refactor MVP: a BSA/AML sub-slice) from intake interview through
  refactor-pass dispositions to Target Blueprint ratification and a
  prototype export, entirely inside the app. Explicitly *not* an
  end-to-end program: P4–P5 remain out of scope, and the exported
  operation log is an **operation trace**, distinct from the governed
  Crosswalk (which requires consolidated provisions that the prototype
  does not draft).
- **G2 — Per-task model routing.** Every AI call site is a named task with a
  default model, user-visible and user-overridable, executed through the
  single OpenRouter integration.
- **G3 — Governance as software.** The instruction set's gates, routing
  tables, and ⚖ decision points are enforced by code: schema-validated
  artifacts, an append-only decision log, disposition state machines, and
  blocked progression on unmet gates.
- **G4 — Full provenance.** Every AI-produced statement carries its task,
  model, parameters, and request identity; every run is stamped with scope
  contract version + manifest hash + model configuration.
- **G5 — Model-diversity enforcement.** Second-opinion tasks (C-ADV2-style)
  are refused on the primary run's model family.
- **G6 — Demoable.** The working group can watch a program move through the
  phases in one sitting.

### Non-goals

- **NG1.** Production hardening, multi-tenancy, SSO. (Single team, local or
  single-host deployment.)
- **NG2.** The automated `baseline_set_for` resolver — Phase 3 effect
  classification remains human-applied per `spec/20` §3, and the UI says so.
- **NG3.** The redesign pass UI beyond data-model stubs (the Ratified
  Mandate and Misalignment Register types exist; their screens come after
  the refactor slice works).
- **NG4.** Phases 4–5 beyond crosswalk data structures.
- **NG5.** Operative legal text, per ADR-003 — the app watermarks every
  export as proposed/advisory.
- **NG6.** Automated census/web harvesting. The corpus is imported from the
  existing census work; the app freezes and hashes, it does not crawl.

---

## 4. Users and roles

The §4 roles of the instruction set, mapped to app accounts: Program Owner,
Scope Owner, Distillation Lead, Policy Reviewer, Corpus Steward. A single
login may hold multiple roles, and every ⚖ action records *which role*
performed it — but **two-person rules require two distinct verified
identities (ADR-012)**. Role assignment cannot manufacture independence: a
solo operator may exercise the full workflow for demonstration, and the
resulting audit is marked `non_gating_demo_only` — it cannot satisfy a gate,
and any export containing it says so on its face. A compliant fidelity
audit requires a second person; there is no warning-and-proceed path.

---

## 5. Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Web UI (single-page app)                                  │
│  dashboard · interview · corpus · blueprint · registers ·  │
│  review queue · crosswalk · model settings · run log       │
└──────────────────────────┬─────────────────────────────────┘
                           │ REST/JSON
┌──────────────────────────┴─────────────────────────────────┐
│  App server (Python)                                       │
│  ┌──────────────┐ ┌───────────────┐ ┌───────────────────┐  │
│  │ Phase engine │ │ Gate checker  │ │ Disposition state │  │
│  │ (P0–P3 flow) │ │ (schema+rule) │ │ machine + ⚖ log   │  │
│  └──────┬───────┘ └───────────────┘ └───────────────────┘  │
│  ┌──────┴──────────────────────────────────────────────┐   │
│  │ MODEL ROUTER                                        │   │
│  │ task registry (models.yaml) · per-program overrides │   │
│  │ diversity rule · retries/fallbacks · cost meter ·   │   │
│  │ provenance stamper                                  │   │
│  └──────┬──────────────────────────────────────────────┘   │
│         │  one integration: OpenAI-compatible client,      │
│         │  base_url=openrouter.ai/api/v1, one API key      │
└─────────┼──────────────────────────────────────────────────┘
          ▼
   OpenRouter  ──►  {Anthropic, OpenAI, Google, Mistral, …}
┌────────────────────────────────────────────────────────────┐
│  Storage: program workspace on disk                        │
│  artifacts as schema-validated JSON (git-friendly) ·       │
│  SQLite index · append-only decision-log JSONL ·           │
│  raw AI request/response archive (hashed)                  │
└────────────────────────────────────────────────────────────┘
```

Stack recommendation (open decision D1): **Python/FastAPI** server — the
eventual engine (T0–T8, statute-distill tooling) is Python, so extraction
and validation code written for the prototype migrates — with a **React**
SPA. SQLite + on-disk JSON keeps every artifact human-readable,
git-versionable, and exportable; no database server to administer.

## 6. The model router (the heart of the prototype)

### 6.1 Task registry

Every AI call site in the codebase is a **named task** — nothing calls the
model ad hoc. Each task is declared in `models.yaml`:

```yaml
tasks:
  intake_interview:
    phase: P0
    description: Conversational purpose elicitation (SKILL.md conduct rules)
    default_model: <fast, strong instruction-following chat model>
    params: { temperature: 0.7, max_tokens: 2048 }
    fallbacks: [<second-choice chat model>]
    structured_output: null        # free conversation; synthesis task differs
    allow_families: any
  purpose_synthesis:
    phase: P0
    description: Typed PurposeStatement from interview transcript
    default_model: <frontier reasoning model>
    structured_output: schemas/purpose_statement.schema.json
  distill_extract:
    phase: P2
    description: Obligation-family extraction into element tables
    default_model: <frontier long-context model>
    params: { temperature: 0.2, max_tokens: 16384 }
  claim_verify:
    phase: P2
    description: Claim-level verification records; high volume, parallel
    default_model: <fast inexpensive model>
  defect_detect:      { phase: P2, default_model: <frontier long-context model> }
  operation_propose:  { phase: P3, default_model: <frontier reasoning model> }
  effect_classify_assist:
    phase: P3
    description: DRAFT effect-class analysis for the human classifier (NG2)
    default_model: <strongest reasoning model>
  second_census:
    phase: P1
    description: Independent second pass for C-ADV2
    default_model: <deliberately different family than distill_extract>
    diversity_rule: must_differ_family_from [distill_extract, defect_detect]
  render_prose:       { phase: any, default_model: <fast inexpensive model> }
```

Concrete model IDs live only in `models.yaml` (the model market moves too
fast for a PRD); the PRD fixes the *shape*: every task declares phase,
default, params, fallbacks, structured-output schema, and family
constraints.

### 6.2 Routing behavior

- **Resolution order:** per-program override → user's task-level toggle →
  `models.yaml` default. Every resolution is logged.
- **The toggle UI:** the Model Settings panel lists tasks grouped by phase,
  each showing its current model, provider, rough cost class (¢/$$/$$$ per
  1k tokens, live from OpenRouter metadata), and a dropdown of allowed
  alternatives. Changing a model mid-program is allowed and stamps
  subsequent runs; it never silently re-runs prior work.
- **Diversity enforcement (G5):** a task with a `must_differ_family_from`
  constraint hard-fails (with a clear message) if the user selects a model
  whose family matches the *actually used* model of the run it must be
  independent of — for `second_census`, that comparison is against the
  program's primary census **run record**, not against task defaults. The
  interim check is family = provider prefix of the model ID, acknowledged
  as weak (shared lineages, fine-tunes, and shared prompts escape it); the
  run record therefore also captures model lineage/version, provider
  endpoint, prompt/method version, and operator, so richer independence
  profiles (different lineage, different team, or materially different
  method) can be enforced later without re-instrumenting (ADR-017f).
- **Fallbacks & retries:** transient failures retry with backoff; hard
  failures fall through the task's `fallbacks` chain (OpenRouter's `models`
  array). A fallback that changes the model is a provenance-visible event,
  and for diversity-constrained tasks the fallback list is pre-filtered
  against the constraint.
- **Structured outputs:** tasks with a declared schema request structured
  output where the routed model supports it, and otherwise run
  JSON-mode + local schema validation + bounded repair-retry loop. Output
  that never validates fails the task run visibly; invalid JSON never
  enters an artifact.
- **Privacy posture (fail-closed, ADR-016):** all requests set provider
  preferences to no-training/ZDR-eligible providers by default (corpus
  material is public regulatory text, but interview transcripts are ADR-010
  sensitive). Tasks flagged `sensitive` (the interview family) **fail with
  a clear error when no policy-eligible provider is available** — the
  router never silently relaxes the privacy policy to complete a call. A
  per-program setting can tighten the default to ZDR-only, accepting the
  smaller provider pool.
- **Cost metering:** the router accumulates OpenRouter's usage/cost data
  per task, per phase, per program; the dashboard shows running spend, and a
  per-program budget triggers a soft warning and a hard stop (both
  configurable; hard stop requires Program Owner acknowledgment to lift).

### 6.3 Provenance stamp (G4)

Every model response that contributes to an artifact is wrapped:

```json
{
  "task_id": "distill_extract",
  "model_requested": "…", "model_served": "…", "provider": "…",
  "params": { "temperature": 0.2 },
  "request_id": "…", "timestamp": "…",
  "app_commit": "…", "registry_version": "…",
  "prompt_hash": "sha256:…", "skill_version": "…",
  "fallback_history": [],
  "input_hash": "sha256:…", "output_hash": "sha256:…",
  "cost": { "prompt_tokens": 0, "completion_tokens": 0, "usd": 0.0 }
}
```

The stamp records generously from M0 because provenance is a one-way door —
what isn't captured at run time is unrecoverable. Raw request/response
bodies are archived (hashed, compressed) in the restricted store (§8);
artifacts reference stamps by hash. This makes "which model said this, under
what settings" answerable for the life of the archive under the D6 retention
policy. The stamp is *provenance* (what happened); the full reproducibility
manifest — enough to attempt a rerun, with the provenance / reproducibility
/ determinism distinction made explicit — is deferred (ADR-017b), which is
why the prototype claims auditability, not replayability.

## 7. Phase coverage (what the prototype actually implements)

| Phase | Coverage | Key screens / behaviors |
|---|---|---|
| **P0** | Full for refactor mode | Interview chat (skill conduct rules as system prompt; streaming); typed PurposeStatement assembly; kill tests surfaced in-flow; ratification screen (⚖, rationale required); MandateHypotheses captured but P0.9 ratification UI deferred (NG3) |
| **P1** | Import-freeze, not census | Manifest import from the existing BSA/AML census (CSV/JSON); status/evidence-role display; dedup report view; freeze button → manifest hash; gap register CRUD. Second census runs as a routed task (`second_census`) over the same contract, diff view included |
| **P2** | Full on a bounded slice | Family partition editor; distillation runs (per family, resumable, cost-visible); blueprint browser with citation popovers to source spans; defect register (D1–D10) with verbatim excerpts; two-frame fidelity audit runner (sampling seeded from manifest hash; adjudication screens) |
| **P3** | Refactor pass with human classification workflow; redesign stubs | Operation proposals with effect-class *drafts* (`effect_classify_assist`, NG2); the human classification step is a real workflow, not an Accept button: a **classification packet** form capturing affected (actor, activity, jurisdiction, as-of) cells, the baseline provisions consulted (citations), hierarchy/status/applicability notes, conflicting sources, the elected class — with `unresolved` as a first-class result routing like `change` — and rationale. Routing table enforced in the review queue; disposition state machine; invariant checks; Target Blueprint ratification |
| **P4–P5** | Not implemented (ADR-014) | The export bundle (blueprint, registers, decision log, **operation trace**, provenance archive) is watermarked ADVISORY DRAFT. The operation trace is explicitly not the governed Crosswalk; Crosswalk data structures exist as schema stubs only |

Gates are literal: a phase's "Continue" control is disabled until the gate
checklist (schema-validated artifacts + rule checks + required ⚖ entries)
passes. Waivers follow the **ADR-013 taxonomy**: every gate rule carries
`waiver_policy ∈ {nonwaivable, program_owner_waivable, deviation_only}`,
and there is no generic "waive gate" control anywhere in the app.
Nonwaivable at minimum: mode-gated change control (OR-1), human disposition
of normative findings (OR-4), reviewer independence (ADR-012), and schema
validity of ratified artifacts. A permitted waiver is per-rule, logged with
role and rationale.

## 8. Storage and artifact model

One directory per program:

Two stores with different rules (ADR-016):

```
programs/<program_id>/
  governed/                     # git-safe by design; schema-validated JSON
    purpose_statement.json      #   (verbatim answers here only if consented)
    mandate.json                # hypotheses (schemas/mandate.schema.json)
    scope_contract.json
    manifest/  manifest.json + manifest.sha256
    blueprint/ derived/… refactored/… target/…    (per-family JSON)
    registers/ defects.json deviations.json gaps.json
    decisions.log.jsonl         # append-only; every ⚖, waiver, override
    runs/      <run_id>/stamps.jsonl              (provenance stamps only)
  restricted/                   # GITIGNORED; access-controlled reads
    transcripts/                # verbatim interview logs (ADR-010)
    raw/       <run_id>/        # raw model request/response bodies
  exports/   <date>-bundle/     # built from an explicit allowlist only
```

`governed/` is designed to be committed to git wholesale, making program
history version-controlled. `restricted/` never enters git — the repo
scaffold ships the `.gitignore` and the export builder draws exclusively
from an allowlist, so sensitive material cannot leak into history or
bundles by default. Retention/deletion for `restricted/` is D6; encryption
at rest is deferred (ADR-017c). Contracts arrive with their milestones
(ADR-015): M0 ships the base set (manifest, decision log, provenance stamp,
gate rule), and no milestone passes while emitting an uncontracted artifact
— AGENTS.md rule 5 applies throughout.

## 9. Security and privacy

- One secret: the OpenRouter key, held server-side (env var / OS keychain),
  never in the browser. Per-key spend limit set at the OpenRouter account
  level as the backstop behind the app's own budget stop.
- Corpus content is public regulatory material; interview transcripts are
  the sensitive class (ADR-010) — stored in the workspace with
  access-controlled reads in the UI, excluded from exports except consented
  excerpts, and sent to models only under the no-training/ZDR provider
  preference.
- The app binds to localhost by default; single-host demo deployment is a
  conscious decision (D3), not a default.

## 10. Milestones

- **M0 — Router + walking skeleton (1 wk).** Repo scaffold (own repo, per
  ADR-001, with pyproject/tests/`make check` from day one — the Codex item 2
  obligations land here); model router with task registry, provenance
  stamps, cost meter; one trivial task through OpenRouter; the ADR-015 base
  contracts (manifest, decision log, provenance stamp, gate rule) and the
  ADR-016 store split with its `.gitignore`.
  *Exit:* `make check` green; a routed, stamped, fallback-tested call; base
  schemas validating; a sensitive-task call observed failing closed against
  a deliberately empty provider pool.
- **M1 — Intake (1–2 wk).** Interview chat + purpose synthesis +
  ratification + typed artifacts. *Exit:* a ratified PurposeStatement for
  the AML slice, produced entirely in-app; the full applicable
  purpose-elicitation eval suite (refactor-relevant cases C01, C04–C07,
  C09–C12, C14–C16) passes against the in-app skill, not a hand-picked
  subset.
- **M2 — Corpus + freeze (1 wk).** Manifest import, freeze/hash, gap
  register; second-census diff view. *Exit:* frozen manifest for the AML
  slice with hash-stamped runs.
- **M3 — Distill (2–3 wk).** Extraction, blueprint browser, defect register,
  claim verification, fidelity audit frames. Audit sampling rates and
  precision/recall thresholds are fixed and logged *before* the audit runs
  (ADR-009 requires it; instruction set §15.1 closes here). *Exit:* Derived
  Blueprint + Defect Register for the slice; both audit frames run against
  the pre-registered thresholds; a second person performs adjudication or
  the audit carries the `non_gating_demo_only` mark (ADR-012).
- **M4 — Refactor pass (2 wk).** Proposals, routing table, review queue,
  dispositions, invariants, ratification. *Exit:* Target Blueprint for the
  slice; zero open dispositions; export bundle.
- **M5 — Working-group demo (1 wk).** Polish the demo path; cost report;
  the §11 metrics dashboard. *Exit:* a scripted demo run on a fixed fixture
  corpus completes without operator intervention beyond the scripted ⚖
  actions, in under 45 minutes, with the export bundle produced and every
  demo-only limitation (ADR-012 marks, operation-trace framing, manual
  classification) visible on screen rather than narrated around. Full
  per-milestone acceptance matrices remain deferred (ADR-017d); this exit
  is the lightweight fixture-and-checklist version.

Redesign-pass UI (P0.9 ratification, Misalignment Register, objective-hook
review) is chartered as the next PRD revision after M5, against the
liquidity MVP.

## 11. Metrics

Product: cost per program / per phase / per task (the router's meter);
task latency; fallback and structured-output-repair rates; review-queue
throughput (dispositions/hour, median queue age). Method (from instruction
set §13, surfaced on the dashboard): fidelity precision/recall,
citation-integrity rate, % provisions with blueprint hooks, register
closure, unlogged-change count (target 0).

## 12. Risks

| Risk | Mitigation |
|---|---|
| Model drift under a stable name (provider swaps weights) | Pin fully-qualified model IDs incl. version tags where offered; record `model_served` + provider per call; treat unexplained metric shifts as a drift signal |
| OpenRouter as single point of failure / lock-in | The integration is OpenAI-compatible by construction; the router's client is base-URL + key config, swappable to any compatible gateway or direct provider in one place |
| Structured-output quality varies by model | Schema-validate everything locally; bounded repair loop; per-task model constraints exclude models that persistently fail validation |
| Cost runaway on large corpora | Per-program budget with hard stop; per-task cost classes visible at toggle time; distillation runs are resumable and per-family, never monolithic |
| Provider privacy policies change | Default no-training/ZDR preference is config, revisited per program; interview transcripts flagged sensitive regardless |
| The toggle invites cargo-cult model shopping | Every override is logged with who/when; the C-ADV2 diff view is the honest way to compare models — the dashboard links to it from the settings panel |

## 13. Open decisions

- **D1 — Stack. ELECTED (2026-07-18):** FastAPI + React + SQLite/JSON per
  §5.
- **D2 — The AML demo slice. ELECTED (2026-07-18) via a live P0.1
  interview** (the first dogfood run of the elicitation skill): **AML/CFT
  program-establishment obligations (the "pillars" rules) for depository
  institutions + MSBs + broker-dealers incl. the FINRA SRO layer**, refactor
  mode, other sectors as named boundaries. Ratified Purpose Statement:
  `programs/aml-program-rules-refactor-demo/governed/purpose_statement.json`
  (0.2, DL-001) — which also serves as the fixture program for the
  M-milestones.
- **D3 — Demo deployment. DEFAULT ELECTED (2026-07-18):** localhost +
  screen share; revisit before M5 only if working-group members need
  hands-on access (which would mean single-host + logins, ~1–2 days extra).
- **D4 — models.yaml initial assignments. DEFERRED TO M0 by design:** the
  concrete model IDs are filled in on build day from the then-current
  OpenRouter catalog. Interim selection criteria: cost class, context
  window, observed structured-output reliability on our schemas;
  qualification benchmarks are the v2 standard (ADR-017a). Revisit at each
  milestone.
- **D5 — Interview implementation. ELECTED (2026-07-18):** skill verbatim
  as system prompt at M1; a code-structured state machine only if eval
  cases fail.
- **D6 — Raw-archive retention. PROVISIONAL DEFAULT (2026-07-18):**
  interview-task raw bodies kept 90 days then deleted; no encryption at
  rest in the prototype (ADR-017c). Explicitly provisional — revisit at v2
  or on first external respondent, whichever comes first.
