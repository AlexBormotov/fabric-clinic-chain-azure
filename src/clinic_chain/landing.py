"""Local stand-in for the pipeline's Copy activities and the SharePoint Dataflow.

Copies every source of the U04 stand unchanged into `<lakehouse>/Files/landing/<system>/<run_id>/`:
SQL tables as Parquet, blobs as they are, each SharePoint sheet as CSV.
"""

import csv
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from clinic_chain import stand
from clinic_chain.sources import contracts


def land_sql(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with stand.sql() as conn:
        cur = conn.cursor()
        for table in stand.BILLING_TABLES:
            cur.execute(f"SELECT * FROM billing.{table}")
            names = [d[0] for d in cur.description]
            rows = [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
            pq.write_table(pa.Table.from_pylist(rows), target / f"{table}.parquet")


def land_blobs(container: str, target: Path) -> None:
    client = stand.blobs().get_container_client(container)
    for name in client.list_blob_names():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(client.download_blob(name).readall())


def _cell(value, kind: str):
    if isinstance(value, datetime):
        return value.date().isoformat() if kind == "date" else value.strftime(contracts.DATETIME)
    return "" if value is None else value


def land_sharepoint(sources: Path, specs: dict[str, dict], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, spec in specs.items():
        system, _, table = name.partition(".")
        if system != "sharepoint":
            continue
        header, rows = contracts.read(sources, spec)
        kinds = [c["type"] for c in spec["columns"]]
        with (target / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows([_cell(v, k) for v, k in zip(row, kinds, strict=True)] for row in rows)


def land(sources: Path, specs: dict[str, dict], landing: Path, run_id: str) -> None:
    land_sql(landing / "billing" / run_id)
    for container in ("lab", "adt", "fhir"):
        land_blobs(container, landing / container / run_id)
    land_sharepoint(sources, specs, landing / "sharepoint" / run_id)
