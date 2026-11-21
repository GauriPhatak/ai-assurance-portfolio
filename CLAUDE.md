# CLAUDE.md

Guidance for Claude Code in this repository. Read it fully at the start of each session.

## What this repo is

A portfolio of AI governance and assurance projects in healthcare and education, built alongside preparation for the IAPP AIGP certification. Each project pairs a statistical audit, written in Python, with a governance deliverable written for a named reader (for example, a university academic integrity office or a hospital AI governance committee).

The owner, Gauri, is a statistics PhD. Do not explain standard statistics. Do explain software engineering choices briefly when they are not obvious.

The repo exists to show the owner's own technical skill. That shapes everything below.

## Authorship rules (most important)

**Owner-written code.** In these areas, do not write implementation code:

- `src/aiassure/`: the shared statistics package (intervals, group error rates, base-rate and false accusation analysis, power and minimum detectable differences)
- `src/detector_audit/detectors/binoculars.py`: the Binoculars detector, implemented from Hans et al. (2024)
- simulation tests that check statistical properties, such as interval coverage

In those areas, help by explaining concepts and APIs, reviewing the owner's code for bugs, numerical problems and edge cases, suggesting test cases in words, and answering questions. Write pseudocode only when asked. If the owner explicitly asks you to write code in one of these areas, remind her of this rule once, then do what she asks.

**Claude-assisted code.** You may write these, with the owner reviewing:

- packaging, `pyproject.toml`, Makefile, CI and pre-commit configuration
- the detector harness: the common `Detector` interface, adapters for third-party detectors, caching, batching, config loading
- data download and preparation scripts
- the AI essay generation pipeline
- plotting helpers, the Streamlit app, and unit tests for harness code
- formatting of documentation the owner has drafted

When unsure which category something falls into, ask.

## How to work

- Propose a short plan before any change that touches more than two files.
- Ask before adding a dependency, changing the repo structure, or deleting anything.
- Keep commits small, with messages that say what changed and why.
- Only the active project is in scope. Do not scaffold future projects until asked.
- Planning, regulatory research and governance writing happen in a separate claude.ai chat. Decisions reach you through this file. At the end of each milestone, propose an update to the Status section.

## Repository layout (target)

```
.
├── CLAUDE.md
├── README.md                     portfolio front page
├── pyproject.toml
├── Makefile
├── .github/workflows/ci.yml
├── src/
│   ├── aiassure/                 shared statistics package (owner-written)
│   └── detector_audit/           project 1 code: harness, detectors, generation
├── tests/
├── notebooks/                    exploration only, outputs stripped
└── projects/
    └── 01-ai-detector-audit/
        ├── README.md             question, data, methods, findings
        ├── configs/              YAML experiment configs
        ├── results/              small derived tables and figures (committed)
        ├── governance/           policy memo, classification note, tool fact sheets
        └── app/                  Streamlit app
```

Raw data, model weights and cached model outputs live under `data/` and `.cache/`, both gitignored.

## Engineering conventions

- Python 3.11 or newer, `src/` layout. Environments are managed with uv: `make setup` creates `.venv` with a uv-managed Python 3.12 (`uv venv --python 3.12 --managed-python`) and installs the package with `uv pip install -e ".[dev]"`. Do not use pip or the MSYS2 Python directly. Make targets call `.venv`'s Python, so no activation is needed.
- ruff for linting and formatting. Type hints on public functions. NumPy-style docstrings.
- pytest for tests. CI runs lint and tests on every push and must pass on CPU with small models.
- Every random process takes an explicit seed. Experiment settings live in YAML configs, with no hard-coded paths or magic numbers in analysis code.
- Notebooks are for exploration only. Anything that produces a reported number lives in `src/` or a script and runs from `make`.
- GPU use is optional and chosen by config. Long jobs are resumable, and model outputs are cached by model ID, model revision and input hash.
- Every results file records model IDs and revisions, dataset versions and checksums.
- Make targets: `setup`, `lint`, `test`, `data`, `reproduce` (regenerates every committed table and figure).

## Statistical conventions

- Every reported rate shows its numerator, its denominator and a 95% interval. Use Wilson intervals by default and Clopper-Pearson when stating a guaranteed bound.
- Differences between groups use Newcombe intervals. Ratios use Katz log intervals.
- Essays written to the same prompt are not independent. Use cluster-aware intervals (for example, a cluster bootstrap over prompts) where this matters.
- Never report a non-significant difference as "no bias". Report the minimum detectable difference alongside it.
- Statistical functions get simulation tests (for example, checking that interval coverage is close to nominal) in addition to unit tests.

## Data and privacy rules

- The corpora contain real student writing. Never commit essay text, never print full essays in logs or results, and never send corpus text to an external API. Use open-weight models run locally or on a GPU host.
- Confirm each dataset's license and terms of use before downloading, and record them in the project README.

## Writing conventions (all docs, READMEs and governance deliverables)

