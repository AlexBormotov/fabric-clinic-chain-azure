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

# # Silver
# Builds typed, conformed Silver tables from Bronze. Each fact comes from one system of record:
# FHIR for patients, encounters, conditions and medication requests; the lab system for results;
# billing for claims; ADT for bed events and ED visits; SharePoint for beds, staff and rosters.
# `patient_record` holds every system's patient rows, standardized but not matched (U07 does that).
#
# A row is dropped when it exactly duplicates an earlier one, when a required column is empty, or
# when a non-empty value fails to cast. `reconciliation` counts every row in, out and dropped by
# reason, per Silver table and source, so that input = output + dropped.
#
# Locally the same file is imported by `scripts/silver.py` and the tests; the last cell runs only
# when Fabric executes the notebook. `bronze_root` is resolved by parameter.yml at deploy (U19).

# PARAMETERS CELL ********************

run_id = ""
bronze_root = "abfss://00000000-0000-0000-0000-000000000000@onelake.dfs.fabric.microsoft.com/00000000-0000-0000-0000-000000000000/Tables"
silver_root = "Tables"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from functools import reduce

from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

META = ["_run_id", "_source_file", "_ingested_at"]

# Silver table -> (Bronze table, columns as (name, type, required)); names are the source names.
TABLES = {
    "lab_result": (
        "lab_results",
        [
            ("result_id", "string", True),
            ("lab_patient_id", "string", True),
            ("clinic_id", "string", True),
            ("collected_at", "timestamp", True),
            ("loinc_code", "string", True),
            ("test_name", "string", True),
            ("value_numeric", "decimal(20,8)", False),
            ("value_text", "string", False),
            ("unit", "string", False),
        ],
    ),
    "claim": (
        "billing_claim",
        [
            ("claim_id", "string", True),
            ("account_id", "string", True),
            ("clinic_id", "string", True),
            ("claim_type", "string", True),
            ("payer", "string", True),
            ("service_start", "timestamp", True),
            ("service_end", "timestamp", True),
            ("billed_amount", "decimal(12,2)", True),
            ("paid_amount", "decimal(12,2)", True),
            ("status", "string", True),
            ("denial_reason", "string", False),
        ],
    ),
    "claim_line": (
        "billing_claim_line",
        [
            ("claim_id", "string", True),
            ("line_no", "int", True),
            ("service_code", "string", True),
            ("service_name", "string", True),
            ("amount", "decimal(12,2)", True),
        ],
    ),
    "adt_event": (
        "adt_events",
        [
            ("event_id", "int", True),
            ("event_type", "string", True),
            ("event_time", "timestamp", True),
            ("clinic_id", "string", True),
            ("stay_id", "string", True),
            ("adt_patient_id", "string", True),
            ("ward_id", "string", True),
            ("bed_id", "string", True),
            ("from_ward_id", "string", False),
            ("from_bed_id", "string", False),
        ],
    ),
    "ed_visit": (
        "adt_ed_visits",
        [
            ("ed_visit_id", "string", True),
            ("clinic_id", "string", True),
            ("adt_patient_id", "string", True),
            ("arrival_at", "timestamp", True),
            ("triage_at", "timestamp", True),
            ("provider_seen_at", "timestamp", True),
            ("departure_at", "timestamp", True),
            ("disposition", "string", True),
            ("stay_id", "string", False),
        ],
    ),
    "bed": (
        "sharepoint_beds",
        [
            ("clinic_id", "string", True),
            ("clinic_name", "string", True),
            ("ward_id", "string", True),
            ("ward_name", "string", True),
            ("bed_id", "string", True),
        ],
    ),
    "staff": (
        "sharepoint_staff",
        [
            ("staff_id", "string", True),
            ("clinic_id", "string", True),
            ("role", "string", True),
            ("ward_id", "string", True),
            ("given_name", "string", True),
            ("family_name", "string", True),
            ("npi", "string", False),
        ],
    ),
    "roster": (
        "sharepoint_roster",
        [
            ("staff_id", "string", True),
            ("week_start", "date", True),
            ("ward_id", "string", True),
            ("shift", "string", True),
            ("shifts_planned", "int", True),
        ],
    ),
}

