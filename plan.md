---
id: PLAN-U04
spec: SPEC-001 / U04
owner: AlexBormotov
status: approved (approach A, both gap resolutions; amendment approved) by owner 2026-10-23
previous: PLAN-U03 (approach B, landed in #6; see git history of this file)
---

# PLAN-U04 — Local source stand

## Facts this plan rests on (checked 2026-10-23)

- U03 output (`make sources`, data rows): billing `patient_account` 16,048, `claim` 32,722,
  `claim_line` 83,473; lab `patients` 931, `results` 59,083; ADT `patients` 15,217, `events` 13,125,
  `ed_visits` 11,446; SharePoint `beds.xlsx`, `rosters.xlsx`. Raw FHIR: 1,209 JSON files, 885 MB in
  `data/raw/fhir/<clinic>/fhir/`.
- Images (MCR tag lists): `mcr.microsoft.com/mssql/server:2022-CU27-ubuntu-22.04` (latest 2022 CU);
  `mcr.microsoft.com/azure-storage/azurite:3.37.0` (released 2026-08-26).
- Python drivers (PyPI): `mssql-python` 1.16.0 (Microsoft, 2026-10-13) ships its own driver,
  manylinux x86_64 cp313 wheel, no ODBC packages in the image, has bulk copy; `pymssql` 2.4.5 was
  released 3 days ago. `azure-storage-blob` 12.31.0 (2026-09-30).
- The `dev` service joins the compose network on `docker compose run`, so it reaches `sqlserver:1433`
  and `azurite:10000` by service name, locally and in CI.
- `make test` must pass without cloud and without the 4-minute Synthea run (INT-001/AC13); the CI
  `test` job has no `data/`.

## Two gaps in the spec that need the owner's decision

1. **Completion command.** SPEC-001 says `make up && make test`. Read-back against U03 output needs the
   full population and running services, which `make test` cannot assume (AC13, CI `test` job).
   Proposed wording: stand tests carry a `stand` marker, excluded from `make test`, and run by
   `make up && make test-stand`; a new CI job `stand` runs `make synth sources up test-stand`. It stays
   optional until the end, like `synth` (added to `tasks/todo.md`).
2. **ADT files have no home.** U04 scope places only `fhir/` and `lab/` in Blob, but U05 Bronze must
   land `adt/patients`, `adt/events` (history) and `adt/ed_visits` from somewhere; live events are
   U11. Proposed: upload `adt/` to Azurite as the ADT system's export. Ground truth stays local; it is
   not a source.

## Settings for every approach

- `docker-compose.yml`: services `sqlserver` and `azurite` with healthchecks, no `depends_on` from
  `dev` (other targets must not start the stand). SQL Server 2 GB memory limit.
- Secrets: the SA password lives in a git-ignored `.env`, written with a random value by `make up` on
  first run; compose passes it to `sqlserver` and `dev`. Azurite uses Microsoft's published
  development account key; `.gitleaks.toml` allowlists that one key, with a link to the docs.
- `make up`: `docker compose up -d --wait sqlserver azurite`, then load (idempotent: drop and recreate
  schema `billing`, overwrite blobs). `make down` unchanged.
- SQL Server: database `clinic_billing`, DDL from `docs/contracts/billing.sql` (the file the DDL test
  already checks).
- Blob containers on Azurite: `fhir` (`<clinic>/<file>.json`), `lab`, `adt` (if gap 2 is approved).
- SharePoint stand-in: the folder `data/sources/sharepoint/` itself. No copy, no service; U05 reads it
  as the Dataflow Gen2 would read the site.
- Read-back tests (`tests/test_stand.py`, `stand` marker): per table `SELECT COUNT(*)` equals CSV row
  count; per container blob count equals file count, and lab blob bytes equal file bytes; SharePoint
  sheet row counts equal the U03 workbooks.

## The choice: how data gets into the stand

### Approach A — Python loader in the dev container (recommended)

`scripts/load_stand.py` + `src/clinic_chain/stand.py`: applies `billing.sql`, bulk-copies the three
billing CSVs with `mssql-python` (rows typed by the existing `contracts` module), uploads files with
`azure-storage-blob`. Tests use the same connection helpers to read back.

- Files: `docker-compose.yml`, `Makefile`, `pyproject.toml`, `uv.lock`, `.gitignore`, `.gitleaks.toml`,
  `src/clinic_chain/stand.py`, `scripts/load_stand.py`, `tests/test_stand.py`,
  `.github/workflows/ci.yml`, `README.md`, `CLAUDE.md`, `spec.md` (gap wording), `plan.md`,
  `tasks/todo.md`.
- Invariants: one loading path, one reading path, both in the CI image; the contract types decide SQL
  values (dates, decimals, NULLs) in one place.
- Red check: `make test-stand` (counts); a fast unit test that CSV → row conversion keeps NULLs and
  decimals for one fixture row of each billing table.
- Cost: two Python dependencies; loading speed depends on the driver's bulk copy (~130k rows).
- Reverse: delete the two services, the module, the script and the dependencies.

### Approach B — Native tools in one-shot compose services

A `stand-init` service runs `sqlcmd` + `BULK INSERT ... FORMAT='CSV'` inside the SQL Server
container from a bind-mounted `data/sources/billing`; an `azure-cli` container runs
`az storage blob upload-batch` against Azurite.

- Files: as A, minus `stand.py`/`load_stand.py`, plus `docker/stand-init.sql` and a shell entrypoint.
- Invariants: no loader code in Python; SQL Server parses the CSV itself.
- Red check: same `make test-stand`; still needs a Python SQL driver for the read-back, so the stand
  is written by one toolchain and read by another.
- Cost: one more image (`azure-cli`, ~1 GB); CSV quoting and empty-string → NULL rules move to
  `BULK INSERT` options that no fast test covers; bind-mount paths differ between Docker Desktop on
  Windows and CI.
- Reverse: delete the services and the init files.

## Amendment 2026-10-23 (build stopped, returned to the owner)

The fact "no ODBC packages in the image" is false. `mssql-python` bundles the ODBC driver, but on
Linux the driver needs system libraries: `make up` failed with "DDBC Error: Failed to load the
driver", and `ldd` shows `libltdl.so.7 => not found`. Upstream README (Debian/Ubuntu):
`apt-get install -y libltdl7 libkrb5-3 libgssapi-krb5-2`. Proposed: add these three packages to the
existing `apt-get install` line of `docker/dev.Dockerfile`, which adds that file to the approved
set. Alternatives are worse: `pymssql` (3 days old, no bulk copy) or approach B.
`.env.example` joins the set too: its header requires every variable the project reads, so it lists
`MSSQL_SA_PASSWORD` without a value. Both approved by the owner 2026-10-23.

## Implementation notes (measured 2026-10-23)

- `make up` on a warm image: ~1 min 10 s, including 885 MB of FHIR into Azurite; a second run
  reloads in place and `make test-stand` stays green (8 passed).
- Negative control: deleting one `billing.claim_line` row and the `lab/results.csv` blob turns
  exactly those two tests red; `make up` restores green.
- gitleaks flags the Azurite key as `generic-api-key`; `.gitleaks.toml` allowlists that one line.
  `.gitignore` already covered `.env`, so it is unchanged.

## Recommendation

A, with both gap resolutions. It reuses `contracts` for typing, keeps one toolchain, and every
check runs in the existing image.
