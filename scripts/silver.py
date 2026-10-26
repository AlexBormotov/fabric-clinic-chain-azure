"""Build Silver from the local Bronze with the Fabric notebook on local Spark + Delta."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from clinic_chain import spark

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze", type=Path, default=ROOT / "data" / "lh_bronze" / "Tables")
    parser.add_argument("--silver", type=Path, default=ROOT / "data" / "lh_silver" / "Tables")
    args = parser.parse_args()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    session = spark.session()
    spark.notebook("nb_silver").run(session, run_id, str(args.bronze), str(args.silver))
    report = session.read.format("delta").load(str(args.silver / "reconciliation"))
    report.orderBy("silver_table", "source", "measure", "reason").show(200, truncate=False)


if __name__ == "__main__":
    main()
