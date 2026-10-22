---
id: PLAN-U02
spec: SPEC-001 / U02
owner: AlexBormotov
status: approved (approach A) — returned 2026-10-22 on false facts, re-approved with option 3a
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

## Facts found false during implementation (2026-10-22) — returned to owner

Measured on a full run (3 clinics, 1,200 patients) in the dev container.

1. **`-r` does not end the simulation.** `-r` is the reference date for the population; the
   simulation runs until "now" unless `-e endDate` is given (`App.java`, v4.0.0). Without `-e` the
   last encounter was dated on the run day, so output depended on the calendar.
   **Fix (inside the approved files):** pass `-e 20260930`. Verified: last encounter 2026-09-29.
2. **Synthea is not deterministic with the default thread pool.** Two runs with identical seeds
   differed in 5 of 1,200 patient files (`CarePlan.activity`, `AllergyIntolerance.reaction.severity`),
   beyond the run-dependent `metadata/` file.
   **Fix (inside the approved files):** `--generate.thread_pool_size=1`. Verified: two full runs are
   byte-identical except `metadata/*.json` (run timestamp in name and content). Cost: one run takes
   ~5 min instead of ~1.7 min.
3. **`exporter.years_of_history=2` does not confine encounters to the 2-year window.** Synthea keeps
   older history linked to still-active conditions, medications and care plans ("anything older may
   be filtered out", `synthea.properties`). Measured: 9,707 of 20,083 encounters (48%) start before
   2024-09-30, the oldest in 1921. The spec's completion condition "300, 400 and 500 patients per
   clinic over a 2-year window" therefore cannot be checked as "every encounter inside the window".

Also measured: output is ~880 MB (Boston 193 MB, Worcester 295 MB, Springfield 396 MB), dominated
by `ExplanationOfBenefit` and `Observation`.

### Decision needed for item 3

- **Option 3a (recommended): keep Synthea's output as delivered; apply the analytical window
  downstream.** Raw FHIR and Bronze hold the full exported history, as a real EHR extract would.
  Silver/Gold metrics use the window 2024-10-01 … 2026-09-30. The U02 test asserts: exact patient
  counts; no encounter after the end date; each clinic has encounters inside the window. (Not
  "every patient has an encounter in the window": measured, 13 of 1,200 patients have none, which
  is realistic for registered patients with no visits.) The spec's U02 completion condition is reworded to that, and the window becomes an
  explicit Gold-layer rule (written to `GLOSSARY.md` in U09).
- **Option 3b: post-filter the bundles in U02** to drop resources older than the window. Breaks
  references between resources (claims and observations pointing at dropped encounters) and makes
  the raw data less realistic; rejected unless the owner prefers a strictly windowed raw set.

Fixes 1 and 2 stay regardless of the choice. The determinism test compares everything except
`metadata/`.

**Owner decision (2026-10-22): option 3a.** `spec.md` U02 completion reworded accordingly. To keep
the slow job short (measured 4 min locally), the determinism test re-runs one clinic (Boston) and compares it with
the first run; all clinics go through the same code path.
