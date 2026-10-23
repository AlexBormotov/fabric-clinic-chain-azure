---
id: SPEC-001
requirement: INT-001
owner: AlexBormotov
status: approved by owner 2026-10-21 (open points 1-3 accepted as proposed)
---

# SPEC-001 — Work units for INT-001

Acceptance criteria are referenced by identifier (`INT-001/AC<n>`) and are never reworded here; the
text lives in `intent.md` only. Each unit below states the criteria it serves, what it is blocked by,
its completion condition, the seam where that condition is checked, and its routing.

Two seams exist, agreed once for all units:

- **Local seam:** `make test` (and CI running the same target). Every unit that can be verified
  without Fabric is checked here.
- **Cloud seam:** `docs/evidence/cloud-run.md`, an evidence checklist filled during the single cloud
  run (U20), each item with a screenshot or captured output. Units whose criteria cannot be
  checked locally contribute a checklist item instead of a local test.

Verification of the claim: not applicable for every unit (new work); each cites INT-001.

## Coverage

| Criterion | Units |
|---|---|
| INT-001/AC1 | U02, U03 |
| INT-001/AC2 | U04, U05, U06, U08, U20 |
| INT-001/AC3 | U09, U10, U20 |
| INT-001/AC4 | U11, U12, U14, U20 |
| INT-001/AC5 | U14, U20 |
| INT-001/AC6 | U13 |
| INT-001/AC7 | U07 |
| INT-001/AC8 | U15 |
| INT-001/AC9 | U16, U17, U20 |
| INT-001/AC10 | U20 |
| INT-001/AC11 | U20 |
| INT-001/AC12 | U18, U19, U20 |
| INT-001/AC13 | U01 and every unit with a local seam |
| INT-001/AC14 | U20 |
| INT-001/AC15 | U21 |

## Slice 0 — Foundation

### U01 Repository scaffolding
- **Serves:** AC13.
- **Blocked by:** none.
- **Scope:** `pyproject.toml` (uv), `Makefile` (`setup`, `lint`, `test`, `up`, `down`), ruff, pytest,
  sqlfluff (T-SQL dialect), `docker-compose.yml` skeleton, `.env.example`, `.github/workflows/ci.yml`
  (separate lint, test and gitleaks jobs, each calling a make target), `.github/CODEOWNERS`,
  `REVIEW.md`, README skeleton.
- **Completion:** `make lint test` green locally and in CI on `main`; a deliberately committed fake
  secret on a throwaway branch fails the gitleaks job (negative control).
- **Routing:** agent.

## Slice 1 — Batch path

### U02 Synthea population
- **Serves:** AC1.
- **Blocked by:** U01.
- **Scope:** Synthea in Docker with a fixed seed; three clinics mapped to three cities; FHIR R4
  bundles written to `data/raw/fhir/` (git-ignored).
- **Completion:** `make synth` is deterministic (same seed → identical file hashes, `metadata/`
  excluded) and a test asserts 300, 400 and 500 patients per clinic, no encounter after 2026-09-30,
  and encounters inside the window 2024-10-01 … 2026-09-30 for every clinic. Synthea keeps older
  history linked to active conditions; the window is applied downstream (PLAN-U02, option 3a,
  approved 2026-10-22).
- **Routing:** agent.

### U03 Source derivation and noise
- **Serves:** AC1.
- **Blocked by:** U02.
- **Scope:** from the FHIR output, derive billing and claims (SQL Server schema), lab CSV, ADT history
  (admission, transfer, discharge, with ward and bed), Excel staff rosters and bed reference; per-system
  local patient IDs; noise per AC1; ED arrival and triage timestamps (Synthea has none) generated from
  emergency encounters; ground-truth link table. Source schemas are written to `docs/contracts/`.
  Referred inpatients (not in FHIR or lab) are added to ADT and billing to reach a configured ward
  occupancy (PLAN-U03 approach B, approved 2026-10-23).
- **Completion:** tests assert every noisy record resolves through ground truth, each noise rate is
  within ±1 percentage point of its configured value, and outputs match the contract schemas.
- **Routing:** agent.

