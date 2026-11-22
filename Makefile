# Environment is managed by uv (https://docs.astral.sh/uv/).
# Targets call the virtual environment's Python directly, so no activation is needed.
PY_VERSION ?= 3.12
P1 := projects/01-ai-detector-audit
MANIFEST := $(P1)/configs/data_sources.yaml
# Committed count tables suppress cells with fewer essays than this.
MIN_CELL_COUNT := 11

ifeq ($(OS),Windows_NT)
VENV_PY := .venv/Scripts/python.exe
else
VENV_PY := .venv/bin/python
endif

.PHONY: setup lint format test pre-commit data data-verify counts reproduce clean

setup:
	uv venv --clear --python $(PY_VERSION) --managed-python
	uv pip install --python $(VENV_PY) -e ".[dev]" --group notebooks
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

# Download, checksum-verify and extract all corpora into data/raw (gitignored).
data:
	$(VENV_PY) -m detector_audit.corpora.download --manifest $(MANIFEST)

# Manual-download fallback: check files already placed in data/raw, then extract.
data-verify:
	$(VENV_PY) -m detector_audit.corpora.download --manifest $(MANIFEST) --verify-only

counts:
	$(VENV_PY) -m detector_audit.corpora.counts --manifest $(MANIFEST) --out $(P1)/results/corpus_essay_counts \
		--min-cell-count $(MIN_CELL_COUNT)

reproduce:
	@echo "make reproduce: not implemented until M4 (statistical analysis)."
	@exit 1

clean:
	rm -rf build dist .pytest_cache .ruff_cache
	find . -path ./.venv -prune -o -type d -name __pycache__ -exec rm -rf {} +
	find . -path ./.venv -prune -o -type d -name "*.egg-info" -exec rm -rf {} +
