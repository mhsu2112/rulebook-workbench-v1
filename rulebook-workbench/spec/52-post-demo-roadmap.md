# 52 — Post-Demo Roadmap & Sequencing

| | |
|---|---|
| **Status** | Draft 0.1 — planning aid, not a commitment |
| **Date** | 2026-07-21 |
| **Audience** | Program Owner; Foundry working group |
| **Companions** | `spec/50-v2-backlog.md` (the item catalog) · `spec/51-multi-user-openrouter-prd.md` (login PRD) |
| **Rule of the road** | The demo sets priority. This document is the decision *structure*, not a fixed plan. Revisit after the working group responds. |

## 1. The shape of the decision

The post-demo work is not one backlog to sort top-to-bottom. It is **two independent
tracks that answer two different questions**, plus **one connective decision that
should be made before either track commits**:

- **Track A — Deepen the method.** Makes the substantive pipeline more complete and
  more defensible. Answers: *"Is the output trustworthy, and is the chain finished?"*
  Built the way everything has been built so far (Program Owner + AI assistance).
- **Track B — Widen access.** Lets other people use the workbench safely. Answers:
  *"Can my colleagues log in and run this themselves?"* This is `spec/51`. Needs a
  **different resource** (security-competent engineer) and **two decisions only the
  Program Owner can make** before it can start.
- **The connective ADR — identity into governed records.** Sits between the tracks and
  should be written first regardless of which track leads, because it changes schemas
  both tracks touch and settles a governance-honesty question that matters even if
  login never ships (see §4).

The tracks are genuinely parallel: different skills, different failure modes, no shared
critical path except the connective ADR. Do **not** interleave their big builds as if
they were one queue.

## 2. Track A — Deepen the method

Ordered by dependency. Effort is expressed in relative size, not engineer-days, because
this track is AI-assisted (as all prior milestones were).

| # | Item | What it answers | Depends on | Size |
|---|---|---|---|---|
| A-1 | **Second census (C-ADV2)** — independent, diversity-enforced re-extraction of the existing blueprints, diffed against the first (backlog A2) | "How do I know the AI read the corpus right?" | existing Derived Blueprints | S–M |
| A-2 | **Blueprint self-audit** (backlog A1) — the six-attribute worksheet run against our *own* extraction | "Who audits *your* artifact?" | A-1 helpful, not required | S |
| A-3 | **Materialize the composite** (backlog B6) — apply the ratified operation trace to produce the target element tables | Turns the Target Blueprint from trace-form into a clean structured object | ratified Target Blueprints | M |
| A-4 | **Consolidated Rulebook drafting (P4.2)** with the fidelity loop — draft → re-distill → diff → deviation register | Completes the last diagram arrow (③ Align → the rulebook itself) | **A-3** (hard prerequisite) | L |

Rationale for this order: A-1 and A-2 harden and validate what already exists and are
the cheapest way to answer skeptics — do them first. A-3 is the honest foundation for
drafting and a hard prerequisite for A-4. A-4 is the capstone and the largest, most
sensitive build in the whole project (it emits prose that looks like rules); it stays
last because it should sit on validated, materialized inputs, not on trace-form
approximations.

## 3. Track B — Widen access (login / per-user OpenRouter)

The full design is `spec/51`. Its own six-phase plan is sound; reproduced here only to
place it in the larger sequence:

1. ADR, contracts, historical-migration design, hosting decision — 3–5 d
2. OIDC login, sessions, users, program membership — 4–6 d
3. Role authority, independence rules, restricted access — 3–5 d
4. Encrypted OpenRouter connection + request-scoped routing — 4–6 d
5. Usage ledger, run handoff, concurrency safety — 3–5 d
6. Security tests, migration, deployment, pilot fixes — 3–5 d
7. **Independent specialist security review — 2–4 d, before real credentials or
   restricted material touch the shared instance** (non-negotiable)

**Track B cannot start on priority alone.** Two decisions gate it (see §7): *who builds
the security-sensitive parts* (this is the one feature where AI-assisted-but-unreviewed
is genuinely dangerous — the failure mode is a leaked credential, not a wrong table) and
*where it is hosted* (which fixes the OpenRouter callback URL, the identity-provider
config, and where the restricted store physically lives). Until both are answered, the
track is parked no matter how it ranks.

## 4. The connective ADR — do this first, regardless

