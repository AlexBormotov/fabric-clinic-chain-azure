"""U12 Eventhouse model. Fast tests check the KQL database item for consistency and that the
scripted scenario agrees with the batch bed history; the `kusto` tests run the schema on the Kusto
emulator (`make kql-test`)."""

import json
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ITEM = ROOT / "fabric" / "kqldb_beds.KQLDatabase"
SCRIPT = (ITEM / "DatabaseSchema.kql").read_text(encoding="utf-8")
EMULATOR = "http://kusto:8080"
DB = "kqldb_beds"

T1 = datetime(2026, 1, 1, 8)
T2, T3, T4 = T1 + timedelta(hours=5), T1 + timedelta(days=1), T1 + timedelta(days=2)
BEDS = [
    ("boston", "Boston", "ICU", "Intensive care", "BOS-ICU-01"),
    ("boston", "Boston", "ICU", "Intensive care", "BOS-ICU-02"),
    ("boston", "Boston", "MED", "Medicine", "BOS-MED-01"),
    ("boston", "Boston", "MED", "Medicine", "BOS-MED-02"),
    ("boston", "Boston", "MED", "Medicine", "BOS-MED-03"),
    ("boston", "Boston", "MED", "Medicine", "BOS-MED-04"),
    ("boston", "Boston", "SURG", "Surgery", "BOS-SURG-01"),
]
# (event_id, type, time, stay, ward, bed, from_ward, from_bed). S1 is discharged from MED-01 at
# T3, the instant S3 takes it; S2 moves ICU-01 -> MED-02; S4 leaves MED-03; SURG gets no event.
EVENTS = {
    1: ("A01", T1, "S1", "MED", "BOS-MED-01", None, None),
    2: ("A01", T1, "S2", "ICU", "BOS-ICU-01", None, None),
    3: ("A02", T2, "S2", "MED", "BOS-MED-02", "ICU", "BOS-ICU-01"),
    4: ("A03", T3, "S1", "MED", "BOS-MED-01", None, None),
    5: ("A01", T3, "S3", "MED", "BOS-MED-01", None, None),
    6: ("A01", T2, "S4", "MED", "BOS-MED-03", None, None),
    7: ("A03", T4, "S4", "MED", "BOS-MED-03", None, None),
    8: ("A01", T4, "S5", "ICU", "BOS-ICU-02", None, None),
    9: ("A01", T1, "S6", "MED", "BOS-MED-04", None, None),
}
CURRENT = {  # bed -> (occupied, stay_id)
    "BOS-ICU-01": (False, None),
    "BOS-ICU-02": (True, "S5"),
    "BOS-MED-01": (True, "S3"),
    "BOS-MED-02": (True, "S2"),
    "BOS-MED-03": (False, None),
    "BOS-MED-04": (True, "S6"),
}
OCCUPANCY = {"ICU": (2, 1, 0.5), "MED": (4, 3, 0.75), "SURG": (1, 0, 0.0)}
# Arrival orders, one ingest per batch. Late: 3 before 2, 5 before 4, 7 before 6.
IN_ORDER = [[1, 2, 9], [3, 6], [4, 5], [7, 8]]
LATE = [[1, 9], [3], [5, 6], [4, 7, 8], [2]]
DUPLICATE = [[1, 2, 9], [3, 6, 2], [4, 5, 3], [7, 8, 4, 5], [7, 1]]
REVERSED = [[9, 8, 7], [6, 5, 4], [3, 2, 1]]


def body(event_id: int) -> dict:
    """The event as the replay producer sends it (contract row as JSON)."""
    kind, at, stay, ward, bed, from_ward, from_bed = EVENTS[event_id]
    return {
        "event_id": event_id,
        "event_type": kind,
        "event_time": at.strftime("%Y-%m-%d %H:%M:%S"),
        "clinic_id": "boston",
        "stay_id": stay,
        "adt_patient_id": "P" + stay[1:],
        "ward_id": ward,
        "bed_id": bed,
        "from_ward_id": from_ward,
        "from_bed_id": from_bed,
    }


