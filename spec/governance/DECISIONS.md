# Decision Log (ADRs)

Append-only. Format: context → decision → consequence. Status: `accepted` /
`proposed` / `superseded-by-ADR-n`. Source review: Codex cross-review of
2026-07-18 ("the nine improvements"), adjudicated by Mike Hsu.

---

**ADR-001 — Separate governing-materials repository.** `accepted`
Context: instruction set, skill, PRD, and repo did not form one consistent
system; the statute-distill directory is not a standalone git repo (git root
resolves to the home directory) and mixes research fixtures with governing
docs. Decision: create `Foundry/rulebook-workbench` as the governing-materials
repo with the SPEC-HIERARCHY layer model; statute-distill remains the
research/reference-implementation repo; engine code gets its own repo at T0.
Consequence: terminology and functions can be aligned here without breaking
existing projects; reproducible-build obligations (pyproject, Makefile, tests,
`make check`) attach to the future code repo, not to this one.

**ADR-002 — Versioning convention.** `accepted`
Documents carry semver in headers, bumped in place (git history holds
priors); the product milestone "workbench v1" (dual-mode) is named only in
README/ADRs. Resolves the "named v0.2 but opens as v1" defect.

**ADR-003 — Operative-text product boundary.** `accepted`
PRD NG2 stands; Phase 4 outputs are *proposed* consolidated drafts (advisory
working papers), never operative instruments. See SPEC-HIERARCHY §Standing.

**ADR-004 — Primitive governance: select + mapped extension.** `accepted`
Core set stays at fifteen. Regulatory profile selects its subset and extends
by declared mapping (`RECALIBRATE` ⊂ `REGRADE` specialization; `INTRODUCE`
usage constrained per ADR-005). Unmapped operations prohibited.

**ADR-005 — `fill_gap`/`INTRODUCE` rule.** `accepted`
In the refactor pass, `INTRODUCE + fill_gap` is permitted **only** when an
applicable authority baseline (per `baseline_set_for`, spec/20 §3)
establishes that the duty already exists and the operation merely makes it
explicit — with human review in every instance. Absent that baseline the
effect is `change` (or `unresolved`) and the move parks. Resolves the
contradiction where D9 gaps were finalizable but the operation to fix them
was whitelisted out.

**ADR-006 — MandateHypotheses vs. RatifiedMandate.** `accepted`
The elicitation interview produces `MandateHypotheses` (attributed,
non-authoritative candidate framings) only. A `RatifiedMandate` is created
solely in a Principal-led P0.9 process with verified identity/authority.
Rankings from a non-Principal respondent are never recorded as "adopted."
Prevents laundering a sponsor's preferences into apparent policy authority.

**ADR-007 — Compound-program decomposition.** `accepted`
Exactly two modes, no blend — but compound initiatives decompose by rule
rather than being forced into one artificial election: (a) refactor program
now + separately chartered redesign successor; (b) one redesign program whose
refactor pass is an explicitly gated subprogram (OR-8); (c) separate programs
by mutable instrument tier or by Authority. The skill applies this at S2;
the instruction set records the decomposition in the Purpose Statement.

**ADR-008 — Regulatory effect classification requires a baseline resolver.** `accepted`
`clarify` / `fill_gap` / `change` cannot be established by structural diff
alone. The regulatory profile defines
`baseline_set_for(target, actor, activity, jurisdiction, as_of)` resolving
hierarchy & delegation, applicability & effective intervals, status controls
(incl. stays/vacaturs), evidentiary ceilings, live-source conflicts, and the
operative-law / authoritative-interpretation / guidance / enforcement-evidence
distinction. Spec: spec/20 §3. Implementation lands with the engine repo.

**ADR-009 — Two-frame fidelity audit.** `accepted`
P2.6 uses output→source sampling for precision AND source→output sampling for
recall; stratified (obligation family, source role, hierarchy, status);
sample seed derived deterministically from the manifest hash; thresholds
fixed before the pilot.

