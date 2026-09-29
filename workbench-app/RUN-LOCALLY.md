# Running the Rulebook Workbench on your machine

A self-contained analytical web app. It does **not** depend on any AI desktop app,
browser extension, or cloud account — you run it locally with Python and open it in a
browser. The only external service it calls is **OpenRouter**, and only when you ask it
to do generative work (the interview, distillation, proposals). Reading finished
material costs nothing.

Setup takes about ten minutes.

---

## 0. The one thing people get wrong

Run commands from **`workbench-app/`**, and keep the repo's folders together — the app
reads shared schemas from `../spec/`. A git clone or the share zip already has this
layout:

```
rulebook-workbench-v1/          ← the repo (any folder name)
├── spec/                       ← specs, schemas, skills
├── examples/                   ← published example programs
└── workbench-app/              ← the application (you run commands from here)
workbench-data/                 ← YOUR programs, created beside the repo on first run
```

Your own work goes in **`workbench-data/`**, outside the repo, so it is never committed.
To keep it somewhere else, set `WORKBENCH_DATA=/absolute/path` in `.env` (step 3). The app
prints the data folder's location when it starts.

*Upgrading from an older copy?* If you had programs in `workbench-app/programs/`, the
app will list them at startup — move them into `workbench-data/programs/`.

---

## 1. Prerequisites

- **Python 3.11 or newer.** Check with `python3 --version`.
  (macOS: `brew install python@3.11`; Windows: install from python.org and tick "Add to
  PATH", or use WSL.)
- **An OpenRouter account and API key.** Create a key at
  <https://openrouter.ai/settings/keys>. Put a small credit limit on it (e.g. $20) — the
  app spends against it, so the limit is your backstop.
- macOS or Linux is the smooth path. Windows works via **WSL**, or by running the raw
  command in step 4 instead of `make`.

---

## 2. Install

From inside the **`workbench-app`** folder:

```bash
cd workbench-app
python3 -m venv .venv            # create an isolated environment
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e ".[dev]"          # install the app and its dependencies
```

Optional but recommended — confirm it's healthy:

```bash
python -m pytest                 # the test suite; should report all tests passing
```

---

## 3. Add your OpenRouter key

The app reads the key from a local `.env` file that is **never** shared or committed.

```bash
cp .env.example .env
```

Open `.env` and paste your key after the `=`:

```
OPENROUTER_API_KEY=sk-or-your-key-here
```

Save it. Do not share this file. It is already in `.gitignore`.

---

## 4. Run it

```bash
make app
```

Then open **<http://localhost:8000>** in your browser.

The redesigned interface (release 1) is at **<http://localhost:8000/v2>**. It works
on the same programs and records as the classic interface, which stays at `/`. The
first time you open it, it asks for your name and role; these go on every decision
you record and are kept in that browser only.

**Windows / no `make`:** run the app directly:

```bash
PYTHONPATH=src python -m uvicorn --factory workbench.server:create_app --port 8000
```

To stop it, press `Ctrl+C` in the terminal. To restart after any code change, run the
command again (`make app` clears the port for you first).

---

## 5. What you'll see

- The **Overview** tab shows a program's whole pipeline at a glance, with links to the
  documents it produced and its decision log.
- If the share included finished programs (AML, liquidity), you can **read** every
  blueprint, crosswalk, and register for free — no key needed for reading.
- To **run** the pipeline yourself (interview → distill → refactor/redesign → align),
  the app calls OpenRouter and spends against your key. Expect roughly:
  distillation ~$0.15/source, proposals ~$0.30/finding. A full small corpus is a few
  dollars.
- The **Guides** in the left panel (About, Reviewer's Guides) explain the method and how
  to disposition operations. Start with **About the workbench**.
- The **Read only** toggle (bottom-left) hides all the action controls — handy for
  showing someone the finished work without risk of clicking anything.

---

## 6. Notes & limits

- **Single user per machine.** This local build has no login: whoever runs it acts as
  the Program Owner, and governed actions trust the name typed into the form. That's fine
  for trying it out solo. Real multi-person use (authenticated identity, per-user keys) is
  a separate, planned piece.
- **Your data stays local.** Everything lives in files in your data folder (default
  `workbench-data/` beside the repo).
  Nothing is uploaded anywhere except the individual model requests you trigger, which go
  to OpenRouter under the app's no-training / zero-data-retention routing preference.
- **Interview transcripts** (if you run the Phase 0 interview) are written to a
  `restricted/` folder that is git-ignored and excluded from shares by design.
- **Costs are yours.** The app has a per-program budget stop, but your OpenRouter key
  limit is the real ceiling — set one.

---

## 7. Trouble

- *"OPENROUTER_API_KEY not set"* — you skipped step 3, or the `.env` is in the wrong
  folder (it belongs in `workbench-app/`). Restart the app after editing it.
- *App won't start, schema errors* — the `spec/` folder isn't beside `workbench-app/`
  (see §0).
- *My programs have disappeared* — the app is looking at a different data folder. Check
  the "Workbench data folder:" line printed at startup and `WORKBENCH_DATA` in `.env`.
- *"Address already in use" / port 8000 busy* — an old copy is still running.
  `make app` kills it automatically; otherwise `lsof -ti:8000 | xargs kill`.
- *Blank page* — hard-refresh the browser (Cmd/Ctrl+Shift+R).
