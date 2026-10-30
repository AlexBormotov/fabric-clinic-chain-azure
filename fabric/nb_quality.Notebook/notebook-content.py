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

# # Data quality
# Verifies Soda v4 data contracts on Silver: keys, value ranges and referential integrity,
# including that every encounter's patient is an EHR patient record. Each checked table is
# registered as a global temp view and checked as dataset `silver/global_temp/<table>`; nothing is
# written. Any check that does not pass, or a contract that does not evaluate, fails the run.
# Why Soda runs this way on Runtime 2.0: `docs/adr/0003-soda-on-runtime-2.md`.
#
# Locally the same file is imported by `scripts/quality.py` and the tests; the install cell and the
# last cell run only in Fabric. The pipeline enables the install with `_inlineInstallationEnabled`.

# CELL ********************

# MAGIC %pip install soda-core==4.29.0 soda-sparkdf==4.29.0

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# PARAMETERS CELL ********************

run_id = ""
silver_root = "Tables"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import json
import os

# Soda Core sends anonymous telemetry unless this is set before its first import.
os.environ["SODA_CORE_TELEMETRY_ENABLED"] = "false"

from pyspark.sql import SparkSession

# soda_core first: importing soda_sparkdf first trips a circular import in its plugin entry point.
from soda_core.common.yaml import ContractYamlSource
from soda_core.contracts.contract_verification import CheckOutcome, ContractVerificationSession
from soda_sparkdf import SparkDataFrameDataSource

DATA_SOURCE = "silver"
SCHEMA = "global_temp"
EHR_PATIENT_RI = """
SELECT e.encounter_id
FROM global_temp.encounter e
LEFT ANTI JOIN (SELECT local_patient_id FROM global_temp.patient_record WHERE system = 'ehr') p
  ON e.fhir_patient_id = p.local_patient_id
"""


def reference(table: str, column: str) -> dict:
    return {
        "valid_reference_data": {"dataset": f"{DATA_SOURCE}/{SCHEMA}/{table}", "column": column}
    }


NOT_EMPTY = {"row_count": {"threshold": {"must_be_greater_than": 0}}}
KEY = [{"missing": None}, {"duplicate": None}]

