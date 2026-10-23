"""Billing system: claims from Synthea EOBs plus one institutional claim per referred stay.

Synthea adjudicates every claim as complete, so denials are generated here: per payer, exactly
round(rate * n) claims are denied, with zero paid.
"""

import random
from collections import Counter


def _rate(table: dict, payer: str) -> float:
    return table.get(payer, table["default"])


def external_payers(synthea_claims: list, persons: list, rng: random.Random) -> dict:
    """Payer per non-registered person, drawn from the clinic's Synthea payer mix."""
    mix = Counter(c["payer"] for c in synthea_claims)
    payers, weights = zip(*sorted(mix.items()), strict=True)
    return {p["person_id"]: rng.choices(payers, weights)[0] for p in persons}


def referred_claims(stays: list, payer_of: dict, cfg: dict) -> list:
    claims = []
    for s in stays:
        if s["encounter_id"] or s["open"]:
            continue  # Synthea stays are billed through their EOBs; open stays are not billed yet
        payer = payer_of[s["person_id"]]
        lines = []
        for seg in s["segments"]:
            days = max(1, round((seg["end"] - seg["start"]).total_seconds() / 86400))
            ward = cfg["wards"][seg["ward_id"]]
            lines.append(
                {
                    "service_code": f"ROOM-{seg['ward_id']}",
                    "service_name": f"{ward['name']} room and board, {days} day(s)",
                    "amount": round(days * ward["day_rate_usd"], 2),
                }
            )
        billed = round(sum(line["amount"] for line in lines), 2)
        claims.append(
            {
                "person_id": s["person_id"],
                "claim_type": "institutional",
                "payer": payer,
                "service_start": s["segments"][0]["start"],
                "service_end": s["segments"][-1]["end"],
                "billed": billed,
                "paid": round(billed * _rate(cfg["billing"]["paid_ratio"], payer), 2),
                "lines": lines,
                "stay_id": s["stay_id"],
            }
        )
    return claims


def walk_in_claims(visits: list, payer_of: dict, cfg: dict) -> list:
    """One professional claim per ED visit of a walk-in (registered patients bill via Synthea)."""
    claims = []
    for v in visits:
        payer = payer_of.get(v["person_id"])
        if payer is None or v["disposition"] == "admitted":
            continue  # referred admissions are billed with their stay
        billed = float(cfg["ed"]["visit_charge_usd"])
        claims.append(
            {
                "person_id": v["person_id"],
                "claim_type": "professional",
                "payer": payer,
                "service_start": v["arrival_at"],
                "service_end": v["departure_at"],
                "billed": billed,
                "paid": round(billed * _rate(cfg["billing"]["paid_ratio"], payer), 2),
                "lines": [
                    {
                        "service_code": "ED-VISIT",
                        "service_name": "Emergency department visit",
                        "amount": billed,
                    }
                ],
            }
        )
    return claims


def apply_denials(claims: list, cfg: dict, rng: random.Random) -> None:
    billing = cfg["billing"]
    by_payer: dict[str, list] = {}
    for c in claims:
        c["status"], c["denial_reason"] = "paid", None
        by_payer.setdefault(c["payer"], []).append(c)
    for payer in sorted(by_payer):
        group = by_payer[payer]
        for c in rng.sample(group, round(_rate(billing["denial_rate"], payer) * len(group))):
            c["status"], c["paid"] = "denied", 0.0
            c["denial_reason"] = rng.choice(billing["denial_reasons"])
