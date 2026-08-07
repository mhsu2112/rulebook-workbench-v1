# Rulebook Workbench (v1)

A governed AI system for consolidating sprawling regulatory rulebooks. It reads a body of
rules, distills them into a faithful structured "blueprint," and supports cleaning up
(**refactor**) or reshaping (**redesign**) that blueprint under strict human-in-the-loop
governance — producing advisory working papers, never operative law. It runs locally as a
self-contained web app.

> New here? The full guide is **[workbench-app/RUN-LOCALLY.md](workbench-app/RUN-LOCALLY.md)**.
> Quickstart below.

## Quickstart — run it on your machine

Requires **Python 3.11+** and an **OpenRouter API key**
(<https://openrouter.ai/settings/keys> — put a small credit limit on it).

```bash
# after cloning this repo:
cd workbench-app
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env                                  # then paste your OpenRouter key into .env
make app                                              # Windows / no make:
                                                      #   PYTHONPATH=src python -m uvicorn --factory workbench.server:create_app --port 8000
```

Open **<http://localhost:8000>**. Start on the **Overview** tab and the **About the
workbench** guide in the left panel. Reading the finished example programs is free;
running the pipeline spends your own OpenRouter credit.

Windows notes and troubleshooting: **[workbench-app/RUN-LOCALLY.md](workbench-app/RUN-LOCALLY.md)**.

## What's in here

- **`workbench-app/`** — the application (Python/FastAPI + a dependency-free browser UI).
  Run all commands from here.
- **`rulebook-workbench/`** — the governing specs, schemas, skills, and example program
  data (blueprints, registers, decision logs). The app reads schemas from here, so keep
  the two folders together — a clone already does.
- **`docs/`** — the standalone overview (HTML + PDF). `docs/archive/` holds share
  packages and the pre-consolidation git histories; it is local-only and git-ignored.
  See `docs/README.md`.

## What this is (and isn't)

An **analytical workbench with drafting support**. Everything it produces — blueprints,
registers, crosswalks, proposed drafts — is an **advisory working paper, not operative
law**. A human ratifies every governing decision; the system proposes, checks, and
records — it never enacts. Consolidated output is a recommendation to be reviewed and
adopted through your own legal and regulatory process, not a substitute for it.

Under the hood it is governed by design: per-task model routing through a single
OpenRouter integration, fail-closed privacy for sensitive tasks, schema-validated
structured outputs, a provenance stamp on every model call, and an append-only decision
log. See `rulebook-workbench/governance/` and `rulebook-workbench/spec/` for the full
specification, and `workbench-app/README.md` for the code-level overview.

## Governance & privacy

- **Human-in-the-loop.** Governing decisions require explicit ratification with a recorded
  rationale (append-only decision log).
- **No secrets in this repo.** Your `OPENROUTER_API_KEY` lives only in a local `.env`
  (git-ignored); copy `workbench-app/.env.example` to create it.
- **Restricted stores stay local.** Interview transcripts and other sensitive per-program
  material are written to git-ignored `programs/*/restricted/` directories and are not
  published here.