PATIENT_COLUMNS = [
    ("local_patient_id", "string", True),
    ("clinic_id", "string", True),
    ("given_name", "string", True),
    ("family_name", "string", True),
    ("birth_date", "date", True),
    ("sex", "string", True),
    ("phone", "string", False),
    ("postal_code", "string", False),
]
# patient_record system -> (Bronze table, local patient ID column); EHR (FHIR) patients come from
# bundles.
PATIENT_SOURCES = {
    "lab": ("lab_patients", "lab_patient_id"),
    "adt": ("adt_patients", "adt_patient_id"),
    "billing": ("billing_patient_account", "account_id"),
}

# Only the fields Silver reads; anything else in a resource is ignored.
CONCEPT = "STRUCT<coding: ARRAY<STRUCT<code: STRING, display: STRING>>, text: STRING>"
REF = "STRUCT<reference: STRING>"
FHIR_SCHEMAS = {
    "Patient": "id STRING, gender STRING, birthDate STRING,"
    " name ARRAY<STRUCT<use: STRING, family: STRING, given: ARRAY<STRING>>>,"
    " telecom ARRAY<STRUCT<system: STRING, value: STRING>>,"
    " address ARRAY<STRUCT<postalCode: STRING>>",
    "Encounter": f"id STRING, status STRING, `class` STRUCT<code: STRING>, type ARRAY<{CONCEPT}>,"
    f" subject {REF}, period STRUCT<start: STRING, `end`: STRING>, reasonCode ARRAY<{CONCEPT}>",
    "Condition": f"id STRING, clinicalStatus {CONCEPT}, code {CONCEPT}, subject {REF},"
    f" encounter {REF}, onsetDateTime STRING, abatementDateTime STRING, recordedDate STRING",
    "MedicationRequest": f"id STRING, status STRING, medicationCodeableConcept {CONCEPT},"
    f" medicationReference {REF}, subject {REF}, encounter {REF}, authoredOn STRING",
    # Not a Silver table: resolves the code of a MedicationRequest that references it.
    "Medication": f"id STRING, code {CONCEPT}",
}
FHIR_TABLES = {
    "Patient": "patient_record",
    "Encounter": "encounter",
    "Condition": "condition",
    "MedicationRequest": "medication_request",
}


def first(array: Column) -> Column:
    return F.try_element_at(array, F.lit(1))


def ref_id(ref: Column) -> Column:
    return F.regexp_replace(ref.reference, "^urn:uuid:", "")


def code(concept: Column) -> Column:
    return first(concept.coding).code


def display(concept: Column) -> Column:
    return F.coalesce(first(concept.coding).display, concept.text)


def flag_duplicates(df: DataFrame, columns: list[str]) -> DataFrame:
    """Marks every copy after the first of rows that are equal in `columns`."""
    copy = F.row_number().over(Window.partitionBy(*columns).orderBy(F.lit(0)))
    return df.withColumn("_duplicate", copy > 1)


def conform(df: DataFrame, columns: list[tuple[str, str, bool]]) -> DataFrame:
    """Casts each column; `_drop` is the first reason the row is dropped, NULL if it is kept."""
    reasons = [F.when(F.col("_duplicate"), F.lit("exact_duplicate"))]
    cast = []
    for name, kind, required in columns:
        value = F.col(name).try_cast(kind)
        failed = value.isNull() if required else F.col(name).isNotNull() & value.isNull()
        reasons.append(F.when(failed, F.lit(f"invalid_{name}")))
        cast.append(value.alias(name))
    return df.select(*cast, "_source_file", F.coalesce(*reasons).alias("_drop"))


def standardize_patient(df: DataFrame) -> DataFrame:
    """Trims names (dropping Synthea's numeric suffixes), sex to M/F/U, phone to 10 digits."""

    def name(column: str) -> Column:
        return F.trim(F.regexp_replace(F.regexp_replace(column, r"\d", ""), r"\s+", " "))

    sex = F.upper(F.substring(F.trim("sex"), 1, 1))
    digits = F.regexp_replace("phone", r"\D", "")
    return df.withColumns(
        {
            "given_name": name("given_name"),
            "family_name": name("family_name"),
            "sex": F.when(sex.isin("M", "F"), sex).otherwise(F.lit("U")),
            "phone": F.when(F.length(digits) == 10, digits).when(
                (F.length(digits) == 11) & digits.startswith("1"), F.substring(digits, 2, 10)
            ),
        }
    )


def bronze(spark: SparkSession, bronze_root: str, table: str) -> DataFrame:
    return spark.read.format("delta").load(f"{bronze_root}/{table}")


