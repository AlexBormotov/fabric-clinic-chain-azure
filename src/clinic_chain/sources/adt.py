"""Bed management (ADT) history: wards and beds, inpatient stays, ED visits.

Synthea inpatient stays are placed first. Referred inpatients then arrive as a seasonal Poisson
process per ward until the configured occupancy is reached; an arrival with no free bed for its
whole stay is diverted (not admitted), so no bed is ever double-booked.
"""

import bisect
import math
import random
from datetime import date, datetime, timedelta

LOS_SIGMA = 0.6  # lognormal spread of length of stay


def beds_for(clinic: str, cfg: dict) -> list[dict]:
    prefix = clinic[:3].upper()
    return [
        {"clinic_id": clinic, "ward_id": ward, "bed_id": f"{prefix}-{ward}-{n:02d}"}
        for ward, count in cfg["clinics"][clinic]["beds"].items()
        for n in range(1, count + 1)
    ]


def ward_for(encounter_type: str) -> str:
    text = encounter_type.lower()
    if "intensive" in text or "icu" in text:
        return "ICU"
    if "surg" in text:
        return "SUR"
    return "MED"


def lognormal_minutes(median: float, rng: random.Random, cap: float | None = None) -> timedelta:
    value = rng.lognormvariate(math.log(median), LOS_SIGMA)
    return timedelta(minutes=min(value, cap) if cap else value)


def poisson(lam: float, rng: random.Random) -> int:
    limit, k, p = math.exp(-lam), 0, rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


class Ward:
    """Beds of one ward with their booked intervals, each kept sorted by start."""

    def __init__(self, beds: list[str]):
        self.booked: dict[str, list[tuple[datetime, datetime]]] = {b: [] for b in beds}

    def copy(self) -> "Ward":
        other = Ward([])
        other.booked = {bed: list(intervals) for bed, intervals in self.booked.items()}
        return other

    def free_bed(self, start: datetime, end: datetime) -> str | None:
        for bed, intervals in self.booked.items():
            i = bisect.bisect_left(intervals, (start,))
            if i > 0 and intervals[i - 1][1] > start:
                continue
            if i < len(intervals) and intervals[i][0] < end:
                continue
            return bed
        return None

    def book(self, bed: str, start: datetime, end: datetime) -> None:
        bisect.insort(self.booked[bed], (start, end))

    def occupancy(self, start: datetime, end: datetime) -> float:
        busy = sum(
            (min(e, end) - max(s, start)).total_seconds()
            for intervals in self.booked.values()
            for s, e in intervals
            if e > start and s < end
        )
        return busy / (len(self.booked) * (end - start).total_seconds())


def _season(day: date, amplitude: float) -> float:
    return 1 + amplitude * math.cos(2 * math.pi * (day.timetuple().tm_yday - 15) / 365.25)


def name_pools(persons: list[dict]) -> dict:
    return {
        "given": sorted({p["given_name"] for p in persons}),
        "family": sorted({p["family_name"] for p in persons}),
        "postal": sorted({p["postal_code"] for p in persons if p["postal_code"]}),
    }


def new_person(clinic: str, origin: str, n: int, pools: dict, rng: random.Random) -> dict:
    """A non-registered person: `referred` inpatient or ED `walk_in`."""
    return {
        "person_id": f"{origin[0].upper()}-{clinic[:3].upper()}-{n:05d}",
        "origin": origin,
        "clinic_id": clinic,
        "given_name": rng.choice(pools["given"]),
        "family_name": rng.choice(pools["family"]),
        "birth_date": (date(1936, 1, 1) + timedelta(days=rng.randrange(70 * 365))).isoformat(),
        "sex": rng.choice("MF"),
        "phone": f"555-{rng.randrange(100, 1000)}-{rng.randrange(1000, 10000)}",
        "postal_code": rng.choice(pools["postal"]),
    }


