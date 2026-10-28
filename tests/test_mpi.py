"""U07 master patient index. Fast tests run the Fabric notebook on a fixture `patient_record`;
the `stand` test evaluates the MPI built by `make mpi` against ground truth."""

import json
import random
from datetime import date
from pathlib import Path

import pytest

from clinic_chain import mpi_eval, spark

ROOT = Path(__file__).resolve().parents[1]
NB = spark.notebook("nb_mpi")
SCHEMA = (
    "system STRING, local_patient_id STRING, clinic_id STRING, given_name STRING,"
    " family_name STRING, birth_date DATE, sex STRING, phone STRING, postal_code STRING"
)
GIVEN = ["Anna", "Boris", "Clara", "Dmitri", "Elena", "Felix", "Greta", "Hugo", "Irina", "Jonas"]
FAMILY = ["Ivanova", "Kohler", "Bruen", "Okafor", "Tanaka", "Haddad", "Novak", "Silva"]
DESIGNED = [
    # one person in three systems: a surname typo, a day/month swap, a missing phone
    ("ehr", "a1", "boston", "Maria", "Lopez", date(1980, 3, 12), "F", "5551110001", "02132"),
    ("lab", "L1", "boston", "Maria", "Lopes", date(1980, 3, 12), "F", "5551110001", None),
    ("billing", "B1", "boston", "Maria", "Lopez", date(1980, 12, 3), "F", None, "02132"),
    # a within-system duplicate
    ("adt", "P1", "worcester", "John", "Smith", date(1975, 6, 20), "M", "5552220002", "01583"),
    ("adt", "P2", "worcester", "John", "Smith", date(1975, 6, 20), "M", "5552220002", "01583"),
    # another person who shares Maria's phone
    ("billing", "B2", "boston", "Peter", "Novak", date(1990, 1, 15), "M", "5551110001", "02132"),
]


def fillers(n: int) -> list[tuple]:
    """Distinct persons, one record each, so that u is estimated on mostly unrelated pairs."""
    rng = random.Random(3)
    names = rng.sample([(g, f) for g in GIVEN for f in FAMILY], n)
    return [
        (
            "adt",
            f"F{i}",
            rng.choice(["boston", "worcester", "springfield"]),
            given,
            family,
            date(rng.randrange(1930, 2020), rng.randrange(1, 13), rng.randrange(1, 29)),
            rng.choice("MF"),
            f"555{3000000 + i}",
            f"0{rng.randrange(1000, 2000)}",
        )
        for i, (given, family) in enumerate(names)
    ]


@pytest.fixture(scope="module")
def session():
    return spark.session()


@pytest.fixture(scope="module")
def mpi(session, tmp_path_factory):
    root = tmp_path_factory.mktemp("silver")
    rows = DESIGNED + fillers(60)
    session.createDataFrame(rows, SCHEMA).write.format("delta").save(str(root / "patient_record"))
    stats = NB.run(session, "r1", str(root))
    xref = session.read.format("delta").load(str(root / "patient_xref")).collect()
    return stats, {(r.system, r.local_patient_id): r.master_patient_id for r in xref}, len(rows)


def test_jaro_winkler_matches_reference_values():
    # Winkler (1990) examples.
    assert round(NB.jaro_winkler("martha", "marhta"), 4) == 0.9611
    assert round(NB.jaro_winkler("dwayne", "duane"), 4) == 0.84
    assert round(NB.jaro_winkler("dixon", "dicksonx"), 4) == 0.8133
    assert NB.jaro_winkler("abc", "xyz") == 0.0
    assert NB.jaro_winkler("same", "same") == 1.0
    assert NB.jaro_winkler(None, "x") is None


def test_noisy_records_of_one_person_share_a_master(mpi):
    _, master, _ = mpi
    assert master["ehr", "a1"] == master["lab", "L1"] == master["billing", "B1"]
    assert master["adt", "P1"] == master["adt", "P2"]


def test_a_shared_phone_alone_does_not_match(mpi):
    _, master, _ = mpi
    assert master["billing", "B2"] != master["ehr", "a1"]


def test_every_record_has_exactly_one_master(mpi):
    stats, master, n = mpi
    assert len(master) == stats["records"] == n
    assert stats["masters"] == len(set(master.values())) == n - 3


def test_components_follow_chains_only(session):
    nodes = session.createDataFrame([(r,) for r in "abcde"], "rid STRING")
    edges = session.createDataFrame(
        [("a", "b"), ("c", "b"), ("d", "e")], "a_rid STRING, b_rid STRING"
    )
    labels, _ = NB.components(session, nodes, edges)
    assert dict(labels.collect()) == {"a": "a", "b": "a", "c": "a", "d": "d", "e": "d"}


def test_run_requires_run_id(session, tmp_path):
    with pytest.raises(ValueError):
        NB.run(session, "", str(tmp_path))


def test_pipeline_runs_mpi_after_silver():
    item = ROOT / "fabric" / "pl_land_sources.DataPipeline"
    activities = json.loads((item / "pipeline-content.json").read_text())["properties"][
        "activities"
    ]
    [notebook] = [a for a in activities if a["name"] == "run_nb_mpi"]
    assert [d["activity"] for d in notebook["dependsOn"]] == ["run_nb_silver"]
    assert notebook["typeProperties"]["parameters"]["run_id"]["value"] == "@pipeline().RunId"


# --- full population: needs `make silver` and `make mpi` ----------------------------------


@pytest.mark.stand
def test_mpi_meets_the_precision_and_recall_gates(session):
    result = mpi_eval.evaluate(
        session, ROOT / "data" / "lh_silver" / "Tables", ROOT / "data" / "sources" / "ground_truth"
    )
    assert result["records"] == result["records_linked_to_ground_truth"]
    assert result["precision"] >= mpi_eval.GATES["precision"], result
    assert result["recall"] >= mpi_eval.GATES["recall"], result
