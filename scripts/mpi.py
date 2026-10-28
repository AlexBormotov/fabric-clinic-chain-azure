"""Run the MPI notebook on the local Silver, or evaluate it against ground truth (--eval)."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from clinic_chain import mpi_eval, spark

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver", type=Path, default=ROOT / "data" / "lh_silver" / "Tables")
    parser.add_argument("--eval", action="store_true", help="write docs/evidence/mpi.json")
    args = parser.parse_args()
    session = spark.session()
    if args.eval:
        truth = ROOT / "data" / "sources" / "ground_truth"
        result = {
            "measured_at": datetime.now(UTC).strftime("%Y-%m-%d"),
            **mpi_eval.evaluate(session, args.silver, truth),
        }
        out = ROOT / "docs" / "evidence" / "mpi.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    print(spark.notebook("nb_mpi").run(session, run_id, str(args.silver)))


if __name__ == "__main__":
    main()
