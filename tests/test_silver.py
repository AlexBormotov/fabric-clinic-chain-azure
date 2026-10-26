"""U06 Silver. Fast tests run the Fabric notebook on local Spark over tiny Bronze tables; `stand`
tests check the Silver built by `make silver` against Bronze and the raw FHIR files."""

import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pyspark.sql import functions as F

from clinic_chain import spark
from clinic_chain.sources import contracts

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = contracts.load(ROOT / "docs" / "contracts")
NB = spark.notebook("nb_silver")
BRONZE = spark.notebook("nb_bronze")
SAMPLE = {
    "string": "x",
    "int": "7",
    "decimal": "1.50",
    "date": "2025-01-02",
    "datetime": "2025-01-02 03:04:05",
}
SPARK_TYPE = {
    "string": "string",
    "int": "int",
    "decimal": "decimal",
    "date": "date",
    "datetime": "timestamp",
}
PATIENT = {
    "given_name": " Ann  Marie ",
    "family_name": "Lee",
    "sex": "F",
    "phone": "+1 555 856 7458",
}


def concept(code: str, display: str) -> dict:
    return {"coding": [{"code": code, "display": display}]}


ENCOUNTER = {
    "resourceType": "Encounter",
    "id": "e1",
    "status": "finished",
    "class": {"code": "IMP"},
    "type": [concept("32485007", "Hospital admission")],
    "subject": {"reference": "urn:uuid:p1"},
    "period": {"start": "2025-01-02T05:04:05+02:00", "end": "2025-01-03T03:04:05+00:00"},
}
PATIENT_BUNDLE = [
    {
        "resourceType": "Patient",
        "id": "p1",
        "gender": "female",
        "birthDate": "1969-04-26",
        "name": [{"use": "official", "family": "Lee12", "given": ["Ann843"]}],
        "telecom": [{"system": "phone", "value": "555-856-7458"}],
        "address": [{"postalCode": "02132"}],
    },
    ENCOUNTER,
    ENCOUNTER,
    {**ENCOUNTER, "id": "e2", "period": {}},
    {
        "resourceType": "Condition",
        "id": "c1",
        "clinicalStatus": concept("active", None),
        "code": concept("44054006", "Diabetes"),
        "subject": {"reference": "urn:uuid:p1"},
        "encounter": {"reference": "urn:uuid:e1"},
        "onsetDateTime": "2025-01-02T03:04:05+00:00",
    },
    {
        "resourceType": "MedicationRequest",
        "id": "m1",
        "status": "active",
        "medicationCodeableConcept": concept("856987", "Acetaminophen"),
        "subject": {"reference": "urn:uuid:p1"},
        "authoredOn": "2025-01-02T03:04:05+00:00",
    },
    {
        "resourceType": "MedicationRequest",
        "id": "m2",
        "status": "active",
        "medicationReference": {"reference": "urn:uuid:med1"},
        "subject": {"reference": "urn:uuid:p1"},
        "authoredOn": "2025-01-02T03:04:05+00:00",
    },
    {"resourceType": "Medication", "id": "med1", "code": concept("389221", "Etonogestrel")},
    {"resourceType": "Observation", "id": "o1"},
    {"resourceType": "Claim", "id": "cl1"},
]


@pytest.fixture(scope="module")
def session():
    return spark.session()


def read(session, path: Path):
    return session.read.format("delta").load(str(path))


def bronze_rows(spec: dict, values: dict) -> tuple[list[dict], str]:
    """A valid row, its exact duplicate and a row whose first typed required column does not cast
    (or, with no typed column, whose first column is empty); returns the rows and that reason."""
    good = {c["name"]: SAMPLE[c["type"]] for c in spec["columns"]} | values
    typed = [c["name"] for c in spec["columns"] if c["type"] != "string" and not c.get("nullable")]
    column = typed[0] if typed else spec["columns"][0]["name"]
    bad = {**good, column: "n/a" if typed else None}
    return [good, dict(good), bad], f"invalid_{column}"