def commands(script: str) -> list[str]:
    """Commands of a database script: blocks separated by blank lines, comments dropped."""
    lines = [ln for ln in script.splitlines() if not ln.lstrip().startswith("//")]
    blocks = "\n".join(lines).split("\n\n")
    return [b.strip() for b in blocks if b.strip()]


def tables(script: str) -> dict[str, list[tuple[str, str]]]:
    found = {}
    for cmd in commands(script):
        m = re.match(r"\.create-merge table (\w+) \((.*)\)$", cmd)
        if m:
            found[m[1]] = [tuple(c.strip().split(":")) for c in m[2].split(",")]
    return found


def functions(script: str) -> dict[str, str]:
    found = {}
    for cmd in commands(script):
        m = re.match(r"\.create-or-alter function with \(.*?\) (\w+)\(\) \{(.*)\}$", cmd, re.S)
        if m:
            found[m[1]] = m[2]
    return found


# Fabric runs DatabaseSchema.kql on sync and accepts only these commands (Learn, read 2026-10-29).
ALLOWED = (
    r"\.create-merge table \w+ \(",
    r"\.create-or-alter function ",
    r"\.alter table \w+ policy update ",
    r"\.create-or-alter table \w+ ingestion json mapping ",
)


def test_script_uses_only_commands_fabric_syncs():
    for cmd in commands(SCRIPT):
        assert any(re.match(p, cmd) for p in ALLOWED), cmd


def test_tables_follow_the_contracts():
    kusto = {"int": "long", "string": "string", "datetime": "datetime"}
    contracts = ROOT / "docs" / "contracts"
    adt = yaml.safe_load((contracts / "adt.yaml").read_text())["tables"]["events"]["columns"]
    beds = yaml.safe_load((contracts / "sharepoint.yaml").read_text())["tables"]["beds"]
    found = tables(SCRIPT)
    assert found["adt_event"] == [(c["name"], kusto[c["type"]]) for c in adt] + [
        ("ingested_at", "datetime")
    ]
    assert found["bed"] == [(c["name"], kusto[c["type"]]) for c in beds["columns"]]
    assert found["adt_raw"] == [("payload", "dynamic")]


def test_functions_reference_only_defined_objects():
    known_tables, known_functions = set(tables(SCRIPT)), functions(SCRIPT)
    builtins = {"ingestion_time", "count"}
    for name, text in known_functions.items():
        calls = set(re.findall(r"(\w+)\(\)", text)) - builtins
        assert calls <= set(known_functions) - {name}, (name, calls)
        # A tabular source stands alone on its line, after an optional "(".
        sources = set(re.findall(r"^\s*\(?(\w+)\s*$", text, re.M)) - {"union"}
        assert sources <= known_tables, (name, sources)
        assert sources or calls, name


def test_update_policy_and_mapping_wire_raw_to_typed():
    policy = re.search(r"\.alter table (\w+) policy update @'(.*)'", SCRIPT)
    assert policy[1] == "adt_event"
    (rule,) = json.loads(policy[2])
    assert rule["Source"] == "adt_raw" and rule["IsEnabled"] and rule["IsTransactional"]
    assert rule["Query"].removesuffix("()") in functions(SCRIPT)
    mapping = re.search(
        r"\.create-or-alter table (\w+) ingestion json mapping '(\w+)' '(.*)'", SCRIPT
    )
    assert mapping[1] == "adt_raw" and mapping[2] == "adt_raw_json"
    assert json.loads(mapping[3]) == [{"column": "payload", "path": "$", "datatype": "dynamic"}]


def test_item_files():
    platform = json.loads((ITEM / ".platform").read_text())
    assert platform["metadata"]["type"] == "KQLDatabase"
    assert platform["metadata"]["displayName"] == ITEM.name.split(".")[0]
    uuid.UUID(platform["config"]["logicalId"])
    props = json.loads((ITEM / "DatabaseProperties.json").read_text())
    assert props["databaseType"] == "ReadWrite"
    uuid.UUID(props["parentEventhouseItemId"])


