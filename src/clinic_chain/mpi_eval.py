"""Pairwise precision and recall of the MPI against the generator's ground truth.

Ground truth never reaches Fabric, so this runs locally and in CI only. A record pair is predicted
when both records share a master patient ID, and true when both belong to one person.
"""

from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from clinic_chain import spark as local

GATES = {"precision": 0.98, "recall": 0.95}


def pairs(df: DataFrame, key: str) -> int:
    """Record pairs that share `key`."""
    sizes = df.groupBy(key).count()
    return sizes.select(F.sum(F.col("count") * (F.col("count") - 1) / 2)).first()[0] or 0


def evaluate(session: SparkSession, silver_root: Path, ground_truth: Path) -> dict:
    nb = local.notebook("nb_mpi")
    xref = session.read.format("delta").load(str(silver_root / "patient_xref"))
    links = session.read.option("header", True).csv(str(ground_truth / "patient_links.csv"))
    joined = xref.join(links, ["system", "local_patient_id"])
    true_pairs = pairs(joined, "person_id")
    predicted = pairs(joined, "master_patient_id")
    hits = pairs(
        joined.withColumn("both", F.concat_ws("|", "master_patient_id", "person_id")), "both"
    )

    records = nb.records(session, str(silver_root))
    person = links.select(F.concat_ws(":", "system", "local_patient_id").alias("rid"), "person_id")
    blocked = (
        nb.candidates(records)
        .join(person.withColumnRenamed("rid", "a_rid").withColumnRenamed("person_id", "a"), "a_rid")
        .join(person.withColumnRenamed("rid", "b_rid").withColumnRenamed("person_id", "b"), "b_rid")
    )
    review = session.read.format("delta").load(str(silver_root / "patient_match_review"))
    return {
        "records": xref.count(),
        "records_linked_to_ground_truth": joined.count(),
        "persons": joined.select("person_id").distinct().count(),
        "masters": xref.select("master_patient_id").distinct().count(),
        "true_pairs": int(true_pairs),
        "predicted_pairs": int(predicted),
        "true_positive_pairs": int(hits),
        "precision": round(hits / predicted, 4) if predicted else 0.0,
        "recall": round(hits / true_pairs, 4) if true_pairs else 0.0,
        "candidate_pairs": blocked.count(),
        "blocking_recall": round(blocked.where("a = b").count() / true_pairs, 4),
        "review_pairs": review.count(),
        "thresholds": {"match": nb.MATCH, "review": nb.REVIEW},
        "gates": GATES,
    }