### U04 Local source stand
- **Serves:** AC2, AC13.
- **Blocked by:** U03.
- **Scope:** docker compose services: SQL Server 2022 (billing source, loaded from U03), Azurite
  (Blob emulator holding `fhir/`, `lab/` and the ADT system's export `adt/`), a folder standing in
  for SharePoint (amended 2026-10-23, PLAN-U04).
- **Completion:** `make up && make test-stand` reads back source row counts equal to U03 output; the
  stand tests carry a `stand` marker and are excluded from `make test`, which must pass without
  running services (AC13). CI job `stand` runs them (amended 2026-10-23, PLAN-U04).
- **Routing:** agent.

### U05 Bronze
- **Serves:** AC2.
- **Blocked by:** U04.
- **Scope:** PySpark notebooks kept as importable `.py` modules (Fabric notebook format in Git) that
  land each source as Delta in Bronze with ingestion metadata; Data Pipeline definitions for Blob and
  SQL copies (cloud-only, deployed in U19).
- **Completion:** local Spark 4.1 + Delta tests: Bronze row counts equal source row counts per source.
- **Routing:** agent.

### U06 Silver
- **Serves:** AC2.
- **Blocked by:** U05.
- **Scope:** FHIR flattening; conformed patients, encounters, conditions, medications, lab results,
  claims, ADT; type casting, deduplication of exact duplicates; MPI identifiers joined in from U07.
- **Completion:** tests on fixtures for each table; reconciliation report Bronze → Silver with every
  dropped row counted by reason.
- **Routing:** agent.

### U07 Master patient index
- **Serves:** AC7.
- **Blocked by:** U05.
- **Scope:** PySpark matching: blocking on (birth year, surname soundex), Jaro-Winkler and exact-field
  agreement scoring, auto-match threshold, review band. ADR on the approach (Splink as next step).
- **Completion:** `make mpi-eval` writes precision and recall against ground truth to
  `docs/evidence/mpi.json`; a test fails if precision < 0.98 or recall < 0.95 (owner to confirm
  thresholds at spec approval).
- **Routing:** agent; thresholds are the owner's decision.

### U08 Gold star schema
- **Serves:** AC2.
- **Blocked by:** U06, U07.
- **Scope:** Warehouse T-SQL: dimensions (date, clinic, ward, bed, patient, payer, diagnosis) and facts
  (encounter, bed-day, claim, lab result, ED visit); load from Silver. Locally against SQL Server;
  T-SQL kept to the Fabric Warehouse surface, with differences listed in the Lakehouse/Warehouse ADR.
- **Completion:** reconciliation test source → Gold with every difference explained; sqlfluff clean.
- **Routing:** agent.

### U09 Metric definitions and reference values
- **Serves:** AC3.
- **Blocked by:** U03.
- **Scope:** definitions of the eight metrics written to `GLOSSARY.md`; an independent computation
  (pandas, straight from generator output, not from Gold) producing `docs/evidence/metric-reference.json`.
- **Completion:** owner approves the definitions; a test compares Gold-based SQL metric queries to the
  reference values with a stated tolerance.
- **Routing:** person approves definitions (judgement call); agent implements.

### U10 Semantic model and report
- **Serves:** AC3.
- **Blocked by:** U08, U09.
- **Scope:** PBIP/TMDL in Git: Direct Lake on OneLake over Gold without PHI columns, DAX measures for
  the eight metrics, RLS role by clinic, one report page per contour (occupancy, quality, economics).
- **Completion (local):** TMDL parses and no PHI column is present (scripted check). Measure values are
  checked in the cloud run against U09.
- **Routing:** agent writes; person opens it in Power BI Desktop once (manual check).

## Slice 2 — Real time

### U11 ADT replay producer
- **Serves:** AC4.
- **Blocked by:** U03.
- **Scope:** Python producer replaying ADT history with time acceleration, rate 10–50 events/s,
  configurable share of late and duplicate events; Event Hubs protocol (emulator locally, Eventstream
  custom endpoint in the cloud).
- **Completion:** test against the Event Hubs emulator: all events received, achieved rate within ±10%
  of target, late and duplicate shares within ±1 percentage point.
- **Routing:** agent.

### U12 Eventhouse model
- **Serves:** AC4.
- **Blocked by:** U11.
- **Scope:** KQL tables, ingestion mapping, update policy, current bed state via `arg_max`, ward
  occupancy function used by the dashboard and the Activator rule.
- **Completion:** KQL tests against the Kusto emulator: the current-state function returns the
  expected state for scripted event sequences, including late and duplicate events.
- **Routing:** agent.

### U13 Bed state history (SCD2)
- **Serves:** AC6.
- **Blocked by:** U06, U11.
- **Scope:** PySpark merge building SCD2 bed state history in Silver ordered by event time, re-splitting
  intervals when a late event arrives.
- **Completion:** tests for in-order, late, duplicate and out-of-order sequences produce the expected
  intervals with no gaps or overlaps.
- **Routing:** agent.

### U14 Live bed map and alert
- **Serves:** AC4, AC5.
- **Blocked by:** U12.
- **Scope:** Real-Time dashboard (KQLDashboard item), Activator rule (Reflex item) posting to a Teams
  channel above 90% ward occupancy, both kept in Git for `fabric-cicd`.
- **Completion:** cloud seam items: measured event-to-dashboard latency, and the Teams message
  screenshot.
- **Routing:** agent writes; verified in U20.

## Slice 3 — Quality and security

### U15 Data quality
- **Serves:** AC8.
- **Blocked by:** U06.
- **Scope:** Soda v4 (`soda-sparkdf`) checks on Silver, including patient ↔ encounter referential
  integrity; ADR on making it work on Runtime 2.0.
- **Completion:** local run on PySpark 4.1 passes on clean fixtures and fails on a fixture with one
  orphaned encounter (negative control). The same check runs in a Fabric notebook in U20.
- **Routing:** agent.

### U16 Warehouse PHI protection
- **Serves:** AC9.
- **Blocked by:** U08.
- **Scope:** dynamic data masking and column-level security on PHI columns, roles for privileged and
  non-privileged readers.
- **Completion:** local test on SQL Server: the non-privileged login sees masked values and is denied
  CLS-protected columns; the privileged login sees clear values.
- **Routing:** agent.

### U17 OneLake security and model RLS
- **Serves:** AC9.
- **Blocked by:** U10.
- **Scope:** OneLake data access roles for the Lakehouse; RLS role membership for clinic users; ADR on
  Direct Lake versus PHI security, including the planned fallback experiment.
- **Completion:** cloud seam items: a clinic-scoped user sees only their clinic; a user outside the
  OneLake role cannot read Silver PHI tables.
- **Routing:** agent writes; verified in U20.

## Slice 4 — Delivery and infrastructure

### U18 Terraform
- **Serves:** AC12.
- **Blocked by:** U01.
- **Scope:** modules `azure-sources` (Blob storage, Azure SQL free offer, firewall), `fabric`
  (three workspaces, items that Terraform owns, Git integration for Dev, deployment pipeline) and
  `capacity` (F2, `azurerm_fabric_capacity`); remote state is not required (single operator), state
  is git-ignored.
- **Completion:** `terraform fmt -check`, `terraform validate` and `tflint` green in CI.
- **Routing:** agent.

### U19 Deployment automation
- **Serves:** AC12.
- **Blocked by:** U05, U18.
- **Scope:** `fabric-cicd` deploy script with `parameter.yml` for environment-specific values;
  GitHub Actions workflow deploying to Test and Prod with a service principal; republish step for
  Dataflows Gen2 after deploy; ADR on fabric-cicd versus deployment pipelines.
- **Completion:** `actionlint` clean; unit test that `parameter.yml` resolves every placeholder for
  each environment. Live deploy verified in U20.
- **Routing:** agent.

## Cloud run

### U20 Single cloud run
- **Serves:** AC2, AC3, AC4, AC5, AC9, AC10, AC11, AC12, AC14.
- **Blocked by:** every unit above.
- **Scope:** runbook `docs/runbook-cloud.md`: create accounts in the order of the intent's
  constraints; Terraform apply; deploy; run pipelines; replay ADT; measure latency; trigger the alert;
  run the Direct Lake fallback experiment (model on SQL endpoint with Warehouse RLS); observe smoothing
  and throttling in the capacity metrics app; apply and destroy F2; take screenshots; tear everything
  down; check spend.
- **Completion:** every item in `docs/evidence/cloud-run.md` filled with evidence; Azure cost analysis
  shows ≤ $10; resource listing after teardown is empty; Microsoft 365 recurring billing shown off.
- **Routing:** person, with the agent assisting: external accounts, payment details and spend are not
  delegated.

### U21 Documentation
- **Serves:** AC15.
- **Blocked by:** U20.
- **Scope:** README (architecture diagram, local run, cloud runbook link, screenshots, the accelerated
  ADT replay explained, results), ADRs in `docs/adr/`.
- **Completion:** every ADR named in AC15 exists with context, decision and consequences; every link
  and image in the README resolves (scripted check).
- **Routing:** agent; owner reviews.

## Open points for approval

1. MPI thresholds in U07: precision ≥ 0.98, recall ≥ 0.95.
2. Live latency is reported, not gated (AC4 says "within seconds"); proposed reporting target p95 ≤ 10 s.
3. Metric definitions (U09) are approved separately once written.