def write_bronze(session, root: Path) -> dict[str, str]:
    """Every Bronze table with fixture rows; returns the expected drop reason per Bronze table."""
    reasons = {}
    for name, spec in CONTRACTS.items():
        if name.startswith("ground_truth."):
            continue
        table = name.replace(".", "_")
        patients = table in {source for source, _ in NB.PATIENT_SOURCES.values()}
        rows, reasons[table] = bronze_rows(spec, PATIENT if patients else {})
        columns = [c["name"] for c in spec["columns"]]
        schema = ", ".join(f"`{c}` STRING" for c in columns)
        df = session.createDataFrame([[r[c] for c in columns] for r in rows], schema)
        df.select(
            "*",
            F.lit("r1").alias("_run_id"),
            F.lit(f"/landing/{table}/r1/file").alias("_source_file"),
            F.current_timestamp().alias("_ingested_at"),
        ).write.format("delta").save(str(root / table))
    bundles = [
        ("boston/p1.json", PATIENT_BUNDLE),
        ("boston/hospitalInformation1.json", [{"resourceType": "Organization", "id": "org1"}]),
    ]
    session.createDataFrame(
        [
            (json.dumps({"entry": [{"resource": r} for r in resources]}), f"/landing/fhir/r1/{f}")
            for f, resources in bundles
        ],
        "content STRING, _source_file STRING",
    ).write.format("delta").save(str(root / "fhir_bundle"))
    return reasons


@pytest.fixture(scope="module")
def silver(session, tmp_path_factory):
    root = tmp_path_factory.mktemp("silver")
    reasons = write_bronze(session, root / "bronze")
    counts = NB.run(session, "r1", str(root / "bronze"), str(root / "silver"))
    return root / "silver", reasons, counts


def reconciliation(session, tables: Path) -> dict[tuple, dict]:
    """(silver_table, source) -> {"input": n, "output": n, "dropped": {reason: n}}."""
    out: dict[tuple, dict] = {}
    for r in read(session, tables / "reconciliation").collect():
        entry = out.setdefault((r.silver_table, r.source), {"dropped": {}})
        if r.measure == "dropped":
            entry["dropped"][r.reason] = r.rows
        else:
            entry[r.measure] = r.rows
    return out


def test_reconciliation_counts_every_row(session, silver):
    tables, reasons, counts = silver
    report = reconciliation(session, tables)
    csv_part = {"input": 3, "output": 1}
    expected = {
        (table, source): {**csv_part, "dropped": {"exact_duplicate": 1, reasons[source]: 1}}
        for table, (source, _) in NB.TABLES.items()
    }
    for source, _ in NB.PATIENT_SOURCES.values():
        expected["patient_record", source] = {
            **csv_part,
            "dropped": {"exact_duplicate": 1, reasons[source]: 1},
        }
    expected |= {
        ("patient_record", "fhir_bundle:Patient"): {"input": 1, "output": 1, "dropped": {}},
        ("encounter", "fhir_bundle:Encounter"): {
            "input": 3,
            "output": 1,
            "dropped": {"exact_duplicate": 1, "invalid_start_at": 1},
        },
        ("condition", "fhir_bundle:Condition"): {"input": 1, "output": 1, "dropped": {}},
        ("medication_request", "fhir_bundle:MedicationRequest"): {
            "input": 2,
            "output": 2,
            "dropped": {},
        },
    }
    for kind in ("Medication", "Observation", "Claim", "Organization"):
        expected[None, f"fhir_bundle:{kind}"] = {
            "input": 1,
            "output": 0,
            "dropped": {"out_of_scope": 1},
        }
    assert report == expected
    assert counts["patient_record"] == 4
    assert counts == {t: read(session, tables / t).count() for t in counts}


def test_every_bronze_table_feeds_silver():
    used = {source for source, _ in NB.TABLES.values()}
    used |= {source for source, _ in NB.PATIENT_SOURCES.values()} | {"fhir_bundle"}
    assert used == set(BRONZE.SOURCES)


