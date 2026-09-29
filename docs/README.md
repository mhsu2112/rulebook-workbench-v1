# docs/

Overview collateral and historical archives for the Rulebook Workbench.

## Published collateral (tracked)

- **`Rulebook Workbench Overview.html`** / **`.html.pdf`** — the standalone overview of
  what the workbench is and how it runs. Self-contained; open the HTML in any browser.

## Local-only (moved to the data folder on 2026-09-29)

Local-only material no longer lives in the repo. It is in the data folder
(`../workbench-data/`, outside git):

- **`exports/uk-derivatives-reporting-derived.html`** — derived working paper from the
  UK derivatives reporting program. Kept local for the same reason that program's data is:
  the public mirror ships the workbench design and the AML / liquidity examples only.
- **`archive/`** — historical snapshots, not needed to run or develop the app:
  - `workbench-share-20260721.zip` — the 2026-07-21 self-contained share package.
  - `stage-zips/` — incremental delivery/stage archives from the v1.0 → v1.3 build.
  - `v11-backup/` — pre-v1.1 snapshot of `models.yaml`, `src/`, `tests/`, plus a stray
    `server.py.bak`.
  - `legacy-git-bundles/` — the two pre-consolidation git histories, preserved as bundles:
    - `legacy-spec-rulebook-workbench.bundle` — the spec repo's `master` (M0–M4 milestones,
      instruction set 0.3, ADR-001..017).
    - `legacy-app-workbench-app.bundle` — the app repo's `main` (M0 walking skeleton through
      Phase 4 Align spine).

    Inspect or recover either with:

    ```bash
    git clone ../workbench-data/archive/legacy-git-bundles/legacy-app-workbench-app.bundle /tmp/legacy-app
    ```

## Provenance

The workbench was originally built inside a Foundry engagement folder. It is now a
standalone project under `05-policy-sludge-code`; Foundry engagement and licensing
materials (Lex Balanus) stay in `01-engagements/Foundry`.
