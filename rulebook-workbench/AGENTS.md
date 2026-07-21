# AGENTS.md — Rulebook Workbench

Instructions for any AI agent (or human) working in this repository.

1. **Precedence.** `governance/SPEC-HIERARCHY.md` governs. On any apparent
   conflict between documents in this repo, or between this repo and the
   statute-distill repo: STOP, do not silently harmonize, and record the
   conflict as a proposed ADR in `governance/DECISIONS.md` for the owner to
   disposition. This mirrors the statute-distill rule but names this repo's
   hierarchy — for *regulatory* workbench matters, this repo controls; for
   core-calculus semantics and the criminal profile, the StatuteDistill PRD
   controls (pinned per `spec/00-core-calculus.md`).
2. **Do not edit upstream from here.** Never modify files in
   `statute-distill_lex-allium` as part of work in this repo. Propose upstream
   changes as ADRs.
3. **One version per document.** Bump the header version and rely on git
   history; do not create `-v0.2.md` sibling files.
4. **Terminology discipline.** Use the vocabulary of `spec/30-instruction-set.md`
   §3 (Definitions) everywhere — skills, schemas, evals, commit messages. A new
   term requires a Definitions entry in the same change.
5. **Schemas are contracts.** If a document changes the shape of an artifact
   (Purpose Statement, Mandate, registers), the corresponding schema in
   `schemas/` changes in the same commit, and vice versa.
6. **Evals accompany mechanics.** A change to a skill's conduct rules requires
   a corresponding update to its eval cases in `evals/`.
7. **No engine code here.** Implementation code lives in its own repository;
   this repo holds governing materials only.
