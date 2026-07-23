# 55 — Worksheet / Ledger Architecture (four-zone UI)

| | |
|---|---|
| **Status** | Draft 0.1 — design spec for approval BEFORE any UI code |
| **Date** | 2026-07-23 |
| **Audience** | Program Owner; Foundry working group |
| **Companions** | `spec/54` (presets — folds into model policy here) · ADR-016 (restricted store) · the decision-log + provenance-stamp contracts |
| **Decisions baked in** | Full four-zone rebuild · record panel **tab-scoped** (program-wide only on Overview) · **model policy is a ratified decision** · bottom terminal is **contextual** (one dock, the phase's interviewer) |
| **Primary function** | Standing up a NEW program. The layout is judged first on that flow, not on reviewing finished ones. |

## 1. The principle

Every phase currently does two jobs in one surface: it is a place to **act**
(ask, propose, disposition, ratify, freeze — forward-looking) and it is the
**record** of what was acted (artifact, decision-log entry, provenance —
backward-looking). Merging them is why it "feels like editing a spreadsheet as
you go," and it slightly undercuts the governance story, where a decision is an
*event* and the record is *append-only*.

v1.2 separates them spatially and permanently:

> **The middle is the worksheet (you act). The right is the ledger (the record,
> read-only). The bottom is the terminal (you converse). The left is
> navigation.**

The ledger should *look* immutable and distinct from the place where choices are
still open. That is the whole idea.

## 2. The four zones

**Left — navigation.** Programs (with the ⋮ menu), Guides, the user strip and
Read-only toggle. Essentially unchanged.

**Middle — the worksheet (act).** The phase tab strip on top; below it, the
current phase's *actions only*: the corpus builder, the discovery queue, the
disposition cards, the ratify controls, the "open document" buttons. What leaves
the middle: the raw chat, and the raw decision-log dump — both move to the
ledger. The middle must always answer **"what do I do next?"** (see §6).

**Right — the ledger (record, read-only, contextual).** Scoped to the current
tab. Three stacked streams for that phase:

1. **Conversation** — the transcript of that phase's interview (Purpose → the
   purpose interview; Corpus → the source-discovery Q&A). Read-only history.
2. **Decisions** — the decision-log entries that belong to this phase (its
   ratifications, dispositions, freezes), each with who/when/why.
3. **Models used** — provenance for this phase: task → model actually served,
   cost, call count — flowing from the ratified model policy (§4).

On the **Overview** tab the ledger is **program-wide**: the full decision log,
the full provenance, all transcripts. Everywhere else it is the phase slice.
Styled as a record — quiet, bordered, non-interactive — so it reads as "the
ledger," not "more controls."

**Bottom — the terminal (converse, contextual).** An IDE-style dock hosting
*whichever interviewer the current phase needs*: the purpose interviewer in
Purpose, the source-discovery interviewer in Corpus. Collapsible like a terminal
panel. In phases with no conversational step it collapses to a thin bar. The
live exchange happens here; its transcript accrues in the ledger on the right.
This is also what finally makes "chat" honest — it's an *input device* that
drives the workflow, not a peer of the tabs.

Both the ledger and the terminal **re-scope when you switch tabs.**

## 3. Screen real estate (the honest constraint)

Four zones on a laptop is tight, so all three non-middle zones are collapsible
and the terminal/ledger have sensible defaults (§6). The middle never shrinks
below a usable width; the right ledger is collapsible to an edge tab; the
terminal defaults open only where a conversation is active. This is a hard
requirement, not a nicety — a cramped four-pane view would fail the
non-technical audience faster than the current single surface.

## 4. Model policy as a ratified decision (resolving the ex-post problem)

This is the crux. "Which model" splits cleanly into two concepts:

- **Model policy** — the choice set *before* tasks run (the preset picker from
  `spec/54`, optionally fine-tuned). A **forward decision.**
- **Model provenance** — which model *actually ran* each task, with cost. A
  **record.**

We make policy a first-class **ratified artifact**, exactly like the Purpose
Statement and the frozen manifest:

- **Provisional by default.** A new program starts under the **Recommended**
  policy, marked *provisional*. You can change the preset / fine-tune freely
  while provisional.
- **Lock = ratify.** A single "Lock model policy ⚖" action freezes the resolved
  task→model map. It writes a decision-log entry (`type: model_policy`,
  who/when/rationale, the preset name + lab, the full resolved map, and a hash),
  and the policy becomes **read-only** for that program.
- **Change only by re-opening.** After lock, changing models requires an
  explicit re-open (a new logged decision), the same discipline as a
  scope-change against a frozen manifest — never a silent edit.
- **Provenance flows from it.** The ledger's "Models used" shows, per phase,
  *policy says X → ran on X, $Y* — and would flag any drift. For a program that
  already ran, the policy is simply already-ratified and the selector is a
  record, not a live control. The ex-post feeling disappears.

