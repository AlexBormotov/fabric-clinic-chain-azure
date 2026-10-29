"""U10 semantic model and report. Structural checks of the TMDL and PBIR in `fabric/` against Gold
(`sql/gold/`) and `GLOSSARY.md`; measure values are checked in the cloud run (U20)."""

import json
import re
import uuid
from pathlib import Path

import pytest

from clinic_chain import tmdl

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "fabric" / "sm_clinic_chain.SemanticModel"
REPORT = ROOT / "fabric" / "rpt_clinic_chain.Report"
# dim_patient columns that are not PHI; every other dim_patient column is.
NOT_PHI = {"master_patient_id", "sex", "home_clinic_id", "source_records"}
PHI_NAME = re.compile(r"given|family|first_name|last_name|birth|phone|address|postal|zip|ssn|email")
# Gold SQL type -> TMDL dataType a Direct Lake column may declare for it.
TYPES = {
    "varchar": "string",
    "char": "string",
    "int": "int64",
    "smallint": "int64",
    "bigint": "int64",
    "bit": "boolean",
    "date": "dateTime",
    "datetime2": "dateTime",
    "decimal": "double",
    "float": "double",
}


def gold_tables() -> dict[str, dict[str, str]]:
    """Columns and base types of every `CREATE TABLE gold.<name>` in sql/gold/."""
    tables = {}
    for path in sorted((ROOT / "sql" / "gold").glob("*.sql")):
        text = path.read_text()
        for name, body in re.findall(r"CREATE TABLE gold\.(\w+) \((.*?)\n\s*\);", text, re.S):
            tables[name] = dict(re.findall(r"^\s*(\w+) (\w+)", body, re.M))
    return tables


@pytest.fixture(scope="module")
def model() -> tmdl.Model:
    return tmdl.load(MODEL / "definition")


def test_parser_rejects_space_indentation():
    with pytest.raises(tmdl.TmdlError):
        tmdl.parse("table t\n    column c\n")


def test_model_parses_into_direct_lake_tables(model):
    assert model.tables
    for table in model.tables.values():
        assert len(table.partitions) == 1, table.name
        partition = table.partitions[0]
        assert partition["type"] == "entity", table.name
        assert partition["mode"] == "directLake", table.name
        assert partition["schemaName"] == "gold", table.name
        assert partition["entityName"] == table.name, table.name
        assert partition["expressionSource"] in model.expressions, table.name
    for expression in model.expressions.values():
        assert "AzureStorage.DataLake(" in expression
        assert "https://onelake.dfs.fabric.microsoft.com/" in expression


def test_model_columns_exist_in_gold(model):
    gold = gold_tables()
    for table in model.tables.values():
        source = gold[table.partitions[0]["entityName"]]
        for props in table.columns.values():
            column = props["sourceColumn"]
            assert column in source, (table.name, column)
            assert props["dataType"] == TYPES[source[column]], (table.name, column)


def test_model_has_no_phi_columns(model):
    phi = set(gold_tables()["dim_patient"]) - NOT_PHI
    assert phi >= {"given_name", "family_name", "birth_date", "phone", "postal_code"}
    for table in model.tables.values():
        for name, props in table.columns.items():
            assert props["sourceColumn"] not in phi, (table.name, name)
            assert not PHI_NAME.search(name.lower()), (table.name, name)


def test_every_glossary_metric_has_a_measure(model):
    metrics = re.findall(r"^\| `(\w+)` \|", (ROOT / "GLOSSARY.md").read_text(), re.M)
    assert len(metrics) == 8
    measures = {m for t in model.tables.values() for m in t.measures}
    assert set(metrics) <= measures


def test_dax_references_resolve(model):
    names = {(t.name, c) for t in model.tables.values() for c in [*t.columns, *t.measures]}
    measures = {m for t in model.tables.values() for m in t.measures}
    expressions = [m for t in model.tables.values() for m in t.measures.values()]
    expressions += [f for role in model.roles.values() for f in role.filters.values()]
    for dax in expressions:
        for table, column in re.findall(r"\b(\w+)\[(\w+)\]", dax):
            assert (table, column) in names, (table, column)
        for bare in re.findall(r"(?<![\w\]])\[(\w+)\]", dax):
            columns = {c for t in model.tables.values() for c in t.columns}
            assert bare in measures or bare in columns, bare


def test_relationships_join_model_columns(model):
    assert model.relationships
    for rel in model.relationships:
        for end in ("fromColumn", "toColumn"):
            table, column = rel[end].split(".")
            assert column in model.tables[table].columns, rel[end]
        assert rel["toColumn"].split(".")[0].startswith("dim_"), rel


def test_clinic_role_filters_by_user(model):
    role = model.roles["clinic"]
    assert role.permission == "read"
    assert "USERPRINCIPALNAME()" in role.filters["dim_clinic"]
    assert "user_clinic[clinic_id]" in role.filters["dim_clinic"]
    # Facts reach the role's filter through their relationship to dim_clinic.
    filtered = {
        rel["fromColumn"].split(".")[0]
        for rel in model.relationships
        if rel["toColumn"] == "dim_clinic.clinic_id"
    }
    facts = {t for t in model.tables if t.startswith("fact_")}
    assert facts <= filtered


def test_report_fields_exist_in_the_model(model):
    pbir = json.loads((REPORT / "definition.pbir").read_text())
    assert (REPORT / pbir["datasetReference"]["byPath"]["path"]).resolve() == MODEL.resolve()
    pages = json.loads((REPORT / "definition" / "pages" / "pages.json").read_text())
    assert pages["pageOrder"] == ["occupancy", "quality", "economics"]
    names = {(t.name, c) for t in model.tables.values() for c in [*t.columns, *t.measures]}
    visuals = list((REPORT / "definition" / "pages").glob("*/visuals/*/visual.json"))
    assert visuals
    shown = set()
    for path in visuals:
        for field in re.findall(r'"queryRef": "(\w+)\.(\w+)"', path.read_text()):
            assert field in names, (path.parent.name, field)
            shown.add(field[1])
    metrics = re.findall(r"^\| `(\w+)` \|", (ROOT / "GLOSSARY.md").read_text(), re.M)
    assert set(metrics) <= shown


def test_platform_logical_ids():
    ids = []
    for path in sorted((ROOT / "fabric").glob("*/.platform")):
        ids.append(uuid.UUID(json.loads(path.read_text())["config"]["logicalId"]))
    assert len(ids) == len(set(ids))
    for item in (MODEL, REPORT):
        logical = json.loads((item / ".platform").read_text())["config"]["logicalId"]
        assert uuid.UUID(logical).version == 4, item.name
