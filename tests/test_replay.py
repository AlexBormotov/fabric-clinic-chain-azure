"""U11 ADT replay. Fast tests cover the schedule; the `stand` test replays into the emulator."""

import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from clinic_chain import adt_replay

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "data" / "sources" / "adt" / "events.csv"
START = datetime(2025, 1, 1)


def fixture_events(n: int = 1000) -> list[dict]:
    """n events, some sharing a timestamp, as `load` returns them."""
    return [
        {
            "event_id": i + 1,
            "event_type": "A01",
            "event_time": (START + timedelta(minutes=7 * (i // 3))).strftime("%Y-%m-%d %H:%M:%S"),
            "clinic_id": ("boston", "worcester", "springfield")[i % 3],
            "stay_id": f"V-{i}",
            "adt_patient_id": f"P{i}",
            "ward_id": "MED",
            "bed_id": "B",
            "from_ward_id": None,
            "from_bed_id": None,
        }
        for i in range(n)
    ]


def as_received(sends: list[adt_replay.Send], rate: float) -> list[tuple]:
    at = adt_replay.offsets(sends, rate)
    pairs = enumerate(zip(sends, at, strict=True))
    return [(k, s.event, START + timedelta(seconds=t)) for k, (s, t) in pairs]


def test_shares_are_exact_and_measurable():
    events = fixture_events()
    sends = adt_replay.schedule(events, late_share=0.05, duplicate_share=0.03, seed=1)
    assert sum(s.late for s in sends) == 50
    assert sum(s.copy for s in sends) == 30
    m = adt_replay.measure(as_received(sends, rate=50))
    assert m["events"] == 1000 and m["sends"] == 1030
    assert m["late_share"] == 0.05
    assert m["duplicate_share"] == 0.03


def test_every_event_sent_and_copies_follow_originals():
    events = fixture_events()
    sends = adt_replay.schedule(events, 0.05, 0.03, seed=2)
    ids = [s.event["event_id"] for s in sends]
    assert set(ids) == {e["event_id"] for e in events}
    assert [s.copy for s in sends].count(False) == len(events)
    first, originals = {}, 0  # originals: position among non-copy sends
    for s in sends:
        if s.copy:
            between = originals - first[s.event["event_id"]] - 1  # originals sent after it
            assert 0 <= between <= adt_replay.MAX_SHIFT
        else:
            first[s.event["event_id"]] = originals
            originals += 1
    assert max(Counter(ids).values()) == 2


def test_late_events_trail_a_later_event_and_others_keep_order():
    events = fixture_events()
    sends = adt_replay.schedule(events, 0.10, 0.0, seed=3)
    latest = None
    for s in sends:
        t = s.event["event_time"]
        assert s.late == (latest is not None and t < latest)
        latest = max(latest or t, t)
    in_order = [s.event["event_id"] for s in sends if not s.late]
    assert in_order == sorted(in_order)


def test_schedule_is_seeded():
    events = fixture_events()
    a = adt_replay.schedule(events, 0.05, 0.03, seed=4)
    assert a == adt_replay.schedule(events, 0.05, 0.03, seed=4)
    assert a != adt_replay.schedule(events, 0.05, 0.03, seed=5)


def test_offsets_keep_event_time_and_hit_rate():
    sends = adt_replay.schedule(fixture_events(), 0.05, 0.03, seed=6)
    at = adt_replay.offsets(sends, rate=20)
    assert at == sorted(at) and at[0] == 0
    assert at[-1] == pytest.approx((len(sends) - 1) / 20)
    assert adt_replay.measure(as_received(sends, rate=20))["rate"] == pytest.approx(20)


def test_load_orders_by_event_time(tmp_path):
    csv = tmp_path / "events.csv"
    header = "event_id,event_type,event_time,clinic_id,stay_id,adt_patient_id,ward_id,bed_id,"
    csv.write_text(
        header + "from_ward_id,from_bed_id\n"
        "2,A03,2025-01-02 00:00:00,boston,V1,P1,MED,B1,,\n"
        "1,A01,2025-01-01 00:00:00,boston,V1,P1,MED,B1,,\n"
    )
    rows = adt_replay.load(csv)
    assert [r["event_id"] for r in rows] == [1, 2]
    assert rows[0]["from_bed_id"] is None


def _positions(consumer) -> dict[str, int | str]:
    """Sequence number of the last event per partition, so a read sees only the next replay."""
    positions = {}
    for pid in consumer.get_partition_ids():
        props = consumer.get_partition_properties(pid)
        positions[pid] = "-1" if props["is_empty"] else props["last_enqueued_sequence_number"]
    return positions


@pytest.mark.stand
def test_replay_into_emulator():
    from azure.eventhub import EventHubConsumerClient

    limit, rate, late_share, duplicate_share = 2000, 50.0, 0.05, 0.03
    consumer = EventHubConsumerClient.from_connection_string(
        adt_replay.EMULATOR, consumer_group="replay-check", eventhub_name=adt_replay.EVENTHUB
    )
    events = adt_replay.load(EVENTS, limit)
    received = []
    with consumer:
        start = _positions(consumer)
        summary = adt_replay.run(
            events, adt_replay.EMULATOR, adt_replay.EVENTHUB, rate, late_share, duplicate_share, 7
        )

        def collect(_, batch):
            for e in batch:
                seq = e.properties[b"replay_seq"]
                received.append((seq, e.body_as_json(), e.enqueued_time))

        reader = threading.Thread(
            target=consumer.receive_batch,
            kwargs={
                "on_event_batch": collect,
                "starting_position": start,
                "starting_position_inclusive": False,
                "max_wait_time": 2,
            },
            daemon=True,
        )
        reader.start()
        deadline = time.monotonic() + 120
        while len(received) < summary["sends"] and time.monotonic() < deadline:
            time.sleep(0.5)
        time.sleep(3)  # anything beyond the expected count would show up as an extra send
    m = adt_replay.measure(received)
    print({"producer": summary, "consumer": m})
    assert m["events"] == limit
    assert {r[1]["event_id"]: r[1] for r in received} == {e["event_id"]: e for e in events}
    assert m["sends"] == summary["sends"] == limit + round(duplicate_share * limit)
    assert m["rate"] == pytest.approx(rate, rel=0.10)
    assert m["late_share"] == pytest.approx(late_share, abs=0.01)
    assert m["duplicate_share"] == pytest.approx(duplicate_share, abs=0.01)
