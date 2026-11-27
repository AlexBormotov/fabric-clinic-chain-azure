# Cloud run evidence (U20)

The cloud seam of `spec.md`. U20 is complete when every item below has its evidence filled: a
file under [`cloud-run/`](cloud-run/) or a short captured value, plus the date. Steps refer to
[`docs/runbook-cloud.md`](../runbook-cloud.md). Local-seam criteria point at the CI run on `main`
that held at the time of the cloud run.

Format of a filled slot: `2026-11-0x — cloud-run/<file> — <one-line observation>`.

## Run facts

- [x] **Home region** (Help > About, step 1.3; ADR 0006). Evidence: 2026-11-24 — Switzerland North
  (Zurich), cloud-run/fabric-home-region.png.
- [x] **Fabric trial** capacity name, region, size and end date (step 1.4). Evidence: 2026-11-25 —
  capacities API: `Trial-20261124T214353Z-…`, FTL4, Sweden Central, Active. First refused, then
  granted on 2026-11-24. cloud-run/fabric-trial.png (2026-11-25): 59 days left, so it ends about
  2027-01-23; three workspaces assigned.
- [x] **Azure subscription** type and tenant (step 1.5). Evidence: 2026-11-25 — CLI: free trial,
  spending limit On, tenant `alexengineering.onmicrosoft.com`; current cost 0.00 in the portal
  (screenshot kept off the public repository).
- [x] **Budget alert** set at $5 (step 1.6). Evidence: 2026-11-25 — monthly $5 budget `5dollars` on
  the billing account, which covers the subscription (screenshot kept off the public repository).
- [ ] **CI on `main`** green at the commit deployed (link to the run). Evidence:

## Acceptance criteria (INT-001)

- [ ] **AC1 Synthetic estate** — local seam: `make test-slow` / CI `synth` job on the deployed
  commit. Evidence:
