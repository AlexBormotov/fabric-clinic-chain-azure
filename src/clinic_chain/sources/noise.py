"""Per-system patient registers: local IDs, duplicates and demographic noise.

Every rate is applied as an exact count (round(rate * n)) of seeded-random records, so the
measured rate equals the configured one up to rounding. Each noise function always changes its
field, which lets tests count noisy records by comparing with ground truth.
"""

import random
import string

PHONE_FORMATS = (
    "({a}) {b}-{c}",
    "{a}{b}{c}",
    "+1 {a} {b} {c}",
    "{a}.{b}.{c}",
)


def typo(name: str, rng: random.Random) -> str:
    """One keyboard-style edit: swap, drop or replace a letter; never returns `name` unchanged."""
    while True:
        i = rng.randrange(len(name))
        edit = rng.choice(("swap", "drop", "replace") if len(name) > 2 else ("replace",))
        if edit == "swap" and i < len(name) - 1:
            out = name[:i] + name[i + 1] + name[i] + name[i + 2 :]
        elif edit == "drop":
            out = name[:i] + name[i + 1 :]
        else:
            out = name[:i] + rng.choice(string.ascii_lowercase) + name[i + 1 :]
        if out != name and out:
            return out


def can_swap_day_month(birth_date: str) -> bool:
    _, month, day = birth_date.split("-")
    return int(day) <= 12 and day != month


def swap_day_month(birth_date: str) -> str:
    year, month, day = birth_date.split("-")
    return f"{year}-{day}-{month}"


def reformat_phone(phone: str, rng: random.Random) -> str:
    a, b, c = phone.split("-")
    return rng.choice(PHONE_FORMATS).format(a=a, b=b, c=c)


def build_register(
    persons: list[dict], system: str, id_format: str, rates: dict, rng: random.Random
) -> list[dict]:
    """Patient records of one system: one per person plus duplicates, with noise applied.

    Returns records with `local_patient_id`, `person_id` (ground truth, not exported to the
    source table) and the demographic fields as the system holds them.
    """
    records = [dict(p) for p in persons]
    for p in rng.sample(persons, round(rates["duplicate"] * len(persons))):
        records.append(dict(p))
    width = id_format.count("#")
    ids = rng.sample(range(10 ** (width - 1), 10**width), len(records))
    prefix = id_format.rstrip("#")
    for record, number in zip(records, ids, strict=True):
        record["local_patient_id"] = f"{prefix}{number}"
        record["system"] = system

    n = len(records)
    for r in rng.sample(records, round(rates["name_typo"] * n)):
        field = rng.choice(("given_name", "family_name"))
        r[field] = typo(r[field], rng)
    swappable = [r for r in records if can_swap_day_month(r["birth_date"])]
    for r in rng.sample(swappable, round(rates["dob_day_month_swap"] * n)):
        r["birth_date"] = swap_day_month(r["birth_date"])
    with_phone = [r for r in records if r["phone"].count("-") == 2]
    for r in rng.sample(with_phone, round(rates["phone_format"] * n)):
        r["phone"] = reformat_phone(r["phone"], rng)
    return records


def local_ids_by_person(register: list[dict]) -> dict[str, list[str]]:
    by_person: dict[str, list[str]] = {}
    for r in register:
        by_person.setdefault(r["person_id"], []).append(r["local_patient_id"])
    return by_person
