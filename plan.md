---
id: PLAN-U05
spec: SPEC-001 / U05
owner: AlexBormotov
status: approved (approach A, Dataflow gap closed in U05, Java 21) by owner 2026-10-23
previous: PLAN-U04 (approach A, landed in #7; see git history of this file)
---

# PLAN-U05 — Bronze

## Facts this plan rests on (checked 2026-10-23)

- Fabric Runtime 2.0 is GA and the default (learn.microsoft.com, page dated 2026-10-22): Spark 4.1,
  **Java 21**, Scala 2.13, Python 3.13, **Delta Lake 4.2**.
- The dev image has **JDK 17** (`openjdk-17-jre-headless`, Debian bookworm, which has no 21). Its
  comment claims the JDK matches Runtime 2.0; that is no longer true.
- PyPI: `delta-spark` 4.2.0 (2026-04-10) requires `pyspark>=4.0.1,<=4.1.1`; `pyspark` 4.1.1
  (2026-01-09). `delta-spark` pulls `io.delta:delta-spark_2.13:4.2.0` from Maven Central at session
  start (jar present). `pyarrow` 25.0.1 has a cp313 manylinux wheel.
- Fabric Git format: a PySpark notebook is `<name>.Notebook/notebook-content.py` plus `.platform`
  (docs dated 2026-03-05). The file is plain Python with comment markers between cells.
- Dataflow Gen2 can write to **Lakehouse Files** as well as Tables (docs dated 2026-10-06).
- U04 stand: billing in SQL Server, `fhir`/`lab`/`adt` in Azurite, SharePoint workbooks in a folder.
  Source counts: billing 16,048 / 32,722 / 83,473 rows; lab 931 / 59,083; ADT 15,217 / 13,125 /
  11,446; FHIR 1,209 bundle files; SharePoint `beds`, `rosters`.

## Gap in the spec that needs the owner's decision

**No unit owns the Dataflow Gen2.** INT-001/AC2 says SharePoint Excel lands through Dataflows Gen2,
and U19 republishes them, but no unit writes one. Proposed: U05 adds `df_sharepoint` (Power Query
reading the two workbooks, destination Lakehouse Files as CSV), cloud-only like the pipeline.

## Settings for every approach

- **Flow (cloud):** pipeline `pl_land_sources` copies each source unchanged into Lakehouse Files
  `landing/<system>/<run_id>/` (SQL tables as Parquet, blobs as they are), runs the Dataflow for
  SharePoint (CSV into the same layout), then a Notebook activity builds Bronze for that `run_id`.
- **Flow (local):** `src/clinic_chain/landing.py` stands in for the Copy activities and the Dataflow:
  it reads the U04 stand (SQL → Parquet via `pyarrow`, blobs → files, xlsx sheets → CSV) into
  `data/lakehouse/Files/landing/...`; the same Bronze code then runs on local Spark + Delta.
  `make bronze` does both.
- **Bronze tables:** `<system>_<table>` (`billing_claim`, `lab_results`, `adt_events`,
  `fhir_bundle`, `sharepoint_beds`, …), source columns as landed plus `_run_id`, `_source_file`,
  `_ingested_at` (UTC). Each run overwrites the table: sources are full extracts, raw history stays in
  `landing/<run_id>/` and Delta time travel.
- **FHIR grain:** one row per bundle file (raw JSON text); flattening is U06. 1,209 rows.
- **Versions:** `pyspark==4.1.1`, `delta-spark==4.2.0`, `pyarrow==25.0.1`. Java 21 in the dev image:
  `COPY --from=eclipse-temurin:21-jre` replaces the Debian JDK 17 (one line, no base-image change).
  Ivy cache in a compose volume so the Delta jar downloads once.
- **Cloud-only definitions:** `fabric/pl_land_sources.DataPipeline/pipeline-content.json`,
  `fabric/df_sharepoint.Dataflow/` (if the gap is approved). Connections and workspace IDs are
  placeholders resolved by `parameter.yml` in U19. Lakehouse items come with U18/U19.
- **Tests:**
  - fast (`make test`, local Spark on tiny landed fixtures): each format lands with the metadata
    columns, row count equals the fixture's, rerun overwrites (no doubling); pipeline JSON parses,
    has a Copy activity per source and points at the notebook that exists.
  - full (`stand` marker, CI job `stand` after `make up bronze`): per source, Bronze row count equals
    the source row count read from the stand.

## The choice: where the Bronze code lives

### Approach A — Self-contained notebook (recommended)

One parameterized notebook `fabric/nb_bronze.Notebook/notebook-content.py` holds all Bronze logic
(source table: format, landing path, Bronze name). Its run cell is guarded by
`if __name__ == "__main__"`, so tests import the file with `importlib` and call its functions with a
local SparkSession.

- Files: `fabric/nb_bronze.Notebook/*`, `fabric/pl_land_sources.DataPipeline/*`,
  `fabric/df_sharepoint.Dataflow/*`, `src/clinic_chain/landing.py`, `src/clinic_chain/spark.py`
  (local session), `scripts/bronze.py`, `tests/test_bronze.py`, `Makefile`, `pyproject.toml`,
  `uv.lock`, `docker/dev.Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`,
  `README.md`, `CLAUDE.md`, `spec.md` (gap), `plan.md`.
- Invariants: the file Fabric runs is the file the tests run; nothing to build or attach in Fabric;
  the notebook starts on the starter pool (seconds).
- Red check: fast tests import the notebook itself; a broken notebook fails `make test`.
- Assumption to confirm in U20: Fabric runs notebook cells with `__name__ == "__main__"` (IPython
  kernel). If not, the guard becomes a check for the `spark` global, a one-line change.
- Cost: code shared with later notebooks (Silver) cannot be imported in Fabric without `%run`, so
  each notebook stays self-contained.
- Reverse: delete the `fabric/` items and the local runner.

### Approach B — Library wheel, thin notebook

Bronze logic in `src/clinic_chain/bronze.py`, built as a wheel and attached to a Fabric Environment;
the notebook only imports and calls it.

- Files: as A, plus `fabric/env_clinic.Environment/` and a wheel build step in CI and U19.
- Invariants: one import path for all notebooks; ordinary unit tests.
- Red check: same tests against the module; the notebook itself is untested locally.
- Cost: custom libraries in an Environment are installed at session start, which adds minutes to
  each session (starter pools otherwise start in seconds); one more item to deploy and republish on every code change;
  the notebook in Git is no longer the code that runs.
- Reverse: inline the module back into the notebook, delete the Environment.

## Recommendation

A, with the Dataflow gap closed in U05 and the dev image moved to Java 21.

## Implementation notes (measured 2026-10-23)

- `make bronze` on the full population: ~2 min 45 s; every Bronze table equals its source
  (billing 16,048 / 32,722 / 83,473; lab 931 / 59,083; ADT 15,217 / 13,125 / 11,446; SharePoint
  beds 48, staff 292, roster 6,615; FHIR 1,206). Correction: FHIR has **1,206** bundle files; the
  1,209 above also counted the three `metadata/` files, which are not a source.
- Fast tests share one notebook run pair (r1, then r2): `make test` 20 passed in ~35 s, most of it
  Spark start and Delta writes. Negative control: dropping the CSV `escape` option fails exactly
  the quoting test.
- FHIR is read with `recursiveFileLookup` + `pathGlobFilter` rather than a `*/*.json` glob, which
  made Spark log a `FileNotFoundException` while probing for streaming metadata.
- Locally `make bronze` deletes the previous landing before the new one (each holds ~900 MB). In
  Fabric, landing history is kept; retention is not set by this unit.
- The pipeline and Dataflow definitions are untested against Fabric until U19/U20: IDs are zero
  GUIDs for `parameter.yml`, and the Dataflow's Lakehouse Files destination (CSV under
  `landing/sharepoint/<run_id>/`) is not part of the documented item definition parts, so it is
  bound when the Dataflow is first published and then committed back from Fabric.