# Silver table -> contract body (columns, dataset-level checks).
CONTRACTS = {
    "patient_record": {
        "columns": [
            {
                "name": "system",
                "checks": [{"invalid": {"valid_values": ["ehr", "lab", "adt", "billing"]}}],
            },
            {"name": "local_patient_id", "checks": [{"missing": None}]},
            {
                "name": "clinic_id",
                "checks": [{"invalid": {"valid_values": ["boston", "worcester", "springfield"]}}],
            },
            {"name": "sex", "checks": [{"invalid": {"valid_values": ["M", "F", "U"]}}]},
            {
                "name": "phone",
                "checks": [
                    {"invalid": {"valid_format": {"name": "10 digits", "regex": "^[0-9]{10}$"}}}
                ],
            },
            {"name": "birth_date", "checks": [{"missing": None}]},
        ],
        "checks": [
            NOT_EMPTY,
            {"duplicate": {"columns": ["system", "local_patient_id"]}},
            {
                "failed_rows": {
                    "name": "Birth date from 1900 to today",
                    "qualifier": "birth_date",
                    "expression": "birth_date < DATE '1900-01-01' OR birth_date > current_date()",
                }
            },
        ],
    },
    "encounter": {
        "columns": [
            {"name": "encounter_id", "checks": KEY},
            {"name": "fhir_patient_id", "checks": [{"missing": None}]},
            {
                "name": "class_code",
                "checks": [{"invalid": {"valid_values": ["AMB", "EMER", "IMP", "HH", "VR"]}}],
            },
            {"name": "start_at", "checks": [{"missing": None}]},
        ],
        "checks": [
            NOT_EMPTY,
            {
                "failed_rows": {
                    "name": "Encounter patient is an EHR patient record",
                    "qualifier": "ehr_patient",
                    "query": EHR_PATIENT_RI,
                }
            },
            {
                "failed_rows": {
                    "name": "Encounter does not end before it starts",
                    "qualifier": "period",
                    "expression": "end_at < start_at",
                }
            },
        ],
    },
    "condition": {
        "columns": [
            {"name": "condition_id", "checks": KEY},
            {
                "name": "encounter_id",
                "checks": [{"invalid": reference("encounter", "encounter_id")}],
            },
        ],
        "checks": [NOT_EMPTY],
    },
    "lab_result": {
        "columns": [
            {"name": "result_id", "checks": KEY},
            {"name": "lab_patient_id", "checks": [{"missing": None}]},
            {"name": "value_numeric", "checks": [{"invalid": {"valid_min": 0}}]},
        ],
        "checks": [NOT_EMPTY],
    },
    "claim": {
        "columns": [
            {"name": "claim_id", "checks": KEY},
            {"name": "billed_amount", "checks": [{"invalid": {"valid_min": 0}}]},
            {"name": "paid_amount", "checks": [{"invalid": {"valid_min": 0}}]},
            {"name": "status", "checks": [{"invalid": {"valid_values": ["paid", "denied"]}}]},
        ],
        "checks": [
            NOT_EMPTY,
            {
                "failed_rows": {
                    "name": "A denied claim has a reason",
                    "qualifier": "denial_reason",
                    "expression": "status = 'denied' AND denial_reason IS NULL",
                }
            },
        ],
    },
    "claim_line": {
        "columns": [
            {"name": "claim_id", "checks": [{"invalid": reference("claim", "claim_id")}]},
            {"name": "amount", "checks": [{"invalid": {"valid_min": 0}}]},
        ],
        "checks": [{"duplicate": {"columns": ["claim_id", "line_no"]}}],
    },
    "adt_event": {
        "columns": [
            {"name": "event_id", "checks": KEY},
            {
                "name": "event_type",
                "checks": [{"invalid": {"valid_values": ["A01", "A02", "A03"]}}],
            },
            {"name": "bed_id", "checks": [{"invalid": reference("bed", "bed_id")}]},
        ],
        "checks": [NOT_EMPTY],
    },
    "ed_visit": {
        "columns": [{"name": "ed_visit_id", "checks": KEY}],
        "checks": [
            NOT_EMPTY,
            {
                "failed_rows": {
                    "name": "Arrival, triage, provider and departure in order",
                    "qualifier": "timeline",
                    "expression": "triage_at < arrival_at OR provider_seen_at < triage_at"
                    " OR departure_at < provider_seen_at",
                }
            },
        ],
    },
    "bed": {"columns": [{"name": "bed_id", "checks": KEY}], "checks": [NOT_EMPTY]},
}


def contract_yaml(table: str, body: dict) -> str:
    """The contract as YAML; JSON is valid YAML, so no YAML library is needed."""
    return json.dumps({"dataset": f"{DATA_SOURCE}/{SCHEMA}/{table}", **body}, indent=2)


def run(spark: SparkSession, run_id: str, silver_root: str, contracts: dict = CONTRACTS) -> dict:
    """Verify every contract; returns {"ok", "checks", "failed": [(table, check)], "results"}."""
    if not run_id:
        raise ValueError("run_id is required")
    for table in {"patient_record", *contracts}:
        spark.read.format("delta").load(f"{silver_root}/{table}").createOrReplaceGlobalTempView(
            table
        )
    source = SparkDataFrameDataSource.from_existing_session(session=spark, name=DATA_SOURCE)
    results, failed, ok = [], [], True
    for table, body in contracts.items():
        session = ContractVerificationSession.execute(
            contract_yaml_sources=[ContractYamlSource.from_str(contract_yaml(table, body))],
            data_source_impls=[source],
        )
        ok = ok and session.is_ok
        for verification in session.contract_verification_results:
            if verification.error or not verification.check_results:
                failed.append((table, f"contract error: {verification.error}"))
            for r in verification.check_results:
                label = ".".join(
                    p for p in (r.check.column_name, r.check.type, r.check.qualifier) if p
                )
                results.append(
                    (table, label, r.check.name, r.outcome.name, r.diagnostic_metric_values)
                )
                if r.outcome != CheckOutcome.PASSED:
                    failed.append((table, label))
    return {"ok": ok and not failed, "checks": len(results), "failed": failed, "results": results}


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

if __name__ == "__main__":
    result = run(spark, run_id, silver_root)  # noqa: F821 (Fabric session global)
    for row in result["results"]:
        print(*row[:4])
    if not result["ok"]:
        raise RuntimeError(f"data quality failed: {result['failed']}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
