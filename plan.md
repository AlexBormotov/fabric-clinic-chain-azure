---
id: PLAN-U16
spec: SPEC-001 / U16
owner: AlexBormotov
status: approach A taken 2026-10-28 under the owner's standing go-ahead
previous: PLAN-U09 (#16), PLAN-U13 (#15), PLAN-U08 (#11); see git history of this file
---

# PLAN-U16 — Warehouse PHI protection

## Facts this plan rests on

Read on Microsoft Learn on 2026-10-28:

- "Dynamic data masking in Fabric Data Warehouse" (ms.date 2026-06-25):
  - Four mask functions: `default()`, `email()`, `random(a, b)` and `partial(prefix,"pad",suffix)`.
  - `default()` gives `XXXX` for strings and `1900-01-01` for dates.
  - Viewing unmasked data needs "`UNMASK` on the column or `CONTROL` on the database".
  - Workspace Admin, Member and Contributor hold `CONTROL` and see clear values.
- "How to implement dynamic data masking" (ms.date 2024-10-09):
  - `MASKED WITH (FUNCTION = ...)` works inline in `CREATE TABLE`.
  - `ALTER COLUMN ... ADD MASKED` adds a mask to an existing column.
  - The page shows `GRANT UNMASK ON dbo.EmployeeData TO [user]` (table level) and grants to a role.
- "Column-level security in Fabric Data Warehouse" (ms.date 2024-08-21):
  - CLS is done with `GRANT` on a column list, and roles are preferred.
  - Only Entra authentication is supported.
  - Direct Lake on a Warehouse falls back to DirectQuery under CLS.
- "SQL granular permissions" (ms.date 2026-06-25):
  - `GRANT`, `REVOKE` and `DENY` work, as do custom and built-in database roles.
  - `CREATE USER` cannot be run explicitly: "When you run `GRANT` or `DENY`, Fabric creates the
    database user automatically."
- "T-SQL surface area" (ms.date 2026-09-16):
  - `CREATE USER` is listed as unsupported.
  - `ALTER TABLE ... ALTER COLUMN` is in preview.
  - No page documents `CREATE LOGIN`. Fabric has no SQL logins; identities are Entra.
- "Share your warehouse and manage permissions" (ms.date 2025-07-14):
  - Item `Read` is CONNECT only.
  - `ReadData` equals `db_datareader`; the workspace Viewer role has it.
  - `ReadAll` reads the OneLake files through Spark.
- SQL Server 2022 supports the same mask functions, column `DENY` and `UNMASK` on a table.
- Not verified in documentation, left to the cloud run (U20):
  - `ALTER ROLE ... ADD MEMBER` with an Entra group that has no database user yet;
  - `GRANT SELECT ON SCHEMA::`.

## PHI in Gold

| Table | Column | PHI | Masked | Denied to `gold_reader` |
|---|---|---|---|---|
| `dim_patient` | `given_name`, `family_name` | yes | `partial(1,"xxxx",0)` | yes |
| `dim_patient` | `birth_date` | yes | `default()` (1900-01-01) | yes |
| `dim_patient` | `phone` | yes | `default()` | yes |
| `dim_patient` | `postal_code` | yes | `partial(3,"xx",0)` | yes |
| `dim_patient` | `master_patient_id`, `sex`, `home_clinic_id`, `source_records` | no | no | no |

- `master_patient_id` is a hash of the MPI cluster label, not of demographics.
- Event dates in facts stay clear. The analysis needs them, and without demographics they do not
  identify anyone.
- No other Gold table holds a PHI column (tested).

## Spec change inside this unit (2026-10-28)

The first version of this unit denied only `phone` to `gold_reader` and left the other four PHI
columns masked. Security review on PR #18 found that this leaks PHI. A masked column still answers
predicates (`WHERE birth_date = ...`, `LIKE 'A%'`), and Microsoft Learn says DDM does not prevent
inference.

The coordinator changed the unit before merge:

- `gold_reader` is denied every PHI column. The column `DENY` is the access control; DDM is defense
  in depth.
- The spec's check that "a non-privileged user sees masked values" now runs as a principal outside
  both roles. Locally that is a login with `db_datareader` only. It models a Fabric Viewer, who
  reads through `ReadData` (`db_datareader`).
- **A Viewer still sees masks only and can infer PHI through predicates.** So the Viewer role is not
  granted on the Gold warehouse to non-PHI users. Those readers get `gold_reader` and item Read.

## Approach A — inline masks, schema GRANT plus column DENY (taken)

- Masks are declared inline in `CREATE TABLE gold.dim_patient` (`00_tables.sql`). The inline form
  is GA, while `ALTER COLUMN` is in preview, and the table is recreated on every build anyway.
- `sql/gold/30_security.sql` sets the roles and grants:
  - it creates roles `gold_reader` and `gold_phi_reader` if they are missing;
  - both roles get `GRANT SELECT ON SCHEMA::gold`;
  - `gold_reader` gets `DENY SELECT` on the five PHI columns of `gold.dim_patient`;
  - `gold_phi_reader` gets `GRANT UNMASK ON gold.dim_patient`.
- `sql/fabric/security_members.sql` holds the Fabric-only part. It adds Entra groups to the roles.
  It is not run locally. Its comments state three rules:
  - item Read only;
  - no workspace role;
  - no `ReadAll`.
- Files: `sql/gold/00_tables.sql`, `sql/gold/30_security.sql`, `sql/fabric/security_members.sql`,
  `src/clinic_chain/stand.py` (connect as another login), `tests/test_gold_security.py`,
  `README.md`, `plan.md`.
- Invariants:
  - every PHI column is masked and denied to `gold_reader`;
  - every `dim_patient` column is classified as PHI or not;
  - no PHI-named column exists outside `dim_patient` (this covers U09's `fact_stay`);
  - no Gold view names a PHI column, because ownership chaining would bypass the `DENY`;
  - `sql/gold/` creates no user, login or role membership.
- Red checks:
  - fast: classification, masks, denied set and no-principal tests.
  - `stand`, as `u16_reader` (role `gold_reader`):
    - selecting any PHI column fails with "SELECT permission was denied on the column";
    - so do `SELECT *` and the predicates `WHERE birth_date = ...` and `LIKE 'A%'`;
    - the non-PHI `dim_patient` columns and the facts are readable, and `silver` is denied.
  - `stand`, as `u16_datareader` (`db_datareader` only, the Viewer model): names show as `Xxxxx`,
    birth dates as 1900-01-01, and postal codes as the first three characters plus `xx`.
  - `stand`, as `u16_phi_reader`: values equal what `sa` reads, phone included.
  - The logins exist only in test setup and are dropped afterwards.
- Reverse: delete `30_security.sql` and the `MASKED WITH` clauses, then
  `DROP ROLE gold_reader, gold_phi_reader`.

## Approaches not taken

- **B. Column whitelist: `GRANT SELECT` per table plus a column list on `dim_patient`.** It fails
  closed for new columns, but it must list every Gold table. The classification test covers new
  columns instead.
- **C. Masks added by `ALTER COLUMN ... ADD MASKED` in `30_security.sql`.** It keeps the security
  in one file, but `ALTER COLUMN` is in preview in Fabric.

## Implementation notes (2026-10-28)

- sqlfluff (tsql) cannot parse `DENY SELECT ON t (col)`. It parses `DENY SELECT (col) ON t`, which
  both engines accept.
- mssql_python pools connections, so the test kills the login's sessions before it drops the login.
- Negative control, rerun after the spec change: one rebuild with the `phone, postal_code` DENY, the
  `UNMASK` and the `given_name` mask removed. Five tests failed: masks, denied set, datareader masked
  view, reader denial and clear view. All passed after the restore: 10 security tests, plus 11
  `stand` tests across Gold, PHI and metrics.
