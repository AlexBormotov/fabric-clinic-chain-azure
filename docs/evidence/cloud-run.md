# Cloud run evidence (U20)

The cloud seam of `spec.md`. U20 is complete when every item below has its evidence filled: a
file under [`cloud-run/`](cloud-run/) or a short captured value, plus the date. Steps refer to
[`docs/runbook-cloud.md`](../runbook-cloud.md). Local-seam criteria point at the CI run on `main`
that held at the time of the cloud run.

Format of a filled slot: `2026-11-0x — cloud-run/<file> — <one-line observation>`.

## Run facts

- [ ] **Home region** ("Your data is stored in", step 1.3; ADR 0006). Evidence:
- [ ] **Fabric trial** capacity name, region, size and end date (step 1.4). Evidence:
- [ ] **Azure subscription** type and tenant (step 1.5). Evidence:
- [ ] **Budget alert** set at $5 (step 1.6). Evidence:
- [ ] **CI on `main`** green at the commit deployed (link to the run). Evidence:

## Acceptance criteria (INT-001)

- [ ] **AC1 Synthetic estate** — local seam: `make test-slow` / CI `synth` job on the deployed
  commit. Evidence:
- [ ] **AC2 Batch path** — `pl_land_sources` run all green in Test (step 7.1); Silver
  reconciliation exported; Gold row counts equal the local `make gold` counts, every difference
  explained (step 7.2). Evidence:
- [ ] **AC3 Metrics** — report pages render (step 7.3); `gold.metric_summary` and
  `gold.metric_payer_mix` equal `metric-reference.json` within 1e-6 (step 7.2). Evidence:
- [ ] **AC4 Real time** — replay at 10–50 events/s with late and duplicate shares (summary JSON),
  Eventhouse counts match, live map shows it (step 8); latency reported per part, five runs (step 9).
  Evidence:
- [ ] **AC5 Alerting** — Teams channel post above 90% and the Activator history (step 10). Evidence:
- [ ] **AC6 Bed state history** — local seam: `tests/test_bed_history.py` in CI; `nb_bed_history`
  succeeded in the cloud pipeline (step 7.1). Evidence:
- [ ] **AC7 MPI** — local seam: [`mpi.json`](mpi.json); `nb_mpi` succeeded in the cloud pipeline.
  Evidence:
- [ ] **AC8 Data quality** — `nb_quality` in Fabric: 48 checks pass on Silver (step 7.1); local
  negative control (orphaned encounter) in CI. Evidence:
- [ ] **AC9 PHI protection** — masked view and CLS denial for `analyst`, clear values for
  `phi.reader`, clinic RLS for `clinic.boston`, OneLake denial on `patient_record` (step 12); model
  without PHI columns (CI `test_model_has_no_phi_columns`). Evidence:
- [ ] **AC10 Direct Lake fallback** — DirectQuery shown in Performance Analyzer, cause recorded
  (step 11). Evidence:
- [ ] **AC11 Capacity behaviour** — smoothing and throttling observed in the Capacity Metrics app
  (step 13). Evidence:
- [ ] **AC12 Delivery** — Dev Git-synced (step 5.3); Actions deploy to Test and Prod green (step 6);
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

- [ ] `terraform apply` creates workspaces, items and Azure sources on the trial; SQL database on
  the free offer (step 4.2). Evidence:
- [ ] Fabric CU quota in West Europe allows an F2 on this subscription (step 14). Evidence:
- [ ] F2 apply → destroy within one sitting, assigned to no workspace, start and end times (step 14).
  Evidence:
- [ ] Whether the Azure free credit covered the F2 meter (step 17, credits page). Evidence:

### PLAN-U19 Deployment

- [ ] OIDC client assertion accepted by Entra; no secret anywhere (step 6). Evidence:
- [ ] `$items` lookup resolves Terraform items (`lh_bronze`, `lh_silver`, `wh_gold`, `eh_beds`) in
  Test and Prod (step 6). Evidence:
- [ ] Dataflow `df_sharepoint` deployed by the service principal (the docs conflict) (step 6).
  Evidence:
- [ ] Pipeline runs of items owned by the service principal succeed when the owner starts them
  (step 7.1). Evidence:
- [ ] Dataflow SharePoint connection bound and destination set by hand; `make republish` works
  with device code (step 6). Evidence:

### PLAN-U12 Eventhouse model

- [ ] Eventstream Direct ingestion into `adt_raw` with mapping `adt_raw_json` (step 8). Evidence:
- [ ] Update policy fills `adt_event` with `ingested_at`; distinct `event_id` = rows of
  `events.csv` (step 8). Evidence:

### PLAN-U14 Live bed map and alert

- [ ] `nb_bed_reference` loaded the KQL `bed` table in the pipeline; `ward_occupancy()` non-empty
  (step 7.1, 8). Evidence:
- [ ] `rtd_beds` deployed with the cluster URI filled by fabric-cicd and renders (step 8). Evidence:
- [ ] `act_ward_occupancy` definition accepted on deploy, or the UI recipe used (say which)
  (step 6). Evidence:
- [ ] Action switched to Teams channel post in the UI (step 6). Evidence:
- [ ] Latency, five runs: event → Eventhouse and Eventhouse → dashboard, each part and the sum
  (step 9). Evidence:
- [ ] Alert fired on crossing 0.90; `bed` restored by `nb_bed_reference`; rule stopped (step 10).
  Evidence:

### PLAN-U16 Warehouse PHI protection

- [ ] `ALTER ROLE … ADD MEMBER` with an Entra group that has no database user yet (step 7.2).
  Evidence:
- [ ] `GRANT SELECT ON SCHEMA::` accepted by Fabric Warehouse (step 7.2). Evidence:
- [ ] `analyst` (`gold_reader`) is denied PHI columns; `phi.reader` sees clear values (step 12).
  Evidence:

### PLAN-U17 OneLake security and model RLS

- [ ] Terraform creates `DefaultReader` (overridden by name, or imported) and `PhiReader`
  (step 4.2). Evidence:
- [ ] ReadAll-only user reads `encounter`, is denied `patient_record` (Spark and OneLake API); a
  `PhiReader` member reads it (step 12). Evidence:
- [ ] Gold reload reads `silver.patient_record` through the SQL endpoint in delegated mode
  (step 7.2). Evidence:
- [ ] `clinic.boston` sees only Boston; `readmission_30d_rate` per clinic equals
  `gold.metric_summary` (step 12). Evidence:
- [ ] Redeploying the model keeps the `clinic` role member (step 12). Evidence:
- [ ] ADR 0005 experiment outcome, and the fixed identity used (step 7.3, 11). Evidence:

### PLAN-U10 Semantic model

- [ ] Measure values in the report equal the U09 reference (step 7.3). Evidence:

### Data residency (ADR 0006)

- [ ] Trial capacity, Blob, Azure SQL and F2 all in West Europe; home region recorded
  (steps 1.3, 1.4, 4.2, 14). Evidence:
