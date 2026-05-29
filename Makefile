PY := python/.venv/bin/python

.PHONY: setup regen-model regen-model-check test lint

# Use uv because system python 3.14 ships without ensurepip on this box.
setup:
	cd python && uv venv --python 3.14 .venv
	uv pip install --python python/.venv/bin/python -e python[dev]

regen-model:
	$(PY) scripts/regen_model.py

regen-model-check:
	$(PY) scripts/regen_model.py --check --skip-fetch

test:
	cd python && .venv/bin/pytest

lint:
	cd python && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
