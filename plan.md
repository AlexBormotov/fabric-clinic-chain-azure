---
id: PLAN-U02
spec: SPEC-001 / U02
owner: AlexBormotov
status: approved by owner 2026-10-22, approach A
previous: PLAN-U01 (approach B, landed in #1; see git history of this file)
---

# PLAN-U02 — Synthea population

## Facts this plan rests on (checked 2026-10-21)

- Synthea latest release v4.0.0 (2026-03-05), asset `synthea-with-dependencies.jar`; requires JDK 17
  or newer (README, `build.gradle` `sourceCompatibility = '17'`). The dev image has JDK 17.
- CLI: `-s seed`, `-cs clinicianSeed`, `-p populationSize`, `-r referenceDate`, `[state [city]]`,
  `--key=value` overrides any `synthea.properties` key.
- Defaults that matter: `exporter.years_of_history = 10`, `exporter.fhir.transaction_bundle = true`,
  `exporter.fhir.use_us_core_ig = true`, `generate.only_alive_patients = false`.
- Synthea's demographics are US states and cities only. The three clinics therefore sit in three US
  cities; nothing in INT-001 requires a location.
- Unknown until measured: output size for 1,200 patients over 2 years, generation time, and whether
  two runs with the same seeds produce byte-identical files.

## Settings for every approach

Per clinic, one Synthea run: `-s <seed> -cs <seed> -r 20260930 -p <300|400|500> Massachusetts <city>`
with `--exporter.years_of_history=2 --generate.only_alive_patients=true --exporter.baseDirectory=...`.
Cities: Boston, Worcester, Springfield. Output under `data/raw/fhir/<clinic>/` (git-ignored).
`only_alive_patients=true` makes the patient count exact; patients who died before the reference date
are not generated (stated in the README; in-hospital deaths inside the window remain).

## The choice: where Synthea runs

### Approach A — inside the dev container (recommended)

`scripts/synth.py` downloads the pinned jar once to `data/cache/` (sha256 checked), then runs it per
clinic with `java -jar`. `make synth` calls it through the same `$(RUN)` wrapper as other targets.

- **Files:** `scripts/synth.py`, `config/synthea.yaml` (clinics, seeds, cities, sizes, jar version and
  sha256), `Makefile` (`synth`, `test-slow`), `tests/test_synth.py`, `.gitignore` (`data/`),
  `pyproject.toml` (pytest `slow` marker), `.github/workflows/ci.yml` (`synth` job), README, CLAUDE.md.
- **Invariants:** one environment for everything; the jar is pinned by version and hash.
- **Checks that go red:** hash mismatch on download; patient-count test; determinism test.
- **Reversal:** ordinary revert.

### Approach B — a separate Synthea image

`docker/synthea.Dockerfile` (eclipse-temurin 17 + jar) as its own compose service.

- **Files:** as A plus the Dockerfile and a compose service.
- **Trade-off:** isolates Synthea from the dev image, but adds a second image to keep pinned and a
  second environment, for no gain while the dev image already carries JDK 17.
- **Reversal:** ordinary revert.

### Approach C — commit generated data

Rejected: likely hundreds of MB in Git, and the generator would no longer be proven by a test.

## Tests

- `tests/test_synth.py`, marked `slow` (not in `make test`; run by `make test-slow` and a separate CI
  job `synth`):
  - each clinic directory holds exactly 300, 400 and 500 Patient resources;
  - every exported encounter falls inside the 2-year window ending 2026-09-30;
  - determinism: a second run with the same config produces identical content. If Synthea writes
    run-dependent values (timestamps, generator metadata), the test compares content after removing
    only those fields, and the removed fields are listed in the test. If outputs differ beyond such
    fields, work stops and this plan returns to the owner (the spec's completion condition assumes
    determinism).
- Fast tests in `make test`: config validation (sizes 300/400/500, unique seeds, pinned hash present).

## Completion check (from SPEC-001 / U02)

`make synth` is deterministic and the slow test asserts 300, 400 and 500 patients per clinic over a
2-year window; CI `synth` job green. Measured size and runtime are recorded in the PR description.

## Files outside this set

Any other file touched stops work and returns this plan to the owner.