def build_stays(clinic: str, synthea: dict, cfg: dict, rng: random.Random) -> tuple[list, list]:
    """All inpatient stays of one clinic and the referred persons created for them.

    A stay is {stay_id, person_id, segments: [{ward_id, bed_id, start, end}], open, encounter_id}.
    `end` of an open stay is the horizon; it has no discharge event.
    """
    window_start = datetime.fromisoformat(cfg["window"]["start"])
    horizon = datetime.fromisoformat(cfg["window"]["end"]) + timedelta(days=1)
    beds = beds_for(clinic, cfg)
    wards = {w: Ward([b["bed_id"] for b in beds if b["ward_id"] == w]) for w in cfg["wards"]}
    stays = []

    def place(person_id, segments, encounter_id=None):
        stays.append(
            {
                "person_id": person_id,
                "segments": segments,
                "open": segments[-1]["end"] >= horizon,
                "encounter_id": encounter_id,
            }
        )

    for s in sorted(synthea["stays"], key=lambda s: s["start"]):
        end = min(s["end"], horizon)
        preferred = ward_for(s["type"])
        for ward in [preferred, *(w for w in wards if w != preferred)]:
            if bed := wards[ward].free_bed(s["start"], end):
                break
        else:
            raise RuntimeError(f"{clinic}: no free bed for Synthea stay {s['encounter_id']}")
        wards[ward].book(bed, s["start"], end)
        segment = {"ward_id": ward, "bed_id": bed, "start": s["start"], "end": end}
        place(s["person_id"], [segment], s["encounter_id"])

    # Calibrate each ward's offered load so that achieved occupancy (after diversions) meets the
    # target. ICU goes first: its transfers land in MED before MED is calibrated.
    target = cfg["referred"]["occupancy_target"]
    referred: list[list[dict]] = []
    for ward in cfg["wards"]:
        lo, hi = 1.0, 3.0
        for _ in range(12):
            trial = {w: v.copy() for w, v in wards.items()}
            _referred(clinic, ward, (lo + hi) / 2, trial, cfg, window_start, horizon)
            if trial[ward].occupancy(window_start, horizon) < target:
                lo = (lo + hi) / 2
            else:
                hi = (lo + hi) / 2
        referred += _referred(clinic, ward, (lo + hi) / 2, wards, cfg, window_start, horizon)

    # Referred persons: a new person per stay, except 30-day readmissions of a recent patient.
    pools = name_pools(synthea["persons"])
    persons: list[dict] = []
    last_discharge: dict[str, datetime] = {}
    for segments in sorted(referred, key=lambda segs: (segs[0]["start"], segs[0]["bed_id"])):
        at = segments[0]["start"]
        recent = sorted(
            p for p, d in last_discharge.items() if timedelta(0) < at - d <= timedelta(days=30)
        )
        if recent and rng.random() < cfg["referred"]["readmission_30d"]:
            person_id = rng.choice(recent)
        else:
            person = new_person(clinic, "referred", len(persons) + 1, pools, rng)
            persons.append(person)
            person_id = person["person_id"]
        last_discharge[person_id] = segments[-1]["end"]
        place(person_id, segments)

    stays.sort(key=lambda s: (s["segments"][0]["start"], s["person_id"]))
    prefix = clinic[:3].upper()
    for n, stay in enumerate(stays, 1):
        stay["stay_id"] = f"V-{prefix}-{n:06d}"
        stay["clinic_id"] = clinic
    return stays, persons


def _referred(
    clinic: str,
    ward: str,
    load: float,
    wards: dict[str, Ward],
    cfg: dict,
    window_start: datetime,
    horizon: datetime,
) -> list[list[dict]]:
    """Referred arrivals to one ward at `load` x the target rate, booked into `wards`.

    Returns the segments of each admitted stay. Every draw happens whether or not a bed is free,
    so runs at different loads share one random stream and occupancy grows with load.
    """
    rng = random.Random(f"{cfg['seed']}:{clinic}:{ward}")
    ref = cfg["referred"]
    median = cfg["wards"][ward]["los_median_days"]
    med_median = cfg["wards"]["MED"]["los_median_days"]
    lam = load * ref["occupancy_target"] * cfg["clinics"][clinic]["beds"][ward]
    lam /= median * math.exp(LOS_SIGMA**2 / 2)
    stays = []
    day = window_start.date()
    while day < horizon.date():
        midnight = datetime.combine(day, datetime.min.time())
        for _ in range(poisson(lam * _season(day, ref["winter_amplitude"]), rng)):
            at = midnight + timedelta(seconds=rng.randrange(86400))
            end = min(at + lognormal_minutes(median * 1440, rng), horizon)
            transfer = ward == "ICU" and rng.random() < ref["icu_to_med_transfer"]
            med_end = min(end + lognormal_minutes(med_median * 1440, rng), horizon)
            bed = wards[ward].free_bed(at, end)
            if bed is None:
                continue  # diverted
            wards[ward].book(bed, at, end)
            segments = [{"ward_id": ward, "bed_id": bed, "start": at, "end": end}]
            if transfer and end < horizon and (med_bed := wards["MED"].free_bed(end, med_end)):
                wards["MED"].book(med_bed, end, med_end)
                segments.append({"ward_id": "MED", "bed_id": med_bed, "start": end, "end": med_end})
            stays.append(segments)
        day += timedelta(days=1)
    return stays


