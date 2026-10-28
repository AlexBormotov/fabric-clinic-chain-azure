---
id: PLAN-U15
spec: SPEC-001 / U15
owner: AlexBormotov
status: approach A taken 2026-10-28 under the owner's standing go-ahead
previous: PLAN-U07 (approach A, landed in #10; see git history of this file)
---

# PLAN-U15 — Data quality

## Facts this plan rests on (read 2026-10-28)

- PyPI, 2026-10-28: `soda-core` 4.29.0 and `soda-sparkdf` 4.29.0, both released 2026-10-27,
  `requires_python >=3.10`. The v4 line ships weekly: 4.24.0 on 2026-09-16, then 4.25 to 4.29.
  `soda-sparkdf` requires `soda-core==4.29.0`, `soda-databricks==4.29.0`, `freezegun` and
  `pyspark[connect]>=3.5.0`. It has no upper bound on PySpark. The last v3 package,
  `soda-core-spark-df` 3.5.6, pins `pyspark<4.0.0`.
- `uv lock` with `pyspark==4.1.1` on Python 3.13 resolves with no override. It adds
  `soda-databricks` (which pulls in `databricks-sql-connector` and `databricks-sdk`), the
  `pyspark[connect]` extras (grpcio, pandas 3.1.0, numpy 2.5.4) and OpenTelemetry. It lowers
  `requests` from 2.34.2 to 2.33.1 (`soda-core` pins `<2.34.0`).
- Measured in the dev container: a v4 data contract runs on local PySpark 4.1.1 with ANSI mode
  on, with no pin and no shim. Importing `soda_sparkdf` before `soda_core` logs a circular-import
  warning from the plugin entry point. Importing `soda_core` first avoids it.
- v4 checks are data contracts in YAML (`dataset`, `columns[].checks`, dataset-level `checks`).
  Check types: `missing`, `invalid` (`valid_values`, `valid_min`, `valid_format`,
  `valid_reference_data`, …), `duplicate` (on a column, or on `columns` at dataset level),
  `row_count`, `failed_rows` (`expression` or `query`), `freshness`, `schema`, `aggregate`,
  `metric`. SodaCL is v3 only. Docs: docs.soda.io, "Spark Dataframe" reference, read 2026-10-28.
- A dataset is `<data source>/<schema>/<table>`. The data source wraps the running session through
  `SparkDataFrameDataSource.from_existing_session` and runs `DESCRIBE` and SQL on catalog names.
  Silver tables are Delta paths, so they must be visible to the catalog under a schema.
- `valid_reference_data` cannot filter the referenced table. The `ehr` filter on `patient_record`
  therefore needs a `failed_rows` query.
- Soda Core sends anonymous telemetry to `collect.soda.io` by default. Setting
  `SODA_CORE_TELEMETRY_ENABLED=false` turns it off; it must be set before the first import.
- Microsoft Learn, "Manage Apache Spark libraries" (updated 2026-08-04, read 2026-10-28):
  `%pip install` is off in notebook pipeline runs by default. A boolean notebook activity
  parameter `_inlineInstallationEnabled` = `True` turns it on. An Environment in Full mode is the
  recommended route for pipelines. Fabric Runtime 2.0 is Spark 4.1 on Python 3.13
  (`docs/research/fabric-facts-2026-10-21.md`).
- Full Silver profile (2026-10-28):
  - Every `encounter.fhir_patient_id` exists in the `ehr` patient records.
  - Each of these references resolves in full: condition → encounter, lab → lab patient,
    claim → billing account, claim_line → claim, adt → adt patient, adt → bed, roster → staff.
  - No duplicate IDs.
  - 2,182 of 32,722 claims have `paid_amount > billed_amount`. This comes from Synthea, so there
    is no check on it.

## Approaches: getting Soda v4 to run on Runtime 2.0

### Approach A — stock packages, Silver as global temp views (taken)

- **Install:**
  - Pin `soda-core==4.29.0` and `soda-sparkdf==4.29.0` in `pyproject.toml`.
  - In Fabric, the notebook's first cell runs `%pip install` with the same pins.
  - The pipeline activity passes `_inlineInstallationEnabled` = `true`.
  - pip leaves the runtime's PySpark alone, because 4.1 already satisfies `>=3.5.0`.
- **Data:**
  - `nb_quality` registers each checked Silver table as a global temp view.
  - It verifies one contract per table against dataset `silver/global_temp/<table>`.
  - This works the same on local Spark and in Fabric, and writes nothing to the catalog or the
    Lakehouse.
- **Contracts:**
  - The YAML lives in the notebook, so the Fabric item is self-contained.
  - Each contract is passed to `ContractVerificationSession.execute` through
    `ContractYamlSource.from_str`.
  - Telemetry is off.
  - Any outcome other than PASSED fails the run. So does a contract error. The run cell raises,
    so the pipeline activity fails.

### Approach B — Fabric Environment item with the pins (Full mode)

- The pins are the same. The difference is that they are published once into a Fabric
  Environment attached to `nb_quality`. Microsoft recommends this route for pipelines.
- It adds an Environment item to Git, deployment and Terraform (U18/U19). Publishing takes 3 to 6
  minutes and session start takes 1 to 3 minutes more. This repository cannot check the item's
  format locally.
- Kept as the fallback if inline install fails or resolves differently in U20.

### Approach C — shim or pinned older PySpark

- Not needed: no incompatibility was found on PySpark 4.1.1. A downgrade is also ruled out by the
  intent ("no downgrade to work around a library").

## Files (approach A)

- `fabric/nb_quality.Notebook/notebook-content.py` and `.platform` (new logicalId)
- `fabric/pl_land_sources.DataPipeline/pipeline-content.json` (`run_nb_quality` after
  `run_nb_silver`)
- `scripts/quality.py`
- `tests/test_quality.py`
- `tests/test_bronze.py` (the pipeline activity set)
- `docs/adr/0003-soda-on-runtime-2.md`
- `pyproject.toml` and `uv.lock`
- `Makefile` (`quality`) and `.github/workflows/ci.yml` (`make quality` in the `stand` job)
- `README.md`, `CLAUDE.md` and `plan.md`

## Checks

- Every key table has non-null IDs and unique IDs (on two columns where the key has two).
  - `bed` has the unique-ID check only.
- Every key table has a non-empty row count, except `claim_line`.
- Value ranges and domains:
  - `patient_record`: system, sex and clinic in their domains; a 10-digit phone; birth date from
    1900 to today.
  - `encounter`: class code; no end before start.
  - `lab_result`: values ≥ 0.
  - `claim`: amounts ≥ 0; status; a denied claim has a reason.
  - `claim_line`: amount ≥ 0.
  - `adt_event`: event type.
  - `ed_visit`: timestamps in order.
- Referential integrity:
  - The required check is that every `encounter.fhir_patient_id` exists in `patient_record` where
    `system = 'ehr'`. It is a `failed_rows` query.
  - condition → encounter, claim_line → claim and adt_event → bed use native
    `valid_reference_data`.

## Invariants

- No Silver data is written. The checks read Silver and register only session-scoped views.
- A check that cannot be evaluated counts as a failure, never as a pass.
- No telemetry leaves the run.

## Red checks

- Fast test: clean fixtures pass every check.
- Fast test: the same fixtures plus one encounter whose patient is not an `ehr` record fail
  exactly one check, the referential-integrity check.
- Fast test: a contract that references a missing column fails the run instead of passing.
- `stand` test: every check passes on the full Silver.
- `test_bronze.py` pins the pipeline activity set. `test_quality.py` pins the
  `_inlineInstallationEnabled` parameter.

## Reversal

Delete the notebook, its pipeline activity, the script, the tests, the `make` target and the CI
step, and drop the two pins (`uv lock`). Silver is untouched, so nothing else changes.