- No em dashes or en dashes. Use commas, colons, parentheses or separate sentences instead.
- Plain language. Each governance document names its reader and the decision it supports.
- Every regulatory claim carries the date it was checked and a primary source link.

## Portfolio plan

1. **AI writing detector audit** (education). Active.
2. **Student dropout early warning audit** on OULAD (education). Next. Includes differential prediction (the Cleary model, not DIF), an EU AI Act classification memo, and monitoring from the 2013 to the 2014 course presentations.
3. **Hospital vendor model validation** (healthcare). Local validation of a published readmission score (LACE) on Diabetes 130, transportability to a target population, and a disparity audit when race is missing or unreliable.
4. **De-identification risk and synthetic data** (cross-cutting). A mock HIPAA Expert Determination report.

The shared `aiassure` package is reused across all projects.

## Project 1: AI writing detector audit

**Question.** How often do AI writing detectors falsely flag genuine student writing? Does the false positive rate differ for English learners? At realistic levels of AI use, what share of flagged students would be wrongly accused?

**Reader.** A university academic integrity office deciding whether and how to use detector scores.

**Data.**

- ELLIPSE corpus: essays by English language learners.
- PERSUADE 2.0 corpus: argumentative essays from a broad student population. Check which demographic fields it includes, such as English learner status. A comparison within one corpus is cleaner than one across two corpora, because corpora differ in prompts, grade levels and how they were collected.
- AI-written essays generated on the same prompts with open-weight instruction-tuned models, in three variants: unedited, paraphrased, and lightly edited.

**Detectors.** Open source only, no paid APIs.

- Binoculars, implemented by the owner from Hans et al. (2024), using a small open model pair.
- At least one off-the-shelf classifier detector and a simple perplexity baseline. Choose these in Milestone 2 and record their model IDs.

**Analysis.** False positive and true positive rates by writer group and by detector; threshold curves; the false accusation share as a function of prevalence and student mix; cluster-aware intervals; minimum detectable differences.

**Governance deliverables.**

- A policy memo for the integrity office: evidence standards, appeal rights, Title VI national origin risk, accommodations.
- A classification note on the EU AI Act: Annex III point 3, especially 3(b) on evaluating learning outcomes and 3(d) on detecting prohibited behaviour during tests.
- A one-page fact sheet for each detector.

**Milestones.**

- M0: repo skeleton, packaging, CI. (Claude-assisted)
- M1: data download scripts, data cards, and a sampling plan with power analysis. (power analysis is owner-written)
- M2: detector harness and off-the-shelf detectors (Claude-assisted); Binoculars (owner-written).
- M3: AI essay generation pipeline, resumable and cached. (Claude-assisted)
- M4: statistical analysis in `aiassure`. (owner-written)
- M5: governance memo, classification note, Streamlit app, and the project README write-up.

## Verified context (checked 2026-11-20)

Recheck primary sources before citing any of these in a deliverable. Several changed during 2025 and 2026.

- **EU AI Act, Digital Omnibus.** Regulation (EU) 2026/1744, in force since 27 July 2026. Annex III high-risk obligations now apply from 2 December 2027, and Annex I (AI in regulated products such as medical devices) from 2 August 2028. Article 50 transparency duties applied from 2 August 2026. The new Article 4a allows processing of special category data for bias detection and correction under strict conditions, including that other data (such as synthetic or anonymised data) would not be effective.
- **EU AI Act, Article 6(3).** An Annex III system that profiles natural persons is always high-risk.
- **Detector evidence.** Liang et al. (2023, Patterns) found that seven detectors flagged, on average, about 61% of TOEFL essays by non-native English writers as AI-generated. Turnitin states that it tests to keep false positives under 1%. UCLA and UC San Diego (2024) and Curtin University (January 2026) stopped using AI detection.
- **US health rules.** The HHS Section 1557 rule at 45 CFR 92.210 is in force for patient care decision support tools. ONC's HTI-5 final rule (published 28 October 2026, effective 28 December 2026) removed the HTI-1 source attribute ("model card") and risk management requirements for decision support interventions.
- **Standards.** ISO/IEC 42005:2025 is the AI system impact assessment standard, giving guidance for ISO/IEC 42001 clause 6.1.4. The NIST AI RMF 1.0 functions are Govern, Map, Measure and Manage.
- **Healthcare governance.** The Joint Commission launched a voluntary Responsible Use of AI in Healthcare certification on 1 June 2026.
- **AIGP.** IAPP body of knowledge version 2.1 has applied since 2 February 2026.

Starting points for rechecking:

- EU AI Act Service Desk, Article 4a: https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-4a
- HTI-5 final rule: Federal Register document 2026-21943
- Section 1557 rule: 45 CFR 92.210
- ISO/IEC 42005: https://www.iso.org/standard/42005
- Liang, Yuksekgonul, Mao, Wu and Zou (2023), "GPT detectors are biased against non-native English writers", Patterns

## Status

- Done: GitHub repo created.
- Next: M0, repo skeleton.