def fhir_resources(spark: SparkSession, bronze_root: str) -> DataFrame:
    """One row per resource of every bundle: clinic (the bundle's folder), type, raw JSON."""
    bundles = bronze(spark, bronze_root, "fhir_bundle")
    entries = F.from_json("content", "entry ARRAY<STRUCT<resource: STRING>>").entry
    return bundles.select(
        F.element_at(F.split("_source_file", "/"), -2).alias("clinic_id"),
        "_source_file",
        F.explode(entries.resource).alias("resource"),
    ).withColumn("resource_type", F.get_json_object("resource", "$.resourceType"))


def parse(resources: DataFrame, resource_type: str) -> DataFrame:
    """Resources of one type with duplicates flagged and the fields of its schema in `r`."""
    df = resources.filter(F.col("resource_type") == resource_type)
    df = flag_duplicates(df, ["resource"])
    return df.withColumn("r", F.from_json("resource", FHIR_SCHEMAS[resource_type]))


def fhir_frame(resources: DataFrame, resource_type: str) -> DataFrame:
    """Raw Silver columns of one in-scope resource type, before `conform`."""
    df = parse(resources, resource_type)
    r = F.col("r")
    if resource_type == "Patient":
        official = first(F.filter(r["name"], lambda n: n.use == "official"))
        name = F.coalesce(official, first(r["name"]))
        return df.select(
            F.lit("ehr").alias("system"),
            r.id.alias("local_patient_id"),
            "clinic_id",
            first(name.given).alias("given_name"),
            name.family.alias("family_name"),
            r.birthDate.alias("birth_date"),
            r.gender.alias("sex"),
            first(F.filter(r.telecom, lambda t: t.system == "phone")).value.alias("phone"),
            first(r.address).postalCode.alias("postal_code"),
            "_source_file",
            "_duplicate",
        )
    if resource_type == "Encounter":
        return df.select(
            r.id.alias("encounter_id"),
            ref_id(r.subject).alias("fhir_patient_id"),
            "clinic_id",
            r.status.alias("status"),
            r["class"].code.alias("class_code"),
            code(first(r.type)).alias("type_code"),
            display(first(r.type)).alias("type_display"),
            code(first(r.reasonCode)).alias("reason_code"),
            r.period.start.alias("start_at"),
            r.period["end"].alias("end_at"),
            "_source_file",
            "_duplicate",
        )
    if resource_type == "Condition":
        return df.select(
            r.id.alias("condition_id"),
            ref_id(r.subject).alias("fhir_patient_id"),
            ref_id(r.encounter).alias("encounter_id"),
            "clinic_id",
            code(r.clinicalStatus).alias("clinical_status"),
            code(r.code).alias("code"),
            display(r.code).alias("display"),
            r.onsetDateTime.alias("onset_at"),
            r.abatementDateTime.alias("abatement_at"),
            r.recordedDate.alias("recorded_at"),
            "_source_file",
            "_duplicate",
        )
    medications = parse(resources, "Medication").select(
        F.col("r.id").alias("medication_id"),
        code(F.col("r.code")).alias("medication_code"),
        display(F.col("r.code")).alias("medication_display"),
    )
    return (
        df.withColumn("medication_id", ref_id(r.medicationReference))
        .join(medications.dropDuplicates(["medication_id"]), "medication_id", "left")
        .select(
            r.id.alias("medication_request_id"),
            ref_id(r.subject).alias("fhir_patient_id"),
            ref_id(r.encounter).alias("encounter_id"),
            "clinic_id",
            r.status.alias("status"),
            F.coalesce(code(r.medicationCodeableConcept), "medication_code").alias(
                "medication_code"
            ),
            F.coalesce(display(r.medicationCodeableConcept), "medication_display").alias(
                "medication_display"
            ),
            r.authoredOn.alias("authored_at"),
            "_source_file",
            "_duplicate",
        )
    )


FHIR_COLUMNS = {
    "Encounter": [
        ("encounter_id", "string", True),
        ("fhir_patient_id", "string", True),
        ("clinic_id", "string", True),
        ("status", "string", False),
        ("class_code", "string", False),
        ("type_code", "string", False),
        ("type_display", "string", False),
        ("reason_code", "string", False),
        ("start_at", "timestamp", True),
        ("end_at", "timestamp", False),
    ],
    "Condition": [
        ("condition_id", "string", True),
        ("fhir_patient_id", "string", True),
        ("encounter_id", "string", False),
        ("clinic_id", "string", True),
        ("clinical_status", "string", False),
        ("code", "string", True),
        ("display", "string", False),
        ("onset_at", "timestamp", True),
        ("abatement_at", "timestamp", False),
        ("recorded_at", "timestamp", False),
    ],
    "MedicationRequest": [
        ("medication_request_id", "string", True),
        ("fhir_patient_id", "string", True),
        ("encounter_id", "string", False),
        ("clinic_id", "string", True),
        ("status", "string", False),
        ("medication_code", "string", True),
        ("medication_display", "string", False),
        ("authored_at", "timestamp", True),
    ],
}