`spec/51` phase 1 already calls for an ADR. Elevate it: it is the pivot between the two
tracks and worth writing **before committing to either**, because —

- It decides **how authenticated identity enters the decision log and provenance
  stamps** — a versioned schema change to `decision_log_entry` and `provenance_stamp`
  that Track B builds on and Track A's outputs inherit.
- It settles the **historical-decisions honesty question**: the ~405 existing decisions
  were written under self-asserted identity stamped `identity_verified: true`. The ADR
  fixes the `identity_assurance` distinction (`legacy_self_asserted` vs
  `oidc_authenticated`) and the covering-artifact migration (`spec/51` §10) — leaving
  the append-only entries byte-for-byte unchanged while making the record honest about
  what was and wasn't verified. **This matters for Track A's publishable outputs even if
  login never ships.**
- It is cheap (1–2 days) and de-risks everything after it.

Write it early. It is the one item that is high-leverage under every demo outcome.

## 5. Dependency map

```
        (connective) Identity-into-governance ADR
                     │
        ┌────────────┴─────────────┐
   TRACK A (method)           TRACK B (access)
   A-1 second census          gate: who-builds? + hosting  ── decisions, not code
      │                            │
   A-2 self-audit             spec/51 phases 1→6
      │                            │
   A-3 materialize composite   phase 7 security review (before real creds)
      │
   A-4 Consolidated Rulebook drafting (P4.2)
```

Only two hard prerequisites exist: the ADR before Track B's schema work, and A-3 before
A-4. Everything else can float to fit attention and demo feedback.

## 6. Recommended sequence (held loosely)

**Default: lead with Track A.** For a working group evaluating a *method*, completing and
validating the method is worth more than making an unproven thing accessible — login is
plumbing that makes an unfinished thing reachable. The sequence:

1. **Connective ADR** (1–2 d) — always first.
2. **A-1 second census** → **A-2 self-audit** — validate what exists; strongest answer to
   skeptics; cheap.
3. **A-3 materialize composite** → **A-4 Consolidated Rulebook drafting** — finish the
   diagram.
4. **Track B** — begin only once (a) the demo shows access is the real bottleneck *and*
   (b) the two gating decisions in §7 are made.

**Branch on demo feedback:** if the working-group response is "everyone wants to use it
*now*," Track B jumps ahead of A-3/A-4 — but the connective ADR still goes first, and the
two gating decisions still block the start. A-1/A-2 (validation) should precede external
exposure in *either* ordering.

## 7. Decision gates — owned by the Program Owner, not by code

Surface these now; they block real work and are not engineering tasks:

1. **Who builds the security-sensitive parts of Track B?** Recommend: someone who has
   shipped OAuth / session / crypto. Not a solo AI-assisted build.
2. **Where is the shared instance hosted?** `spec/51` §15 gives three concrete options
   (private cloud VM / managed platform / office Mac mini). Choose with data-residency of
   the restricted store in mind.
3. **Which single identity provider?** (Google Workspace *or* Entra ID — one, per the PRD.)
4. **Who administers membership, and who is Program Owner of the three existing programs**
   in the authenticated world? (Migration bootstrapping — not covered by build phases.)
5. **Restricted-store access policy:** confirm break-glass (recorded reason + security
   event) rather than blanket admin read, per the revised PRD.

Decisions 1–2 gate Track B's *start*. Decisions 3–5 are needed by Track B phase 1.

## 8. Quick wins to interleave

Non-critical-path items from `spec/50` that improve daily use and give visible progress
between big builds — slot in as palate-cleansers, not as a track:

- **B9** model-catalog wiring (verify slugs, surface ZDR eligibility at toggle time).
- **B4** progress / "thinking" indicator on long operations.
- **B2a** distillation-UX (fewer clicks, live per-item status) — pairs with B4.

## 9. Sequencing traps to avoid

- **Backlog-order execution.** The backlog is a catalog, not a sequence; running it top to
  bottom mixes the two tracks and blocks on the wrong things.
- **Starting login before the two gating decisions.** It will stall mid-build on hosting
  and callback-URL specifics.
- **Drafting the Consolidated Rulebook (A-4) on trace-form inputs.** Materialize first
  (A-3), or the fidelity loop has a moving target.
- **Shipping access before validation.** Second census + self-audit (A-1/A-2) should
  precede putting the workbench in more hands, in either track ordering.
- **Treating the security review as optional polish.** It is a gate, before real
  credentials — not an acceptance checkbox.
