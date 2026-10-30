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
| `make lint` | ruff, sqlfluff, actionlint, then `make tf-check` |
| `make tf-check` | Terraform fmt and validate, tflint (offline, no cloud call) |
| `make test` | pytest (fast tests) |
| `make test-slow` | Synthea and source-derivation tests on the full population (~10 min) |
| `make synth` | generate the synthetic population into `data/raw/fhir/` (~4 min, ~880 MB) |
| `make sources` | derive the source systems from the FHIR output into `data/sources/` (~1.5 min) |
| `make up` / `make down` | start and load the local source stand / stop it (~1 min) |
| `make test-stand` | read the stand, Bronze and Silver back and compare with their inputs |
| `make bronze` | land the stand into `data/lh_bronze/Files/` and build Bronze on local Spark (~3 min) |
| `make silver` | build Silver from Bronze into `data/lh_silver/` and print the reconciliation (~2.5 min) |
| `make mpi` / `make mpi-eval` | match patient records into `patient_xref` / score it against ground truth |
| `make gold` | copy Silver into the stand's SQL Server and build the Gold star schema (~30 s) |
| `make bed-history` | apply new ADT events to the SCD2 bed state history in `bed_state_history` |

| `make quality` | Soda data contracts on Silver; fails when a check fails |

| `make replay` | replay ADT events into the Event Hubs emulator at 50 events/s (`ARGS='--limit 2000'`) |

| `make deploy ENVIRONMENT=Test` | deploy `fabric/` to a Fabric workspace (CI, see Deployment) |
| `make republish ENVIRONMENT=Test` | republish deployed Dataflows Gen2 as the owner |
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
- **Event Hubs emulator** (for the Eventstream custom endpoint): event hub `adt`, 3 partitions,
  with its own Azurite.

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
| `patient_record` | patients of the EHR (FHIR), lab, ADT and billing, one row per source record |
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

## Master patient index

`nb_mpi` runs after `nb_silver` and matches `patient_record` rows across and within systems. It
writes `patient_xref` (system, local patient ID → master patient ID) and `patient_match_review`
(uncertain pairs, not merged). Scoring follows Fellegi–Sunter, as described in
[ADR 0001](docs/adr/0001-mpi-approach.md):

- blocking on birth year with surname soundex, on birth date and on phone;
- Jaro-Winkler for names;
- weights log2(m/u), with u measured on random pairs.

`make mpi-eval` scores the result against the generator's ground truth, which never reaches Fabric.
Results are in [`docs/evidence/mpi.json`](docs/evidence/mpi.json). CI fails below precision 0.98 or
recall 0.95.

## Gold

The Gold star schema is a Fabric Warehouse built in T-SQL ([`sql/gold/`](sql/gold/)): dimensions
date, clinic, ward, bed, patient (one row per master patient), payer and diagnosis; facts encounter,
bed-day (occupied hours per stay segment and day), claim, lab result and ED visit, all within the
2024-10-01 … 2026-09-30 window. The procedure `gold.reload` truncates and refills it from a `silver`
schema, which is a set of views over the Lakehouse in Fabric and copied tables locally. The T-SQL
stays inside what both Fabric Warehouse and SQL Server accept
([ADR 0002](docs/adr/0002-lakehouse-warehouse.md)). `make gold` builds it on the stand's SQL Server.
Tests check:

- that Gold reconciles with Silver: rows per fact inside the window, and bed hours recomputed from
  ADT events in Spark;
- that keys are unique and every fact key resolves to a dimension.

PHI lives only in `gold.dim_patient`: names, birth date, phone and postal code.
- Role `gold_reader` is denied every PHI column (column-level security). The denial also covers
  predicates on those columns.
- Each PHI column is also masked (dynamic data masking). Masks cover readers outside both roles,
  such as a Fabric Viewer. A Viewer can still infer values through predicates, so non-PHI readers
  get `gold_reader`, not Viewer.
