# ADR 0002: Lakehouse for Bronze and Silver, Warehouse for Gold

- Status: accepted 2026-10-28 (PLAN-U08, approach A)
- Unit: U08

## Context

Bronze and Silver are built by PySpark notebooks and need Delta history, schemas inferred from files
and Python libraries: the Lakehouse is their natural home. Gold serves two kinds of consumers:

- Power BI through Direct Lake, which reads Delta in OneLake;
- SQL users, who must see PHI masked (dynamic data masking) and be denied PHI columns (column-level
  security, AC9). DDM and CLS are Warehouse features; a Lakehouse SQL analytics endpoint is
  read-only.

Locally there is no Fabric. The source stand already runs SQL Server 2022, which cannot read Delta.

## Decision

- **Gold is a Fabric Warehouse built with T-SQL** (`sql/gold/`): a star schema and one procedure,
  `gold.reload`, that truncates and refills every table from a `silver` schema.
  - In Fabric, `silver` is a set of views over `lh_silver.dbo.*` (`sql/fabric/silver_views.sql`),
    read by three-part names within the workspace.
  - Locally, `scripts/gold.py` copies the Delta Silver into `silver` tables on SQL Server, then
    runs the same scripts.
- **The T-SQL is kept to the intersection of both engines**, as read in Microsoft Learn on 2026-10-28
  (Warehouse "Data types", dated 2026-06-11; "T-SQL surface area", dated 2026-09-16):

| Topic | Fabric Warehouse | Local SQL Server | In this repo |
|---|---|---|---|
| Strings | `varchar` only, UTF-8 collation | `varchar` / `nvarchar` | Gold tables use `varchar`. The local database is created with `Latin1_General_100_BIN2_UTF8`. |
| Date and time | `datetime2(≤6)`, `date` | everything | `datetime2(6)`, `date` |
| Small integers | no `tinyint` | `tinyint` | `smallint`, `bit` |
| Keys | PK, UK and FK only `NOT ENFORCED` | `NOT ENFORCED` does not parse | No declared keys. Uniqueness and references are tested (`tests/test_gold.py`). |
| Recursion | not supported | supported | `dim_date` from cross-joined digits |
| Silver access | views over the Lakehouse endpoint | no Delta reader | Views in Fabric, copied tables locally |

  A fast test fails if `sql/gold/` uses a type or statement the Warehouse rejects.
- **Full reload, not incremental.** The data is small (largest fact: 59k rows), and a full reload
  keeps Gold equal to Silver by construction.
- **Facts carry `master_patient_id`** from `silver.patient_xref` (U07). The analytical window
  (2024-10-01 … 2026-09-30) is applied here; Silver keeps history.

## Consequences

- One script set runs in both places, and the local reconciliation tests check the Fabric logic,
  except for the views.
- The views and three-part names are verified only in the cloud run (U20).
- Collation is binary and case-sensitive, as in Fabric: identifiers and string comparisons must
  match case exactly. The local database reproduces this, so a case slip fails locally too.
- Locally, strings in the copied Silver tables are `nvarchar`, because bulk copy into UTF-8
  `varchar` corrupts non-ASCII names. Those tables stand in for views and are not part of Gold.
- Without declared keys, Direct Lake and the SQL optimizer get no key hints. Relationships are set in
  the semantic model (U10).
