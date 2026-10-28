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

# # Master patient index
# Matches `patient_record` rows across and within systems and writes `patient_xref`: one master
# patient ID per source record. Fellegi–Sunter scoring: candidate pairs come from blocking, each
# field comparison falls into an agreement level, and a level weighs log2(m/u). m (agreement among
# true matches) is set a priori; u (agreement by chance) is measured on random record pairs. Pairs
# scoring at least MATCH are merged into connected components; pairs between REVIEW and MATCH go
# to `patient_match_review` and are not merged. The approach is recorded in
# `docs/adr/0001-mpi-approach.md`.
#
# Locally the same file is imported by `scripts/mpi.py` and the tests; the last cell runs only when
# Fabric executes the notebook.

# PARAMETERS CELL ********************

run_id = ""
silver_root = "Tables"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import math
from functools import reduce

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

FIELDS = ["clinic_id", "given_name", "family_name", "birth_date", "sex", "phone", "postal_code"]
# m: share of true matches at each agreement level, set a priori (see the ADR). A comparison with a
# value missing on either side has no level and weighs 0.
M = {
    "given_name": {"high": 0.95, "mid": 0.04, "low": 0.01},
    "family_name": {"high": 0.95, "mid": 0.04, "low": 0.01},
    "birth_date": {"exact": 0.95, "swapped": 0.02, "year": 0.02, "other": 0.01},
    "sex": {"agree": 0.98, "disagree": 0.02},
    "phone": {"agree": 0.80, "disagree": 0.20},
    "postal_code": {"agree": 0.95, "disagree": 0.05},
    "clinic_id": {"agree": 0.98, "disagree": 0.02},
}
# Thresholds in log2 likelihood ratio, set in the valley of the candidate-score histogram (scores
# cluster below 12 and above 28 on the full population), without ground truth.
MATCH = 20.0
REVIEW = 12.0  # between REVIEW and MATCH a pair goes to review
U_SAMPLE = 600  # records whose pairs estimate u (~180k pairs)


