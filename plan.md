---
id: PLAN-U06
spec: SPEC-001 / U06
owner: AlexBormotov
status: approach A approved 2026-10-26 with the MPI order changed as proposed; built
previous: PLAN-U05 (approach A, landed in #8; see git history of this file)
---

# PLAN-U06 — Silver

## Facts this plan rests on (measured 2026-10-23 on the full population)

- Bronze (U05): 12 tables; `fhir_bundle` holds 1,206 raw bundles: 1,200 patient bundles plus
  `hospitalInformation*` and `practitionerInformation*` per clinic. Largest bundle 12 MB.
- Resources in the 1,200 patient bundles (all history / inside the 2024-10-01 … 2026-09-30 window):
  Observation 97,376 / 97,376; DiagnosticReport 31,768 / 22,056; Claim and ExplanationOfBenefit
  30,360 / 18,001 each; Procedure 27,580; Encounter 20,083 / 10,371; DocumentReference 20,083;
  Condition 16,971 / 6,160; MedicationRequest 10,277 / 7,630; Patient 1,200; others below 5,000.
- The lab system (59,083 results) and billing (32,722 claims) were derived in U03 **from the same
  FHIR facts** (laboratory Observations, ExplanationOfBenefit). Taking them from FHIR too would count
  each fact twice.
- Bronze types: billing is typed Parquet (decimal, date, datetime2); lab, ADT and SharePoint are
  strings; FHIR is raw JSON text.
- SPEC-001: U07 (MPI) is blocked by U05 only, U08 (Gold) by U06 and U07.

## Gap in the spec that needs the owner's decision

**U06 cannot join MPI identifiers.** Its scope says "MPI identifiers joined in from U07", but U07
runs after U05 and needs conformed patient records itself: as written, U06 waits for U07 and U07
would have to redo U06's conformance on raw Bronze. Proposed order: U06 builds
`silver.patient_record` (every system's patient rows, standardized) without MPI; U07 is blocked by
U06, reads `patient_record` and writes `silver.patient_xref` (system, local ID → master patient ID);
U08 joins facts to the master patient through `patient_xref`. Spec edits: U06 scope drops the MPI
join, U07 "Blocked by: U06", U08 scope gains the `patient_xref` join.

## Settings for every approach

- **Code:** one self-contained notebook `fabric/nb_silver.Notebook/notebook-content.py` (the U05
  pattern: imported by tests, run cell guarded), parameters `run_id`, `bronze_root`, `silver_root`;
  session time zone set to UTC in the notebook. `pl_land_sources` gains a `run_nb_silver` activity
  after `run_nb_bronze`. `make silver` runs it locally; `make bronze` stays as is.
- **Lakehouses:** `lh_bronze` and `lh_silver`. Locally `data/lakehouse/` becomes `data/lh_bronze/`
  and Silver goes to `data/lh_silver/Tables/` (touches the U05 runner, tests and docs: paths only).
- **System of record per fact:** FHIR → patient, encounter, condition, medication_request; lab
  system → lab_result; billing → claim, claim_line; ADT → adt_event, ed_visit; SharePoint → bed,
  staff, roster (Gold needs ward and bed dimensions). FHIR Observations, Claims and EOBs are not
  carried to Silver (they are the lab and billing facts); every other FHIR resource type is out of
  scope and counted as such.
- **Tables:** `patient_record` (system, local_patient_id, clinic_id, given/family name trimmed,
  birth_date, sex, phone as 10 digits or NULL, postal_code; one row per source patient row, noise
  kept: resolving it is U07), plus one table per fact above with typed columns (timestamps UTC,
  decimals, dates) and source keys. History is kept: the analytical window is applied in Gold and
  the metrics.
- **Drops:** exact duplicates (all source columns equal) and rows whose required key or timestamp
  fails to cast; nothing else is filtered.
- **Reconciliation:** `silver.reconciliation` per run: for each Silver table, input rows (Bronze rows,
  or FHIR resources of that type), output rows and dropped rows by reason (`exact_duplicate`,
  `invalid_<column>`); for FHIR also resources by out-of-scope type. Invariant tested:
  `input = output + Σ dropped`.
- **Tests:** fast (`make test`, fixtures for every table: a bundle with each in-scope resource and one
  out-of-scope, CSV rows with a duplicate and an uncastable timestamp, reconciliation balance);
  full (`stand` marker, after `make bronze silver`): reconciliation balances for every table, Silver
  row counts equal the measured FHIR resource counts and the source counts minus counted drops.

## The choice: how FHIR is flattened

### Approach A — Explicit schemas with `from_json` (recommended)

Per in-scope resource type, a small `StructType` naming only the fields Silver keeps. The bundle is
parsed once with a schema of `entry[].resource` as a JSON string plus `resourceType`, filtered by
type, then each resource string is parsed with its schema and selected into columns.

- Files: `fabric/nb_silver.Notebook/*`, `fabric/pl_land_sources.DataPipeline/pipeline-content.json`,
  `scripts/silver.py`, `scripts/bronze.py`, `tests/test_silver.py`, `tests/test_bronze.py`,
  `Makefile`, `.github/workflows/ci.yml`, `README.md`, `CLAUDE.md`, `spec.md` (gap), `plan.md`.
- Invariants: the schemas document exactly what Silver reads from FHIR; unknown fields are ignored;
  a missing required field becomes NULL and is dropped and counted, never silently passed.
- Red check: fixture tests per resource type; reconciliation balance.
- Cost: schemas must be written for four resource types (~60 lines).
- Reverse: delete the notebook and its pipeline activity.

### Approach B — Inferred schema (`spark.read.json`)

Let Spark infer one schema over all bundles, then select the needed paths.

- Invariants: none on shape; the inferred schema changes with the data (a field Synthea omits in
  one run disappears from the schema and the select fails).
- Cost: inference scans ~900 MB and merges every resource type into one wide struct; slow locally,
  and differs between fixture and full data, so fast tests do not test the real path.
- Reverse: same as A.

### Approach C — Python parsing in a UDF

Parse each bundle with `json` in `mapInPandas`, emit rows per resource type.

- Invariants: plain Python is easy to read and to test outside Spark.
- Cost: every bundle crosses the JVM↔Python boundary; Python per-row work on the cluster; the most
  common Spark review comment for this pattern is "use from_json".
- Reverse: same as A.

## Recommendation

A, with the MPI order changed as proposed.

## Implementation notes (2026-10-26)

- Medication codes: some MedicationRequests reference a `Medication` resource (1,460 in the bundles)
  instead of carrying `medicationCodeableConcept`. `Medication` is parsed with its own small schema only to resolve
  those codes; it is still reported as `out_of_scope`, as it is not a Silver table.
- `bronze_root` defaults to a OneLake path with placeholder GUIDs, resolved by parameter.yml at
  deploy (U19), like the other IDs in `fabric/`. The pipeline passes only `run_id`.
- Casts use `try_cast` and array access `try_element_at`: Spark 4 runs with ANSI mode on, where a bad
  cast or an empty array would fail the job instead of yielding NULL.
- Full population: `make silver` 2:20; reconciliation balances for every table and source, no row
  dropped; FHIR inputs equal resource counts read from `data/raw/fhir/`. Negative controls: counting
  only third copies as duplicates, and dropping the `+1` phone rule, each turned the matching fast
  test red.
- `tests/test_bronze.py`: the pipeline test now expects `run_nb_silver` and picks `run_nb_bronze` by
  name, since the pipeline has two notebooks.
