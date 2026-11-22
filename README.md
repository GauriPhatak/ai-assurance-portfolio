# ai-assurance-portfolio

<!-- TODO (owner): one-paragraph overview of the portfolio. -->

## Projects

<!-- TODO (owner): list of projects with status and links. -->

## Repository layout

<!-- TODO (owner) -->

## Setup

Requires [uv](https://docs.astral.sh/uv/) and GNU Make. `make setup` creates `.venv` with a uv-managed Python 3.12, installs the package in editable mode with dev dependencies and the `notebooks` dependency group (ipykernel, pandas, matplotlib), and installs the pre-commit hooks.

```
make setup       # create .venv and install
make lint        # ruff check and format check
make test        # pytest
make pre-commit  # run all pre-commit hooks on all files
make data        # download, checksum-verify and extract the corpora into data/raw (gitignored)
make data-verify # manual-download fallback: verify files already in data/raw, then extract
make counts      # regenerate the essay counts table in projects/01-ai-detector-audit/results
```

`make data` needs the zip passwords that the corpus authors publish in their READMEs. Copy `.env.example` to `.env` (untracked) and fill them in, or set the same variables in the environment.

Without Make:

```
uv venv --python 3.12 --managed-python
uv pip install -e ".[dev]" --group notebooks
.venv/Scripts/python -m pre_commit install   # .venv/bin/python on macOS and Linux
```

Notebooks in `notebooks/` are for exploration only. nbstripout runs in pre-commit and strips outputs before every commit.
