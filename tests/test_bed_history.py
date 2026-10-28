"""U13 bed state history. Fast tests feed fixture ADT events to the Fabric notebook in batches;
the `stand` test checks the history built by `make bed-history` on the full population."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pyspark.sql import Window
from pyspark.sql import functions as F

from clinic_chain import spark

ROOT = Path(__file__).resolve().parents[1]
NB = spark.notebook("nb_bed_history")
SCHEMA = (
    "event_id INT, event_type STRING, event_time TIMESTAMP, clinic_id STRING, stay_id STRING,"
    " adt_patient_id STRING, ward_id STRING, bed_id STRING, from_ward_id STRING,"
    " from_bed_id STRING"
)
T1, T2, T3 = datetime(2026, 1, 1, 8), datetime(2026, 1, 2, 10), datetime(2026, 1, 4, 12)
ICU, MED1, MED2 = "BOS-ICU-01", "BOS-MED-01", "BOS-MED-02"
# S1 is admitted to ICU, moved to MED1 and discharged at T3, the instant S2 takes MED1.
EVENTS = {
    1: (1, "A01", T1, "boston", "S1", "P1", "ICU", ICU, None, None),
    2: (2, "A02", T2, "boston", "S1", "P1", "MED", MED1, "ICU", ICU),
    3: (3, "A03", T3, "boston", "S1", "P1", "MED", MED1, None, None),
    4: (4, "A01", T3, "boston", "S2", "P2", "MED", MED1, None, None),
    5: (5, "A01", T1, "boston", "S3", "P3", "MED", MED2, None, None),
}
EXPECTED = {
    ICU: [(T1, T2, True, "S1"), (T2, None, False, None)],
    MED1: [(T2, T3, True, "S1"), (T3, None, True, "S2")],
    MED2: [(T1, None, True, "S3")],
}


@pytest.fixture(scope="module")
def session():
    return spark.session()


@pytest.fixture
def feed(session, tmp_path):
    """Runs the notebook once per batch of events; returns the history after the last batch."""

    def run(*batches: list) -> dict:
        for n, batch in enumerate(batches, 1):
            rows = [EVENTS[e] if isinstance(e, int) else e for e in batch]
            events = session.createDataFrame(rows, SCHEMA)
            events.write.format("delta").mode("overwrite").save(str(tmp_path / "adt_event"))
            run.stats = NB.run(session, f"r{n}", str(tmp_path))
            run.history = history(session, tmp_path)
            assert_contiguous(run.history)
        return {bed: [r[:4] for r in rows] for bed, rows in run.history.items()}

    return run


def history(session, root: Path) -> dict:
    rows = session.read.format("delta").load(str(root / "bed_state_history")).collect()
    by_bed: dict[str, list] = {}
    for r in sorted(rows, key=lambda r: (r.bed_id, r.valid_from)):
        by_bed.setdefault(r.bed_id, []).append(
            (r.valid_from, r.valid_to, r.occupied, r.stay_id, r.is_current, r._run_id)
        )
    return by_bed


def assert_contiguous(by_bed: dict) -> None:
    """Per bed: each interval ends where the next starts, only the last is open."""
    for bed, rows in by_bed.items():
        for (start, end, *_), (nxt, *_) in zip(rows, rows[1:], strict=False):
            assert end is not None and start < end == nxt, (bed, rows)
        assert rows[-1][1] is None and rows[-1][4], (bed, rows)
        assert not any(r[4] for r in rows[:-1]), (bed, rows)


def test_in_order_events(feed):
    assert feed([1, 2, 3, 4, 5]) == EXPECTED
    assert feed.stats == {"events": 5, "new_events": 5, "affected_beds": 3, "intervals": 5}


def test_a_late_transfer_re_splits_the_open_intervals(feed):
    early = feed([1, 3, 4, 5])
    assert early[ICU] == [(T1, None, True, "S1")]
    assert early[MED1] == [(T3, None, True, "S2")]
    assert feed([1, 3, 4, 5], [1, 2, 3, 4, 5]) == EXPECTED
    assert feed.stats["new_events"] == 1
    assert {r[5] for r in feed.history[MED2]} == {"r1"}  # a bed without new events is untouched


def test_duplicates_do_not_change_the_result(feed):
    assert feed([1, 1, 2, 3, 4, 4, 5], [2, 5], [1, 2, 3, 4, 5]) == EXPECTED
    assert feed.stats["new_events"] == 0
    assert {r[5] for rows in feed.history.values() for r in rows} == {"r1"}


def test_out_of_order_batches(feed):
    assert feed([4], [3], [5, 2], [1]) == EXPECTED


def test_a_later_copy_under_a_new_id_merges_into_one_interval(feed):
    resent = (6, "A01", T1 + timedelta(hours=1), "boston", "S3", "P3", "MED", MED2, None, None)
    assert feed([resent], [5, resent])[MED2] == [(T1, None, True, "S3")]


def test_run_requires_run_id(session, tmp_path):
    with pytest.raises(ValueError):
        NB.run(session, "", str(tmp_path))


def test_pipeline_runs_bed_history_after_silver():
    item = ROOT / "fabric" / "pl_land_sources.DataPipeline"
    activities = json.loads((item / "pipeline-content.json").read_text())["properties"][
        "activities"
    ]
    [notebook] = [a for a in activities if a["name"] == "run_nb_bed_history"]
    assert [d["activity"] for d in notebook["dependsOn"]] == ["run_nb_silver"]
    assert notebook["typeProperties"]["parameters"]["run_id"]["value"] == "@pipeline().RunId"


# --- full population: needs `make silver` and `make bed-history` ---------------------------


@pytest.mark.stand
def test_full_history_is_contiguous_and_matches_the_stays(session):
    silver = ROOT / "data" / "lh_silver" / "Tables"
    hist = session.read.format("delta").load(str(silver / "bed_state_history")).cache()
    events = session.read.format("delta").load(str(silver / "adt_event"))
    beds = session.read.format("delta").load(str(silver / "bed"))

    order = Window.partitionBy("bed_id").orderBy("valid_from")
    broken = hist.withColumn("_next", F.lead("valid_from").over(order)).where(
        (F.col("valid_to") <= F.col("valid_from"))
        | ~F.col("valid_to").eqNullSafe(F.col("_next"))
        | (F.col("is_current") != F.col("valid_to").isNull())
    )
    assert broken.count() == 0, broken.limit(5).collect()
    current = hist.where("is_current").groupBy("bed_id").count()
    assert current.where("count != 1").count() == 0
    assert current.count() == events.select("bed_id").distinct().count()
    assert hist.join(beds, "bed_id", "left_anti").count() == 0

    # A stay's segment runs from its admit or transfer to its next event on any bed.
    stay = Window.partitionBy("stay_id").orderBy("event_time", "event_id")
    segments = (
        events.withColumn("valid_to", F.lead("event_time").over(stay))
        .where("event_type != 'A03'")
        .where(F.col("valid_to").isNull() | (F.col("valid_to") > F.col("event_time")))
        .select("bed_id", "stay_id", F.col("event_time").alias("valid_from"), "valid_to")
    )
    occupied = hist.where("occupied").select("bed_id", "stay_id", "valid_from", "valid_to")
    assert segments.exceptAll(occupied).count() == 0
    assert occupied.exceptAll(segments).count() == 0
