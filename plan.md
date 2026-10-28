---
id: PLAN-U12
spec: SPEC-001 / U12
owner: AlexBormotov
status: approach A taken 2026-10-29 under the owner's standing go-ahead
previous: PLAN-U11 (#14), PLAN-U15 (#12), PLAN-U09 (#16), PLAN-U13 (#15); see git history of this file
---

# PLAN-U12 — Eventhouse model

## Facts this plan rests on (read 2026-10-29)

- Kusto emulator (Learn "Install the Azure Data Explorer Kusto emulator", `ms.date` 2026-07-23;
  "Kusto emulator overview", `ms.date` 2025-12-11):
  - Linux image `mcr.microsoft.com/azuredataexplorer/kustainer-linux`; docs say use `latest` or
    `stable`. MCR tag list has no `stable`; `latest` (digest `046cae99…`) is the master build
    `2026.10.28.1608-2643-05affc6-master`, so it moves daily. Pinned:
    `2026.10.13.0655-2640-482fe45-weeklyproduction` (digest `6cc5f566…`, 16 days old, 4.5 GB).
  - `ACCEPT_EULA=Y`; at least 2 GB RAM, 4 GB recommended (docs run it with `-m 4G`); x64 with
    SSE4.2/AVX2, no ARM; HTTP only on port 8080, no auth, no HTTPS.
  - Readiness: `POST /v1/rest/mgmt` with `.show cluster` returns 200.
  - Limits: no managed (queued) ingestion, no Event Hubs/IoT Hub/Event Grid connectors, no
    streaming ingestion, no ingest endpoint; ingestion only by commands (`.ingest`, `.set`,
    `.append`, from files or inline); no extent merge; retention and partitioning policies are
    accepted but not honoured; no Python plugin. Update policies are not listed as a limit.
- `azure-kusto-data` on PyPI: latest 6.0.4, uploaded 2026-05-06.
- Fabric Git format for a KQL database (Learn "Eventhouse and KQL database - Git integration",
  updated 2026-02-17; "KQL Database item definition", 2024-11-12): folder `<name>.KQLDatabase`
  with `.platform` (type `KQLDatabase`), `DatabaseProperties.json` (`databaseType` `ReadWrite`,
  `parentEventhouseItemId` = logical ID of the parent eventhouse, `oneLakeCachingPeriod`,
  `oneLakeStandardStoragePeriod`) and `DatabaseSchema.kql`, a database script run on sync that
  may contain only: `.create-merge table`, `.create-or-alter function`, `.alter table … policy
  update`, `.alter … encoding policy`, `.create-or-alter materialized-view`, `.create-or-alter
  table … ingestion mapping`. No data commands.
- Eventstream → Eventhouse (Learn "Add an Eventhouse destination", updated 2026-02-17): in
  *Direct ingestion* mode the Get data wizard picks an existing table, format JSON and, under
  Advanced, an existing mapping. *Event processing before ingestion* maps columns itself.
- Terraform (`origin/u18-terraform`, `infra/modules/fabric/main.tf`): creates eventhouse
  `eh_beds`, whose default KQL database is also named `eh_beds`; code items come from Git via
  `fabric-cicd` (U19).
- Wire format (`src/clinic_chain/adt_replay.py`): the body is the contract row as JSON,
  `event_id` an int, `event_time` `"YYYY-MM-DD HH:MM:SS"`, empty fields `null`; copies repeat
  `event_id`; late events arrive after an event with a later `event_time`.
- Batch semantics (`fabric/nb_bed_history.Notebook`): A01/A02 occupy `bed_id`, A02 frees
  `from_bed_id`, A03 frees `bed_id`; per bed, changes order by `event_time`, then free before
  occupied, then `event_id`; duplicates by `event_id` collapse.

## Settings for every approach

- Item `fabric/kqldb_beds.KQLDatabase/` (child of Terraform's `eh_beds`; a distinct name avoids
  colliding with its default database). `parentEventhouseItemId` is a zero GUID placeholder, as the
  notebooks do for lakehouse IDs; U19 binds it to `eh_beds`.
- `adt_raw (payload:dynamic)` with JSON mapping `adt_raw_json` (`$` → `payload`); the Eventstream
  destination uses Direct ingestion with that table and mapping. A schema change in the producer
  never fails ingestion.
- Update policy (transactional) `adt_parse()` → `adt_event` with the contract columns plus
  `ingested_at = ingestion_time()` for the latency measurement in U14.
- `bed` reference table: the SharePoint beds sheet (contract `sharepoint.beds`, Silver table
  `bed`). It is data, so not in the schema script; in Fabric it is loaded from `lh_silver.bed`
  (U14/U20). A bed without events counts as free.
- `bed_changes()`, `bed_current()` (`arg_max` per bed), `ward_occupancy()` (beds and occupied
  beds per ward from `bed`, `occupancy` = occupied / beds, rounded to 4 places). The dashboard and
  the Activator rule (U14) read `ward_occupancy()`.

## The choice: how current state is kept

### Approach A — query-time `arg_max` over all events (taken)

`bed_current()` takes `arg_max` per bed over every change. One key encodes the batch order:
`(seconds since 2000 * 2 + occupied) * 10^9 + event_id`.

- Files: `fabric/kqldb_beds.KQLDatabase/{.platform,DatabaseProperties.json,DatabaseSchema.kql}`,
  `tests/test_kql.py`, `docker-compose.yml` (`kusto`), `Makefile` (`kql-test`),
  `.github/workflows/ci.yml` (`kql` job), `pyproject.toml`, `uv.lock`, `README.md`, `CLAUDE.md`,
  `plan.md`.
- Invariants: arrival order never matters; a copy never double counts; the current state per bed
  equals the open interval of `nb_bed_history` for the same events; the script holds only commands
  Fabric sync accepts; `adt_event` columns equal the contract.
- Red checks: `kusto` tests (four arrival orders against one expected state and occupancy);
  fast tests (allowed commands, columns vs contracts, references, update policy and mapping,
  item files, scenario vs the Spark notebook).
- Limits accepted: the key needs whole-second times before 2136 and `event_id` < 10^9 (contract
  times are whole seconds; 13,125 events today). Query cost grows with history; at ~13k events
  per 2 years it is negligible.
- Reverse: delete the item folder, the test, the compose service, the Makefile target and the CI
  job; drop the dependency.

### Approach B — materialized view `arg_max` per bed

- Same answer, maintained incrementally. But the view would need one row per bed from a `union`
  of three projections, which a materialized view source cannot be (single table, single
  `summarize`); a second update policy into a `bed_change` table would fix that at the cost of
  another table. Materialized view behaviour on the emulator is unverified, and the size does
  not need it. Rejected.

### Approach C — order by arrival (`ingestion_time()`)

- Simplest, and wrong: a late discharge after a readmission would free an occupied bed. Rejected.

## Negative control

Swap `arg_max` for `arg_min` in `bed_current()`: the `kusto` tests must go red, then restore.

## Implementation notes

- `make kql-test`, 2026-10-29: 5 `kusto` tests pass in 5–10 s; from `docker compose up` to tests
  done 8 s wall (image already pulled); emulator memory after the run 259 MiB of the 4 GiB cap.
- Measured on the emulator (no workaround needed): `.create database … volatile`,
  `.execute database script` on `DatabaseSchema.kql` as committed (comments included), the
  transactional update policy firing on `.ingest inline … with (format='json',
  ingestionMappingReference=…)`, and `ingestion_time()` inside the policy query. So the completion
  test exercises the real raw → typed path, not the functions alone.
- Emulator limits that stay untested here: no streaming or queued ingestion and no Event Hubs
  data connection, so Eventstream → `adt_raw` and the latency are cloud checks (U14/U20).
- Scenario: 9 events over 7 reference beds in 3 wards (one ward without events). In-order, late
  (3 before 2, 5 before 4, 7 before 6), duplicate (4 copies) and reversed arrival all give the
  same current state and occupancy ICU 1/2, MED 3/4, SURG 0/1; `adt_event` keeps every send.
  A fast test runs the same events through `nb_bed_history` and gets the same current state.
- Negative controls: `arg_min` for `arg_max` turns all four arrival orders red; flipping the
  occupied bit (`iff(occupied, 0, 1)`) turns them red on BOS-MED-01 (free instead of S3 at the
  shared instant). Restored; green.
- Marker `kusto`, not `stand`: `make test-stand` runs after `make up`, and the emulator must not
  share this host with the source stand, so its tests get their own target and CI job `kql`
  (optional, like `stand`).
- `make lint`, `make test` (65 passed) green. In a worktree `make secrets` scans 0 commits; the
  changed paths passed `gitleaks dir`.
- Docker Desktop crashed once mid-run (WSL bootstrap error, with the emulator not running) and
  left this worktree's `ivy-cache` volume with broken Delta jars; the volume was removed and
  rebuilt.
