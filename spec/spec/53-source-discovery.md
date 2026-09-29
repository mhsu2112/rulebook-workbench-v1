# 53 — Assisted Source Discovery (P1 census helper)

| | |
|---|---|
| **Status** | Draft 0.1 — feature spec for the build landing in the same pass |
| **Date** | 2026-07-23 |
| **Audience** | Program Owner; Foundry working group |
| **Companions** | `spec/30-instruction-set.md` P1 (census/manifest) · `spec/50-v2-backlog.md` · the in-app corpus builder (`manifest.add_item`) this feeds |
| **Governance** | Non-waivable: **AI proposes candidates; a human accepts them into the manifest.** Discovery never writes the manifest and never freezes. It removes the blank-page problem; it does not decide the corpus. |

## 1. The problem this closes

The workbench automates everything *downstream* of the census — acquire →
distill → refactor/redesign → align. It never automated the census itself:
deciding **which** statutes, regulations, and guidance make up the corpus. For
AML and liquidity that list was researched by hand and hand-authored into
`data/*-slice.json`. The in-app corpus builder lets a user *type in* sources one
at a time, but still assumes they already know each source exists.

"Repeat the process" for a new topic (e.g. government-sponsored lending) has
nothing to repeat: there was never a discovery step to re-run. This spec adds
one — the last manual seam in an otherwise governed chain — **without** letting
the machine decide what is in scope.

## 2. Governance shape (the load-bearing rule)

Discovery is the P1 census move made one step earlier, under the same OR-4
discipline as every other decision point: the machine surfaces evidence, the
human decides. Concretely:

- The discovery endpoint is **read-only against the manifest**. It returns a
  *review queue* of candidate items. It calls `add_item` for nothing.
- A candidate enters the corpus **only** when a human clicks *Add to corpus* on
  it, which invokes the existing, already-governed `add_item` path.
- Because nothing is frozen at census time, every add is reversible (the
  existing per-item *remove* still applies) until the Corpus Steward freezes
  (OR-7). Freeze is unchanged and remains the ⚖ that pins the corpus.
- Discovery emits **no** governed artifact and writes **no** decision-log entry.
  Accepting a candidate is what the human is accountable for; the proposal is
  not a decision and is not recorded as one.

Everything below is plumbing beneath that rule.

## 3. Two lanes into one queue

Per the Program Owner's choice: **catalog-anchored, model-expanded** — run both,
verify everything against the real catalogs before it can be shown as clean.

### 3a. Catalog lane (locators real by construction)

Direct queries to authoritative catalogs. Candidates carry verifiable locators
because they come *from* the catalog:

- **eCFR search API** (`/api/search/v1/results`) — CFR parts matching the topic.
  Each hit yields title + part → locator `"<title> CFR Part <part>"`, the part
  heading as the title, and the chapter heading (usually the issuing agency) as
  the issuer.
- **Federal Register API** (`/api/v1/documents.json`) — recent rules and notices
  matching the topic, for guidance-grade material and things not yet codified.
  Final rules → `status: live`; proposed rules → `status: proposed` (surfaced,
  but visibly not current law).

