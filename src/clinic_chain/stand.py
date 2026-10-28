"""Local source stand: SQL Server (billing) and Azurite (FHIR, lab, ADT files) in docker compose.

The SharePoint stand-in is the folder `data/sources/sharepoint/` itself; nothing is loaded for it.
"""

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import mssql_python
from azure.storage.blob import BlobServiceClient

from clinic_chain.sources import contracts

DATABASE = "clinic_billing"
BILLING_TABLES = ("patient_account", "claim", "claim_line")  # load order: foreign keys
# Microsoft's published Azurite development account; not a secret.
AZURITE = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://azurite:10000/devstoreaccount1;"
)


def sql(
    database: str = DATABASE, user: str = "sa", password: str | None = None
) -> mssql_python.Connection:
    """Connect as `sa` by default; tests pass a login of their own."""
    password = password or os.environ["MSSQL_SA_PASSWORD"]
    return mssql_python.connect(
        f"Server=sqlserver,1433;Database={database};UID={user};PWD={password};"
        "Encrypt=yes;TrustServerCertificate=yes",
        autocommit=True,
    )


def blobs() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(AZURITE)


def blob_files(sources: Path, fhir: Path) -> dict[str, dict[str, Path]]:
    """Container → blob name → local file."""
    return {
        "fhir": {f"{p.parent.parent.name}/{p.name}": p for p in sorted(fhir.glob("*/fhir/*.json"))},
        "lab": {p.name: p for p in sorted((sources / "lab").glob("*.csv"))},
        "adt": {p.name: p for p in sorted((sources / "adt").glob("*.csv"))},
    }


_PARSE = {
    "string": str,
    "int": int,
    "decimal": Decimal,
    "date": date.fromisoformat,
    "datetime": lambda v: datetime.strptime(v, contracts.DATETIME),
}


def typed_rows(spec: dict, rows: list[list]) -> list[tuple]:
    """CSV strings → Python values of the contract types; empty fields stay None."""
    parsers = [_PARSE[c["type"]] for c in spec["columns"]]
    return [
        tuple(None if v is None else parse(v) for parse, v in zip(parsers, row, strict=True))
        for row in rows
    ]


def load_billing(sources: Path, ddl: Path, specs: dict[str, dict]) -> None:
    with sql("master") as conn:
        conn.cursor().execute(f"IF DB_ID('{DATABASE}') IS NULL CREATE DATABASE {DATABASE}")
    with sql() as conn:
        cur = conn.cursor()
        for table in reversed(BILLING_TABLES):
            cur.execute(f"DROP TABLE IF EXISTS billing.{table}")
        cur.execute("DROP SCHEMA IF EXISTS billing")
        for batch in ddl.read_text().split("\nGO\n"):
            cur.execute(batch)
        for table in BILLING_TABLES:
            spec = specs[f"billing.{table}"]
            _, rows = contracts.read(sources, spec)
            cur.bulkcopy(f"billing.{table}", typed_rows(spec, rows), timeout=600, keep_nulls=True)


def upload(files: dict[str, dict[str, Path]]) -> None:
    service = blobs()
    for name, wanted in files.items():
        container = service.get_container_client(name)
        if not container.exists():
            container.create_container()
        for blob in container.list_blob_names():
            if blob not in wanted:
                container.delete_blob(blob)
        for blob, path in wanted.items():
            with path.open("rb") as f:
                container.upload_blob(blob, f, overwrite=True)