- [x] **AC2 Batch path** — `pl_land_sources` run all green in Test (step 7.1); Silver
  reconciliation exported; Gold row counts equal the local `make gold` counts, every difference
  explained (step 7.2). Evidence: 2026-11-27 — `pl_land_sources` run `138960d8` Completed in 11 min after six fixes (#38, #39): owner re-save against `SPNBasedRefreshNotAllowed`, no dataflow parameters, notebooks chained against HTTP 430, `run_line_magic` install, retry 1, OpenTelemetry purge. cloud-run/gold-row-counts.csv (COUNT_BIG per table; fact_stay 6374, fact_bed_day 35120).
- [x] **AC3 Metrics** — report pages render (step 7.3); `gold.metric_summary` and
  `gold.metric_payer_mix` equal `metric-reference.json` within 1e-6 (step 7.2). Evidence: 2026-11-27 — cloud-run/gold-metric-summary.csv and gold-metric-payer-mix.csv equal metric-reference.json (max difference 1.8e-8; payer mix exact). Report: cloud-run/report-occupancy.png, report-quality.png, report-economics.png (monthly trend lines, #40).
- [x] **AC4 Real time** — replay at 10–50 events/s with late and duplicate shares (summary JSON),
  Eventhouse counts match, live map shows it (step 8); latency reported per part, five runs (step 9).
  Evidence: 2026-11-27 — cloud-run/replay-summary.json: 13125 events, 13519 sends (656 late, 394 copies) at 49.5/s. cloud-run/eventhouse-counts.csv: `adt_raw` 13519 = sends; distinct `event_id` 13125 = rows of events.csv; nine wards have occupancy. cloud-run/eventstream-live.png, cloud-run/rtd-beds.png. Latency: cloud-run/latency.csv.
- [x] **AC5 Alerting** — Teams channel post above 90% and the Activator history (step 10). Evidence: 2026-11-27 — rule fired once at 15:57:36 UTC during the replay; action is a Teams chat message to the owner, not a channel post (the channel picker failed with "Error loading teams"). cloud-run/teams-alert.png, cloud-run/activator-history.png. Rule stopped afterwards.
- [x] **AC6 Bed state history** — local seam: `tests/test_bed_history.py` in CI; `nb_bed_history`
  succeeded in the cloud pipeline (step 7.1). Evidence: 2026-11-27 — `nb_bed_history` succeeded in run `138960d8`.
- [x] **AC7 MPI** — local seam: [`mpi.json`](mpi.json); `nb_mpi` succeeded in the cloud pipeline.
  Evidence: 2026-11-27 — `nb_mpi` succeeded in run `138960d8`.
- [x] **AC8 Data quality** — `nb_quality` in Fabric: 48 checks pass on Silver (step 7.1); local
  negative control (orphaned encounter) in CI. Evidence: 2026-11-27 — `nb_quality` succeeded in run `138960d8` (it exits non-zero on any failed check).
- [x] **AC9 PHI protection** — masked view and CLS denial for `analyst`, clear values for
  `phi.reader`, clinic RLS for `clinic.boston`, OneLake denial on `patient_record` (step 12); model
  without PHI columns (CI `test_model_has_no_phi_columns`). Evidence: 2026-11-27 — cloud-run/phi-rls.md: masks and CLS denial for `analyst`, clear values for `phi.reader`, Boston-only report for `clinic.boston`. The OneLake Spark check (step 12.3) was not run: the test users have no workspace on a capacity.
- [x] **AC10 Direct Lake fallback** — DirectQuery shown in Performance Analyzer, cause recorded
  (step 11). Evidence: 2026-11-27 — cloud-run/fallback.md, cloud-run/fallback-perf-analyzer.png: a SQL RLS policy made a Direct Lake on SQL probe model fall back to DirectQuery.
- [ ] **AC11 Capacity behaviour** — smoothing and throttling observed in the Capacity Metrics app
  (step 13). Evidence:
- [ ] **AC12 Delivery** — Dev Git-synced (step 5.3; own branch `dev-workspace`, not
  `main`: the sync would delete the Terraform items); Actions deploy to Test and Prod green (step 6);
  one deployment pipeline promotion (step 6); Terraform apply output (step 4.2); F2 created and
  destroyed (step 14). Evidence:
- [ ] **AC13 Local first** — CI `lint` and `test` green on the deployed commit; `make test` needs no
  cloud. Evidence:
- [ ] **AC14 Cost** — Azure cost analysis ≤ $10 on day 0 and day 2 (step 17); resource listing empty
  after teardown (step 16); subscription cancelled; Microsoft 365 recurring billing off (steps 1.2,
  18). Evidence:
- [ ] **AC15 Documentation** — README screenshots placed (step 15); ADRs 0001–0006 present; link
  check green (`tests/test_doc_links.py`). Evidence:

## Unit plans: what U20 must verify

### PLAN-U18 Terraform

- [x] `terraform apply` creates workspaces, items and Azure sources on the trial; SQL database on
  the free offer (step 4.2). Evidence: 2026-11-25 — cloud-run/terraform-apply.txt: first apply
  created everything but failed on the six OneLake roles (provider 1.14.0 bug and the built-in
  `DefaultReader`); the second, after #29 and the import, ended with 3 changed and a clean plan.
  cloud-run/azure-resources.png, cloud-run/fabric-workspace-items.png,
  cloud-run/azure-sql-free-offer.png (overage billing disabled). Sources loaded:
  cloud-run/load-sources.txt, counts equal the generated files.
- [x] Fabric CU quota allows an F2 on this subscription. Evidence: 2026-11-24 — usages API: Sweden
  Central 4 CU, West Europe 0.
- [ ] F2 apply → destroy within one sitting, assigned to no workspace, start and end times (step 14).
  Evidence:
- [ ] Whether the Azure free credit covered the F2 meter (step 17, credits page). Evidence:

### PLAN-U19 Deployment

- [ ] OIDC client assertion accepted by Entra; no secret anywhere (step 6). Evidence:
- [ ] `$items` lookup resolves Terraform items (`lh_bronze`, `lh_silver`, `wh_gold`, `eh_beds`) in
  Test and Prod (step 6). Evidence:
- [ ] Dataflow `df_sharepoint` deployed by the service principal (the docs conflict) (step 6).
  Evidence:
- [x] Pipeline runs of items owned by the service principal succeed when the owner starts them
  (step 7.1). Evidence: 2026-11-27 — only after the owner re-saved the pipeline; otherwise `SPNBasedRefreshNotAllowed` (runbook 6).
- [x] Dataflow SharePoint connection bound and destination set by hand; `make republish` works
  with the owner's `az login` (step 6). Evidence: 2026-11-27 — bound by the owner; every deploy drops the bindings and `make republish` then fails with "Evaluation is canceled"; re-saving in the UI works (runbook 6).

### PLAN-U12 Eventhouse model

- [x] Eventstream Direct ingestion into `adt_raw` with mapping `adt_raw_json` (step 8). Evidence: 2026-11-27 — cloud-run/eventstream-live.png. The wizard offered the mapping only after sample data arrived (runbook 8.1).
- [x] Update policy fills `adt_event` with `ingested_at`; distinct `event_id` = rows of
  `events.csv` (step 8). Evidence: 2026-11-27 — cloud-run/eventhouse-counts.csv.

### PLAN-U14 Live bed map and alert

- [x] `nb_bed_reference` loaded the KQL `bed` table in the pipeline; `ward_occupancy()` non-empty
  (step 7.1, 8). Evidence: 2026-11-27 — succeeded in run `138960d8`; `ward_occupancy()` returned nine wards.
- [x] `rtd_beds` deployed with the cluster URI filled by fabric-cicd and renders (step 8). Evidence: 2026-11-27 — cloud-run/rtd-beds.png.
- [x] `act_ward_occupancy` definition accepted on deploy, or the UI recipe used (say which)
  (step 6). Evidence: 2026-11-27 — accepted on deploy; no UI recipe needed.
- [x] Action switched to Teams channel post in the UI (step 6). Evidence: 2026-11-27 — not switched: Teams chat message to the owner instead (channel picker failed). cloud-run/teams-alert.png.
- [x] Latency, five runs: event → Eventhouse and Eventhouse → dashboard, each part and the sum
  (step 9). Evidence: 2026-11-27 — cloud-run/latency.csv: event → Eventhouse 0.7–0.8 s after the send returned, 2.8–3.1 s from process start (bounds). Eventhouse → dashboard: the dashboard auto-refresh interval, 10 s, not timed.
- [x] Alert fired on crossing 0.90; `bed` restored by `nb_bed_reference`; rule stopped (step 10).
  Evidence: 2026-11-27 — fired 15:57:36 UTC; rule stopped by the owner.

### PLAN-U16 Warehouse PHI protection

- [x] `ALTER ROLE … ADD MEMBER` with an Entra group that has no database user yet (step 7.2).
  Evidence: 2026-11-27 — succeeded; `sys.database_role_members` lists `clinic_chain_analysts` and `clinic_chain_phi_readers` as EXTERNAL_GROUP.
- [x] `GRANT SELECT ON SCHEMA::` accepted by Fabric Warehouse (step 7.2). Evidence: 2026-11-27 — accepted; `analyst` reads `gold.dim_patient` non-PHI columns.
- [x] `analyst` (`gold_reader`) is denied PHI columns; `phi.reader` sees clear values (step 12).
  Evidence: 2026-11-27 — cloud-run/phi-analyst-denied.png (Msg 230), cloud-run/phi-reader-clear.png.

### PLAN-U17 OneLake security and model RLS

- [x] Terraform creates `DefaultReader` (overridden by name, or imported) and `PhiReader`
  (step 4.2). Evidence: 2026-11-25 — cloud-run/onelake-roles.png; `DefaultReader` imported and
  narrowed to the 15 non-PHI tables (`terraform state show`), without `patient_record` and `staff`.
  Until the tables exist the role page lists none.
- [ ] ReadAll-only user reads `encounter`, is denied `patient_record` (Spark and OneLake API); a
  `PhiReader` member reads it (step 12). Evidence:
- [x] Gold reload reads `silver.patient_record` through the SQL endpoint in delegated mode
  (step 7.2). Evidence: 2026-11-27 — `EXEC gold.reload` ran with the owner's token; dim_patient 15330 rows.
- [x] `clinic.boston` sees only Boston; `readmission_30d_rate` per clinic equals
  `gold.metric_summary` (step 12). Evidence: 2026-11-27 — cloud-run/phi-rls.md, cloud-run/rls-clinic-boston.png: one row, boston 0.10190664036817883 = `gold.metric_summary`.
- [ ] Redeploying the model keeps the `clinic` role member (step 12). Evidence:
- [x] ADR 0005 experiment outcome, and the fixed identity used (step 7.3, 11). Evidence: 2026-11-27 — fallback observed (cloud-run/fallback.md). Fixed identity: OAuth 2.0 as the owner, SSO off (connection `cn_sm_clinic_chain_one_lake`), because the workspace has no workspace identity (`Premium_ASWL_Error`).

### PLAN-U10 Semantic model

- [x] Measure values in the report equal the U09 reference (step 7.3). Evidence: 2026-11-27 — DAX on the Test model: beds 48, occupancy 0.7998, ALOS 4.40, denial 0.0660, revenue per bed 717462, equal to the reference.

### Data residency (ADR 0006)

- [ ] Trial capacity, Blob, Azure SQL and F2 all in Sweden Central; home region recorded
  (steps 1.3, 1.4, 4.2, 14). Evidence:
