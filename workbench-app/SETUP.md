# Setup — step by step (no coding required)

Two ways to do this: **Option A** hands the work to Claude Code; **Option B**
is the manual version. Either way, do Step 3a (the OpenRouter key) yourself —
that part needs your browser and your account.

---

## Step 3a first — get an OpenRouter API key (browser, ~3 minutes)

1. Go to **https://openrouter.ai** and sign up (Google login works).
2. Click your avatar (top right) → **Keys** → **Create Key**. Name it
   `workbench`. Copy the key — it starts with `sk-or-`. Keep it somewhere
   safe; treat it like a password.
3. Click **Credits** and add **$5** (the smoke test costs a fraction of a
   cent; $5 covers a lot of experimentation).

---

## Option A — paste this into Claude Code

Open Terminal (press **Cmd+Space**, type `Terminal`, press Return), then:

```
cd ~/Work/01-engagements/Foundry && claude
```

When Claude Code starts, paste this entire block as your message:

> In ./workbench-app: rename Makefile.dist to Makefile. Create a Python
> virtual environment in .venv, activate it, run `pip install -e ".[dev]"`,
> then run `python -m pytest` and show me the result — it should say
> "20 passed". Create a `.env` file from `.env.example` and then STOP and
> ask me to paste my OpenRouter API key; put what I paste after
> `OPENROUTER_API_KEY=` in .env (never echo the key back, never commit .env).
> Then run `python scripts/smoke.py` and show me the output. Finally, in
> ../rulebook-workbench: delete the `_to_delete` folder, then `git add -A`
> and commit with message "Ratified AML demo purpose statement; PRD 0.2;
> ADR-012..017". In ./workbench-app: `git init`, `git add -A`, commit with
> message "M0 walking skeleton: model router, gates, storage, contracts".
> Confirm .env was not committed.

That's everything. Expected finale: the smoke test prints
`response: WORKBENCH M0 OK`, a provenance stamp, and a spent amount under
a cent.

---

## Option B — manual, one block at a time

Open Terminal (**Cmd+Space** → `Terminal` → Return). Paste each block, press
Return, and check the expected result before moving on.

**1. Rename the Makefile**

```bash
cd ~/Work/01-engagements/Foundry/workbench-app
mv Makefile.dist Makefile
```

Expected: no output (silence = success).

**2. Install and run the tests**

```bash
cd ~/Work/01-engagements/Foundry/workbench-app
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

Expected: the last line says **`20 passed`**. (The first run may take a
minute while packages download. If macOS asks to install "command line
developer tools", click Install and rerun the block.)

**3. The live smoke test**

Edit the command below FIRST — replace `PASTE-YOUR-KEY-HERE` with the
`sk-or-...` key from Step 3a — then paste it:

```bash
cd ~/Work/01-engagements/Foundry/workbench-app
printf 'OPENROUTER_API_KEY=PASTE-YOUR-KEY-HERE\n' > .env
```

Then run:

```bash
set -a; source .env; set +a
python scripts/smoke.py
```

Expected output ends with something like:

```
response: WORKBENCH M0 OK
stamp:
{ ... "model_served": "google/gemini-3.1-flash-lite", ... }
spent: $0.000xxx
```

That's the M0 exit: a routed, stamped, live call through OpenRouter.

**4. (Optional but recommended) Commit everything to git**

```bash
cd ~/Work/01-engagements/Foundry/rulebook-workbench
rm -rf _to_delete
git add -A
git commit -m "Ratified AML demo purpose statement; PRD 0.2; ADR-012..017"

cd ~/Work/01-engagements/Foundry/workbench-app
git init
git add -A
git commit -m "M0 walking skeleton: model router, gates, storage, contracts"
git status --short
```

Expected: two commit confirmations, and the final `git status` must NOT
list `.env` (it's gitignored — your key never enters git history).

---

## M1 — running the workbench app

After the M0 steps above are done, update your copy and start the app.
**Option A (Claude Code):** in Terminal, `cd ~/Work/01-engagements/Foundry && claude`, then paste:

> In ./workbench-app: run `mv -f Makefile.dist Makefile`, then activate .venv
> and run `pip install -e ".[dev]"` (new dependencies arrived), then
> `python -m pytest` — expect "27 passed". Then start the app with
> `make app` and tell me it's running. Leave it running.

Then open **http://localhost:8000** in your browser: create a program (e.g.
`liquidity-redesign-scoping`), chat with the interviewer, and when it
finishes, hit **Synthesize Purpose Statement** and then **Ratify** in the
right panel. The Models tab is the per-task model toggle.

To run the skill eval suite (12 cases, model-vs-model, costs roughly a few
dollars): in a second Terminal window,

```bash
cd ~/Work/01-engagements/Foundry/workbench-app
source .venv/bin/activate
set -a; source .env; set +a
make evals
```

Expected: a PASS/FAIL line per case and `N/12 cases pass`; per-case details
in `evals-out/`. Stop the app anytime with Ctrl+C in its Terminal window.

## If something goes wrong

- `command not found: python3` → install command line tools when prompted,
  or from https://www.python.org/downloads/ , then redo Step 2.
- `20 passed` doesn't appear → copy the error text and paste it to Claude;
  don't proceed to Step 3.
- Smoke test says `OPENROUTER_API_KEY not set` → redo Step 3's two blocks in
  the same Terminal window (the `source .env` line loads the key).
- Smoke test shows `HTTP 402` → add credits on openrouter.ai.
- New Terminal window later? Run
  `cd ~/Work/01-engagements/Foundry/workbench-app && source .venv/bin/activate`
  before any `python ...` command.
