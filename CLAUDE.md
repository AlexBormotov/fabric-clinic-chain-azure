# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Claude Code wiring

- Rule sets: `.claude/skills` → symlink to `../.agents/skills`. On Windows this needs Developer
  Mode (or admin) and `git config core.symlinks true`; if a clone shows `.claude/skills` as a plain
  file, fix the symlink rather than copying the skills.
- Second-opinion subagents in `.claude/agents/` (`claude-thinking`, `codex-thinking`,
  `cursor-thinking`, `gemini-thinking`) run only when the owner explicitly names that route. Their
  output is advisory. They need `SECOND_OPINION_MONITOR_DIR`, set in `.claude/settings.local.json`;
  usage report: `python .claude/monitoring/second_opinion_usage.py report`.
- Session discipline follows `cherny-workflow`: plan first for anything non-trivial, track it in
  `tasks/todo.md`, read `tasks/lessons.md` at session start.

## Commands

Every `make` target runs inside the dev container (`docker/dev.Dockerfile`: Python 3.13, Java 21,
uv, gitleaks, actionlint), locally and in CI, so a local green and a CI green are the same claim.
Do not run `uv`/`pytest` on the Windows host for anything that must match CI.

- `make setup` — build the image, `uv sync --frozen`
- `make lint` / `make test` / `make secrets`
- `make synth` — Synthea population into `data/raw/fhir/` (~4 min); `make test-slow` — Synthea
  tests (`slow` marker, excluded from `make test`, ~10 min)
- `make sources` — derive billing, lab, ADT, SharePoint and ground truth from `data/raw/fhir/` into
  `data/sources/`; schemas in `docs/contracts/`
- `make up` — start the local source stand (SQL Server 2022, Azurite) and load `data/sources/` and
  `data/raw/fhir/` into it; the SA password is generated into the git-ignored `.env`;
  `make test-stand` — read-back tests (`stand` marker, excluded from `make test`); `make down`
- `make bronze` — after `make up`: land the stand into `data/lh_bronze/Files/landing/` and run
  `fabric/nb_bronze.Notebook/notebook-content.py` on local Spark; tests import that notebook file
  through `clinic_chain.spark.notebook()`
- `make silver` — after `make bronze`: run `fabric/nb_silver.Notebook/notebook-content.py` from
  `data/lh_bronze/Tables/` into `data/lh_silver/Tables/` and print the reconciliation
- `make mpi` — after `make silver`: run `fabric/nb_mpi.Notebook/notebook-content.py` (patient
  matching into `patient_xref`); `make mpi-eval` — precision/recall vs ground truth into
  `docs/evidence/mpi.json`
- `make gold` — after `make up` and `make mpi`: copy Silver into SQL Server (`clinic_gold`, Fabric
  collation) and run `sql/gold/` (T-SQL kept to the Fabric Warehouse surface; ADR 0002)
- `make metric-reference` — metric reference values from `data/sources/` (pandas, not Gold) into
  `docs/evidence/metric-reference.json`; definitions in `GLOSSARY.md`
- `make bed-history` — after `make silver`: run `fabric/nb_bed_history.Notebook/notebook-content.py`
  (SCD2 `bed_state_history` from `adt_event`, incremental via the `bed_event` log)
- `make quality` — after `make silver`: run `fabric/nb_quality.Notebook/notebook-content.py`
  (Soda v4 contracts) on `data/lh_silver/Tables/`; exits non-zero on a failed check. The Soda pins
  in `pyproject.toml` and the notebook's `%pip` cell must match (a test enforces it)
- one test: `docker compose run --rm dev uv run pytest tests/test_smoke.py::test_python_matches_fabric_runtime`
- after changing dependencies in `pyproject.toml`: `docker compose run --rm dev uv lock`
