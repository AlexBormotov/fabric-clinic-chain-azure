"""Run the bed state history notebook on the local Silver."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from clinic_chain import spark

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver", type=Path, default=ROOT / "data" / "lh_silver" / "Tables")
    args = parser.parse_args()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    print(spark.notebook("nb_bed_history").run(spark.session(), run_id, str(args.silver)))


if __name__ == "__main__":
    main()
