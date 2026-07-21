# Use the venv's interpreter when present so `make app` works without activation
PY := $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)

.PHONY: check test smoke models install

install:
	pip install -e ".[dev]"

check: test
	@echo "make check: OK"

test:
	$(PY) -m pytest

# Live smoke test through OpenRouter (requires OPENROUTER_API_KEY in env)
smoke:
	$(PY) scripts/smoke.py

# List the current OpenRouter catalog entries for the models configured in models.yaml
models:
	$(PY) scripts/check_models.py

# Start the workbench app (http://localhost:8000)
app:
	-lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@sleep 1
	PYTHONPATH=src $(PY) -m uvicorn --factory workbench.server:create_app --port 8000

# Live skill eval suite (ADR-011; M1 exit). Requires OPENROUTER_API_KEY.
evals:
	$(PY) scripts/run_evals.py
