"""U08 Gold. Fast tests guard the T-SQL against the Fabric Warehouse surface; `stand` tests
reconcile the Gold built by `make gold` on the local SQL Server with Silver."""

import re
from datetime import datetime, timedelta
from pathlib import Path

import gold
import pytest
import yaml
from pyspark.sql import Window
from pyspark.sql import functions as F

from clinic_chain import spark, stand

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql"
SILVER = ROOT / "data" / "lh_silver" / "Tables"
WINDOW = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())["window"]
# Types and statements Fabric Data Warehouse rejects (Microsoft Learn, read 2026-10-28).
UNSUPPORTED = [
    r"\bnvarchar\b",
    r"\bnchar\b",
    r"\bdatetime\b(?!2)",
    r"\bsmalldatetime\b",
    r"\bdatetimeoffset\b",
    r"\bmoney\b",
    r"\btinyint\b",
    r"\btext\b",
    r"\bCREATE\s+SYNONYM\b",
    r"\bCREATE\s+TRIGGER\b",
    r"\bPRIMARY\s+KEY\b",
    r"\bFOREIGN\s+KEY\b",
]
KEYS = {
    "dim_date": ["date_key"],
    "dim_clinic": ["clinic_id"],
    "dim_ward": ["ward_key"],
    "dim_bed": ["bed_id"],
    "dim_patient": ["master_patient_id"],
    "dim_payer": ["payer"],
    "dim_diagnosis": ["diagnosis_code"],
    "fact_encounter": ["encounter_id"],
    "fact_bed_day": ["stay_id", "segment_start", "date_key"],
    "fact_claim": ["claim_id"],
    "fact_lab_result": ["result_id"],
    "fact_ed_visit": ["ed_visit_id"],
}
# fact column -> (dimension, key); a NULL fact value is allowed only where noted.
REFERENCES = {
    "fact_encounter": {
        "master_patient_id": "dim_patient",
        "clinic_id": "dim_clinic",
        "start_date_key": "dim_date.date_key",
        "diagnosis_code": "dim_diagnosis",
    },
    "fact_bed_day": {
        "master_patient_id": "dim_patient",
        "date_key": "dim_date",
        "ward_key": "dim_ward",
        "bed_id": "dim_bed",
    },
    "fact_claim": {
        "master_patient_id": "dim_patient",
        "payer": "dim_payer",
        "service_date_key": "dim_date.date_key",
    },
    "fact_lab_result": {
        "master_patient_id": "dim_patient",
        "collected_date_key": "dim_date.date_key",
    },
    "fact_ed_visit": {
        "master_patient_id": "dim_patient",
        "arrival_date_key": "dim_date.date_key",
    },
}


def code(path: Path) -> str:
    return "\n".join(line.split("--")[0] for line in path.read_text().splitlines())


def test_gold_sql_avoids_what_the_warehouse_rejects():
    for path in (SQL / "gold").glob("*.sql"):
        for pattern in UNSUPPORTED:
            assert not re.search(pattern, code(path), re.IGNORECASE), (path.name, pattern)


def test_reload_window_matches_the_config():
    text = (SQL / "gold" / "10_reload.sql").read_text()
    assert f"@window_start date = '{WINDOW['start']}'" in text
    assert f"@window_end date = '{WINDOW['end']}'" in text


def test_fabric_views_cover_every_silver_table_gold_reads():
    views = re.findall(r"VIEW silver\.(\w+) AS", (SQL / "fabric" / "silver_views.sql").read_text())
    assert views == gold.SILVER
    used = set(re.findall(r"\bsilver\.(\w+)", code(SQL / "gold" / "10_reload.sql")))
    assert used == set(gold.SILVER)


# --- full population: needs `make up`, `make mpi` and `make gold` --------------------------


@pytest.fixture(scope="module")
def cur():
    with stand.sql(gold.DATABASE) as conn:
        yield conn.cursor()


def scalar(cur, query: str):
    cur.execute(query)
    return cur.fetchone()[0]


@pytest.fixture(scope="module")
def session():
    return spark.session()


def silver(session, table: str):
    return session.read.format("delta").load(str(SILVER / table))


def in_window(df, column: str):
    start = datetime.fromisoformat(WINDOW["start"])
    stop = datetime.fromisoformat(WINDOW["end"]) + timedelta(days=1)
    return df.where((F.col(column) >= start) & (F.col(column) < stop))


@pytest.mark.stand
def test_gold_keys_are_unique(cur):
    for table, key in KEYS.items():
        columns = ", ".join(key)
        duplicates = scalar(
            cur,
            f"SELECT COUNT(*) FROM (SELECT {columns} FROM gold.{table}"
            f" GROUP BY {columns} HAVING COUNT(*) > 1) AS d",
        )
        assert duplicates == 0, table


@pytest.mark.stand
def test_every_fact_key_resolves(cur):
    for fact, references in REFERENCES.items():
        for column, target in references.items():
            dim, _, key = target.partition(".")
            orphans = scalar(
                cur,
                f"SELECT COUNT(*) FROM gold.{fact} AS f WHERE f.{column} IS NOT NULL AND NOT EXISTS"
                f" (SELECT 1 FROM gold.{dim} AS d WHERE d.{key or column} = f.{column})",
            )
            assert orphans == 0, (fact, column)


@pytest.mark.stand
def test_facts_reconcile_with_silver_inside_the_window(session, cur):
    expected = {
        "fact_encounter": in_window(silver(session, "encounter"), "start_at").count(),
        "fact_claim": in_window(silver(session, "claim"), "service_start").count(),
        "fact_lab_result": in_window(silver(session, "lab_result"), "collected_at").count(),
        "fact_ed_visit": in_window(silver(session, "ed_visit"), "arrival_at").count(),
        "dim_patient": silver(session, "patient_xref")
        .select("master_patient_id")
        .distinct()
        .count(),
    }
    actual = {table: scalar(cur, f"SELECT COUNT(*) FROM gold.{table}") for table in expected}
    assert actual == expected


@pytest.mark.stand
def test_bed_hours_equal_adt_stay_segments(session, cur):
    """Bed occupancy recomputed in Spark from ADT events, independently of the T-SQL."""
    start = datetime.fromisoformat(WINDOW["start"])
    stop = datetime.fromisoformat(WINDOW["end"]) + timedelta(days=1)
    stay = Window.partitionBy("stay_id").orderBy("event_time", "event_id")
    segments = (
        silver(session, "adt_event")
        .withColumn("segment_end", F.lead("event_time").over(stay))
        .where(F.col("event_type").isin("A01", "A02"))
        .select(
            F.greatest("event_time", F.lit(start)).alias("s"),
            F.least(F.coalesce("segment_end", F.lit(stop)), F.lit(stop)).alias("e"),
        )
    )
    hours = segments.select(
        F.sum((F.unix_timestamp("e") - F.unix_timestamp("s")) / 3600).alias("h")
    ).first()["h"]
    gold_hours, rows = cur.execute(
        "SELECT SUM(occupied_hours), COUNT(*) FROM gold.fact_bed_day"
    ).fetchone()
    # Each row rounds to 6 decimals.
    assert abs(float(gold_hours) - hours) <= rows * 0.0000005


@pytest.mark.stand
def test_non_ascii_names_survive(session, cur):
    names = {
        r.family_name
        for r in silver(session, "patient_record").where("system = 'ehr'").collect()
        if not r.family_name.isascii()
    }
    assert names
    cur.execute("SELECT family_name FROM gold.dim_patient")
    assert names <= {r[0] for r in cur.fetchall()}
