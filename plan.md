---
id: PLAN-U01
spec: SPEC-001 / U01
owner: AlexBormotov
status: approved by owner 2026-10-21, approach B
---

# PLAN-U01 — Repository scaffolding

## Facts this plan rests on (checked 2026-10-21 on the owner's machine)

- Host: Windows 11, Git Bash, GNU Make 4.4.1, uv 0.9.24, Docker 28.3.3 with Compose v2.39 (Linux
  engine). Not installed: gitleaks, actionlint, sqlfluff, Terraform, Azure CLI.
- Fabric Runtime 2.0: Spark 4.1, Python 3.13 (`docs/research/fabric-facts-2026-10-21.md`).
- Later units run PySpark 4.1 + Delta locally (U05 onward). PySpark on native Windows needs
  `winutils.exe`/`hadoop.dll` and a matching JDK; CI runs on Linux.
- The repository standard requires CI to run the same command a contributor runs
  (`ai-factory-kit/10-repo-standard.md`, Makefile row).

## The choice: where `make lint` and `make test` execute

### Approach A — host-native

Make targets call `uv run ...` directly on the host; CI (ubuntu) runs the same targets.

- **Files:** `pyproject.toml`, `uv.lock`, `Makefile`, `.github/workflows/ci.yml`, configs.
- **Invariant kept:** one command for contributor and CI.
- **Breaks it:** the command is the same but the environment is not: Windows host vs Linux CI. From
  U05 PySpark needs Hadoop native binaries on Windows, so the first Spark test is green in CI and red
  or skipped locally. Check that goes red: none until U05; then the local run itself.
- **Reversal:** ordinary revert.

### Approach B — everything in a dev container (recommended)

Make targets run inside a `dev` image (Python 3.13, JDK 17, uv) through `docker compose run --rm dev`.
CI runs the same `make` targets, which start the same image.

- **Files:** as A, plus `docker/dev.Dockerfile` and a `dev` service in `docker-compose.yml`.
- **Invariants kept:** one command, and one environment (Linux, Python 3.13 as in Fabric Runtime 2.0)
  for contributor and CI. Tools not on the host (gitleaks, sqlfluff, actionlint) live in the image,
  so nothing extra is installed on Windows.
- **Check that goes red:** the CI job and the local run execute the identical image; a drift in
  tool versions shows as a lockfile or Dockerfile diff.
- **Cost:** first build a few minutes; each `make` call pays container start (~1–2 s).
- **Reversal:** ordinary revert; the targets fall back to approach A by removing the wrapper.

### Approach C — hybrid

Lint and pure-Python tests on the host (A); Spark, SQL Server, emulator tests in containers (B).

- **Invariant at risk:** two environments, so "green" means two different claims; the split rule has
  to be maintained per test. Rejected unless B's start-up cost proves painful.

## Steps for the chosen approach (written for B; A drops steps 2 and the wrapper)

1. `pyproject.toml` (Python 3.13, dev deps: ruff, pytest, sqlfluff), `uv.lock`, a placeholder package
   `src/clinic_chain/` and one smoke test.
2. `docker/dev.Dockerfile` (python:3.13-slim + JDK 17 + uv + gitleaks + actionlint), `dev` service in
   `docker-compose.yml`.
3. `Makefile`: `setup`, `lint` (ruff check, ruff format --check, sqlfluff lint, actionlint), `test`
   (pytest), `secrets` (gitleaks on the working tree and history), `up`, `down`.
4. `.github/workflows/ci.yml`: jobs `lint`, `test`, `secrets`, each `make <target>`.
5. `.env.example` (empty for now, header only), `.github/CODEOWNERS` (`* @AlexBormotov`), `REVIEW.md`,
   README skeleton (what it is, `make` targets, status).
6. Update `CLAUDE.md` with the real commands.

## Completion check (from SPEC-001 / U01)

- `make lint test secrets` green locally and in CI on `main`.
- Negative control: a fake AWS-style key committed on a throwaway branch fails the `secrets` job in CI;
  the branch is deleted afterwards and its run linked in the PR description.

## Files outside this set

Any other file touched stops work and returns this plan to the owner.
