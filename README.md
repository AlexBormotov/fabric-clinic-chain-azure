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
| `make test` | pytest |
| `make secrets` | gitleaks over the git history |

CI runs the same targets.
