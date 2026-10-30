"""Replay ADT events to Event Hubs: the local emulator, or an Eventstream custom endpoint."""

import argparse
import json
import os
from pathlib import Path

from clinic_chain import adt_replay

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=ROOT / "data/sources/adt/events.csv")
    parser.add_argument("--rate", type=float, default=50.0, help="sends per second (10-50)")
    parser.add_argument("--late-share", type=float, default=0.05)
    parser.add_argument("--duplicate-share", type=float, default=0.03)
    parser.add_argument("--limit", type=int, help="replay only the first N events")
    parser.add_argument("--seed", type=int, default=20261028)
    parser.add_argument(
        "--connection-string",
        default=os.environ.get("ADT_EVENTHUB_CONNECTION_STRING") or adt_replay.EMULATOR,
        help="default: $ADT_EVENTHUB_CONNECTION_STRING, else the local emulator",
    )
    parser.add_argument("--eventhub", default=adt_replay.EVENTHUB, help="unless EntityPath is set")
    args = parser.parse_args()
    events = adt_replay.load(args.events, args.limit)
    summary = adt_replay.run(
        events,
        args.connection_string,
        args.eventhub,
        args.rate,
        args.late_share,
        args.duplicate_share,
        args.seed,
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
