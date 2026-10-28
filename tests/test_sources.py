"""U03 source derivation. Fast tests run a tiny hand-built FHIR population, `slow` the full one."""

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import synth
import yaml

from clinic_chain.sources import contracts, noise
from clinic_chain.sources.derive import derive

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = contracts.load(ROOT / "docs" / "contracts")
CFG = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())
DT = contracts.DATETIME


# --- checks shared by the tiny and the full population ------------------------------------


def rows(out: Path, table: str) -> list[dict]:
    header, data = contracts.read(out, CONTRACTS[table])
    return [dict(zip(header, r, strict=True)) for r in data]


def link_map(out: Path) -> dict[tuple[str, str], str]:
    return {
        (r["system"], r["local_patient_id"]): r["person_id"]
        for r in rows(out, "ground_truth.patient_links")
    }


def check_contracts(out: Path) -> None:
    errors = [e for name, spec in CONTRACTS.items() for e in contracts.validate(out, name, spec)]
    assert not errors, errors[:10]


def check_ground_truth(out: Path) -> None:
    """Every local patient record, and every fact using one, resolves to exactly one person."""
    persons = {p["person_id"] for p in rows(out, "ground_truth.persons")}
    links = link_map(out)
    assert set(links.values()) <= persons
    registers = {
        "billing": ("billing.patient_account", "account_id", [("billing.claim", "account_id")]),
        "lab": ("lab.patients", "lab_patient_id", [("lab.results", "lab_patient_id")]),
        "adt": (
            "adt.patients",
            "adt_patient_id",
            [("adt.events", "adt_patient_id"), ("adt.ed_visits", "adt_patient_id")],
        ),
    }
    for system, (table, key, facts) in registers.items():
        local = {r[key] for r in rows(out, table)}
        assert local == {lid for (s, lid) in links if s == system}, system
        for fact_table, fact_key in facts:
            assert {r[fact_key] for r in rows(out, fact_table)} <= local, fact_table


def check_beds(out: Path) -> None:
    """No bed holds two stays at once; A01 opens a stay, A02 moves it, A03 closes it once."""
    bed_of, busy = {}, {}
    for e in sorted(rows(out, "adt.events"), key=lambda e: int(e["event_id"])):
        stay, bed = e["stay_id"], e["bed_id"]
        if e["event_type"] == "A01":
            assert stay not in bed_of
        else:
            assert bed_of.get(stay) == (e["from_bed_id"] if e["event_type"] == "A02" else bed)
            busy.pop(bed_of[stay])
        if e["event_type"] == "A03":
            del bed_of[stay]
        else:
            assert bed not in busy, f"{bed} double-booked at {e['event_time']}"
            busy[bed], bed_of[stay] = stay, bed


# --- noise ----------------------------------------------------------------------------------


def fake_persons(n: int) -> list[dict]:
    rng = random.Random(1)
    return [
        {
            "person_id": f"p{i}",
            "given_name": rng.choice(["Anna", "Boris", "Clara", "Dmitri"]),
            "family_name": rng.choice(["Ivanova", "Smith", "Kohler", "Bruen"]),
            "birth_date": f"19{rng.randrange(30, 99)}-{rng.randrange(1, 13):02d}-"
            f"{rng.randrange(1, 29):02d}",
            "phone": f"555-{rng.randrange(100, 1000)}-{rng.randrange(1000, 10000)}",
        }
        for i in range(n)
    ]


def noise_rates(register: list[dict], truth: dict[str, dict]) -> dict[str, float]:
    n = len(register)
    people = len({r["person_id"] for r in register})

    def differs(field):
        return sum(r[field] != truth[r["person_id"]][field] for r in register) / n

    def digits(phone):
        return re.sub(r"\D", "", phone)[-10:]  # "+1 555 ..." carries the country code

    phones = [(r["phone"], truth[r["person_id"]]["phone"]) for r in register]
    named = sum(
        (r["given_name"], r["family_name"])
        != (truth[r["person_id"]]["given_name"], truth[r["person_id"]]["family_name"])
        for r in register
    )
    return {
        "name_typo": named / n,
        "dob_day_month_swap": differs("birth_date"),
        "phone_format": sum(p != t and digits(p) == digits(t) for p, t in phones) / n,
        "phone_missing": sum(p == "" != t for p, t in phones) / n,
        "phone_changed": sum(p != "" and digits(p) != digits(t) for p, t in phones) / n,
        "duplicate": (n - people) / people,
    }


def test_noise_functions_always_change_the_value():
    rng = random.Random(0)
    for name in ["Al", "Anna", "Kohler"] * 50:
        assert noise.typo(name, rng) != name
    assert noise.swap_day_month("1962-07-11") == "1962-11-07"
    assert not noise.can_swap_day_month("1962-07-07")
    assert not noise.can_swap_day_month("1962-07-20")
    assert re.fullmatch(r"\D*555\D*153\D*4215", noise.reformat_phone("555-153-4215", rng))
    assert noise.reformat_phone("555-153-4215", rng) != "555-153-4215"
    assert re.fullmatch(r"555-\d{3}-\d{4}", noise.other_phone("555-153-4215", rng))
    assert noise.other_phone("555-153-4215", rng) != "555-153-4215"


