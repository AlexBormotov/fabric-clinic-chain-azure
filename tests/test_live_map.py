"""U14 live bed map and alert. Fast tests check the Real-Time Dashboard against its published
schema, the Activator definition's wiring and threshold, and the bed reference loader; the `kusto`
tests run every dashboard and alert query and the loader on the Kusto emulator (`make kql-test`)."""

import json
import re
import uuid
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_kql import (
    BEDS,
    DB,
    EMULATOR,
    EVENTS,
    IN_ORDER,
    OCCUPANCY,
    SCRIPT,
    functions,
    query,
    stream,
    tables,
)
from test_kql import kusto as kusto  # noqa: F401 (module fixture: emulator database with the schema)

ROOT = Path(__file__).resolve().parents[1]
FABRIC = ROOT / "fabric"
DASHBOARD = json.loads((FABRIC / "rtd_beds.KQLDashboard" / "RealTimeDashboard.json").read_text())
REFLEX = json.loads((FABRIC / "act_ward_occupancy.Reflex" / "ReflexEntities.json").read_text())
SCHEMAS = ROOT / "tests" / "schemas" / "kql-dashboard-89"
THRESHOLD = 0.90
ZERO = "00000000-0000-0000-0000-000000000000"
BUILTINS = {"now"}


def schema_validator() -> Draft202012Validator:
    """The vendored schema set; each file's relative $id resolves the others' $refs."""
    resources = []
    for path in SCHEMAS.glob("*.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append((contents["$id"], Resource.from_contents(contents)))
    registry = Registry().with_resources(resources)
    root = registry.contents("/static/d/schema/89/dashboard.json")
    return Draft202012Validator(
        root, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER
    )


def deployed(dashboard: dict) -> dict:
    """As fabric-cicd 1.4.0 sends it: an empty clusterUri filled with the database's query URI."""
    copy = json.loads(json.dumps(dashboard))
    for source in copy["dataSources"]:
        source["clusterUri"] = source["clusterUri"] or "https://trd-x.z0.kusto.fabric.microsoft.com"
    return copy


def instance(entity: dict) -> dict:
    return json.loads(entity["payload"]["definition"]["instance"])


def by_type(kind: str) -> list[dict]:
    return [e for e in REFLEX if e["type"] == kind]


[SOURCE] = by_type("kqlSource-v1")
ALERT_QUERY = SOURCE["payload"]["query"]["queryString"]
[RULE] = [e for e in by_type("timeSeriesView-v1") if e["payload"]["definition"]["type"] == "Rule"]
DASHBOARD_QUERIES = {
    tile["title"]: next(
        q["text"] for q in DASHBOARD["queries"] if q["id"] == tile["queryRef"]["queryId"]
    )
    for tile in DASHBOARD["tiles"]
}


def rows(step: dict, name: str) -> list[dict]:
    return [r for r in step["rows"] if r["name"] == name]


# --- Dashboard ----------------------------------------------------------------------------------


def test_dashboard_matches_published_schema():
    errors = [e.message for e in schema_validator().iter_errors(deployed(DASHBOARD))]
    assert errors == []


def test_dashboard_binds_to_kqldb_beds_for_fabric_cicd():
    [source] = DASHBOARD["dataSources"]
    # fabric-cicd fills an empty clusterUri from the deployed KQL database of the same name.
    assert (source["kind"], source["name"], source["clusterUri"]) == (
        "kusto-trident",
        "kqldb_beds",
        "",
    )
    assert source["databaseArtifactId"] == source["database"] == source["workspace"] == ZERO
    assert (FABRIC / "kqldb_beds.KQLDatabase").is_dir()


def test_dashboard_refreshes_at_the_shortest_interval():
    properties = json.loads((SCHEMAS / "dashboard.json").read_text())["properties"]
    live = next(
        o for o in properties["changeDetection"]["oneOf"] if "minRefreshRate" in o["properties"]
    )
    floors = {k: v["enum"][0] for k, v in live["properties"].items() if "enum" in v}
    assert floors == {
        "minRefreshRate": "10s",
        "minRefreshRate_V2": "5s",
        "fallbackRefreshRate": "30s",
    }
    assert DASHBOARD["changeDetection"] == {"kind": "liveUpdates"} | floors
    assert DASHBOARD["autoRefresh"]["enabled"] is True


def test_dashboard_has_the_live_map_tiles():
    assert set(DASHBOARD_QUERIES) == {"Ward occupancy", "Bed state", "Newest event"}
    assert "ward_occupancy()" in DASHBOARD_QUERIES["Ward occupancy"]
    assert "bed_current()" in DASHBOARD_QUERIES["Bed state"]
    assert "ingested_at" in DASHBOARD_QUERIES["Newest event"]


@pytest.mark.parametrize(
    "text", [*DASHBOARD_QUERIES.values(), ALERT_QUERY], ids=[*DASHBOARD_QUERIES, "alert"]
)
def test_queries_name_only_objects_in_the_database_schema(text):
    known_functions, known_tables = set(functions(SCRIPT)), set(tables(SCRIPT))
    calls = set(re.findall(r"\b(\w+)\(\)", text)) - BUILTINS
    assert calls <= known_functions, calls - known_functions
    first = re.match(r"\s*(\w+)", text)[1]
    assert first in known_functions | known_tables, first


# --- Activator ----------------------------------------------------------------------------------


def test_alert_fires_when_occupancy_crosses_090():
    steps = {s["name"]: s for s in instance(RULE)["steps"]}
    [field] = rows(steps["EventDetectStep"], "EventFieldSelector")
    [becomes] = rows(steps["EventDetectStep"], "NumberBecomes")
    args = {a["name"]: a["value"] for a in becomes["arguments"]}
    assert args == {"op": "BecomesGreaterThan", "value": THRESHOLD}
    assert field["arguments"][0]["value"] == "max_occupancy"
    assert "max_occupancy = max(occupancy)" in ALERT_QUERY
    # The threshold lives in the rule only: the source returns every ward's data.
    assert "0.9" not in ALERT_QUERY
    assert RULE["payload"]["definition"]["settings"]["shouldRun"] is True


def test_alert_posts_to_teams_with_a_placeholder_recipient():
    [act] = [s for s in instance(RULE)["steps"] if s["name"] == "ActStep"]
    [teams] = act["rows"]
    args = {a["name"]: a for a in teams["arguments"]}
    assert teams["kind"] == "TeamsMessage"
    assert args["recipients"]["values"] == [{"type": "string", "value": "alerts@example.com"}]
    fields = [
        ref["arguments"][0]["value"]
        for pair in args["additionalInformation"]["values"]
        for ref in pair["arguments"]
        if ref.get("kind") == "EventFieldReference"
    ]
    assert fields == ["max_occupancy", "top_wards"]


def test_alert_source_is_kqldb_beds_in_snapshot_mode():
    payload = SOURCE["payload"]
    assert payload["eventhouseItem"] == {
        "itemId": ZERO,
        "workspaceId": ZERO,
        "itemType": "KustoDatabase",
    }
    assert payload["metadata"]["workspaceId"] == ZERO
    assert payload["queryParameters"] == [] and "eventTimeSettings" not in payload
    assert "\n" not in ALERT_QUERY  # Activator's API mishandles newlines in KQL source queries


def test_reflex_references_resolve():
    ids = [e["uniqueIdentifier"] for e in REFLEX]
    assert len(ids) == len(set(ids)) and all(uuid.UUID(i) for i in ids)
    kinds = {e["uniqueIdentifier"]: e["type"] for e in REFLEX}
    [container] = by_type("container-v1")
    for entity in REFLEX:
        if entity is not container:
            target = entity["payload"]["parentContainer"]["targetUniqueIdentifier"]
            assert target == container["uniqueIdentifier"]
    expected = {"SourceEvent": "kqlSource-v1", "EventTrigger": "timeSeriesView-v1"}
    for entity in by_type("timeSeriesView-v1"):
        body = instance(entity)
        assert body["templateVersion"] == "1.2.4"
        refs = re.findall(
            r'"name":"entityId","type":"string","value":"([^"]+)"',
            json.dumps(body, separators=(",", ":")),
        )
        assert refs and all(kinds.get(r) == expected[body["templateId"]] for r in refs), refs
        assert all(uuid.UUID(step["id"]) for step in body["steps"])


# --- Items --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "folder, kind",
    [
        ("rtd_beds.KQLDashboard", "KQLDashboard"),
        ("act_ward_occupancy.Reflex", "Reflex"),
        ("nb_bed_reference.Notebook", "Notebook"),
    ],
)
def test_item_platform(folder, kind):
    meta = json.loads((FABRIC / folder / ".platform").read_text())
    assert meta["metadata"]["type"] == kind
    assert meta["metadata"]["displayName"] == folder.split(".")[0]
    logical = meta["config"]["logicalId"]
    others = [
        json.loads(p.read_text())["config"]["logicalId"]
        for p in FABRIC.glob("*/.platform")
        if p.parent.name != folder
    ]
    assert uuid.UUID(logical) and logical not in others