def ed_visits(
    clinic: str, synthea: dict, stays: list, cfg: dict, rng: random.Random
) -> tuple[list, list]:
    """ED visits and the walk-in persons created for them.

    Visits: every Synthea emergency encounter, referred admissions that came via ED, and walk-ins
    who go home, added until admissions are `ed.admitted_share` of all visits.
    """
    ed = cfg["ed"]

    def times(arrival: datetime) -> tuple[datetime, datetime]:
        triage = arrival + lognormal_minutes(ed["triage_median_min"], rng, ed["triage_cap_min"])
        seen = triage + lognormal_minutes(ed["provider_median_min"], rng, ed["provider_cap_min"])
        return triage, seen

    synthea_stays = {}
    for s in stays:
        if s["encounter_id"]:
            synthea_stays.setdefault(s["person_id"], []).append(s)
    visits = []
    for e in synthea["ed"]:
        arrival = e["start"]
        triage, seen = times(arrival)
        admitted = next(
            (
                s
                for s in synthea_stays.get(e["person_id"], [])
                if arrival <= s["segments"][0]["start"] <= arrival + timedelta(hours=24)
            ),
            None,
        )
        if admitted:
            departure = admitted["segments"][0]["start"]
            if seen >= departure:  # admission came faster than the drawn ED times
                span = departure - arrival
                triage, seen = arrival + span * 0.1, arrival + span * 0.4
        else:
            departure = seen + lognormal_minutes(ed["stay_after_provider_median_min"], rng)
        visits.append((e["person_id"], arrival, triage, seen, departure, admitted))

    for s in stays:
        if s["encounter_id"] or rng.random() >= cfg["referred"]["via_ed"]:
            continue
        admit = s["segments"][0]["start"]
        offset_triage = lognormal_minutes(ed["triage_median_min"], rng, ed["triage_cap_min"])
        offset_seen = lognormal_minutes(ed["provider_median_min"], rng, ed["provider_cap_min"])
        after = lognormal_minutes(ed["stay_after_provider_median_min"], rng)
        arrival = admit - after - offset_seen - offset_triage
        visits.append((s["person_id"], arrival, arrival + offset_triage, admit - after, admit, s))

    admitted = sum(1 for v in visits if v[5])
    walk_ins = []
    start = datetime.fromisoformat(cfg["window"]["start"])
    days = (datetime.fromisoformat(cfg["window"]["end"]) - start).days + 1
    pools = name_pools(synthea["persons"])
    for n in range(1, max(0, round(admitted / ed["admitted_share"]) - len(visits)) + 1):
        person = new_person(clinic, "walk_in", n, pools, rng)
        walk_ins.append(person)
        arrival = start + timedelta(seconds=rng.randrange(days * 86400))
        triage, seen = times(arrival)
        departure = seen + lognormal_minutes(ed["stay_after_provider_median_min"], rng)
        visits.append((person["person_id"], arrival, triage, seen, departure, None))

    visits.sort(key=lambda v: (v[1], v[0]))
    prefix = clinic[:3].upper()
    return [
        {
            "ed_visit_id": f"E-{prefix}-{n:06d}",
            "clinic_id": clinic,
            "person_id": person_id,
            "arrival_at": arrival,
            "triage_at": triage,
            "provider_seen_at": seen,
            "departure_at": departure,
            "disposition": "admitted" if stay else "discharged",
            "stay_id": stay["stay_id"] if stay else None,
        }
        for n, (person_id, arrival, triage, seen, departure, stay) in enumerate(visits, 1)
    ], walk_ins


def adt_events(stays: list) -> list:
    """A01 admit, A02 transfer, A03 discharge (none for stays still open at the horizon)."""
    events = []
    for s in stays:
        first, *rest = s["segments"]
        events.append(("A01", first["start"], s, first, None))
        previous = first
        for seg in rest:
            events.append(("A02", seg["start"], s, seg, previous))
            previous = seg
        if not s["open"]:
            events.append(("A03", previous["end"], s, previous, None))
    events.sort(key=lambda e: (e[1], e[2]["stay_id"], e[0]))
    return [
        {
            "event_id": n,
            "event_type": kind,
            "event_time": at,
            "clinic_id": s["clinic_id"],
            "stay_id": s["stay_id"],
            "person_id": s["person_id"],
            "ward_id": seg["ward_id"],
            "bed_id": seg["bed_id"],
            "from_ward_id": prev["ward_id"] if prev else None,
            "from_bed_id": prev["bed_id"] if prev else None,
        }
        for n, (kind, at, s, seg, prev) in enumerate(events, 1)
    ]