def test_register_noise_rates_are_exact():
    persons = fake_persons(1000)
    register = noise.build_register(persons, "lab", "L########", CFG["noise"], random.Random(7))
    truth = {p["person_id"]: p for p in persons}
    measured = noise_rates(register, truth)
    for key, rate in CFG["noise"].items():
        assert abs(measured[key] - rate) <= 0.001, key
    assert len({r["local_patient_id"] for r in register}) == len(register)
    assert all(re.fullmatch(r"L\d{8}", r["local_patient_id"]) for r in register)


# --- contracts ------------------------------------------------------------------------------


def test_billing_ddl_matches_contract():
    ddl = (ROOT / "docs" / "contracts" / "billing.sql").read_text()
    for name, spec in CONTRACTS.items():
        if not name.startswith("billing."):
            continue
        body = re.search(rf"CREATE TABLE {name} \((.*?)\n\);", ddl, re.S).group(1)
        columns = [
            (m.group(1), m.group(2) == "NULL")
            for m in re.finditer(r"^\s+(\w+) \w+(?:\([\d, ]+\))? (NOT NULL|NULL)", body, re.M)
        ]
        assert columns == [(c["name"], c.get("nullable", False)) for c in spec["columns"]], name


def test_validator_catches_violations(tmp_path):
    spec = {
        "file": "t.csv",
        "primary_key": ["id"],
        "columns": [{"name": "id", "type": "int"}, {"name": "at", "type": "datetime"}],
    }
    (tmp_path / "t.csv").write_text("id,at\n1,2025-01-01 10:00:00\n1,\nx,2025-01-01\n")
    errors = contracts.validate(tmp_path, "t", spec)
    assert any("at is null" in e for e in errors)
    assert any("'x' is not int" in e for e in errors)
    assert any("'2025-01-01' is not datetime" in e for e in errors)
    assert any("not unique" in e for e in errors)


# --- tiny population, end to end ------------------------------------------------------------


def _iso(at: datetime) -> str:
    return at.isoformat() + "+00:00"


def _bundle(pid: str, birth: str, start: datetime) -> dict:
    def enc(eid, cls, kind, begin, hours):
        return {
            "resourceType": "Encounter",
            "id": eid,
            "class": {"code": cls},
            "type": [{"coding": [{"display": kind}]}],
            "subject": {"reference": f"urn:uuid:{pid}"},
            "period": {"start": _iso(begin), "end": _iso(begin + timedelta(hours=hours))},
            "participant": [
                {
                    "individual": {
                        "reference": "Practitioner?identifier=npi|99001",
                        "display": "Dr. Ann12 Lee34",
                    }
                }
            ],
        }

    return {
        "entry": [
            {"resource": r}
            for r in [
                {
                    "resourceType": "Patient",
                    "id": pid,
                    "name": [{"use": "official", "family": f"Fam{pid}9", "given": ["Giv1"]}],
                    "telecom": [{"system": "phone", "value": "555-100-2000"}],
                    "gender": "female",
                    "birthDate": birth,
                    "address": [{"postalCode": "02110"}],
                },
                enc(f"{pid}-e1", "EMER", "Emergency room admission", start, 1),
                enc(
                    f"{pid}-i1",
                    "IMP",
                    "Admission to surgical department",
                    start + timedelta(hours=3),
                    60,
                ),
                enc(f"{pid}-old", "AMB", "Check up", datetime(2010, 1, 1), 1),
                {
                    "resourceType": "Observation",
                    "category": [{"coding": [{"code": "laboratory"}]}],
                    "code": {"coding": [{"code": "2339-0", "display": "Glucose"}]},
                    "effectiveDateTime": _iso(start),
                    "valueQuantity": {"value": 98.5, "unit": "mg/dL"},
                },
                {
                    "resourceType": "ExplanationOfBenefit",
                    "type": {"coding": [{"code": "institutional"}]},
                    "insurer": {"display": "Medicare"},
                    "billablePeriod": {
                        "start": _iso(start),
                        "end": _iso(start + timedelta(days=2)),
                    },
                    "total": [
                        {
                            "category": {"coding": [{"code": "submitted"}]},
                            "amount": {"value": 1500.0},
                        }
                    ],
                    "payment": {"amount": {"value": 1200.0}},
                    "item": [
                        {
                            "productOrService": {
                                "coding": [{"code": "32485007", "display": "Hospital admission"}]
                            },
                            "net": {"value": 1500.0},
                        }
                    ],
                },
            ]
        ]
    }


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    root = tmp_path_factory.mktemp("tiny")
    fhir_dir = root / "fhir" / "boston" / "fhir"
    fhir_dir.mkdir(parents=True)
    (fhir_dir / "hospitalInformation1.json").write_text(json.dumps({"entry": []}))
    for i in range(6):
        start = datetime(2025, 1, 5, 9) + timedelta(days=20 * i)
        bundle = _bundle(f"pat{i}", f"1970-0{i + 1}-1{i}", start)
        (fhir_dir / f"Pat{i}.json").write_text(json.dumps(bundle))
    beds = {"ICU": 1, "MED": 2, "SUR": 1}
    cfg = {**CFG, "clinics": {"boston": {"name": "Boston Clinic", "beds": beds}}}
    out = root / "sources"
    derive(root / "fhir", out, cfg)
    return out


