"""U05 Bronze. Fast tests run the Fabric notebook on local Spark over tiny landed files; `stand`
tests compare the Bronze built by `make bronze` with the stand."""

import json
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from clinic_chain import spark, stand
from clinic_chain.sources import contracts

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = contracts.load(ROOT / "docs" / "contracts")
LAKEHOUSE = ROOT / "data" / "lh_bronze"
NB = spark.notebook("nb_bronze")
META = ["_run_id", "_source_file", "_ingested_at"]


@pytest.fixture(scope="module")
def session():
    return spark.session()


def read(session, path: Path):
    return session.read.format("delta").load(str(path))


def land_fixture(landing: Path, run_id: str) -> dict[str, int]:
    """One tiny file per source; returns the expected rows per Bronze table."""
    expected = {}
    for table, (system, path, fmt) in NB.SOURCES.items():
        folder = landing / system / run_id
        folder.mkdir(parents=True, exist_ok=True)
        if fmt == "parquet":
            rows = [{"id": "a", "amount": Decimal("1.50")}, {"id": "b", "amount": None}]
            pq.write_table(pa.Table.from_pylist(rows), folder / path)
            expected[table] = 2
        elif fmt == "csv":
            # Quoted comma, doubled quote, embedded newline and an empty field, as csv.writer does.
            (folder / path).write_text(
                'id,name\n1,"Lee, Ann"\n2,"say ""hi"""\n3,"two\nlines"\n4,\n'
            )
            expected[table] = 4
        else:
            for clinic in ("boston", "worcester"):
                (folder / clinic).mkdir(exist_ok=True)
                (folder / clinic / "p1.json").write_text('{\n  "resourceType": "Bundle"\n}')
            expected[table] = 2
    return expected


@pytest.fixture(scope="module")
def bronze(session, tmp_path_factory):
    """Run r1, then r2 over the same tables (Spark runs dominate the test time)."""
    root = tmp_path_factory.mktemp("lakehouse")
    land_fixture(root / "landing", "r1")
    expected = land_fixture(root / "landing", "r2")
    NB.run(session, "r1", str(root / "landing"), str(root / "Tables"))
    counts = NB.run(session, "r2", str(root / "landing"), str(root / "Tables"))
    return root / "Tables", expected, counts


def test_every_source_lands_with_metadata(session, bronze):
    tables, expected, counts = bronze
    assert counts == expected
    for table in NB.SOURCES:
        df = read(session, tables / table)
        assert df.columns[-3:] == META
        assert df.filter(df._source_file.isNull() | df._ingested_at.isNull()).count() == 0


def test_rerun_overwrites(session, bronze):
    tables, _, _ = bronze
    for table in NB.SOURCES:
        runs = read(session, tables / table).select("_run_id").distinct().collect()
        assert [r[0] for r in runs] == ["r2"]


def test_csv_values_survive_quoting(session, bronze):
    rows = read(session, bronze[0] / "lab_results").orderBy("id").collect()
    assert [r["name"] for r in rows] == ["Lee, Ann", 'say "hi"', "two\nlines", None]


def test_parquet_keeps_types_and_fhir_keeps_raw_json(session, bronze):
    claim = read(session, bronze[0] / "billing_claim").orderBy("id").collect()
    assert [r["amount"] for r in claim] == [Decimal("1.50"), None]
    fhir = read(session, bronze[0] / "fhir_bundle").collect()
    assert all(json.loads(r["content"]) == {"resourceType": "Bundle"} for r in fhir)
    assert sorted(Path(r["_source_file"]).parent.name for r in fhir) == ["boston", "worcester"]


def test_run_requires_run_id(session, tmp_path):
    with pytest.raises(ValueError):
        NB.run(session, "", str(tmp_path), str(tmp_path))


def test_pipeline_lands_every_source_then_runs_the_notebook():
    item = ROOT / "fabric" / "pl_land_sources.DataPipeline"
    activities = json.loads((item / "pipeline-content.json").read_text())["properties"][
        "activities"
    ]
    names = {a["name"] for a in activities}
    billing = {
        path.removesuffix(".parquet") for s, path, _ in NB.SOURCES.values() if s == "billing"
    }
    blobs = {s for s, _, fmt in NB.SOURCES.values() if s not in ("billing", "sharepoint")}
    assert names == {f"copy_billing_{t}" for t in billing} | {f"copy_blob_{c}" for c in blobs} | {
        "refresh_df_sharepoint",
        "run_nb_bronze",
        "run_nb_silver",
        "run_nb_mpi",
        "run_nb_bed_history",
        "run_nb_quality",
        "run_nb_bed_reference",
    }
    [notebook] = [a for a in activities if a["name"] == "run_nb_bronze"]
    assert {d["activity"] for d in notebook["dependsOn"]} == names - {
        "run_nb_bronze",
        "run_nb_silver",
        "run_nb_mpi",
        "run_nb_bed_history",
        "run_nb_quality",
        "run_nb_bed_reference",
    }
    assert notebook["typeProperties"]["parameters"]["run_id"]["value"] == "@pipeline().RunId"
    assert (ROOT / "fabric" / "nb_bronze.Notebook" / "notebook-content.py").exists()


def test_dataflow_loads_every_sharepoint_table():
    item = ROOT / "fabric" / "df_sharepoint.Dataflow"
    meta = json.loads((item / "queryMetadata.json").read_text())["queriesMetadata"]
    loaded = {name for name, q in meta.items() if q["loadEnabled"]}
    sharepoint = {t.removeprefix("sharepoint_") for t in NB.SOURCES if t.startswith("sharepoint_")}
    assert (
        loaded == sharepoint == {n.partition(".")[2] for n in CONTRACTS if n[:11] == "sharepoint."}
    )
    assert all(f"shared {name} =" in (item / "mashup.pq").read_text() for name in meta)


# --- full population: needs `make up` and `make bronze` -----------------------------------


def latest_tables(session) -> dict[str, int]:
    return {t: read(session, LAKEHOUSE / "Tables" / t).count() for t in NB.SOURCES}


def source_counts() -> dict[str, int]:
    counts = {}
    with stand.sql() as conn:
        cur = conn.cursor()
        for table in stand.BILLING_TABLES:
            cur.execute(f"SELECT COUNT(*) FROM billing.{table}")
            counts[f"billing_{table}"] = cur.fetchone()[0]
    for name, spec in CONTRACTS.items():
        system, _, table = name.partition(".")
        if system in ("lab", "adt", "sharepoint"):
            counts[f"{system}_{table}"] = len(contracts.read(ROOT / "data" / "sources", spec)[1])
    counts["fhir_bundle"] = sum(
        1 for _ in stand.blobs().get_container_client("fhir").list_blob_names()
    )
    return counts


@pytest.mark.stand
def test_bronze_row_counts_equal_sources(session):
    assert latest_tables(session) == source_counts()