# --- Bed reference loader -----------------------------------------------------------------------


def loader():
    from clinic_chain import spark

    return spark.notebook("nb_bed_reference")


def test_loader_refuses_an_empty_bed_list():
    with pytest.raises(ValueError, match="no beds"):
        loader().command([])


def test_loader_command_quotes_values():
    text = loader().command([("c", 'O"Neil \\ Ward', "w", "Wär'd", "b")])
    assert text.startswith(".set-or-replace bed <| datatable(clinic_id:string, clinic_name:string,")
    assert '"O\\"Neil \\\\ Ward"' in text and '"Wär\'d"' in text


def test_loader_reads_silver_beds(tmp_path):
    from pyspark.sql import functions as F

    from clinic_chain import spark

    session = spark.session()
    columns = (
        "clinic_id STRING, clinic_name STRING, ward_id STRING, ward_name STRING, bed_id STRING"
    )
    beds = session.createDataFrame(list(reversed(BEDS)), columns).withColumn("extra", F.lit(1))
    beds.write.format("delta").save(str(tmp_path / "bed"))
    assert loader().bed_rows(session, str(tmp_path)) == sorted(BEDS, key=lambda b: b[4])


def test_pipeline_loads_beds_after_silver():
    item = FABRIC / "pl_land_sources.DataPipeline" / "pipeline-content.json"
    activities = json.loads(item.read_text())["properties"]["activities"]
    [activity] = [a for a in activities if a["name"] == "run_nb_bed_reference"]
    assert activity["type"] == "TridentNotebook"
    assert [d["activity"] for d in activity["dependsOn"]] == ["run_nb_silver"]