- Role `gold_phi_reader` has `UNMASK` and sees clear values
  ([`sql/gold/30_security.sql`](sql/gold/30_security.sql)).

In Fabric, Entra groups join the roles
([`sql/fabric/security_members.sql`](sql/fabric/security_members.sql)). Locally, the `stand` tests
create three SQL logins and query as each: one per role, and one with only `db_datareader`.

### Metrics

The eight metrics are defined in [`GLOSSARY.md`](GLOSSARY.md) and exposed as Gold views
`gold.metric_summary` and `gold.metric_payer_mix`, per clinic and for the chain.
`make metric-reference` computes the same metrics with pandas straight from `data/sources/` into
[`docs/evidence/metric-reference.json`](docs/evidence/metric-reference.json); a stand test requires
Gold to match it to a relative 1e-6.

## Bed state history

`nb_bed_history` runs after `nb_silver` and writes `bed_state_history`: one row per bed and interval
of constant state (free, or occupied by one stay), with `valid_from`, `valid_to` (NULL on the
current row), `stay_id` and `adt_patient_id`. Events are deduplicated by `event_id`; those not yet
in the `bed_event` log are new. The beds they touch are recomputed from all their events and
applied with one Delta MERGE, so a late, duplicate or out-of-order event yields the same history as
an in-order run. Tests cover each case; on the full population the history has no gaps or overlaps
and its occupied intervals equal the stay segments in `adt_event`.

## Data quality

`nb_quality` runs after `nb_silver` and verifies Soda Core v4 data contracts (`soda-sparkdf`) on
Silver: 48 checks over nine tables. They cover non-null and unique keys, value domains and ranges,
and referential integrity. Every encounter's patient must be an EHR patient record; conditions,
claim lines and ADT events must reference existing encounters, claims and beds. A check that fails
or cannot be evaluated fails the notebook, and with it the pipeline activity. On the full Silver all
48 checks pass in 23 s. A fixture with one orphaned encounter fails the patient ↔ encounter check.
How Soda runs on Runtime 2.0 is recorded in [ADR 0003](docs/adr/0003-soda-on-runtime-2.md).

## ADT replay

`scripts/replay_adt.py` sends `data/sources/adt/events.csv` over the Event Hubs protocol in
event-time order, compressed so the whole replay averages `--rate` events/s (default 50; the full
two years then take about 4.5 minutes). A seeded schedule sends exactly `--late-share` (default 5%)
of events after an event with a later event time and `--duplicate-share` (3%) of events twice.
The body is the contract row as JSON; the partition key is the clinic.

The target is `--connection-string`, else `ADT_EVENTHUB_CONNECTION_STRING`, else the local
emulator. An Eventstream custom endpoint connection string works unchanged.

`make test-stand` replays 2,000 events at 50/s into the emulator, reads them back and checks every
event arrived, the rate within 10% and the late and duplicate shares within 1 percentage point.

## Infrastructure

[`infra/`](infra/README.md) holds the Terraform for the cloud run: Blob storage and the Azure SQL
free offer, three Fabric workspaces (Dev, Test, Prod) with their lakehouses, warehouse and
eventhouse, Git integration for Dev, a deployment pipeline and an F2 capacity that is created and
destroyed once. Defaults take the cheapest path: workspaces on the Fabric trial, F2 off. The owner
applies it with `az login`; nothing secret is committed.

## Semantic model and report

[`fabric/sm_clinic_chain.SemanticModel/`](fabric/sm_clinic_chain.SemanticModel/) is a Direct Lake
on OneLake model in TMDL over the Gold Warehouse tables. [`fabric/rpt_clinic_chain.Report/`](fabric/rpt_clinic_chain.Report/)
is a PBIR report bound to it by path, with one page per contour: occupancy, quality, economics.

- Tables: `dim_date`, `dim_clinic`, `dim_bed`, `dim_payer` and the bed-day, stay, ED visit and claim
  facts, each related to `dim_clinic` and `dim_date`. `dim_patient` and every PHI column stay out.
