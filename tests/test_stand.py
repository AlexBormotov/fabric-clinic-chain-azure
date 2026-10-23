"""U04 local source stand. `stand` tests need `make up` and read it back against data/sources/."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from clinic_chain import stand
from clinic_chain.sources import contracts

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = contracts.load(ROOT / "docs" / "contracts")
SOURCES = ROOT / "data" / "sources"
FHIR = ROOT / "data" / "raw" / "fhir"


def test_typed_rows_follow_contract_types():
    account = ["ACC1000001", "boston", "Ann", "Lee", "1980-02-03", "F", None, "02115"]
    claim = ["C1", "ACC1000001", "boston", "IMP", "Medicare", "2025-01-02 03:04:05",
             "2025-01-03 00:00:00", "1200.50", "0.00", "denied", "CO-50"]  # fmt: skip
    line = ["C1", "2", "1234", "Room", "99.90"]
    assert stand.typed_rows(CONTRACTS["billing.patient_account"], [account]) == [
        ("ACC1000001", "boston", "Ann", "Lee", date(1980, 2, 3), "F", None, "02115")
    ]
    [typed] = stand.typed_rows(CONTRACTS["billing.claim"], [claim])
    assert typed[5] == datetime(2025, 1, 2, 3, 4, 5)
    assert typed[7:9] == (Decimal("1200.50"), Decimal("0.00"))
    assert stand.typed_rows(CONTRACTS["billing.claim_line"], [line]) == [
        ("C1", 2, "1234", "Room", Decimal("99.90"))
    ]


def test_blob_files_map_clinic_folders(tmp_path):
    (tmp_path / "fhir" / "boston" / "fhir").mkdir(parents=True)
    (tmp_path / "fhir" / "boston" / "fhir" / "a.json").write_text("{}")
    (tmp_path / "fhir" / "boston" / "metadata").mkdir()
    (tmp_path / "fhir" / "boston" / "metadata" / "run.json").write_text("{}")
    (tmp_path / "sources" / "lab").mkdir(parents=True)
    (tmp_path / "sources" / "lab" / "results.csv").write_text("x\n")
    files = stand.blob_files(tmp_path / "sources", tmp_path / "fhir")
    assert list(files["fhir"]) == ["boston/a.json"]
    assert list(files["lab"]) == ["results.csv"]
    assert files["adt"] == {}


@pytest.mark.stand
@pytest.mark.parametrize("table", stand.BILLING_TABLES)
def test_billing_row_counts(table):
    _, rows = contracts.read(SOURCES, CONTRACTS[f"billing.{table}"])
    with stand.sql() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM billing.{table}")
        assert cur.fetchone()[0] == len(rows) > 0


@pytest.mark.stand
def test_billing_nulls_survive():
    _, rows = contracts.read(SOURCES, CONTRACTS["billing.claim"])
    denied = sum(r[-1] is not None for r in rows)
    with stand.sql() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM billing.claim WHERE denial_reason IS NOT NULL")
        assert cur.fetchone()[0] == denied < len(rows)


@pytest.mark.stand
@pytest.mark.parametrize("container", ["fhir", "lab", "adt"])
def test_blobs_match_files(container):
    files = stand.blob_files(SOURCES, FHIR)[container]
    held = {b.name: b.size for b in stand.blobs().get_container_client(container).list_blobs()}
    assert files
    assert held == {name: path.stat().st_size for name, path in files.items()}


@pytest.mark.stand
def test_sharepoint_folder_holds_contract_tables():
    for name, spec in CONTRACTS.items():
        if name.startswith("sharepoint."):
            _, rows = contracts.read(SOURCES, spec)
            assert rows
            assert contracts.validate(SOURCES, name, spec) == []
