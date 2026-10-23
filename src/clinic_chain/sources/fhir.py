"""Read the Synthea FHIR output into the plain records the source generators need."""

import json
import re
from datetime import datetime
from pathlib import Path

_DIGITS = re.compile(r"\d+")


def clean_name(name: str) -> str:
    """Synthea appends digits to every name ("Kohler843"); real systems hold the plain name."""
    return _DIGITS.sub("", name)


def ts(value: str) -> datetime:
    """FHIR instant → naive UTC datetime (all outputs are UTC)."""
    return datetime.fromisoformat(value).replace(tzinfo=None)


def _ref_id(reference: str) -> str:
    return reference.removeprefix("urn:uuid:")


def _in_window(day: str, window: dict) -> bool:
    return window["start"] <= day[:10] <= window["end"]


def _person(r: dict, clinic: str) -> dict:
    name = next((n for n in r["name"] if n.get("use") == "official"), r["name"][0])
    phone = next((t["value"] for t in r.get("telecom", []) if t["system"] == "phone"), "")
    return {
        "person_id": r["id"],
        "origin": "synthea",
        "clinic_id": clinic,
        "given_name": clean_name(name["given"][0]),
        "family_name": clean_name(name["family"]),
        "birth_date": r["birthDate"],
        "sex": {"male": "M", "female": "F"}.get(r.get("gender"), "U"),
        "phone": phone,
        "postal_code": r.get("address", [{}])[0].get("postalCode", ""),
    }


def _lab(r: dict, person_id: str) -> dict | None:
    if "valueQuantity" in r:
        numeric, text = r["valueQuantity"]["value"], None
        unit = r["valueQuantity"].get("unit") or r["valueQuantity"].get("code")
    elif "valueCodeableConcept" in r:
        concept = r["valueCodeableConcept"]
        numeric, unit = None, None
        text = concept.get("text") or concept["coding"][0].get("display")
    else:
        return None
    coding = r["code"]["coding"][0]
    return {
        "person_id": person_id,
        "collected_at": ts(r["effectiveDateTime"]),
        "loinc_code": coding["code"],
        "test_name": coding.get("display", r["code"].get("text", "")),
        "value_numeric": numeric,
        "value_text": text,
        "unit": unit,
    }


def _claim(r: dict, person_id: str) -> dict:
    lines = [
        {
            "service_code": item["productOrService"]["coding"][0]["code"],
            "service_name": item["productOrService"]["coding"][0].get("display", ""),
            "amount": round(item.get("net", {}).get("value", 0.0), 2),
        }
        for item in r.get("item", [])
    ]
    billed = next(
        (
            t["amount"]["value"]
            for t in r.get("total", [])
            if t["category"]["coding"][0]["code"] == "submitted"
        ),
        0.0,
    )
    return {
        "person_id": person_id,
        "claim_type": r["type"]["coding"][0]["code"],
        "payer": r.get("insurer", {}).get("display", "NO_INSURANCE"),
        "service_start": ts(r["billablePeriod"]["start"]),
        "service_end": ts(r["billablePeriod"]["end"]),
        "billed": round(billed, 2),
        "paid": round(r.get("payment", {}).get("amount", {}).get("value", 0.0), 2),
        "lines": lines,
    }


def read_clinic(clinic_dir: Path, clinic: str, window: dict) -> dict:
    """One clinic's registered patients plus their in-window stays, ED visits, labs and claims."""
    out = {"persons": [], "stays": [], "ed": [], "labs": [], "claims": [], "physicians": {}}
    for path in sorted((clinic_dir / "fhir").glob("*.json")):
        if path.name.startswith(("hospitalInformation", "practitionerInformation")):
            continue
        resources = [e["resource"] for e in json.loads(path.read_bytes())["entry"]]
        person_id = next(r["id"] for r in resources if r["resourceType"] == "Patient")
        for r in resources:
            kind = r["resourceType"]
            if kind == "Patient":
                out["persons"].append(_person(r, clinic))
            elif kind == "Encounter" and _in_window(r["period"]["start"], window):
                code = r["class"]["code"]
                record = {
                    "encounter_id": r["id"],
                    "person_id": _ref_id(r["subject"]["reference"]),
                    "start": ts(r["period"]["start"]),
                    "end": ts(r["period"]["end"]),
                    "type": r["type"][0]["coding"][0].get("display", ""),
                }
                if code == "IMP":
                    out["stays"].append(record)
                elif code == "EMER":
                    out["ed"].append(record)
                for p in r.get("participant", []):
                    individual = p.get("individual", {})
                    npi = individual.get("reference", "").rpartition("|")[2]
                    if npi:
                        out["physicians"][npi] = individual.get("display", "")
            elif kind == "Observation" and _in_window(r.get("effectiveDateTime", ""), window):
                categories = {c["code"] for cat in r.get("category", []) for c in cat["coding"]}
                if "laboratory" in categories and (lab := _lab(r, person_id)):
                    out["labs"].append(lab)
            elif kind == "ExplanationOfBenefit" and _in_window(
                r["billablePeriod"]["start"], window
            ):
                out["claims"].append(_claim(r, person_id))
    return out
