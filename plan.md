---
id: PLAN-U14
spec: SPEC-001 / U14
owner: AlexBormotov
status: approach A taken 2026-10-29 under the owner's standing go-ahead
previous: PLAN-U19 (#19), PLAN-U12 (#20), PLAN-U10 (#17), PLAN-U18 (#13), PLAN-U11 (#14); see git history of this file
---

# PLAN-U14 — Live bed map and alert

## Facts this plan rests on (read 2026-10-29)

- Real-Time Dashboard Git format (Learn "KQL Dashboard item definition", `ms.date` 2024-09-19):
  folder `<name>.KQLDashboard` with `.platform` and `RealTimeDashboard.json`, the dashboard file
  that the UI exports ("Create a Real-Time Dashboard", `ms.date` 2026-10-11).
- Its JSON schema is published per version at `https://dataexplorer.azure.com/static/d/schema/<v>/`
  (`dashboard.json` plus `tile`, `query`, `dataSource`, `parameter`, `baseQuery`, `embeddedApp`).
  The newest version served is 89 (90 returns HTML; `Last-Modified` 2026-10-04). Vendored under
  `tests/schemas/kql-dashboard-89/`.
  - A `kusto-trident` data source requires `clusterUri`, `databaseArtifactId`, `database` ("the
    Artifact ID of the database, duplicate of databaseArtifactId") and `workspace`.
  - A `table` tile requires `queryRef`; queries carry `dataSource.dataSourceId` and the KQL text.
  - Refresh: `autoRefresh` (`minInterval`/`defaultInterval` from `1s` … `1d`) and
    `changeDetection` (`liveUpdates`: `minRefreshRate` ≥ `10s`, `minRefreshRate_V2` ≥ `5s`,
    `fallbackRefreshRate` ≥ `30s`). Learn "Live refresh in Real-Time Dashboard" (`ms.date`
    2026-08-27): live refresh re-queries a visual when `ingestion_time()` of its data advances,
    else at the fallback interval; it is the default for new dashboards.
- Activator Git format (Learn "Reflex definition", `ms.date` 2026-02-26): folder `<name>.Reflex`
  with `.platform` and `ReflexEntities.json`, an array of entities (`container-v1`,
  `kqlSource-v1`, `timeSeriesView-v1` for events, objects, attributes and rules) whose
  `definition.instance` is a JSON string. Learn says the easiest valid instance is a UI-built one
  read back with Get Item Definition.
  - Learn shows `eventhouseItem.targetUniqueIdentifier`; Microsoft's `skills-for-fabric`
    (`activator-cli` authoring references, last commit 2026-09-10, "from working readback") uses
    `eventhouseItem: {itemId, workspaceId, itemType: "KustoDatabase"}` with `itemId` the KQL
    database, plus required `queryParameters` and `metadata`; snapshot mode (`queryParameters: []`)
    for a current-state query. `fabric-rti-mcp` (2026-07-16) uses a third shape. Three shapes in
    Microsoft sources: the format is not stable. Taken: `skills-for-fabric`.
  - Templates (`skills-for-fabric`, template version `1.2.4`): `SourceEvent`; `EventTrigger` =
    `FieldsDefaultsStep` (an `EventSelector` row) → `EventDetectStep` (`EventFieldSelector` +
    change condition such as `NumberBecomes`/`BecomesGreaterThan`) → `ActStep`. `SplitEvent`, the
    step that maps rows to per-object instances, has no published instance shape anywhere.
  - Teams action in the definition: only `TeamsMessage` to `recipients` (email addresses, i.e. a
    chat from the Activator bot). No documented definition shape for group chat or channel post.
- Activator from a KQL query (Learn "Create Activator alerts from KQL query results", `ms.date`
  2026-04-17): the UI action menu offers Teams "Message to individuals", "Group chat message" and
  "Channel post" (team and channel picked from drop-downs); default poll 5 minutes; queries every
  1–5 minutes keep the eventhouse always on. Rules overview (`ms.date` 2026-03-22): stateful
  `BECOMES` conditions fire only on entry into the state.
- fabric-cicd 1.4.0 (source, tag `v1.4.0`): publishes `KQLDashboard` and `Reflex` (publish order
  after `KQLDatabase`). For a dashboard data source with `clusterUri` `""`, it looks up the KQL
  database named by the data source `name` among deployed items and fills its query URI. Every
  text file gets, in order: dashboard processing, logical-ID replacement, `parameter.yml`
  (`key_value_replace`, then `find_replace`), default-workspace-ID replacement. The docs' "find_replace
  is not applied" for Activator does not match the 1.4.0 code. Dynamic attributes: `$id` for every
  type, `$queryserviceuri` only for `Eventhouse`. U19's `deploy.ITEM_TYPES` must list both new types.
- `notebookutils.credentials.getToken("kusto")` returns a Kusto token (Learn "NotebookUtils
  credentials", `ms.date` 2026-09-23). Kusto management commands go to `POST
  <query URI>/v1/rest/mgmt` with `{"db", "csl"}`; the emulator accepts the same without auth.
- The U12 gap: Fabric Git sync of `DatabaseSchema.kql` runs schema commands only, so nothing loads
  the `bed` reference table; `ward_occupancy()` is empty in Fabric until something does.

## Settings for every approach

- Dashboard `fabric/rtd_beds.KQLDashboard/`, schema 89, one data source `kqldb_beds`
  (`clusterUri` `""`, fabric-cicd fills it; IDs zero GUIDs bound by `parameter.yml`). Tiles:
  ward occupancy from `ward_occupancy()`, bed state from `bed` + `bed_current()` (a bed without
  events is free), and the newest event with its `ingested_at` for the latency check.
  Refresh: live refresh at the floors (`10s`, `5s` V2, fallback `30s`) and `autoRefresh` at `10s`.
- Bed reference load: notebook `nb_bed_reference` (default lakehouse `lh_silver`) reads Silver
  `bed`, sends one `.set-or-replace bed <| datatable(...)` to the KQL database with a `kusto`
  token, refuses an empty bed list. Pipeline `pl_land_sources` runs it after `run_nb_silver`.
  Locally the same code runs against the Kusto emulator.

## The choice: what goes to Git for the alert

### Approach A — hand-authored Reflex, minimal event graph, plus a manual channel step (taken)

`fabric/act_ward_occupancy.Reflex/` with container → `kqlSource-v1` (snapshot, every 60 s) →
`SourceEvent` → `EventTrigger` rule. The source query returns one row per poll:
`max_occupancy` over all wards and the top three wards as text; the threshold stays in the rule
(`NumberBecomes` `BecomesGreaterThan` 0.90), as Microsoft's guidance says. The action is a
`TeamsMessage` to a placeholder recipient (`alerts@example.com`, `$ENV:ALERT_TEAMS_RECIPIENT` at
deploy). A channel post cannot be expressed in the definition, so the owner switches the action to
"Channel post" in the UI once (README recipe).

- Files: `fabric/rtd_beds.KQLDashboard/{.platform,RealTimeDashboard.json}`,
  `fabric/act_ward_occupancy.Reflex/{.platform,ReflexEntities.json}`,
  `fabric/nb_bed_reference.Notebook/{.platform,notebook-content.py}`,
  `fabric/pl_land_sources.DataPipeline/pipeline-content.json`, `fabric/parameter.yml`,
  `src/clinic_chain/deploy.py` (item types, variable), `.github/workflows/deploy.yml`,
  `docker-compose.yml` (`ALERT_TEAMS_RECIPIENT`), `tests/test_live_map.py`,
  `tests/test_deploy.py` (placeholders, `$queryserviceuri`), `tests/schemas/kql-dashboard-89/`,
  `pyproject.toml`, `uv.lock` (`jsonschema`), `README.md`, `CLAUDE.md`, `tasks/todo.md`, `plan.md`.
- Invariants: every dashboard and alert query names only tables and functions in
  `DatabaseSchema.kql` and runs on the emulator; the alert fires above 0.90 and only on crossing;
  no workspace ID, recipient or channel is committed; a bed load replaces, never appends, and
  never empties the table.
- Red checks: fast tests (schema validation; references; threshold; Reflex reference integrity
  and template steps; loader command); `kusto` tests (dashboard and alert queries on the scenario;
  loader replaces `bed` twice to the same 7 rows); U19's coverage test for every placeholder.
- Limits accepted: one network-level stream, so a second ward crossing 0.90 while another ward is
  still above does not fire again (per-ward objects need `SplitEvent`, undocumented). The Reflex
  format may be rejected on first deploy; then the recipe below recreates the rule in the UI and
  the Dev workspace Git sync brings the service's own definition back into `fabric/`.
- Reverse: delete the three item folders, the activity, the rules and the test; drop the
  dependency and the two item types.

### Approach B — no Reflex in Git; queryset + UI-only alert

- Only a recipe. Smallest risk of a failed deploy, but nothing about the alert is versioned or
  testable, and spec U14 asks for both items in Git. Rejected.

### Approach C — per-ward objects (`SplitEvent` + `AttributeTrigger`)

- Per-ward transitions, the right semantics. Needs the `SplitEvent` instance shape, which no
  Microsoft source publishes; a guess fails at deploy time, not in tests. Rejected; revisit by
  reading back a UI-built rule in U20.

### Bed reference load, alternatives rejected

- External table or OneLake shortcut from KQL to `lh_silver.bed`: `.create external table` is not
  among the commands Git sync runs, so it would still need a post-deploy step, and shortcuts are
  created in the UI.
- Copy activity Lakehouse → KQL: append-only semantics to check per run, no local test.

## Negative controls

- Threshold 0.90 → 0.95 in `ReflexEntities.json`: the threshold test goes red. Restored.
- `ward_occupancy()` → `ward_occupancies()` in one dashboard query: the reference test and the
  emulator query test go red. Restored.
- Loader without the empty-list guard: the guard test goes red. Restored.

## U20 measurement: event to dashboard

1. Open `rtd_beds` (live refresh on) next to a terminal showing a UTC clock; record the screen.
2. Send one event: `date -u +%T.%N; make replay ARGS='--limit 1 --rate 10'` with
   `ADT_EVENTHUB_CONNECTION_STRING` set to the Eventstream custom endpoint. The printed time is the
   send time (the summary returns within the send).
3. Read `ingested_at` of that event on the "Newest event" tile and the recording time at which
   the tile first shows it. Event to Eventhouse = `ingested_at` − send time; Eventhouse to
   dashboard = tile time − `ingested_at`. Repeat 5 times (`--limit 1` sends the same event; clear
   nothing, `event_id` repeats are tolerated) and report each part and the sum.
4. Alert: run `.set-or-replace` on a copy of `bed` with one ward cut to fewer beds than occupied,
   or replay until a ward passes 0.90; screenshot the Teams post and the Activator history; restore
   `bed` by running `nb_bed_reference`. Stop the rule afterwards.