**ADR-010 — Interview transcript vs. ratification artifact.** `accepted`
The verbatim interview log is an *internal evidentiary transcript* (access-
controlled, retention rules TBD); the Purpose Statement for ratification and
any publication carries synthesized conclusions plus only the verbatim
excerpts the respondent consents to. Respondents are told this at interview
start. Resolves the tension between verbatim logging and public-grade outputs.

**ADR-011 — Skill evaluation suite.** `accepted`
The purpose-elicitation skill is a governance control and gets transcript-
level behavioral regression tests (evals/purpose-elicitation-cases.md):
15–25 synthetic cases scored for mode accuracy, unauthorized inference,
question budget, kill-test performance, open-item quality, and output
consistency. A conduct-rule change without an eval update is an invalid
change (AGENTS.md rule 6).

*ADR-012 onward arise from the Codex review of PRD 0.1 (2026-07-18),
adjudicated with an explicit MVP-speed lens: resolve conflicts and one-way
doors now; park productionization visibly (ADR-017).*

**ADR-012 — Reviewer independence is not simulable.** `accepted`
Context: PRD 0.1 §4 let one human holding two roles satisfy a two-person
rule with a warning; instruction set §4 says the fidelity adjudicator MUST
NOT be the producer. Decision: a two-person rule requires two distinct
verified identities. A solo-operated demo may *run* the workflow, but the
resulting audit is marked `non_gating_demo_only` and cannot satisfy a gate;
the export says so. Consequence: demos stay honest about their own
governance; compliant audits require a second person, full stop.

**ADR-013 — Gate waiver taxonomy; no generic waiver.** `accepted`
Every gate rule carries `waiver_policy ∈ {nonwaivable,
program_owner_waivable, deviation_only}`. Nonwaivable at minimum: OR-1
(mode-gated change control), OR-4 (human disposition of normative
findings), ADR-012 independence, schema validity of ratified artifacts.
The app never implements a generic "waive gate" control; waivers are
per-rule, logged, and only where the policy permits. The full
machine-readable gate catalogue (rule ID, evidence, role, failure message)
is built incrementally per milestone, but the taxonomy binds from M0.

**ADR-014 — Honest MVP boundary.** `accepted`
The prototype is a **refactor vertical slice**: P0 interview → P1
import-and-freeze → P2 distill → P3 refactor pass → Target Blueprint
ratification → prototype export. It is not an end-to-end program. Its
operation log is exported as an **operation trace**, explicitly distinct
from the governed two-way Crosswalk (which requires P4 consolidated
provisions and stays out of scope).

**ADR-015 — Contracts land with their milestone.** `accepted`
Modified adoption of "schemas before UI": rather than all contracts before
any build, each artifact's schema (+ cross-references, state transitions,
immutability rules) is defined in the same milestone that first produces
the artifact — M0 ships the thin base set (manifest, decision log,
provenance stamp, gate rule). A milestone that emits an uncontracted
artifact does not pass. Preserves the gate-checker's foundations at MVP
speed.

**ADR-016 — Split stores; sensitive tasks fail closed.** `accepted`
The program workspace splits: `governed/` (schema-validated artifacts,
hashes, decision log — git-safe by design) and `restricted/` (interview
transcripts, raw model request/response bodies — gitignored, access-
controlled, retention per D6). Exports draw from an allowlist only. Tasks
flagged sensitive (interview family) FAIL when no provider meeting the
no-training/ZDR policy is available — the router never silently relaxes
privacy policy. Encryption at rest: deferred to ADR-017 list.

**ADR-017 — Deferred productionization register.** `accepted`
Parked as explicit v2+ obligations so deferral is a decision, not amnesia:
(a) model qualification benchmarks before dropdown exposure (D4 interim:
cost/context/structured-output-reliability); (b) full RunManifest with the
provenance/reproducibility/determinism distinction; (c) encryption at rest
for the restricted store; (d) full per-milestone acceptance matrices with
fixture corpora (M-milestones get lightweight fixture + threshold checks
now); (e) complete gate catalogue tooling; (f) independence *profiles*
(lineage/team/method) beyond the interim family check. Each returns to the
board at the v2 PRD.

