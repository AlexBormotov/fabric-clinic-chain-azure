"""U15 data quality. Fast tests verify the Soda contracts of the Fabric notebook on fixture Silver
tables; the `stand` test runs them on the Silver built by `make silver`."""

import json
import re
import tomllib
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from clinic_chain import spark

ROOT = Path(__file__).resolve().parents[1]
NB = spark.notebook("nb_quality")
T0, T1 = datetime(2025, 1, 2, 3, 0), datetime(2025, 1, 2, 4, 0)
CLEAN = {
    "patient_record": (
        "system STRING, local_patient_id STRING, clinic_id STRING, sex STRING, phone STRING,"
        " birth_date DATE",
        [
            ("ehr", "p1", "boston", "F", "5550000001", date(1980, 1, 1)),
            ("lab", "L1", "boston", "F", None, date(1980, 1, 1)),
        ],
    ),
    "encounter": (
        "encounter_id STRING, fhir_patient_id STRING, class_code STRING, start_at TIMESTAMP,"
        " end_at TIMESTAMP",
        [("e1", "p1", "AMB", T0, T1)],
    ),
    "condition": (
        "condition_id STRING, encounter_id STRING",
        [("c1", "e1"), ("c2", None)],
    ),
    "lab_result": (
        "result_id STRING, lab_patient_id STRING, value_numeric DECIMAL(20,8)",
        [("r1", "L1", Decimal("1.5")), ("r2", "L1", None)],
    ),
    "claim": (
        "claim_id STRING, billed_amount DECIMAL(12,2), paid_amount DECIMAL(12,2), status STRING,"
        " denial_reason STRING",
        [
            ("cl1", Decimal("10"), Decimal("8"), "paid", None),
            ("cl2", Decimal("5"), Decimal("0"), "denied", "CO-50"),
        ],
    ),
    "claim_line": (
        "claim_id STRING, line_no INT, amount DECIMAL(12,2)",
        [("cl1", 1, Decimal("10")), ("cl1", 2, Decimal("0"))],
    ),
    "adt_event": ("event_id INT, event_type STRING, bed_id STRING", [(1, "A01", "b1")]),
    "ed_visit": (
        "ed_visit_id STRING, arrival_at TIMESTAMP, triage_at TIMESTAMP,"
        " provider_seen_at TIMESTAMP, departure_at TIMESTAMP",
        [("v1", T0, T0, T1, T1)],
    ),
    "bed": ("bed_id STRING", [("b1",)]),
}


@pytest.fixture(scope="module")
def session():
    return spark.session()


def silver(session, root: Path, extra_encounters: list[tuple] = ()) -> str:
    for table, (schema, rows) in CLEAN.items():
        if table == "encounter":
            rows = rows + list(extra_encounters)
        session.createDataFrame(rows, schema).write.format("delta").save(str(root / table))
    return str(root)


def test_clean_silver_passes_every_check(session, tmp_path):
    result = NB.run(session, "r1", silver(session, tmp_path))
    assert result["failed"] == []
    assert result["ok"]
    assert result["checks"] == 48
    assert {r[3] for r in result["results"]} == {"PASSED"}


@pytest.mark.parametrize("patient", ["ghost", "L1"], ids=["unknown", "lab_only"])
def test_one_orphaned_encounter_fails_the_referential_check(session, tmp_path, patient):
    """Negative control: an encounter whose patient is unknown, or exists only outside the EHR."""
    orphan = ("e2", patient, "AMB", T0, T1)
    result = NB.run(session, "r1", silver(session, tmp_path, [orphan]))
    assert not result["ok"]
    assert result["failed"] == [("encounter", "failed_rows.ehr_patient")]
    [check] = [r for r in result["results"] if r[1] == "failed_rows.ehr_patient"]
    assert check[4]["failed_rows_count"] == 1


def test_a_contract_that_does_not_evaluate_fails(session, tmp_path):
    broken = {"bed": {"columns": [{"name": "no_such_column", "checks": [{"missing": None}]}]}}
    result = NB.run(session, "r1", silver(session, tmp_path), broken)
    assert not result["ok"]
    assert result["failed"]


def test_run_requires_run_id(session, tmp_path):
    with pytest.raises(ValueError):
        NB.run(session, "", str(tmp_path))


def test_notebook_installs_the_locked_soda_versions():
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    pinned = {d for d in deps if d.startswith("soda-")}
    source = (ROOT / "fabric" / "nb_quality.Notebook" / "notebook-content.py").read_text()
    [install] = re.findall(r"^# MAGIC %pip install (.+)$", source, re.M)
    assert set(install.split()) == pinned == {"soda-core==4.29.0", "soda-sparkdf==4.29.0"}


def test_pipeline_runs_quality_after_silver_with_inline_install():
    item = ROOT / "fabric" / "pl_land_sources.DataPipeline"
    activities = json.loads((item / "pipeline-content.json").read_text())["properties"][
        "activities"
    ]
    [notebook] = [a for a in activities if a["name"] == "run_nb_quality"]
    assert notebook["type"] == "TridentNotebook"
    assert [d["activity"] for d in notebook["dependsOn"]] == ["run_nb_silver"]
    parameters = notebook["typeProperties"]["parameters"]
    assert parameters["run_id"]["value"] == "@pipeline().RunId"
    assert parameters["_inlineInstallationEnabled"] == {"value": True, "type": "bool"}


# --- full population: needs `make silver` --------------------------------------------------


@pytest.mark.stand
def test_full_silver_passes_every_check(session):
    result = NB.run(session, "stand", str(ROOT / "data" / "lh_silver" / "Tables"))
    assert result["failed"] == [], result["failed"]
    assert result["ok"] and result["checks"] == 48
