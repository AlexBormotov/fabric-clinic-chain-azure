"""ADT replay (U11): ADT events over the Event Hubs protocol in accelerated event time.

A seeded schedule sends a share of events late (after an event with a later event time) and a share
twice. Sends keep their event-time gaps, compressed so the whole replay averages the target rate.
"""

import csv
import json
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from azure.eventhub import EventData, EventHubProducerClient

from clinic_chain.sources import contracts

# The emulator's documented connection string; SAS_KEY_VALUE is a literal placeholder.
EMULATOR = (
    "Endpoint=sb://eventhubs;SharedAccessKeyName=RootManageSharedAccessKey;"
    "SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;"
)
EVENTHUB = "adt"
MAX_SHIFT = 20  # positions a late event or a duplicate copy trails behind


@dataclass(frozen=True)
class Send:
    event: dict
    due: datetime  # running maximum of event times up to this send
    late: bool = False
    copy: bool = False


def load(path: Path, limit: int | None = None) -> list[dict]:
    """Contract rows in event-time order; empty fields become None, `event_id` an int."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = [{k: v or None for k, v in row.items()} for row in csv.DictReader(f)]
    for row in rows:
        row["event_id"] = int(row["event_id"])
    rows.sort(key=lambda r: (r["event_time"], r["event_id"]))  # the format sorts as it reads
    return rows[:limit]


def _time(event: dict) -> datetime:
    return datetime.strptime(event["event_time"], contracts.DATETIME)


def schedule(
    events: list[dict], late_share: float, duplicate_share: float, seed: int
) -> list[Send]:
    """Send list with exactly round(share * n) late events and duplicate copies."""
    rng = random.Random(seed)
    n = len(events)
    times = [_time(e) for e in events]
    n_late = round(late_share * n)
    # A late event goes right after its anchor: a later in-order event at most MAX_SHIFT ahead.
    anchor: dict[int, int] = {}
    candidates = list(range(n))
    rng.shuffle(candidates)
    for i in candidates:
        if len(anchor) == n_late:
            break
        if i in anchor.values():
            continue
        window = range(i + 1, min(n, i + MAX_SHIFT + 1))
        later = [j for j in window if times[j] > times[i] and j not in anchor]
        if later:
            anchor[i] = rng.choice(later)
    if len(anchor) != n_late:
        raise ValueError(f"late share {late_share} needs more events with distinct times")
    order = sorted(range(n), key=lambda i: (anchor[i], 1, i) if i in anchor else (i, 0, i))

    # A duplicate copy follows its original after 1..MAX_SHIFT originals (fewer at the end).
    copies_after = defaultdict(list)
    for p in sorted(rng.sample(range(n), round(duplicate_share * n))):
        copies_after[min(n - 1, p + rng.randint(1, MAX_SHIFT))].append(order[p])

    sends, due = [], times[0] if n else None
    for p, i in enumerate(order):
        due = max(due, times[i])
        sends.append(Send(events[i], due, late=i in anchor))
        sends += [Send(events[c], due, copy=True) for c in copies_after[p]]
    return sends


def offsets(sends: list[Send], rate: float) -> list[float]:
    """Wall-clock seconds from the start per send: event time compressed to `rate` on average."""
    if len(sends) < 2 or sends[-1].due == sends[0].due:
        return [i / rate for i in range(len(sends))]
    span = (sends[-1].due - sends[0].due).total_seconds()
    seconds_per_send = (len(sends) - 1) / rate
    return [(s.due - sends[0].due).total_seconds() / span * seconds_per_send for s in sends]


def replay(sends: list[Send], at: list[float], producer: EventHubProducerClient) -> float:
    """Send each event at its offset; sends that are due together go in one batch per clinic.

    Returns the elapsed wall-clock seconds."""
    start = time.monotonic()
    i = 0
    while i < len(sends):
        wait = start + at[i] - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        now = time.monotonic() - start
        j = i
        while j < len(sends) and at[j] <= now:
            j += 1
        by_clinic = defaultdict(list)
        for k in range(i, j):
            by_clinic[sends[k].event["clinic_id"]].append(k)
        for clinic, ks in by_clinic.items():
            batch = producer.create_batch(partition_key=clinic)
            for k in ks:
                data = EventData(json.dumps(sends[k].event))
                data.properties = {"replay_seq": k}
                try:
                    batch.add(data)
                except ValueError:  # batch full
                    producer.send_batch(batch)
                    batch = producer.create_batch(partition_key=clinic)
                    batch.add(data)
            producer.send_batch(batch)
        i = j
    return time.monotonic() - start


def measure(received: list[tuple[int, dict, datetime]]) -> dict:
    """Shares and rate as a consumer sees them, from (replay_seq, body, enqueued time) triples.

    An event is late when an earlier send carried a later event time; repeats of an event id are
    duplicate copies. Rate is sends per second between the first and last enqueue."""
    seen, late, latest = set(), 0, None
    for _, event, _ in sorted(received, key=lambda r: r[0]):
        if event["event_id"] in seen:
            continue
        seen.add(event["event_id"])
        t = _time(event)
        if latest is not None and t < latest:
            late += 1
        latest = t if latest is None else max(latest, t)
    enqueued = sorted(r[2] for r in received)
    span = (enqueued[-1] - enqueued[0]).total_seconds() if received else 0
    return {
        "events": len(seen),
        "sends": len(received),
        "late_share": late / len(seen) if seen else 0.0,
        "duplicate_share": (len(received) - len(seen)) / len(seen) if seen else 0.0,
        "rate": (len(received) - 1) / span if span else 0.0,
    }


def run(
    events: list[dict],
    connection_string: str,
    eventhub: str | None,
    rate: float,
    late_share: float,
    duplicate_share: float,
    seed: int,
) -> dict:
    sends = schedule(events, late_share, duplicate_share, seed)
    at = offsets(sends, rate)
    # An Eventstream custom endpoint string carries EntityPath; the SDK rejects a second name.
    name = None if "EntityPath=" in connection_string else eventhub
    producer = EventHubProducerClient.from_connection_string(connection_string, eventhub_name=name)
    with producer:
        elapsed = replay(sends, at, producer)
    span = (sends[-1].due - sends[0].due).total_seconds() if sends else 0
    return {
        "events": len(events),
        "sends": len(sends),
        "late": sum(s.late for s in sends),
        "copies": sum(s.copy for s in sends),
        "acceleration": round(span / at[-1]) if sends and at[-1] else None,
        "elapsed_s": round(elapsed, 2),
        "rate": round((len(sends) - 1) / elapsed, 2) if elapsed else None,
    }