def test_scenario_agrees_with_batch_bed_history(tmp_path):
    """The expected current state is the open interval of nb_bed_history for the same events."""
    from clinic_chain import spark

    session = spark.session()
    schema = (
        "event_id INT, event_type STRING, event_time TIMESTAMP, clinic_id STRING, stay_id STRING,"
        " adt_patient_id STRING, ward_id STRING, bed_id STRING, from_ward_id STRING,"
        " from_bed_id STRING"
    )
    rows = [
        (i, kind, at, "boston", stay, "P" + stay[1:], ward, bed, fw, fb)
        for i, (kind, at, stay, ward, bed, fw, fb) in EVENTS.items()
    ]
    session.createDataFrame(rows, schema).write.format("delta").save(str(tmp_path / "adt_event"))
    spark.notebook("nb_bed_history").run(session, "kql", str(tmp_path))
    history = session.read.format("delta").load(str(tmp_path / "bed_state_history"))
    current = {r.bed_id: (r.occupied, r.stay_id) for r in history.where("is_current").collect()}
    assert current == CURRENT


# --- Kusto emulator ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kusto():
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

    client = KustoClient(KustoConnectionStringBuilder.with_no_authentication(EMULATOR))
    deadline, started = time.monotonic() + 300, time.monotonic()
    while True:
        try:
            client.execute_mgmt("NetDefaultDB", ".show cluster")
            break
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(5)
    print(f"emulator ready after {time.monotonic() - started:.0f} s")
    client.execute_mgmt("NetDefaultDB", f".create database {DB} volatile ifnotexists")
    result = client.execute_mgmt(DB, ".execute database script <|\n" + SCRIPT)
    states = [(r["CommandText"][:60], r["Result"]) for r in result.primary_results[0]]
    assert all(s == "Completed" for _, s in states), states
    client.execute_mgmt(DB, ".clear table bed data")
    rows = "\n".join(",".join(b) for b in BEDS)
    client.execute_mgmt(DB, ".ingest inline into table bed <|\n" + rows)
    yield client
    client.close()


def stream(client, batches: list[list[int]]) -> None:
    """Fresh tables, then one JSON ingest into adt_raw per batch, as Eventstream would deliver."""
    for table in ("adt_raw", "adt_event"):
        client.execute_mgmt(DB, f".clear table {table} data")
    for batch in batches:
        lines = "\n".join(json.dumps(body(i)) for i in batch)
        client.execute_mgmt(
            DB,
            ".ingest inline into table adt_raw with (format='json', "
            "ingestionMappingReference='adt_raw_json') <|\n" + lines,
        )


def query(client, text: str) -> list[dict]:
    return [r.to_dict() for r in client.execute_query(DB, text).primary_results[0]]


@pytest.mark.kusto
@pytest.mark.parametrize(
    "batches",
    [IN_ORDER, LATE, DUPLICATE, REVERSED],
    ids=["in-order", "late", "duplicate", "out-of-order"],
)
def test_current_state_and_occupancy(kusto, batches):
    stream(kusto, batches)
    sends = sum(len(b) for b in batches)
    (typed,) = query(kusto, "adt_event | summarize rows = count(), ids = dcount(event_id)")
    assert typed == {"rows": sends, "ids": len(EVENTS)}  # the update policy typed every send
    current = {
        r["bed_id"]: (r["occupied"], r["stay_id"] or None) for r in query(kusto, "bed_current()")
    }
    assert current == CURRENT
    occupancy = {
        r["ward_id"]: (r["beds"], r["occupied_beds"], r["occupancy"])
        for r in query(kusto, "ward_occupancy()")
    }
    assert occupancy == OCCUPANCY


@pytest.mark.kusto
def test_parse_keeps_contract_values(kusto):
    stream(kusto, [[3]])
    (row,) = query(kusto, "adt_event | project-away ingested_at")
    expected = body(3) | {"event_time": T2, "from_ward_id": "ICU", "from_bed_id": "BOS-ICU-01"}
    assert {k: (v.replace(tzinfo=None) if k == "event_time" else v) for k, v in row.items()} == (
        expected
    )
    (lag,) = query(kusto, "adt_event | project s = datetime_diff('second', now(), ingested_at)")
    assert 0 <= lag["s"] < 600
