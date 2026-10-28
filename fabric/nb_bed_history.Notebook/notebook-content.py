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

# # Bed state history (SCD2)
# Builds `bed_state_history` from `adt_event`: one row per bed and interval of constant state
# (free, or occupied by one stay). A01 occupies `bed_id`, A02 occupies `bed_id` and frees
# `from_bed_id`, A03 frees `bed_id`. Each interval ends where the bed's next change starts;
# `valid_to` is NULL on the current interval.
#
# Events are deduplicated by `event_id`. Events not yet in the `bed_event` log are new; the beds
# they touch are recomputed from all their logged events plus the new ones and applied with one
# MERGE, so a late, duplicate or out-of-order event gives the same history as an in-order run.
# History is written before the log: a failed run is repeated with the same result.
#
# Locally the same file is imported by `scripts/bed_history.py` and the tests; the last cell runs
# only when Fabric executes the notebook.

# PARAMETERS CELL ********************

run_id = ""
silver_root = "Tables"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from delta.tables import DeltaTable
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

EVENT_COLUMNS = [
    "event_id",
    "event_type",
    "event_time",
    "clinic_id",
    "stay_id",
    "adt_patient_id",
    "ward_id",
    "bed_id",
    "from_ward_id",
    "from_bed_id",
]
STATE = ["clinic_id", "ward_id", "occupied", "stay_id", "adt_patient_id", "event_id"]


def distinct_events(df: DataFrame) -> DataFrame:
    """One row per `event_id`: a resent event is the same event."""
    first = Window.partitionBy("event_id").orderBy("event_time", "event_type", "bed_id")
    return (
        df.select(*EVENT_COLUMNS)
        .withColumn("_copy", F.row_number().over(first))
        .where("_copy = 1")
        .drop("_copy")
    )


def changes(events: DataFrame) -> DataFrame:
    """State changes per bed: the occupied side of A01/A02, the freed side of A02/A03."""
    occupy = events.where(F.col("event_type").isin("A01", "A02")).select(
        "clinic_id",
        "ward_id",
        "bed_id",
        F.col("event_time").alias("valid_from"),
        F.lit(True).alias("occupied"),
        "stay_id",
        "adt_patient_id",
        "event_id",
    )
    free = events.where(F.col("event_type") == "A03").select(
        "clinic_id", "ward_id", "bed_id", "event_time", "event_id"
    )
    moved_out = events.where(F.col("event_type") == "A02").select(
        "clinic_id",
        F.col("from_ward_id").alias("ward_id"),
        F.col("from_bed_id").alias("bed_id"),
        "event_time",
        "event_id",
    )
    free = free.unionByName(moved_out).select(
        "clinic_id",
        "ward_id",
        "bed_id",
        F.col("event_time").alias("valid_from"),
        F.lit(False).alias("occupied"),
        F.lit(None).cast("string").alias("stay_id"),
        F.lit(None).cast("string").alias("adt_patient_id"),
        "event_id",
    )
    return occupy.unionByName(free)


def intervals(changes: DataFrame) -> DataFrame:
    """SCD2 intervals per bed. At one instant a bed is freed before it is taken; zero-length
    intervals are dropped and consecutive changes to the same state merge."""
    order = Window.partitionBy("bed_id").orderBy("valid_from", "occupied", "event_id")
    df = changes.withColumn("valid_to", F.lead("valid_from").over(order)).where(
        F.col("valid_to").isNull() | (F.col("valid_to") > F.col("valid_from"))
    )
    same = F.lag("occupied").over(order).eqNullSafe(F.col("occupied")) & F.lag("stay_id").over(
        order
    ).eqNullSafe(F.col("stay_id"))
    running = order.rowsBetween(Window.unboundedPreceding, Window.currentRow)
    df = df.withColumn("_island", F.sum(F.when(same, 0).otherwise(1)).over(running))
    first = {c: F.min_by(c, "valid_from").alias(c) for c in STATE}
    return (
        df.groupBy("bed_id", "_island")
        .agg(
            F.min("valid_from").alias("valid_from"),
            F.max_by("valid_to", "valid_from").alias("valid_to"),
            *first.values(),
        )
        .select(
            "clinic_id",
            "ward_id",
            "bed_id",
            "valid_from",
            "valid_to",
            F.col("valid_to").isNull().alias("is_current"),
            "occupied",
            "stay_id",
            "adt_patient_id",
            "event_id",
        )
    )


def run(spark: SparkSession, run_id: str, silver_root: str) -> dict[str, int]:
    """Apply events not yet logged to `bed_state_history`; returns run statistics."""
    if not run_id:
        raise ValueError("run_id is required")
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    history_path, log_path = f"{silver_root}/bed_state_history", f"{silver_root}/bed_event"
    events = distinct_events(spark.read.format("delta").load(f"{silver_root}/adt_event")).cache()
    logged = DeltaTable.isDeltaTable(spark, log_path)
    log = spark.read.format("delta").load(log_path).select(*EVENT_COLUMNS) if logged else None
    new = events.join(log, "event_id", "left_anti") if logged else events
    beds = [
        r.bed_id
        for r in new.select("bed_id")
        .unionByName(new.select(F.col("from_bed_id").alias("bed_id")))
        .where(F.col("bed_id").isNotNull())
        .distinct()
        .collect()
    ]
    stats = {"events": events.count(), "new_events": new.count(), "affected_beds": len(beds)}
    if beds:
        known = log.unionByName(new) if logged else new
        touching = known.where(F.col("bed_id").isin(beds) | F.col("from_bed_id").isin(beds))
        recomputed = (
            intervals(changes(touching))
            .where(F.col("bed_id").isin(beds))
            .withColumn("_run_id", F.lit(run_id))
        )
        if DeltaTable.isDeltaTable(spark, history_path):
            values = [c for c in recomputed.columns if c not in ("bed_id", "valid_from")]
            changed = " OR ".join(f"NOT (t.{c} <=> s.{c})" for c in values if c != "_run_id")
            (
                DeltaTable.forPath(spark, history_path)
                .alias("t")
                .merge(recomputed.alias("s"), "t.bed_id = s.bed_id AND t.valid_from = s.valid_from")
                .whenMatchedUpdate(changed, {c: f"s.{c}" for c in values})
                .whenNotMatchedInsertAll()
                .whenNotMatchedBySourceDelete(F.col("t.bed_id").isin(beds))
                .execute()
            )
        else:
            recomputed.write.format("delta").save(history_path)
        logged_new = new.withColumn("_run_id", F.lit(run_id))
        if logged:
            (
                DeltaTable.forPath(spark, log_path)
                .alias("t")
                .merge(logged_new.alias("s"), "t.event_id = s.event_id")
                .whenNotMatchedInsertAll()
                .execute()
            )
        else:
            logged_new.write.format("delta").save(log_path)
    events.unpersist()
    stats["intervals"] = spark.read.format("delta").load(history_path).count()
    return stats


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

if __name__ == "__main__":
    print(run(spark, run_id, silver_root))  # noqa: F821 (Fabric session global)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