def jaro_winkler(a: str | None, b: str | None) -> float | None:
    """Jaro-Winkler similarity (prefix scale 0.1, prefix up to 4); Spark has no built-in."""
    if a is None or b is None:
        return None
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    window = max(max(len(a), len(b)) // 2 - 1, 0)
    used_a, used_b = [False] * len(a), [False] * len(b)
    matches = 0
    for i, c in enumerate(a):
        for j in range(max(0, i - window), min(len(b), i + window + 1)):
            if not used_b[j] and b[j] == c:
                used_a[i] = used_b[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    in_b = iter(c for c, used in zip(b, used_b, strict=True) if used)
    transpositions = sum(c != next(in_b) for c, used in zip(a, used_a, strict=True) if used)
    m = matches
    jaro = (m / len(a) + m / len(b) + (m - transpositions / 2) / m) / 3
    prefix = 0
    for x, y in zip(a[:4], b[:4], strict=False):
        if x != y:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def records(spark: SparkSession, silver_root: str) -> DataFrame:
    df = spark.read.format("delta").load(f"{silver_root}/patient_record")
    rid = F.concat_ws(":", "system", "local_patient_id").alias("rid")
    return df.select(rid, "system", "local_patient_id", *FIELDS)


def sides(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    columns = ["rid", *FIELDS]
    return (
        df.select(*[F.col(c).alias(f"a_{c}") for c in columns]),
        df.select(*[F.col(c).alias(f"b_{c}") for c in columns]),
    )


def blocks() -> dict[str, list[Column]]:
    """Blocking keys: a pair is compared when it agrees on any of them."""
    return {
        "year_soundex": [F.year("birth_date"), F.soundex("family_name")],
        "birth_date": [F.col("birth_date")],
        "phone": [F.col("phone")],
    }


def candidates(df: DataFrame) -> DataFrame:
    """Distinct record pairs (a_rid < b_rid) that agree on at least one blocking key."""
    keyed = {
        name: df.where(reduce(Column.__and__, [k.isNotNull() for k in key])).select(
            "rid", F.concat_ws("|", *key).alias("key")
        )
        for name, key in blocks().items()
    }
    pairs = [
        k.alias("a")
        .join(k.alias("b"), "key")
        .where(F.col("a.rid") < F.col("b.rid"))
        .select(F.col("a.rid").alias("a_rid"), F.col("b.rid").alias("b_rid"))
        for k in keyed.values()
    ]
    return pairs[0].unionByName(pairs[1]).unionByName(pairs[2]).distinct()


def compare(pairs: DataFrame, df: DataFrame) -> DataFrame:
    """Adds one agreement-level column per field in M (NULL when a value is missing)."""
    a, b = sides(df)
    p = pairs.join(a, "a_rid").join(b, "b_rid")

    def col(side: str, field: str) -> Column:
        return F.col(f"{side}_{field}")

    # A lambda: PySpark would otherwise read the type hints as a pandas UDF signature.
    similarity = F.udf(lambda a, b: jaro_winkler(a, b), "double")

    def name(field: str) -> Column:
        score = similarity(F.lower(col("a", field)), F.lower(col("b", field)))
        return (
            F.when(score >= 0.92, "high").when(score >= 0.80, "mid").when(score.isNotNull(), "low")
        )

    def agree(field: str) -> Column:
        missing = col("a", field).isNull() | col("b", field).isNull()
        return F.when(
            ~missing, F.when(col("a", field) == col("b", field), "agree").otherwise("disagree")
        )

    da, db = col("a", "birth_date"), col("b", "birth_date")
    swapped = (
        (F.year(da) == F.year(db))
        & (F.month(da) == F.dayofmonth(db))
        & (F.dayofmonth(da) == F.month(db))
    )
    birth = (
        F.when(da == db, "exact")
        .when(swapped, "swapped")
        .when(F.year(da) == F.year(db), "year")
        .when(da.isNotNull() & db.isNotNull(), "other")
    )
    levels = {
        "given_name": name("given_name"),
        "family_name": name("family_name"),
        "birth_date": birth,
        **{f: agree(f) for f in ("sex", "phone", "postal_code", "clinic_id")},
    }
    return p.select("a_rid", "b_rid", *[level.alias(f"lv_{f}") for f, level in levels.items()])


def weights(spark: SparkSession, df: DataFrame) -> dict[str, dict[str, float]]:
    """log2(m/u) per field and level; u from all pairs of a fixed sample of records."""
    sample = df.orderBy(F.xxhash64("rid"), "rid").limit(U_SAMPLE)
    a, b = sample.select(F.col("rid").alias("a_rid")), sample.select(F.col("rid").alias("b_rid"))
    pairs = a.crossJoin(b).where(F.col("a_rid") < F.col("b_rid"))
    compared = compare(pairs, sample).cache()
    out = {}
    for field, m in M.items():
        counts = dict(
            compared.groupBy(f"lv_{field}")
            .count()
            .where(F.col(f"lv_{field}").isNotNull())
            .collect()
        )
        total = sum(counts.values())
        # Add-one smoothing keeps a level never seen by chance finite.
        out[field] = {
            level: math.log2(p / ((counts.get(level, 0) + 1) / (total + len(m))))
            for level, p in m.items()
        }
    compared.unpersist()
    return out


def score(compared: DataFrame, w: dict[str, dict[str, float]]) -> DataFrame:
    terms = [
        F.coalesce(
            *[F.when(F.col(f"lv_{field}") == level, F.lit(v)) for level, v in levels.items()],
            F.lit(0.0),
        )
        for field, levels in w.items()
    ]
    return compared.withColumn("score", sum(terms[1:], terms[0]))


def components(spark: SparkSession, nodes: DataFrame, edges: DataFrame) -> tuple[DataFrame, int]:
    """Connected components by min-label propagation: rid -> smallest rid reachable."""
    both = edges.select(F.col("a_rid").alias("src"), F.col("b_rid").alias("dst")).unionByName(
        edges.select(F.col("b_rid").alias("src"), F.col("a_rid").alias("dst"))
    )
    labels = nodes.select("rid", F.col("rid").alias("label")).localCheckpoint()
    iterations = 0
    while True:
        iterations += 1
        offered = (
            both.join(labels, both.src == labels.rid)
            .groupBy("dst")
            .agg(F.min("label").alias("offered"))
        )
        updated = (
            labels.join(offered, labels.rid == offered.dst, "left")
            .select("rid", F.least("label", F.coalesce("offered", "label")).alias("label"))
            .localCheckpoint()
        )
        changed = updated.join(labels, ["rid", "label"], "left_anti").count()
        labels = updated
        if not changed:
            return labels, iterations


def write(df: DataFrame, path: str) -> None:
    df.write.format("delta").mode("overwrite").option("overwriteSchema", True).save(path)


def run(spark: SparkSession, run_id: str, silver_root: str) -> dict[str, int]:
    """Write `patient_xref` and `patient_match_review` for `run_id`; returns run statistics."""
    if not run_id:
        raise ValueError("run_id is required")
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    df = records(spark, silver_root).cache()
    w = weights(spark, df)
    scored = score(compare(candidates(df), df), w).cache()
    matched = scored.where(F.col("score") >= MATCH)
    review = scored.where((F.col("score") >= REVIEW) & (F.col("score") < MATCH))
    labels, iterations = components(spark, df.select("rid"), matched)

    xref = df.join(labels, "rid").select(
        "system",
        "local_patient_id",
        F.substring(F.sha2("label", 256), 1, 32).alias("master_patient_id"),
        F.lit(run_id).alias("_run_id"),
    )
    write(xref, f"{silver_root}/patient_xref")
    write(
        review.select(
            F.split_part("a_rid", F.lit(":"), F.lit(1)).alias("system_a"),
            F.split_part("a_rid", F.lit(":"), F.lit(2)).alias("local_patient_id_a"),
            F.split_part("b_rid", F.lit(":"), F.lit(1)).alias("system_b"),
            F.split_part("b_rid", F.lit(":"), F.lit(2)).alias("local_patient_id_b"),
            F.round("score", 2).alias("score"),
            F.lit(run_id).alias("_run_id"),
        ),
        f"{silver_root}/patient_match_review",
    )
    stats = {
        "records": df.count(),
        "candidate_pairs": scored.count(),
        "matched_pairs": matched.count(),
        "review_pairs": review.count(),
        "masters": labels.select("label").distinct().count(),
        "iterations": iterations,
    }
    scored.unpersist()
    df.unpersist()
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
