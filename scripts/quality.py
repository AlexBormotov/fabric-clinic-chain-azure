"""Run the data quality notebook on the local Silver; exits non-zero when a check fails."""

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from clinic_chain import spark

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver", type=Path, default=ROOT / "data" / "lh_silver" / "Tables")
    args = parser.parse_args()
    session = spark.session()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    started = time.monotonic()
    result = spark.notebook("nb_quality").run(session, run_id, str(args.silver))
    for table, label, _, outcome, _ in result["results"]:
        print(f"{outcome:<12} {table}: {label}")
    print(f"{result['checks']} checks, {len(result['failed'])} failed")
    print(f"in {time.monotonic() - started:.0f} s")
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
