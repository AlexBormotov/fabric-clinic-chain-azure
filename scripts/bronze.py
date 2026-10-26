"""Land the local source stand and build Bronze with the Fabric notebook on local Spark + Delta."""

import argparse
import shutil
from datetime import UTC, datetime
from pathlib import Path

from clinic_chain import landing, spark
from clinic_chain.sources import contracts

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=ROOT / "data" / "sources")
    parser.add_argument("--lakehouse", type=Path, default=ROOT / "data" / "lh_bronze")
    args = parser.parse_args()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    files = args.lakehouse / "Files" / "landing"
    # Locally only the latest run is kept: each landing holds ~900 MB of FHIR.
    shutil.rmtree(files, ignore_errors=True)
    landing.land(args.sources, contracts.load(ROOT / "docs" / "contracts"), files, run_id)
    print(f"landed: {run_id}")
    counts = spark.notebook("nb_bronze").run(
        spark.session(), run_id, str(files), str(args.lakehouse / "Tables")
    )
    for table, n in counts.items():
        print(f"bronze.{table}: {n}")


if __name__ == "__main__":
    main()
