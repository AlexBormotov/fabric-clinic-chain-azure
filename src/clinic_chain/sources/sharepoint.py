"""SharePoint Excel workbooks: bed reference and staff rosters."""

import random
from datetime import date, timedelta

from openpyxl import Workbook

from clinic_chain.sources.fhir import clean_name


def write_workbook(path, sheets: dict[str, tuple[list[str], list[list]]]) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    for title, (header, rows) in sheets.items():
        ws = wb.create_sheet(title)
        ws.append(header)
        for row in rows:
            ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def staff(clinic: str, physicians: dict, persons: list, cfg: dict, rng) -> list:
    """Physicians seen in the clinic's encounters (Synthea) plus generated nurses per ward."""
    prefix = clinic[:3].upper()
    rows = []
    for npi in sorted(physicians):
        given, _, family = physicians[npi].removeprefix("Dr. ").partition(" ")
        rows.append(
            {
                "staff_id": f"S-{prefix}-{len(rows) + 1:04d}",
                "clinic_id": clinic,
                "role": "physician",
                "ward_id": rng.choice(sorted(cfg["wards"])),
                "given_name": clean_name(given),
                "family_name": clean_name(family),
                "npi": npi,
            }
        )
    given = sorted({p["given_name"] for p in persons})
    family = sorted({p["family_name"] for p in persons})
    for ward, count in cfg["clinics"][clinic]["beds"].items():
        for _ in range(round(count * cfg["rosters"]["nurses_per_bed"])):
            rows.append(
                {
                    "staff_id": f"S-{prefix}-{len(rows) + 1:04d}",
                    "clinic_id": clinic,
                    "role": "nurse",
                    "ward_id": ward,
                    "given_name": rng.choice(given),
                    "family_name": rng.choice(family),
                    "npi": None,
                }
            )
    return rows


def roster(staff_rows: list, cfg: dict, rng: random.Random) -> list:
    """Weekly roster: each nurse works a day or night pattern on their ward every week."""
    start = date.fromisoformat(cfg["window"]["start"])
    end = date.fromisoformat(cfg["window"]["end"])
    week = start - timedelta(days=start.weekday())
    rows = []
    while week <= end:
        for s in staff_rows:
            if s["role"] == "nurse":
                rows.append(
                    {
                        "staff_id": s["staff_id"],
                        "week_start": week,
                        "ward_id": s["ward_id"],
                        "shift": rng.choice(("day", "night")),
                        "shifts_planned": rng.choice((3, 4, 5)),
                    }
                )
        week += timedelta(days=7)
    return rows