# --- Kusto emulator ---------------------------------------------------------------------------


@pytest.mark.kusto
def test_loader_replaces_the_bed_table(kusto):  # noqa: F811
    nb = loader()
    odd = [("boston", 'O"Neil', "ICU", "Intensive care", "BOS-ICU-01")]
    assert nb.load(odd, EMULATOR, DB) == 1
    assert query(kusto, "bed | project clinic_name") == [{"clinic_name": 'O"Neil'}]
    for _ in range(2):  # replaces, never appends
        assert nb.load(BEDS, EMULATOR, DB) == len(BEDS)
    assert query(kusto, "bed | count") == [{"Count": len(BEDS)}]
    stream(kusto, IN_ORDER)
    occupancy = {
        r["ward_id"]: (r["beds"], r["occupied_beds"], r["occupancy"])
        for r in query(kusto, "ward_occupancy()")
    }
    assert occupancy == OCCUPANCY


@pytest.mark.kusto
def test_dashboard_and_alert_queries_on_the_scenario(kusto):  # noqa: F811
    loader().load(BEDS, EMULATOR, DB)
    stream(kusto, IN_ORDER)
    wards = query(kusto, DASHBOARD_QUERIES["Ward occupancy"])
    assert [(w["ward_name"], w["occupancy"]) for w in wards] == [
        ("Medicine", 0.75),
        ("Intensive care", 0.5),
        ("Surgery", 0.0),
    ]
    beds = {b["bed_id"]: b["state"] for b in query(kusto, DASHBOARD_QUERIES["Bed state"])}
    assert len(beds) == len(BEDS) and beds["BOS-SURG-01"] == "free"
    assert beds["BOS-MED-01"] == "occupied" and beds["BOS-ICU-01"] == "free"
    [newest] = query(kusto, DASHBOARD_QUERIES["Newest event"])
    assert newest["event_id"] in EVENTS and 0 <= newest["lag_s"] < 600
    [alert] = query(kusto, ALERT_QUERY)
    assert alert["max_occupancy"] == 0.75 and alert["max_occupancy"] <= THRESHOLD
    assert alert["top_wards"].count(";") == 2 and "Medicine 0.75" in alert["top_wards"]
