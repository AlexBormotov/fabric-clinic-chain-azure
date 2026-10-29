"""U17 OneLake security on lh_silver and RLS membership. Fast checks of the role definition that
Terraform applies (`infra/modules/fabric/lh_silver_roles.json`) against the Silver notebooks; the
effect in Fabric is verified in the cloud run (U20)."""

import json
import re
from pathlib import Path

import yaml

from clinic_chain import spark

ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "infra" / "modules" / "fabric" / "lh_silver_roles.json"
TERRAFORM = ROOT / "infra" / "modules" / "fabric" / "main.tf"
USER_CLINIC = ROOT / "sql" / "fabric" / "user_clinic.example.sql"
NB = spark.notebook("nb_silver")
# Direct identifiers and quasi-identifiers (HIPAA Safe Harbor), as U16 classifies Gold.
PHI_COLUMN = re.compile(r"given|family|(first|last)_name|birth|phone|address|postal|zip|ssn|email")


def definition() -> dict:
    return json.loads(ROLES.read_text())


def silver_tables() -> set[str]:
    """Every table a notebook writes under the Silver root."""
    tables = {*NB.TABLES, *NB.FHIR_TABLES.values()}
    for path in (ROOT / "fabric").glob("*.Notebook/notebook-content.py"):
        tables |= set(re.findall(r'f"\{silver_root\}/(\w+)"', path.read_text()))
    return tables


def silver_columns() -> dict[str, set[str]]:
    """Columns of the nb_silver tables, where every patient and staff attribute enters Silver."""
    columns = {table: {c for c, _, _ in spec} for table, (_, spec) in NB.TABLES.items()}
    columns["patient_record"] = {c for c, _, _ in NB.PATIENT_COLUMNS}
    for resource, table in NB.FHIR_TABLES.items():
        columns.setdefault(table, set()).update(c for c, _, _ in NB.FHIR_COLUMNS.get(resource, []))
    return columns


def test_every_silver_table_is_in_exactly_one_class():
    classes = definition()["tables"]
    assert set(classes) == {"phi", "non_phi"}
    phi, non_phi = set(classes["phi"]), set(classes["non_phi"])
    assert not phi & non_phi, phi & non_phi
    assert phi | non_phi == silver_tables()


def test_tables_with_phi_columns_are_phi():
    phi = set(definition()["tables"]["phi"])
    flagged = {t for t, cols in silver_columns().items() if any(PHI_COLUMN.search(c) for c in cols)}
    assert {"patient_record", "staff"} <= flagged
    assert flagged <= phi, flagged - phi


def test_only_the_phi_role_reads_phi():
    roles = definition()["roles"]
    assert roles["DefaultReader"] == ["non_phi"]
    assert "phi" in roles["PhiReader"]
    for name, classes in roles.items():
        assert set(classes) <= {"phi", "non_phi"}, name
        if name != "PhiReader":
            assert "phi" not in classes, name


def test_terraform_defines_every_role():
    text = TERRAFORM.read_text()
    assert 'jsondecode(file("${path.module}/lh_silver_roles.json"))' in text
    for name in definition()["roles"]:
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,127}", name), name
        assert f'role_name    = "{name}"' in text, name
        assert f'local.silver_paths["{name}"]' in text, name


def test_user_clinic_template_has_no_real_upns():
    text = USER_CLINIC.read_text()
    rows = re.findall(r"\('([^']+)', '([^']+)'\)", text)
    assert rows
    clinics = set(yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())["clinics"])
    for upn, clinic in rows:
        assert upn.endswith("@example.com"), upn
        assert clinic in clinics, clinic
    assert "sql/fabric/user_clinic.sql" in (ROOT / ".gitignore").read_text().splitlines()
