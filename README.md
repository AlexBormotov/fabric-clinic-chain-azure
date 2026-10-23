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
