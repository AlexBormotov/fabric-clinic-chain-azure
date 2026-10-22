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
| `make test-slow` | Synthea tests: patient counts, date range, determinism (~4 min) |
| `make synth` | generate the synthetic population into `data/raw/fhir/` (~4 min, ~880 MB) |
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
