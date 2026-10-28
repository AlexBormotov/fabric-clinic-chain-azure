"""Build Gold on the local SQL Server: copy Silver into schema `silver`, then run `sql/gold/`.

In Fabric the Warehouse reads Silver through views (`sql/fabric/silver_views.sql`); SQL Server
cannot read Delta, so the same tables are copied here. The database uses the Warehouse collation.
"""

import argparse
from pathlib import Path

from pyspark.sql import types as T

from clinic_chain import spark, stand

ROOT = Path(__file__).resolve().parents[1]
DATABASE = "clinic_gold"
COLLATION = "Latin1_General_100_BIN2_UTF8"
SILVER = [
    "patient_record",
    "patient_xref",
    "encounter",
    "condition",
    "claim",
    "lab_result",
    "adt_event",
    "ed_visit",
    "bed",
]


def sql_type(t: T.DataType) -> str:
    """Delta type → a SQL Server column type for the local copy of Silver.

    Strings are nvarchar here only: bulk copy into UTF-8 varchar corrupts non-ASCII names. The copy
    stands in for Fabric's views; Gold tables themselves stay varchar, as the Warehouse requires.
    """
    if isinstance(t, T.StringType):
        return "nvarchar(4000)"
    if isinstance(t, T.TimestampType):
        return "datetime2(6)"
    if isinstance(t, T.DecimalType):
        return f"decimal({t.precision}, {t.scale})"
    return {T.DateType: "date", T.IntegerType: "int", T.LongType: "bigint"}[type(t)]


def batches(path: Path) -> list[str]:
    return [b for b in path.read_text().split("\nGO\n") if b.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver", type=Path, default=ROOT / "data" / "lh_silver" / "Tables")
    args = parser.parse_args()
    session = spark.session()
    with stand.sql("master") as conn:
        conn.cursor().execute(
            f"IF DB_ID('{DATABASE}') IS NULL CREATE DATABASE {DATABASE} COLLATE {COLLATION}"
        )
    with stand.sql(DATABASE) as conn:
        cur = conn.cursor()
        cur.execute("IF SCHEMA_ID('silver') IS NULL EXEC ('CREATE SCHEMA silver')")
        for table in SILVER:
            df = session.read.format("delta").load(str(args.silver / table))
            df = df.select([c for c in df.columns if not c.startswith("_")])
            columns = ", ".join(f"{f.name} {sql_type(f.dataType)} NULL" for f in df.schema.fields)
            cur.execute(f"DROP TABLE IF EXISTS silver.{table}")
            cur.execute(f"CREATE TABLE silver.{table} ({columns})")
            rows = [tuple(r) for r in df.toLocalIterator()]
            cur.bulkcopy(f"silver.{table}", rows, timeout=600, keep_nulls=True)
            print(f"silver.{table}: {len(rows)}")
        for script in sorted((ROOT / "sql" / "gold").glob("*.sql")):
            for batch in batches(script):
                cur.execute(batch)
        cur.execute("EXEC gold.reload")
        cur.execute(
            "SELECT t.name, SUM(p.rows) FROM sys.tables AS t JOIN sys.partitions AS p"
            " ON t.object_id = p.object_id AND p.index_id IN (0, 1)"
            " WHERE SCHEMA_NAME(t.schema_id) = 'gold' GROUP BY t.name ORDER BY t.name"
        )
        for name, rows in cur.fetchall():
            print(f"gold.{name}: {rows}")


if __name__ == "__main__":
    main()
