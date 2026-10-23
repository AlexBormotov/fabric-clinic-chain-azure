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

Every `make` target runs inside the dev container (`docker/dev.Dockerfile`: Python 3.13, JDK 17,
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
- one test: `docker compose run --rm dev uv run pytest tests/test_smoke.py::test_python_matches_fabric_runtime`
- after changing dependencies in `pyproject.toml`: `docker compose run --rm dev uv lock`