Catalog candidates are marked `verified: true` (they were just returned by the
authority's own index).

### 3b. Model-expanded lane (recall, then verification gate)

A model (`source_discovery` task) reads the ratified Purpose Statement and the
user's search hints and proposes the statutes / CFR parts / guidance a
subject-matter expert would expect — including cross-cutting sources a keyword
search misses. This lane exists for **recall**; it is not trusted for citations.
Every locator it emits is verified before it can be shown as clean:

- a proposed **CFR** locator is verified by fetching it from the eCFR versioner
  at the pinned snapshot date — the *same* call acquisition will later make, so
  "verified" literally means "acquire will find this" (with the DL-002 date
  rescue applied, exactly as in `acquire.py`);
- a proposed **U.S.C.** locator is verified by fetching the uscode.house.gov
  granule and rejecting block/short pages;
- a proposal with **no** locator, or one that fails verification, is still shown
  — flagged `verified: false` with the reason — **never** rendered as clean. The
  human can accept it anyway (their judgment), but the tool never launders an
  unverifiable citation into a confident one.

This reuses the citation-verification discipline the project already trusts
(OR-3), applied at the census instead of at distillation.

## 4. The review-queue contract

`POST /api/programs/{pid}/discover` with `{ "terms": "<topic keywords>" }`
returns:

```
{
  "terms":   ["fhlbank advances", "membership", ...],
  "counts":  { "catalog": N, "model": M, "verified": V, "queued": Q },
  "notes":   [ "eCFR search unreachable — showing model proposals only", ... ],
  "candidates": [
    {
      "proposed_item_id": "12-cfr-1266",
      "title": "PART 1266—FEDERAL HOME LOAN BANK ADVANCES",
      "issuer": "Federal Housing Finance Agency",
      "family": "regulation",
      "status": "live",
      "locator": "12 CFR Part 1266",
      "url": null,
      "evidence_role": null,
      "rationale": "Core advances rule for FHLBank members.",
      "origin": "catalog",          // catalog | model
      "verified": true,
      "verify_note": "eCFR versioner 2026-07-18: present"
    }, ...
  ]
}
```

The queue is **deduped** against the current manifest (by item_id and by
normalized CFR/USC locator) and within itself, then ranked: verified catalog
first, verified model next, unverified last. Truncation, if any, is reported in
`notes` — never silent (the no-silent-caps rule).

The candidate's fields are exactly the fields `add_item` needs, so *Add to
corpus* is a direct hand-off with nothing lost. `issuer` is always non-empty
(catalog derives it from the chapter heading; the model is required to supply
it) so the add never fails the manifest's required-field check.

## 5. Resilience (discovery degrades, never crashes)

Every external dependency is best-effort and isolated:

- eCFR search down → catalog lane returns the Federal Register hits it got, a
  note explains the gap, model lane still runs.
- Model call fails (no key, budget stop, upstream error) → catalog lane still
  returns, a note explains the gap. Discovery with no OpenRouter key at all is
  still useful (catalog-only).
- A single verification GET failing marks *that* candidate unverified with a
  reason; it does not fail the batch.

Partial results are the norm and are always labelled as partial.

## 6. UI

A **Discover sources** panel at the top of the Corpus tab (unfrozen state only —
it disappears once the corpus is frozen). One topic/keywords box, one button.
Results render as candidate cards: a verified/unverified badge, the title,
issuer, locator, family, one-line rationale, and origin. Each card has *Add to
corpus* (calls `add_item`; on success the card shows ✓ Added, buttons disable)
and *Dismiss* (removes the card from the queue only). The manifest table below
is the source of truth; re-running discovery re-dedupes against whatever has
been added.

The panel's framing text states the rule in plain English: *"These are
suggestions. Nothing here is in your corpus until you add it, and you decide
what belongs."*

## 7. What this is not

- Not a scope decision. The Purpose Statement still defines scope; discovery
  proposes sources *within* a scope a human already ratified.
- Not exhaustive or authoritative. It is a strong first pass over two catalogs
  plus model recall — a curator still reads, adds, and removes.
- Not a new gate. It touches no frozen artifact and needs no ADR: it is a
  convenience/recall feature whose only write path is the already-governed
  `add_item`. (Contrast the login work, which *does* need an ADR.)

## 8. Backlog / roadmap placement

Lands now (this pass) as a working first version wired into the Corpus tab.
Follow-ups worth tracking, not blocking on:

- **more catalogs** — GovInfo (Statutes at Large / USC full text search), state
  registers, SRO rulebooks — each a new source in the catalog lane.
- **scope-aware term suggestion** — pre-fill the keywords box from the ratified
  Purpose Statement's scope rather than making the user type them.
- **coverage critic** — a pass that reads the assembled corpus against the
  Purpose Statement and asks "what family of sources is missing?" (mirrors the
  paper's completeness idea; pairs with A1 self-audit in `spec/52` Track A).