def test_tiny_outputs_match_contracts(tiny):
    check_contracts(tiny)


def test_tiny_ground_truth_resolves(tiny):
    check_ground_truth(tiny)


def test_tiny_beds_never_double_booked(tiny):
    check_beds(tiny)


def test_tiny_reads_fhir_as_expected(tiny):
    persons = rows(tiny, "ground_truth.persons")
    registered = [p for p in persons if p["origin"] == "synthea"]
    assert len(registered) == 6
    assert registered[0]["family_name"] == "Fampat" and registered[0]["given_name"] == "Giv"
    assert any(p["origin"] == "referred" for p in persons)
    assert len(rows(tiny, "lab.results")) == 6
    ed = [v for v in rows(tiny, "adt.ed_visits") if v["disposition"] == "admitted"]
    assert len(ed) >= 6  # every Synthea ED visit is followed by its admission three hours later
    for v in ed:
        assert v["arrival_at"] <= v["triage_at"] <= v["provider_seen_at"] <= v["departure_at"]
    staff = rows(tiny, "sharepoint.staff")
    assert {"family_name": "Lee", "given_name": "Ann"}.items() <= staff[0].items()


# --- full population (slow) -----------------------------------------------------------------


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    root = tmp_path_factory.mktemp("full")
    cfg = synth.load_config()
    jar = synth.ensure_jar(cfg)
    for clinic in cfg["clinics"]:
        synth.run_clinic(jar, cfg, clinic, root / "fhir")
    derive(root / "fhir", root / "sources", CFG)
    return root


@pytest.mark.slow
def test_full_outputs_match_contracts(full):
    check_contracts(full / "sources")


@pytest.mark.slow
def test_full_ground_truth_resolves(full):
    check_ground_truth(full / "sources")


@pytest.mark.slow
def test_full_noise_rates_within_one_point(full):
    out = full / "sources"
    persons = rows(out, "ground_truth.persons")
    truth = {p["person_id"]: {**p, "phone": p["phone"] or ""} for p in persons}
    links = link_map(out)
    for system, table, key in [
        ("billing", "billing.patient_account", "account_id"),
        ("lab", "lab.patients", "lab_patient_id"),
        ("adt", "adt.patients", "adt_patient_id"),
    ]:
        register = [
            {**r, "phone": r["phone"] or "", "person_id": links[(system, r[key])]}
            for r in rows(out, table)
        ]
        measured = noise_rates(register, truth)
        for name, rate in CFG["noise"].items():
            assert abs(measured[name] - rate) <= 0.01, (system, name, measured[name])


@pytest.mark.slow
def test_full_beds_never_double_booked(full):
    check_beds(full / "sources")


@pytest.mark.slow
def test_full_occupancy_near_target(full):
    out = full / "sources"
    beds = Counter((b["clinic_id"], b["ward_id"]) for b in rows(out, "sharepoint.beds"))
    start = datetime.fromisoformat(CFG["window"]["start"])
    horizon = datetime.fromisoformat(CFG["window"]["end"]) + timedelta(days=1)
    busy, daily, open_at = defaultdict(float), defaultdict(float), {}

    def add(key, s, e):
        busy[key[0]] += (e - s).total_seconds()
        while s < e:
            next_day = datetime.combine(s.date() + timedelta(days=1), datetime.min.time())
            daily[(key, s.date())] += (min(e, next_day) - s).total_seconds()
            s = next_day

    for e in sorted(rows(out, "adt.events"), key=lambda e: int(e["event_id"])):
        at, key = datetime.strptime(e["event_time"], DT), (e["clinic_id"], e["ward_id"])
        if e["event_type"] != "A01":
            add(*open_at.pop(e["stay_id"]), at)
        if e["event_type"] != "A03":
            open_at[e["stay_id"]] = (key, at)
    for key, s in open_at.values():
        add(key, s, horizon)

    seconds = (horizon - start).total_seconds()
    for clinic in CFG["clinics"]:
        clinic_beds = sum(n for (c, _), n in beds.items() if c == clinic)
        occupancy = busy[clinic] / (clinic_beds * seconds)
        assert abs(occupancy - CFG["referred"]["occupancy_target"]) <= 0.05, (clinic, occupancy)
    assert any(v / (86400 * beds[key]) > 0.9 for (key, _), v in daily.items())


@pytest.mark.slow
def test_full_derivation_is_deterministic(full, tmp_path):
    derive(full / "fhir", tmp_path, CFG)

    def hashes(root):
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*.csv"))
        }

    assert hashes(tmp_path) == hashes(full / "sources")
