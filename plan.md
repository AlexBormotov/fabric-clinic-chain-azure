---
id: PLAN-U07
spec: SPEC-001 / U07
owner: AlexBormotov
status: approach A approved 2026-10-28 with both gaps resolved as proposed; built
previous: PLAN-U06 (approach A, landed in #9; see git history of this file)
---

# PLAN-U07 — Master patient index

## Facts this plan rests on (measured 2026-10-28 on the full population)

- `silver.patient_record`: 33,396 records (FHIR 1,200, lab 931, ADT 15,217, billing 16,048) of
  15,326 persons (ground truth). Records per person: 1 (40), 2 (12,936), 3 (1,969), 4 (330),
  5 (49), 6 (2). True matching record pairs: 21,343.
- U03 noise per system: name typo 4%, day/month swap 2%, phone reformatted 25%, within-system
  duplicates 5%. Nothing removes or changes a phone, a sex or a clinic.
- After U06 normalizes phones, **all 21,343 true pairs share the phone**; 86 pairs of different
  persons share one too (random collisions in the 555 range). Sex and clinic agree in every true
  pair. Phone equality alone would score precision 0.996 and recall 1.0.
- Blocking (candidate pairs / share of true pairs kept): spec's (birth year, surname soundex)
  45,144 / 0.979; plus exact birth date 65,309 / 0.9992; plus phone 65,412 / 1.0.
- Spark 4.1 has `soundex` but no Jaro-Winkler function (checked: `UNRESOLVED_ROUTINE`).
- Ground truth names the FHIR system `ehr`; `silver.patient_record` writes `fhir`.
- Ground truth stays local (`never loaded as a source`): evaluation runs locally and in CI, not in
  Fabric.

## Gaps that need the owner's decision

1. **The data makes the MPI trivial.** With phones intact in every true pair, any scorer that
   uses phone passes the 0.98/0.95 gate, and the result says little about matching. Proposed: add
   two noise rates to U03, `phone_missing` 0.10 (phone emptied) and `phone_changed` 0.05 (a new
   number), applied like the other rates. This is a U03 change: `config/sources.yaml`,
   `src/clinic_chain/sources/noise.py`, `tests/test_sources.py` (exact-rate tests extended),
   `docs/contracts/README.md`, followed by `make sources` and Bronze and Silver rebuilt. Alternative:
   keep the data and state in the evidence that the phone is never noisy.
2. **One name for the FHIR system.** Proposed: Silver writes `ehr`, the term the ground truth
   already uses (FHIR is the format, EHR the system); `nb_silver`, `tests/test_silver.py` and
   README change one value.

## Settings for every approach

- **Code:** notebook `fabric/nb_mpi.Notebook/notebook-content.py` (U05/U06 pattern), parameters
  `run_id`, `silver_root`; reads `patient_record`, writes `patient_xref` (system,
  local_patient_id, master_patient_id) and `patient_match_review` (pairs in the review band, with
  their score). `pl_land_sources` gains `run_nb_mpi` after `run_nb_silver`. `make mpi` runs it
  locally.
- **Blocking:** union of (birth year, surname soundex), exact birth date and phone; the share of
  true pairs kept by blocking is reported.
- **Comparison:** Jaro-Winkler on given and family name (a plain-Python function as a Spark UDF,
  no dependency; tested against published reference values), birth date (exact, day/month
  swapped, same year), sex, phone, postal code, clinic. Records of the same system are compared
  too (within-system duplicates).
- **Clusters:** auto-matched pairs are joined into connected components (iterative min-label
  propagation in Spark); `master_patient_id` is a hash of the smallest record key in the
  component. Review-band pairs are not merged.
- **Evaluation:** `make mpi-eval` (local, reads `data/sources/ground_truth/`) writes
  `docs/evidence/mpi.json`: pairwise precision and recall (a record pair is predicted when both
  records share a master ID; true when they share a person), blocking recall, review-band size,
  thresholds. Ground truth is used only to evaluate, never to set weights or thresholds.
- **Tests:** fast: Jaro-Winkler reference values, blocking and scoring on fixture records, cluster
  propagation (chains merge, review pairs do not); `stand` (CI `stand` job gains `make mpi` and
  `make mpi-eval`): precision ≥ 0.98 and recall ≥ 0.95, every Silver patient record has exactly one
  master ID.
- **ADR:** `docs/adr/0001-mpi-approach.md`: own scoring now, Splink as the next step.

## The choice: how pairs are scored

### Approach A — Fellegi–Sunter weights (recommended)

Each comparison has agreement levels (e.g. name JW ≥ 0.92, ≥ 0.80, lower). Per level, the weight
is log2(m/u): m (agreement among true matches) is set a priori and written in the ADR; u
(agreement by chance) is measured from random record pairs, which needs no ground truth. A pair's
score is the sum; above the match threshold it is auto-matched, between the two thresholds it goes
to review.

- Files: `fabric/nb_mpi.Notebook/*`, `fabric/pl_land_sources.DataPipeline/pipeline-content.json`,
  `scripts/mpi.py`, `tests/test_mpi.py`, `tests/test_bronze.py` (pipeline activity set),
  `docs/adr/0001-mpi-approach.md`, `docs/evidence/mpi.json`, `Makefile`, `.github/workflows/ci.yml`,
  `README.md`, `CLAUDE.md`, `plan.md`; plus the gap files above.
- Invariants: weights are explainable per field; a rare surname agreeing counts more than a common
  one only if term frequency is added later (not now); thresholds sit in the notebook as constants.
- Red check: stand test on precision and recall; fast tests on scoring of fixture pairs.
- Cost: u estimation is one extra Spark pass; about 250 lines in the notebook.
- Reverse: delete the notebook and its pipeline activity; U08 then has no xref.

### Approach B — Hand-set points

Fixed points per agreement (family JW ≥ 0.9: +3, exact birth date: +3, …) and two thresholds.

- Cheapest to write, but the points have no derivation; a reviewer asks "why 3".
- Same files, tests and reversal as A.

### Approach C — Deterministic rule ladder

Ordered rules (exact name + birth date; phone + birth date; JW names + birth year + phone; …);
the first rule that fires matches.

- Easy to read, but every noise combination needs its own rule, and there is no review band by
  score, only by rule.
- Same files, tests and reversal as A.

## Recommendation

A, with both gaps resolved as proposed (phone noise added to U03 first, Silver system `ehr`).

## Implementation notes (2026-10-28)

- U03 noise: `phone_missing` 0.10 and `phone_changed` 0.05 measured exactly on every register
  (lab within 0.0005). The noise-rate test now compares the last 10 digits of a phone, since
  `+1 555 …` carries the country code.
- Thresholds: on the full population candidate scores cluster below 12 and above 28 (log2 units);
  `MATCH` = 20 and `REVIEW` = 12 sit in that valley and were set before running the evaluation.
- Full population: `make mpi` takes 26 s. Blocking keeps 65,392 candidate pairs, 21,338 are merged
  and 22 go to review. The result has 15,330 masters for 15,326 persons.
  `make mpi-eval` gives precision 1.0 and recall 0.9998. Blocking recall is 0.9998: 4 true pairs
  are never compared.
- Negative control: `MATCH` = 0 merges 23,564 pairs and the stand gate test fails.
- The result is near perfect because the noise is light: at most one error per field, and no name
  changes. The ADR says so.
