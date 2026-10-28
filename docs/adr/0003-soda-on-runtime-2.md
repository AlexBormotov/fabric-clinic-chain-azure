# ADR 0003: Soda Core v4 on Fabric Runtime 2.0, stock packages, Silver as global temp views

- Status: accepted 2026-10-28 (PLAN-U15, approach A, under the owner's standing go-ahead)
- Unit: U15

## Context

AC8 asks for Soda Core checks on Silver in Fabric notebooks. The intent fixes the tool, Soda v4
(`soda-sparkdf`), and the runtime, Runtime 2.0 (Spark 4.1, Python 3.13), with no downgrade.

The last v3 Spark package, `soda-core-spark-df` 3.5.6, pins `pyspark<4.0.0`, so it cannot run on
Runtime 2.0. On PyPI on 2026-10-28 the current v4 packages are `soda-core` 4.29.0 and
`soda-sparkdf` 4.29.0, both released 2026-10-27. `soda-sparkdf` requires:

- `soda-core==4.29.0`;
- `soda-databricks==4.29.0`, which brings its SQL dialect along with `databricks-sql-connector`
  and `databricks-sdk`;
- `freezegun`;
- `pyspark[connect]>=3.5.0`, which has no upper bound.

v4 declares checks as data contracts in YAML. SodaCL is v3 only. A contract names a dataset as
`<data source>/<schema>/<table>`, and Soda reads it with `DESCRIBE` and SQL through the Spark
session. Silver tables are Delta paths, not catalog tables.

## Decision

- **Packages.** Use the stock packages, pinned exactly: `soda-core==4.29.0` and
  `soda-sparkdf==4.29.0`.
  - Locally, `uv lock` resolves them next to `pyspark==4.1.1` on Python 3.13 with no override.
  - The full contract set then runs on PySpark 4.1.1 with ANSI mode on. No shim or patch was
    needed.
  - The only side effect is `requests` going from 2.34.2 to 2.33.1, because `soda-core` caps it
    below 2.34.
- **Install in Fabric.**
  - The first cell of `nb_quality` runs `%pip install` with the same pins. A test keeps those pins
    equal to `pyproject.toml`.
  - Inline install is off in pipeline runs by default, so the `run_nb_quality` activity passes
    `_inlineInstallationEnabled` = `true` (Microsoft Learn, "Manage Apache Spark libraries",
    updated 2026-08-04).
  - pip leaves the runtime's PySpark alone, because 4.1 already satisfies `>=3.5.0`.
- **Datasets.**
  - `nb_quality` registers each checked Silver table as a global temp view.
  - It verifies dataset `silver/global_temp/<table>` through
    `SparkDataFrameDataSource.from_existing_session`.
  - This needs no catalog or Lakehouse schema and writes nothing. It behaves the same on local
    Spark and in Fabric.
- **Contracts in the notebook.**
  - One contract per table is kept as a Python dict in the notebook. It is serialized to JSON,
    which is valid YAML, and passed to `ContractVerificationSession.execute` through
    `ContractYamlSource.from_str`.
  - The Fabric item stays self-contained: no resource folder and no file paths.
- **Referential integrity.**
  - patient ↔ encounter is a `failed_rows` query: every `encounter.fhir_patient_id` must be a
    `patient_record` row with `system = 'ehr'`. A `failed_rows` query is needed because
    `valid_reference_data` cannot filter the referenced table.
  - References without a filter use the native `invalid` / `valid_reference_data` check:
    condition → encounter, claim_line → claim and adt_event → bed.
- **Failure.**
  - Any check outcome other than PASSED fails the run. So does a contract that errors or yields
    no checks.
  - The notebook's run cell raises, so the pipeline activity fails. The activity has no retry.
- **Telemetry.** Soda Core sends anonymous usage telemetry to `collect.soda.io` by default. The
  notebook sets `SODA_CORE_TELEMETRY_ENABLED=false` before the first Soda import.
- **Import order.** Importing `soda_sparkdf` before `soda_core` logs a circular-import warning from
  the plugin entry point. The notebook imports `soda_core` first.

## Consequences

- The local run is the same code as the Fabric run, apart from the `%pip` cell. On the full Silver
  it runs 48 checks in 23 s. A fixture with one orphaned encounter fails exactly the patient ↔
  encounter check.
- The dependency footprint grows by the Databricks connector, the gRPC and pandas extras of
  `pyspark[connect]`, and OpenTelemetry. None of them is used at run time.
- **Not yet verified in Fabric (U20):**
  - that `%pip` resolves on Runtime 2.0 without replacing built-in packages;
  - how long the install adds to session start.
  pip pins only the two top-level packages, so transitive versions can drift between runs.
- **Fallback (PLAN-U15 approach B):** publish the same pins into a Fabric Environment in Full
  mode, attach it to `nb_quality`, and drop the `%pip` cell and the activity parameter. That is
  Microsoft's recommended route for pipelines. It costs an extra item in Git, deployment and
  Terraform, plus 3 to 6 minutes of publishing.
- Soda v4 releases weekly. Raising the pins means editing `pyproject.toml` and the notebook
  together, then running `uv lock`, `make test` and `make quality`.
