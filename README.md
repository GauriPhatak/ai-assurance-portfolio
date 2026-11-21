# ai-assurance-portfolio

<!-- TODO (owner): one-paragraph overview of the portfolio. -->

## Projects

<!-- TODO (owner): list of projects with status and links. -->

## Repository layout

<!-- TODO (owner) -->

## Setup

Requires [uv](https://docs.astral.sh/uv/) and GNU Make. `make setup` creates `.venv` with a uv-managed Python 3.12, installs the package in editable mode with dev dependencies, and installs the pre-commit hooks.

```
make setup      # create .venv and install
make lint       # ruff check and format check
make test       # pytest
make pre-commit # run all pre-commit hooks on all files
```

Without Make:

```
uv venv --python 3.12 --managed-python
uv pip install -e ".[dev]"
.venv/Scripts/python -m pre_commit install   # .venv/bin/python on macOS and Linux
```