**Gating (proposed).** Provisional Recommended is fine for the cheap early
steps, but real spend starts at distillation. So: **model policy must be locked
before the corpus can be frozen** (freeze → distill is the commitment point).
That ties the new gate to an existing one instead of inventing an awkward new
block. Open for your call in §9.

**What happens to the Models tab.** It stops being a standalone middle tab. The
*policy* picker moves into program **setup** (alongside Purpose); the
*provenance* moves into the right ledger per phase. One concept, two correct
homes.

## 5. Storage & backend (mostly assembly of data we already have)

- **Model-policy artifact** — `governed/model_policy.json` (`{preset, lab,
  overrides, status: provisional|ratified, ratified_by, hash}`) + a
  decision-log entry on lock. New endpoints: `GET/PUT policy`, `POST
  policy/ratify`. The router already reads the override map; the policy just
  becomes its persisted, ratifiable source.
- **Per-phase provenance** — filter `runs/stamps.jsonl` by `program_id` + the
  phase's task set (we already group tasks by phase for the preset dials). No
  new data.
- **Per-phase decisions** — map decision `type`/`artifact` → phase for the
  ledger slice. No new data.
- **Per-phase transcript** — `restricted/interview.json` (Purpose),
  `restricted/discovery_interview.json` (Corpus). Already written.

So the backend work is: the policy artifact + its ratify gate, and three thin
"give me this phase's slice" read endpoints. The heavy lift is front-end layout.

## 6. The new-program flow (the path that must lead)

The layout is judged here. A fresh program, step by step:

1. **Create** → lands on Purpose. Middle shows a single **"Start here"** card
   ("Tell the interviewer which regime you want to work on"). Terminal opens with
   the interviewer's greeting. Ledger reads *"No decisions yet — they'll appear
   here as you make them."*
2. **Interview** in the terminal → the transcript accrues in the ledger's
   Conversation stream. Middle's next-step updates: *"Keep answering, or
   Synthesize when ready."*
3. **Synthesize** → middle shows the draft statement (the §2.1/`spec/54` status
   header) with open items and the Ratify control. Ledger logs the synthesis and
   the model that ran it.
4. **Set & lock model policy** (setup) → the preset picker; **Lock ⚖** writes the
   decision and locks it. Ledger shows it as a ratified decision.
5. **Ratify Purpose** → decision logged; middle advances, Corpus unlocks.
6. **Corpus** → middle = corpus builder + discovery queue + freeze; terminal
   swaps to the source-discovery interviewer; ledger shows manifest changes, the
   discovery Q&A, and (once running) models used. Freeze is gated on a locked
   policy (§4).
7. **… distill → refactor/redesign → align**, each phase the same rhythm: **act
   in the middle, converse at the bottom, watch the record accrue on the right.**

The demo narrative writes itself — *talk at the bottom, work in the middle, the
ledger fills on the right* — **but it lives or dies on the middle always showing
the next action.** So the first thing I'll build is a **"next step" driver** in
the middle (a per-phase card that names the next action and disables what isn't
ready yet), because an empty canvas on a new program is the one way this design
fails. This is the highest-risk, highest-value piece and it leads the build.

## 7. What stays, moves, or goes

- **Stays:** left panel (programs/⋮/guides/user strip), the phase tab strip,
  downloads + program package, the reading guides, the status header.
- **Moves:** chat → bottom terminal; decision log + provenance + transcripts →
  right ledger; model policy picker → setup.
- **Goes (as a standalone tab):** the Models tab (folds into setup + ledger).

## 8. Build & de-risk plan

This touches the whole front end, and there's a live demo on this app, so:

1. **Backend first, invisibly** — the model-policy artifact + ratify gate + the
   three phase-slice read endpoints, with tests. Ships without changing the UI.
2. **The "next step" driver** in the middle (§6) — the make-or-break piece.
3. **The right ledger** — contextual, read-only, three streams; program-wide on
   Overview.
4. **The bottom terminal** — move chat down, make it contextual.
5. **Retire the Models tab** into setup + ledger.

Each step is testable and, until step 4, the current layout still works — so we
never have a half-broken surface during the demo window. If real estate proves
too tight in testing, the terminal/ledger collapse defaults are the pressure
valve.

## 9. Open decisions for sign-off

1. **Policy gate:** lock model policy **before corpus freeze** (proposed), or
   make locking non-blocking (encouraged, never required)?
2. **Terminal defaults:** open in Purpose & Corpus, collapsed elsewhere
   (proposed) — or always visible / always user-toggled?
3. **Overview ledger:** program-wide ledger on Overview *replaces* today's
   inline decision log there, or sits **alongside** the pipeline checklist
   (proposed: replaces the raw log, keeps the checklist)?
4. **Re-opening a locked policy:** who may do it and does it require a rationale
   (proposed: Program Owner + rationale, logged — same as any change decision)?
