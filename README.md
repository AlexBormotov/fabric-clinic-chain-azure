# fabric-clinic-chain-azure

End-to-end analytics and real-time bed monitoring for a small clinic chain on Microsoft Fabric:
batch (FHIR, Azure SQL, CSV, Excel) through a Lakehouse and Warehouse into a Direct Lake Power BI
model, plus ADT events streamed through Eventstream into Eventhouse with Activator alerts.
All patient data is synthetic (Synthea).

**Status:** foundation in progress. Scope and work units: [`intent.md`](intent.md),
[`spec.md`](spec.md).

## Run it locally

Requirements: Docker with Compose v2 and GNU Make. Everything else runs in the dev container.

| Command | What it does |
|---|---|
| `make setup` | build the dev image and install Python dependencies |
| `make lint` | ruff, sqlfluff, actionlint |
| `make test` | pytest (fast tests) |
| `make test-slow` | Synthea and source-derivation tests on the full population (~10 min) |
| `make synth` | generate the synthetic population into `data/raw/fhir/` (~4 min, ~880 MB) |
| `make sources` | derive the source systems from the FHIR output into `data/sources/` (~1.5 min) |
| `make up` / `make down` | start and load the local source stand / stop it (~1 min) |
| `make test-stand` | read the stand, Bronze and Silver back and compare with their inputs |
| `make bronze` | land the stand into `data/lh_bronze/Files/` and build Bronze on local Spark (~3 min) |
| `make silver` | build Silver from Bronze into `data/lh_silver/` and print the reconciliation (~2.5 min) |
| `make secrets` | gitleaks over the git history |

CI runs the same targets.

## Synthetic population

[Synthea](https://github.com/synthetichealth/synthea) v4.0.0 (jar pinned by sha256 in
[`config/synthea.yaml`](config/synthea.yaml)) generates one FHIR R4 population per clinic: Boston
300, Worcester 400 and Springfield 500 patients, Massachusetts, fixed seeds. Synthea only models US
cities, so the clinics sit there.

- Only patients alive on 2026-09-30 are generated, so counts are exact; deaths inside the window
  remain.
- The simulation ends on 2026-09-30. Synthea keeps older history linked to still-active conditions,
  so raw data reaches back decades, as a real EHR extract would. Analytics use the window
  2024-10-01 … 2026-09-30.
- Runs are single-threaded: Synthea's thread pool makes output vary between runs.

## Source systems

`make sources` derives the other four source systems from the FHIR output (FHIR is the fifth)
(schemas in [`docs/contracts/`](docs/contracts/README.md), settings in
[`config/sources.yaml`](config/sources.yaml)):

- **Billing** (SQL Server / Azure SQL): patient accounts, claims and claim lines. Synthea adjudicates
  every claim as paid, so denials are generated per payer.
- **Lab** (CSV): results of laboratory observations.
- **Bed management** (ADT): admit/transfer/discharge events with ward and bed, and ED visits with
  arrival, triage and provider-seen times (Synthea has none; they are drawn from configured
  distributions).
- **SharePoint** (Excel): bed reference and weekly staff rosters.
- **Ground truth**: every person and every local patient ID that belongs to them.

The 1,200 Synthea patients are the chain's registered population. Synthea alone gives about 170
inpatient stays in two years, under two occupied beds across the chain, so the wards (12, 16 and
20 beds) also take **referred inpatients** who exist only in the bed management and billing systems.
Their arrivals are calibrated per ward to a mean occupancy of 80% with winter peaks.

Each system has its own patient IDs and deliberate noise: 4% name typos, 2% day/month swaps in the
birth date, 25% non-canonical phone formats and 5% duplicate patient records, applied as exact
counts.

## Local source stand

`make up` stands in for the cloud sources in docker compose and loads them:

- **SQL Server 2022** (for Azure SQL): database `clinic_billing`, schema from
  [`docs/contracts/billing.sql`](docs/contracts/billing.sql).
- **Azurite** (for Blob Storage): containers `fhir` (`<clinic>/<patient>.json`), `lab` and `adt`.
- **SharePoint**: the folder `data/sources/sharepoint/`.

Loading is idempotent. `make test-stand` checks that every table and container holds exactly what
`data/sources/` and `data/raw/fhir/` hold.

## Bronze

Fabric items live in [`fabric/`](fabric/) in Fabric's Git format:

- `pl_land_sources` (Data Pipeline) copies every batch source unchanged into Lakehouse Files
  `landing/<system>/<run id>/`, refreshes `df_sharepoint` (Dataflow Gen2: workbooks to CSV), then
  runs `nb_bronze`.
- `nb_bronze` (PySpark notebook) writes one Delta table per source: source columns as landed plus
  `_run_id`, `_source_file` and `_ingested_at`. FHIR stays one raw JSON row per bundle file.

Locally `make bronze` stands in for the pipeline and the Dataflow, then imports and runs the same
notebook file on Spark 4.1 + Delta 4.2 (Fabric Runtime 2.0). Bronze lands in
`data/lh_bronze/Tables/`.

## Silver

`nb_silver` runs after `nb_bronze` in the same pipeline and writes typed tables to `lh_silver`. Each
fact comes from one system of record, because lab results and claims were derived from the same
FHIR facts and would otherwise count twice:

| Silver table | Source |
|---|---|
| `patient_record` | patients of FHIR, lab, ADT and billing, one row per source record |
| `encounter`, `condition`, `medication_request` | FHIR bundles, parsed with explicit schemas |
| `lab_result` | lab system |
| `claim`, `claim_line` | billing |
| `adt_event`, `ed_visit` | ADT |
| `bed`, `staff`, `roster` | SharePoint |

`patient_record` is standardized, not matched: names trimmed (Synthea's numeric suffixes removed),
sex as M/F/U, phone as 10 digits. Matching records to one person is U07. Timestamps are UTC.

A row is dropped only when it exactly duplicates another, when a required column is empty or when
a value does not cast. `reconciliation` records, per Silver table and source, the rows in, the rows
out and the rows dropped by reason; FHIR resource types Silver does not use (Observation, Claim,
ExplanationOfBenefit and others) are counted as `out_of_scope`. On the full population nothing is
dropped: Silver holds 1,200 FHIR patients, 20,083 encounters, 16,971 conditions, 10,277 medication
requests and every source row.
