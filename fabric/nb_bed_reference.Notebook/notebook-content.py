# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "00000000-0000-0000-0000-000000000000",
# META       "default_lakehouse_name": "lh_silver",
# META       "default_lakehouse_workspace_id": "00000000-0000-0000-0000-000000000000"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Bed reference into the KQL database
# Copies Silver `bed` (the SharePoint bed list) into the `bed` table of `kqldb_beds`, which
# `ward_occupancy()` divides by. Fabric Git sync creates the table but loads no data, so the live
# map and the Activator rule see no wards until this runs. One `.set-or-replace` replaces the
# table atomically; an empty bed list is refused rather than loaded.
#
# `kusto_query_uri` and `kusto_database` are bound per workspace at deploy (`parameter.yml`).
# Locally the same file is imported by the tests, which run `load` against the Kusto emulator;
# the last cell runs only in Fabric.

# PARAMETERS CELL ********************

silver_root = "Tables"
kusto_query_uri = "https://example.kusto.fabric.microsoft.com"
kusto_database = "00000000-0000-0000-0000-000000000000"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import json
import urllib.request

from pyspark.sql import SparkSession

COLUMNS = ["clinic_id", "clinic_name", "ward_id", "ward_name", "bed_id"]


def bed_rows(spark: SparkSession, silver_root: str) -> list[tuple[str, ...]]:
    beds = spark.read.format("delta").load(f"{silver_root}/bed").select(*COLUMNS)
    return [tuple(r) for r in beds.orderBy("bed_id").collect()]


def command(rows: list[tuple[str, ...]]) -> str:
    """`.set-or-replace bed` from an inline datatable; values are JSON-quoted KQL strings."""
    if not rows:
        raise ValueError("no beds in Silver; refusing to empty the KQL bed table")
    schema = ", ".join(f"{c}:string" for c in COLUMNS)
    values = ",\n".join(", ".join(json.dumps(v, ensure_ascii=False) for v in row) for row in rows)
    return f".set-or-replace bed <| datatable({schema}) [\n{values}\n]"


def load(rows: list[tuple[str, ...]], query_uri: str, database: str, token: str = "") -> int:
    """Run the command through the Kusto REST management endpoint; return the rows loaded."""
    body = json.dumps({"db": database, "csl": command(rows)}).encode()
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{query_uri.rstrip('/')}/v1/rest/mgmt", data=body, headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        response.read()
    return len(rows)


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

if __name__ == "__main__":
    token = notebookutils.credentials.getToken("kusto")  # noqa: F821 (Fabric global)
    rows = bed_rows(spark, silver_root)  # noqa: F821 (Fabric session global)
    print({"beds": load(rows, kusto_query_uri, kusto_database, token)})

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
