"""Derive the five source systems and the ground truth from the Synthea FHIR output."""

import csv
import random
from datetime import datetime
from pathlib import Path

from clinic_chain.sources import adt, billing, fhir, noise, sharepoint
from clinic_chain.sources.contracts import DATETIME

DEMOGRAPHICS = ("clinic_id", "given_name", "family_name", "birth_date", "sex", "phone")
ID_FORMATS = {"billing": "ACC#######", "lab": "L########", "adt": "P######"}


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(DATETIME)
    if isinstance(value, float):
        return f"{value:.2f}" if value == round(value, 2) else repr(value)
    return value


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_cell(row[c]) for c in columns])


def derive(fhir_root: Path, out: Path, cfg: dict) -> None:

    def rng(name: str) -> random.Random:
        return random.Random(f"{cfg['seed']}:{name}")

    window = cfg["window"]
    persons, stays, ed_visits, labs, claims, staff, beds = [], [], [], [], [], [], []
    for clinic in cfg["clinics"]:
        data = fhir.read_clinic(fhir_root / clinic, clinic, window)
        clinic_stays, referred = adt.build_stays(clinic, data, cfg, rng(f"adt:{clinic}"))
        persons += data["persons"] + referred
        stays += clinic_stays
        visits, walk_ins = adt.ed_visits(clinic, data, clinic_stays, cfg, rng(f"ed:{clinic}"))
        persons += walk_ins
        ed_visits += visits
        labs += [{**lab, "clinic_id": clinic} for lab in data["labs"]]
        payer_of = billing.external_payers(
            data["claims"], referred + walk_ins, rng(f"payer:{clinic}")
        )
        clinic_claims = data["claims"] + billing.referred_claims(clinic_stays, payer_of, cfg)
        clinic_claims += billing.walk_in_claims(visits, payer_of, cfg)
        claims += [{**c, "clinic_id": clinic} for c in clinic_claims]
        clinic_beds = adt.beds_for(clinic, cfg)
        beds += clinic_beds
        staff += sharepoint.staff(
            clinic, data["physicians"], data["persons"], cfg, rng(f"staff:{clinic}")
        )
    billing.apply_denials(claims, cfg, rng("denials"))
    by_id = {p["person_id"]: p for p in persons}

    # Patient registers: each system knows the persons it has records for.
    present = {
        "billing": {c["person_id"] for c in claims},
        "lab": {lab["person_id"] for lab in labs},
        "adt": {s["person_id"] for s in stays} | {v["person_id"] for v in ed_visits},
    }
    registers, local = {}, {}
    for system, ids in present.items():
        chosen = [by_id[i] for i in sorted(ids)]
        r = rng(f"noise:{system}")
        registers[system] = noise.build_register(
            chosen, system, ID_FORMATS[system], cfg["noise"], r
        )
        local[system] = (noise.local_ids_by_person(registers[system]), r)

    def local_id(system: str, person_id: str) -> str:
        ids, r = local[system]
        return ids[person_id][0] if len(ids[person_id]) == 1 else r.choice(ids[person_id])

    # Billing
    write_csv(
        out / "billing/patient_account.csv",
        ["account_id", *DEMOGRAPHICS, "postal_code"],
        [{**p, "account_id": p["local_patient_id"]} for p in registers["billing"]],
    )
    claims.sort(key=lambda c: (c["service_start"], c["person_id"], c["billed"]))
    claim_rows, line_rows = [], []
    for n, c in enumerate(claims, 1):
        claim_id = f"CLM{n:08d}"
        claim_rows.append(
            {
                **c,
                "claim_id": claim_id,
                "account_id": local_id("billing", c["person_id"]),
                "billed_amount": c["billed"],
                "paid_amount": c["paid"],
            }
        )
        line_rows += [
            {**line, "claim_id": claim_id, "line_no": i} for i, line in enumerate(c["lines"], 1)
        ]
    write_csv(
        out / "billing/claim.csv",
        [
            "claim_id", "account_id", "clinic_id", "claim_type", "payer", "service_start",
            "service_end", "billed_amount", "paid_amount", "status", "denial_reason",
        ],
        claim_rows,
    )  # fmt: skip
    write_csv(
        out / "billing/claim_line.csv",
        ["claim_id", "line_no", "service_code", "service_name", "amount"],
        line_rows,
    )

    # Lab
    write_csv(
        out / "lab/patients.csv",
        ["lab_patient_id", *DEMOGRAPHICS],
        [{**p, "lab_patient_id": p["local_patient_id"]} for p in registers["lab"]],
    )
    labs.sort(key=lambda lab: (lab["collected_at"], lab["person_id"], lab["loinc_code"]))
    write_csv(
        out / "lab/results.csv",
        [
            "result_id", "lab_patient_id", "clinic_id", "collected_at", "loinc_code", "test_name",
            "value_numeric", "value_text", "unit",
        ],
        [
            {**lab, "result_id": f"R{n:09d}", "lab_patient_id": local_id("lab", lab["person_id"])}
            for n, lab in enumerate(labs, 1)
        ],
    )  # fmt: skip

    # ADT
    write_csv(
        out / "adt/patients.csv",
        ["adt_patient_id", *DEMOGRAPHICS, "postal_code"],
        [{**p, "adt_patient_id": p["local_patient_id"]} for p in registers["adt"]],
    )
    stay_patient = {s["stay_id"]: local_id("adt", s["person_id"]) for s in stays}
    write_csv(
        out / "adt/events.csv",
        [
            "event_id", "event_type", "event_time", "clinic_id", "stay_id", "adt_patient_id",
            "ward_id", "bed_id", "from_ward_id", "from_bed_id",
        ],
        [{**e, "adt_patient_id": stay_patient[e["stay_id"]]} for e in adt.adt_events(stays)],
    )  # fmt: skip
    write_csv(
        out / "adt/ed_visits.csv",
        [
            "ed_visit_id", "clinic_id", "adt_patient_id", "arrival_at", "triage_at",
            "provider_seen_at", "departure_at", "disposition", "stay_id",
        ],
        [{**v, "adt_patient_id": local_id("adt", v["person_id"])} for v in ed_visits],
    )  # fmt: skip

    # SharePoint
    clinics, wards = cfg["clinics"], cfg["wards"]
    sharepoint.write_workbook(
        out / "sharepoint/beds.xlsx",
        {
            "beds": (
                ["clinic_id", "clinic_name", "ward_id", "ward_name", "bed_id"],
                [
                    [b["clinic_id"], clinics[b["clinic_id"]]["name"], b["ward_id"],
                     wards[b["ward_id"]]["name"], b["bed_id"]]
                    for b in beds
                ],
            )
        },
    )  # fmt: skip
    staff_cols = ["staff_id", "clinic_id", "role", "ward_id", "given_name", "family_name", "npi"]
    roster_cols = ["staff_id", "week_start", "ward_id", "shift", "shifts_planned"]
    roster = sharepoint.roster(staff, cfg, rng("roster"))
    sharepoint.write_workbook(
        out / "sharepoint/rosters.xlsx",
        {
            "staff": (staff_cols, [[s[c] for c in staff_cols] for s in staff]),
            "roster": (roster_cols, [[r[c] for c in roster_cols] for r in roster]),
        },
    )

    # Ground truth
    write_csv(
        out / "ground_truth/persons.csv",
        ["person_id", "origin", *DEMOGRAPHICS, "postal_code"],
        sorted(persons, key=lambda p: p["person_id"]),
    )
    write_csv(
        out / "ground_truth/patient_links.csv",
        ["system", "local_patient_id", "person_id"],
        [
            {"system": "ehr", "local_patient_id": p["person_id"], "person_id": p["person_id"]}
            for p in persons
            if p["origin"] == "synthea"
        ]
        + [r for system in ("billing", "lab", "adt") for r in registers[system]],
    )