**ADR-018 — Owner copy of the Purpose Statement carries the transcript.** `accepted`
Amends ADR-010. The Purpose Statement exists in two copies. The *owner copy*
(the program owner's own record) appends the full verbatim interview
transcript as Appendix A and is marked internal. The *share copy*, and
anything published, still carries synthesized conclusions plus only the
verbatim excerpts the respondent consents to. The transcript itself stays in
`restricted/` (ADR-016); share packages never include it. Respondents are
told at interview start that the owner copy includes the transcript.
Interviews recorded before this ADR were given the ADR-010 notice only; their
owner copies include the transcript on the program owner's decision
(25 September 2026).

**ADR-019 — Explorations: branches outside the official record.** `accepted`
A program may have explorations: branches that start from one changed
interview answer and run forward on their own, so staff can test other
perspectives without adding to the official record (design note, 25 September
2026). A branch lives inside its program (`explorations/<id>/`) and is
addressed as `<program>~x-<id>`, so every step and gate works inside it
unchanged. It copies only what the changed answer does not affect. Its
decisions go to its own log, numbered `EX-<ID>-###`; its ratifications are
recorded as `exploration_ratification` and unlock only the branch's own later
steps. Any signed-in user may act in any role inside a branch, and the log
records who acted and in which role. Branch documents and packages are marked
as not part of the official record, and branches never appear in the
program's packages. A branch inherits its program's pinned models. It joins
the official record only by promotion: the Program Owner creates a new
official program from it (the ADR-007 pattern), its provisional ratifications
are reset for re-ratification, and one decision is logged in each program.


*Addendum 1 (25 September 2026): source explorations.* A branch may instead
start from a changed set of sources. It keeps the program's ratified Purpose
Statement (and any ratified Mandate) as they are, and reopens the frozen corpus
as a draft so sources can be added, replaced or removed. The official corpus is
not touched; the branch records which sources the official corpus held. When the
branch re-freezes its corpus, extractions of sources it kept are carried over
(the scope they were drawn against has not changed), and only new or replaced
sources are distilled; defect detection, the blueprint summary and every later
step run again across all sources. Spreadsheet sources (.xlsx) are read as text
row by row, each value labelled with its column heading, so they can be cited
like any other source.

**ADR-020 — Field-level comparison.** `accepted`
Distill gains a field-level step (design agreed 25 September 2026) so that
reporting regimes can be compared field by field, as RegGenome did for the FCA,
without depending on the regulator's spreadsheets being prepared for the purpose.
The Program Owner picks the field sources and names each one's regime. A
regulator's workbook is read by code after one model call per sheet says which
columns hold the field number, name, definition, format, validation rules and
mandatory/conditional/optional flags; each field cites its source, sheet and row,
and its quote is the row's own text line. A source without a workbook is read by
the model, and a field is kept only if its quote is found verbatim in the source.
The comparison offers each field its likeliest counterparts in the other regime
(by the words of names and definitions) and has the model say which record the
same data point and how they differ: identical, format, definition, validation or
applicability. It also drafts whether harmonizing would change what firms must
report; that draft informs, but never replaces, the human effect classification
in Refactor (PRD NG2). Matches are joined into unified rows; every row spanning
two or more regimes becomes a cited finding in the Defect Register (run
`defects-fields`: D1 validation conflicts, D2 definition or format differences,
D10 applicability differences, D3 identical duplicates) and is worked in Refactor
like any other defect. Once Refactor has worked a field finding, the field
sources and the comparison are fixed. The Field Register downloads as an Excel
workbook. No new package is needed: workbooks are read and written with the
standard library.
