# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "00000000-0000-0000-0000-000000000000",
# META       "default_lakehouse_name": "lh_bronze",
# META       "default_lakehouse_workspace_id": "00000000-0000-0000-0000-000000000000"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Bronze
# Lands every source of one pipeline run as a Delta table in Bronze: source columns as landed (CSV
# as strings, Parquet with its types, FHIR as one raw JSON text per bundle file) plus `_run_id`,
# `_source_file` and `_ingested_at`. Sources are full extracts, so each run overwrites the tables.
#
# Locally the same file is imported by `scripts/bronze.py` and the tests; the last cell runs only
# when Fabric executes the notebook.

# PARAMETERS CELL ********************

run_id = ""
landing_root = "Files/landing"
tables_root = "Tables"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

# Bronze table -> (system folder under landing/<system>/<run_id>/, path inside it, format)
SOURCES = {
    "billing_patient_account": ("billing", "patient_account.parquet", "parquet"),
    "billing_claim": ("billing", "claim.parquet", "parquet"),
    "billing_claim_line": ("billing", "claim_line.parquet", "parquet"),
    "lab_patients": ("lab", "patients.csv", "csv"),
    "lab_results": ("lab", "results.csv", "csv"),
    "adt_patients": ("adt", "patients.csv", "csv"),
    "adt_events": ("adt", "events.csv", "csv"),
    "adt_ed_visits": ("adt", "ed_visits.csv", "csv"),
    "sharepoint_beds": ("sharepoint", "beds.csv", "csv"),
    "sharepoint_staff": ("sharepoint", "staff.csv", "csv"),
    "sharepoint_roster": ("sharepoint", "roster.csv", "csv"),
    "fhir_bundle": ("fhir", "", "bundle"),  # every *.json under <clinic>/ folders
}


def read_source(spark: SparkSession, landing_root: str, run_id: str, table: str) -> DataFrame:
    system, path, fmt = SOURCES[table]
    location = f"{landing_root}/{system}/{run_id}/{path}"
    if fmt == "parquet":
        df = spark.read.parquet(location)
    elif fmt == "csv":
        # Values stay strings; quotes are doubled, as Python's csv module and Dataflow write them.
        df = (
            spark.read.option("header", True)
            .option("multiLine", True)
            .option("escape", '"')
            .csv(location)
        )
    else:
        df = (
            spark.read.option("recursiveFileLookup", True)
            .option("pathGlobFilter", "*.json")
            .text(location, wholetext=True)
            .withColumnRenamed("value", "content")
        )
    return df.select(
        "*",
        F.lit(run_id).alias("_run_id"),
        F.col("_metadata.file_path").alias("_source_file"),
        F.current_timestamp().alias("_ingested_at"),
    )


def run(spark: SparkSession, run_id: str, landing_root: str, tables_root: str) -> dict[str, int]:
    """Write every Bronze table for `run_id`; returns rows written per table."""
    if not run_id:
        raise ValueError("run_id is required")
    counts = {}
    for table in SOURCES:
        df = read_source(spark, landing_root, run_id, table)
        df.write.format("delta").mode("overwrite").option("overwriteSchema", True).save(
            f"{tables_root}/{table}"
        )
        counts[table] = spark.read.format("delta").load(f"{tables_root}/{table}").count()
    return counts


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

if __name__ == "__main__":
    print(run(spark, run_id, landing_root, tables_root))  # noqa: F821 (Fabric session global)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