def patient_frame(spark: SparkSession, bronze_root: str, system: str) -> DataFrame:
    table, id_column = PATIENT_SOURCES[system]
    df = bronze(spark, bronze_root, table)
    df = flag_duplicates(df, [c for c in df.columns if c not in META])
    return df.select(
        F.lit(system).alias("system"),
        F.col(id_column).alias("local_patient_id"),
        *[
            (F.col(c) if c in df.columns else F.lit(None).cast("string")).alias(c)
            for c, _, _ in PATIENT_COLUMNS[1:]
        ],
        "_source_file",
        "_duplicate",
    )


def write(df: DataFrame, path: str) -> None:
    df.write.format("delta").mode("overwrite").option("overwriteSchema", True).save(path)


RECONCILIATION = (
    "silver_table STRING, source STRING, measure STRING, reason STRING, `rows` BIGINT,"
    " run_id STRING"
)


def run(spark: SparkSession, run_id: str, bronze_root: str, silver_root: str) -> dict[str, int]:
    """Write every Silver table and `reconciliation` for `run_id`; returns rows per Silver table."""
    if not run_id:
        raise ValueError("run_id is required")
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    resources = fhir_resources(spark, bronze_root)
    census = dict(resources.groupBy("resource_type").count().collect())
    resources = resources.filter(F.col("resource_type").isin(*FHIR_SCHEMAS)).persist()

    # Silver table -> [(source, input rows, conformed frame, filter selecting its output rows)]
    parts: dict[str, list] = {}
    for table, (source, columns) in TABLES.items():
        df = bronze(spark, bronze_root, source)
        conformed = conform(flag_duplicates(df, [c for c in df.columns if c not in META]), columns)
        parts[table] = [(source, df.count(), conformed, F.lit(True))]
    patient = [("system", "string", True), *PATIENT_COLUMNS]
    parts["patient_record"] = [
        (
            PATIENT_SOURCES[system][0],
            bronze(spark, bronze_root, PATIENT_SOURCES[system][0]).count(),
            conform(patient_frame(spark, bronze_root, system), patient),
            F.col("system") == system,
        )
        for system in PATIENT_SOURCES
    ] + [
        (
            "fhir_bundle:Patient",
            census.get("Patient", 0),
            conform(fhir_frame(resources, "Patient"), patient),
            F.col("system") == "ehr",
        )
    ]
    for resource_type, columns in FHIR_COLUMNS.items():
        parts[FHIR_TABLES[resource_type]] = [
            (
                f"fhir_bundle:{resource_type}",
                census.get(resource_type, 0),
                conform(fhir_frame(resources, resource_type), columns),
                F.lit(True),
            )
        ]

    rows, counts = [], {}
    for table, sources in parts.items():
        kept = []
        for source, n, df, _ in sources:
            rows.append((table, source, "input", None, n))
            dropped = df.filter(F.col("_drop").isNotNull()).groupBy("_drop").count().collect()
            rows += [(table, source, "dropped", reason, k) for reason, k in dropped]
            kept.append(df.filter(F.col("_drop").isNull()).drop("_drop"))
        out = reduce(DataFrame.unionByName, kept).withColumn("_run_id", F.lit(run_id))
        if table == "patient_record":
            out = standardize_patient(out)
        write(out, f"{silver_root}/{table}")
        written = spark.read.format("delta").load(f"{silver_root}/{table}")
        for source, _, _, selects in sources:
            rows.append((table, source, "output", None, written.filter(selects).count()))
        counts[table] = written.count()
    for resource_type, n in census.items():
        if resource_type not in FHIR_TABLES:
            source = f"fhir_bundle:{resource_type}"
            rows += [(None, source, "input", None, n), (None, source, "output", None, 0)]
            rows.append((None, source, "dropped", "out_of_scope", n))
    resources.unpersist()

    write(
        spark.createDataFrame([(*r, run_id) for r in rows], RECONCILIATION),
        f"{silver_root}/reconciliation",
    )
    return counts


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

if __name__ == "__main__":
    print(run(spark, run_id, bronze_root, silver_root))  # noqa: F821 (Fabric session global)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