- Measures carry the metric names of [`GLOSSARY.md`](GLOSSARY.md) and follow its definitions.
- RLS: the role `clinic` keeps the `dim_clinic` rows mapped to `USERPRINCIPALNAME()` in
  `gold.user_clinic` ([`sql/gold/30_access.sql`](sql/gold/30_access.sql)); facts follow through
  their relationships. The table is never reloaded or committed with rows: each environment fills
  it from a git-ignored copy of [`sql/fabric/user_clinic.example.sql`](sql/fabric/user_clinic.example.sql),
  and the role's one member is the Entra group of clinic users. Model RLS does not bind workspace
  Admins, Members or Contributors.
- Under RLS a clinic user's facts stop at their clinics, so `readmission_30d_rate` averages
  `gold.fact_stay.readmitted_30d`, which `gold.reload` computes over every stay of the chain.
- The OneLake URL in `expressions.tmdl` holds zero GUIDs for workspace and Warehouse; deployment
  (U19) replaces them per environment.

`make test` parses the TMDL with a small structural reader (`src/clinic_chain/tmdl.py`) and checks
that every model column exists in Gold with a compatible type, that no PHI column is present, that
every metric has a measure and a visual, and that the RLS role exists. Measure values are compared
with the U09 reference in the cloud run.

## Eventhouse model

`fabric/kqldb_beds.KQLDatabase/` is the KQL database under the `eh_beds` eventhouse, in Fabric's
Git format. Eventstream ingests each event body as JSON into `adt_raw` (mapping `adt_raw_json`);
an update policy types it into `adt_event`, with `ingested_at` for latency. `bed_current()` takes
the latest change per bed by event time (`arg_max`), so late and duplicate events do not change the
answer, and it agrees with `nb_bed_history`. `ward_occupancy()` divides occupied beds by the beds
per ward in `bed`, the SharePoint bed list loaded from Silver; the live map and the Activator rule
read it.

`make kql-test` runs the schema on the Kusto emulator: four arrival orders of one scripted event
set (in order, late, duplicate, reversed) must give the same current state and occupancy. The
emulator needs up to 4 GB, so it runs alone, never next to `make up`.

## Deployment