def test_columns_follow_the_contracts():
    for source, columns in NB.TABLES.values():
        spec = CONTRACTS[source.replace("_", ".", 1)]
        assert [(n, k.partition("(")[0], r) for n, k, r in columns] == [
            (c["name"], SPARK_TYPE[c["type"]], not c.get("nullable")) for c in spec["columns"]
        ]
    for source, id_column in NB.PATIENT_SOURCES.values():
        names = [c["name"] for c in CONTRACTS[source.replace("_", ".", 1)]["columns"]]
        assert names[0] == id_column
        assert set(names[1:]) <= {c for c, _, _ in NB.PATIENT_COLUMNS}


def test_types_are_cast_and_timestamps_are_utc(session, silver):
    tables = silver[0]
    lab = read(session, tables / "lab_result").first()
    assert lab.collected_at == datetime(2025, 1, 2, 3, 4, 5)
    assert lab.value_numeric == Decimal("1.50")
    claim = dict(read(session, tables / "claim").dtypes)
    assert claim["billed_amount"] == "decimal(12,2)"
    assert claim["service_start"] == "timestamp"
    assert read(session, tables / "roster").first().shifts_planned == 7
    encounter = read(session, tables / "encounter").first()
    assert (encounter.start_at, encounter.class_code) == (datetime(2025, 1, 2, 3, 4, 5), "IMP")


def test_patient_records_are_standardized_not_matched(session, silver):
    rows = {r.system: r for r in read(session, silver[0] / "patient_record").collect()}
    assert set(rows) == {"fhir", "lab", "adt", "billing"}
    for system in ("lab", "adt", "billing"):
        assert (rows[system].given_name, rows[system].phone) == ("Ann Marie", "5558567458")
    fhir = rows["fhir"]
    assert (fhir.local_patient_id, fhir.clinic_id, fhir.given_name, fhir.family_name) == (
        "p1",
        "boston",
        "Ann",
        "Lee",
    )
    assert (fhir.birth_date, fhir.sex, fhir.phone, fhir.postal_code) == (
        date(1969, 4, 26),
        "F",
        "5558567458",
        "02132",
    )
    assert rows["lab"].postal_code is None


def test_fhir_facts_link_patient_and_encounter(session, silver):
    tables = silver[0]
    condition = read(session, tables / "condition").first()
    assert (condition.fhir_patient_id, condition.encounter_id, condition.code) == (
        "p1",
        "e1",
        "44054006",
    )
    medications = read(session, tables / "medication_request").collect()
    assert {(m.medication_request_id, m.medication_code) for m in medications} == {
        ("m1", "856987"),
        ("m2", "389221"),
    }


def test_run_requires_run_id(session, tmp_path):
    with pytest.raises(ValueError):
        NB.run(session, "", str(tmp_path), str(tmp_path))


def test_pipeline_runs_silver_after_bronze():
    item = ROOT / "fabric" / "pl_land_sources.DataPipeline"
    activities = json.loads((item / "pipeline-content.json").read_text())["properties"][
        "activities"
    ]
    [notebook] = [a for a in activities if a["name"] == "run_nb_silver"]
    assert notebook["type"] == "TridentNotebook"
    assert [d["activity"] for d in notebook["dependsOn"]] == ["run_nb_bronze"]
    assert notebook["typeProperties"]["parameters"]["run_id"]["value"] == "@pipeline().RunId"


# --- full population: needs `make bronze` and `make silver` -------------------------------


def fhir_resource_counts() -> Counter:
    counts = Counter()
    for path in (ROOT / "data" / "raw" / "fhir").glob("*/fhir/*.json"):
        counts.update(e["resource"]["resourceType"] for e in json.loads(path.read_bytes())["entry"])
    return counts


@pytest.mark.stand
def test_silver_reconciles_with_bronze_and_raw_fhir(session):
    report = reconciliation(session, ROOT / "data" / "lh_silver" / "Tables")
    for part in report.values():
        assert part["input"] == part["output"] + sum(part["dropped"].values())
    fhir = {s.partition(":")[2]: p["input"] for (_, s), p in report.items() if ":" in s}
    assert fhir == fhir_resource_counts()
    bronze = ROOT / "data" / "lh_bronze" / "Tables"
    for (_, source), part in report.items():
        if ":" not in source:
            assert part["input"] == read(session, bronze / source).count()
