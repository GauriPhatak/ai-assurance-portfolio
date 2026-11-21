# Environment is managed by uv (https://docs.astral.sh/uv/).
# Targets call the virtual environment's Python directly, so no activation is needed.
PY_VERSION ?= 3.12

ifeq ($(OS),Windows_NT)
VENV_PY := .venv/Scripts/python.exe
else
VENV_PY := .venv/bin/python
endif

.PHONY: setup lint format test pre-commit data reproduce clean

setup:
	uv venv --clear --python $(PY_VERSION) --managed-python
	uv pip install --python $(VENV_PY) -e ".[dev]"
	$(VENV_PY) -m pre_commit install

lint:
	$(VENV_PY) -m ruff check .
	$(VENV_PY) -m ruff format --check .

format:
	$(VENV_PY) -m ruff check --fix .
	$(VENV_PY) -m ruff format .

test:
	$(VENV_PY) -m pytest

pre-commit:
	$(VENV_PY) -m pre_commit run --all-files

data:
	@echo "make data: not implemented until M1 (data download scripts)."
	@exit 1

reproduce:
	@echo "make reproduce: not implemented until M4 (statistical analysis)."
	@exit 1

clean:
	rm -rf build dist .pytest_cache .ruff_cache
	find . -path ./.venv -prune -o -type d -name __pycache__ -exec rm -rf {} +
	find . -path ./.venv -prune -o -type d -name "*.egg-info" -exec rm -rf {} +