`.github/workflows/deploy.yml` deploys `fabric/` with
[`fabric-cicd`](https://github.com/microsoft/fabric-cicd) 1.4.0 on manual dispatch only: Test, then
Prod if `target` is `Prod`. It never runs on push.
Environment values live in [`fabric/parameter.yml`](fabric/parameter.yml), which commits no ID:

- workspace and item IDs are looked up by name in the target workspace;
- connection IDs and the SharePoint site come from GitHub environment variables.

Why fabric-cicd and not the deployment pipeline:
[ADR 0004](docs/adr/0004-fabric-cicd-vs-deployment-pipelines.md).

The workflow signs in as the deployer service principal through GitHub OIDC. No client secret
exists anywhere. One-time owner setup, after `terraform apply` (U18):

1. Create an Entra app registration, the deployer. Pass its service principal object ID to
   Terraform as `deployer_principal_id`, which makes it Contributor on Test and Prod.
2. On the app, add two federated credentials: issuer `https://token.actions.githubusercontent.com`,
   audience `api://AzureADTokenExchange`, subjects
   `repo:AlexBormotov/fabric-clinic-chain-azure:environment:Test` and `…:environment:Prod`.
3. In the Fabric admin portal, allow service principals to use Fabric APIs, for a security group
   that holds the deployer.
4. In Fabric, create the Azure SQL and Blob Storage connections the pipeline uses. Share them with
   the deployer.
5. In GitHub, create the environments `Test` and `Prod`:
   - limit both to the `main` branch;
   - add yourself as a required reviewer on `Prod`;
   - set these variables in each (variables, not secrets: none of them is a credential):

| Variable | Value |
|---|---|
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_CLIENT_ID` | deployer app (client) ID |
| `FABRIC_WORKSPACE_ID` | `terraform output workspace_ids`, `test` or `prod` |
| `FABRIC_SQL_CONNECTION_ID` | Fabric connection to the billing database |
| `FABRIC_BLOB_CONNECTION_ID` | Fabric connection to the Blob storage account |
| `SHAREPOINT_SITE_URL` | SharePoint site with `beds.xlsx` and `rosters.xlsx` |
| `ALERT_TEAMS_RECIPIENT` | Entra user (email) who gets the occupancy alert in Teams |

After a deploy that changed `df_sharepoint`, the dataflow needs an "apply changes" job. Fabric
does not accept a service principal for that job. Run it yourself:

1. Set `FABRIC_WORKSPACE_ID` in your shell, or in the git-ignored compose environment file.
2. Run `make republish ENVIRONMENT=Test`.
3. Sign in with the device code it prints.

## PHI security

[ADR 0005](docs/adr/0005-direct-lake-vs-phi-security.md) records how the layers fit:

- **Gold (SQL):** U16 denies PHI columns to `gold_reader` and masks them for everyone else.
- **Silver (OneLake):** Terraform sets OneLake security roles on every `lh_silver`. `DefaultReader`
  (everyone with ReadAll) reads the non-PHI tables only; `PhiReader` (one Entra group,
  `phi_reader_group_id`) reads all. The PHI class is `patient_record` and `staff`; the classes are in
  [`infra/modules/fabric/lh_silver_roles.json`](infra/modules/fabric/lh_silver_roles.json).
- **Model:** a fixed-identity connection, so clinic users need no access to the Warehouse and model
  RLS is the only path to the data.

`make test` checks that every table the notebooks write is in exactly one class, that tables with
name, birth, phone or postal columns are PHI, that only `PhiReader` reads PHI, and that Terraform
defines every role. The cloud behaviour is verified in U20.

## Live bed map and alert

[`fabric/rtd_beds.KQLDashboard/`](fabric/rtd_beds.KQLDashboard/) is the Real-Time Dashboard over
`kqldb_beds`: ward occupancy from `ward_occupancy()`, the state of every bed (`bed` joined to
`bed_current()`; a bed without events is free) and the newest event with its `ingested_at`. Live
refresh runs at the shortest rates the schema allows (5–10 s, 30 s fallback).
[`fabric/act_ward_occupancy.Reflex/`](fabric/act_ward_occupancy.Reflex/) is the Activator: every
60 s it reads the highest ward occupancy and the top three wards, and when the highest occupancy
crosses above 0.90 it sends a Teams message. Both are deployed by fabric-cicd; workspace IDs and
the recipient (`ALERT_TEAMS_RECIPIENT`) are bound by `fabric/parameter.yml`.

`nb_bed_reference` loads the KQL `bed` table from Silver `bed` with one `.set-or-replace`, after
`nb_silver` in `pl_land_sources`; Git sync creates the table but no rows, so without it
`ward_occupancy()` is empty.

By hand in Fabric, once per workspace:

1. Open `act_ward_occupancy`, rule "Ward occupancy above 90%". To post to a channel instead of
   the recipient's chat, set the action to Teams, Channel post, pick the team and channel, save.
   The definition format has no channel post, so this stays in the UI.
2. If the deploy rejects the Activator definition (its format is not stable across Microsoft's
   own sources), delete the item, open `rtd_beds`, select the "Ward occupancy" tile, Set alert:
   "On each event when" `occupancy` becomes greater than 0.9, action Teams, Channel post. Then
   commit the Activator the Dev workspace syncs back to Git.

`make test` validates the dashboard against the published schema (vendored, version 89), checks
that every query names only objects in `DatabaseSchema.kql`, the Activator wiring and the 0.90
threshold; `make kql-test` runs every dashboard and alert query and the loader on the emulator.
How U20 measures event-to-dashboard latency is in `plan.md` (PLAN-U14).
