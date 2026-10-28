---
id: PLAN-U10
spec: SPEC-001 / U10
owner: AlexBormotov
status: approach A taken 2026-10-28 under the owner's standing go-ahead
previous: PLAN-U18 (#13), PLAN-U11 (#14), PLAN-U15 (#12), PLAN-U09 (#16); see git history of this file
---

# PLAN-U10 — Semantic model and report

## Facts this plan rests on

All read 2026-10-28.

- **PBIP semantic model folder** (Learn "Power BI Desktop project semantic model folder", dated
  2026-09-23): `definition.pbism` is required; `version` 4.0 or above allows TMDL in a `definition\`
  folder instead of `model.bim`; `.platform` links the item to Fabric Git integration.
- **PBIP report folder** (Learn "Power BI Desktop project report folder", dated 2026-09-23): PBIR is
  generally available and the default; Fabric Git integration exports PBIR. `definition.pbir`
  (`version` 4.0, `datasetReference.byPath`) and a `definition\` folder with `version.json`,
  `report.json`, `pages\pages.json`, `pages\<page>\page.json`, `visuals\<visual>\visual.json`.
  Git integration always writes `byPath` when model and report share a workspace.
- **PBIR schemas** (github.com/microsoft/json-schemas, `fabric/item/report/definition`): required
  keys measured from `page/2.0.0`, `report/3.0.0`, `visualContainer/2.4.0`, `pagesMetadata/1.0.0`,
  `versionMetadata/1.0.0`, `definitionProperties/2.0.0`; `semanticModel/definitionProperties/1.0.0`.
- **Direct Lake TMDL** (Learn "Develop Direct Lake semantic models", dated 2026-09-02):
  `compatibilityLevel` 1604 or higher, partitions with `mode: directLake`, data source in a shared
  expression. Direct Lake on OneLake uses the `AzureStorage.DataLake` connector against the item's
  OneLake location and never falls back to DirectQuery. The URL form
  `https://onelake.dfs.fabric.microsoft.com/<workspace id>/<item id>` with
  `[HierarchicalNavigation=true]` is from Tabular Editor's docs (dated 2026-10-12); Learn shows it
  only as a screenshot.
- **TMDL syntax** (Learn "Tabular Model Definition Language", dated 2023-12-27, updated 2026-06-11):
  tab indentation, three levels (declaration, properties, multi-line expression); `role` with
  `modelPermission` and `tablePermission <table> = <DAX>`; `relationship` with
  `fromColumn`/`toColumn`; one file per table and per role, one for all relationships and all
  expressions.
- **Direct Lake security** (Learn "Integrate Direct Lake security", dated 2025-09-22, updated
  2026-09-09): model RLS is not enforced for users with Write on the model (workspace Admin,
  Member, Contributor); with SSO, users who can read the source can bypass model RLS there; the
  recommendation for model-only rules is a fixed-identity cloud connection.
- **Same Delta table twice in one Direct Lake model** works in Desktop but has open service errors
  (Chris Webb's blog, 2024-09-29 and 2026-04-05). Not used.
- **Python TMDL parsers on PyPI**: `tmdl` 0.0.1 (single release, no documentation), `pytmdl`
  0.1.1a1 (alpha). Neither suitable; a structural parser of about 150 lines is written instead.

## Approaches

- **A (taken).** Direct Lake on OneLake over the Gold Warehouse tables (`schemaName: gold`),
  hand-written TMDL and PBIR in `fabric/`. Facts without PHI; `dim_patient` stays out. Measures
  named exactly as the metrics in `GLOSSARY.md`. Dynamic RLS: one role `clinic` filters
  `dim_clinic` to the clinics mapped to `USERPRINCIPALNAME()` in a new Gold table
  `gold.user_clinic`, which survives `gold.reload` and is filled per environment in U17 (never
  committed).
- B. Direct Lake on SQL over the Warehouse endpoint. Rejected: the metric views and U16's
  CLS/DDM would push queries to DirectQuery fallback; the spec names Direct Lake on OneLake.
- C. Static RLS, one role per clinic. Rejected: the model changes whenever a clinic is added, and
  the spec asks for a single `clinic` role mapped by user.

## Files

- `fabric/sm_clinic_chain.SemanticModel/`: `.platform`, `definition.pbism`, `definition/`
  (`database.tmdl`, `model.tmdl`, `expressions.tmdl`, `relationships.tmdl`, `tables/*.tmdl`,
  `roles/clinic.tmdl`).
- `fabric/rpt_clinic_chain.Report/`: `.platform`, `definition.pbir`, `definition/` (three pages:
  occupancy, quality, economics).
- `sql/gold/30_access.sql` (`gold.user_clinic`).
- `src/clinic_chain/tmdl.py`, `tests/test_semantic_model.py`.
- `README.md`, `plan.md`.

## Invariants and the checks that go red

All in `tests/test_semantic_model.py`, fast (`make test`):

- TMDL parses; every table has one `directLake` entity partition on `gold.<table>` through a
  declared expression (`test_model_parses_into_direct_lake_tables`).
- Every model column is a column of that Gold table, with a compatible type
  (`test_model_columns_exist_in_gold`).
- No PHI: no column sourced from `dim_patient`'s PHI columns (its columns minus the key, sex,
  home clinic and record count) and no column name matching name/birth/phone/address/postal/SSN
  patterns outside an allowlist (`test_model_has_no_phi_columns`).
- Every metric in the `GLOSSARY.md` table has a measure of the same name
  (`test_every_glossary_metric_has_a_measure`).
- Every `table[column]` reference in measures and role filters resolves
  (`test_dax_references_resolve`); relationships join existing columns
  (`test_relationships_join_model_columns`).
- Role `clinic` filters `dim_clinic` through `user_clinic` and `USERPRINCIPALNAME()`
  (`test_clinic_role_filters_by_user`).
- The report binds by path to the model, has the three contour pages, and every field it shows
  exists in the model (`test_report_fields_exist_in_the_model`).
- Every `fabric/*/.platform` has a distinct uuid4 `logicalId` (`test_platform_logical_ids`).

Negative control, run 2026-10-28: a `dim_patient` table with `given_name` added to the model made
`test_model_has_no_phi_columns` fail (`('dim_patient', 'given_name')`) while the other nine tests
passed; the file was then removed.

Measure values are checked against U09's reference in the cloud run (U20), as the spec says.

## Known limit handed to U17

`readmission_30d_rate` counts a readmission at any clinic. Under the `clinic` role, RLS also hides
the other clinics' stays, so a clinic user sees only same-clinic readmissions. The fix is a
precomputed `readmitted_30d` flag on `gold.fact_stay`; it needs a stand run of `make gold` and the
U09 comparison, so it is left to U17 (which owns RLS) rather than changed here without the stand.

## Reversal

Revert the PR. The Fabric items disappear from Git; `gold.user_clinic` is dropped by hand
(`DROP TABLE gold.user_clinic`), as no reload drops it.
