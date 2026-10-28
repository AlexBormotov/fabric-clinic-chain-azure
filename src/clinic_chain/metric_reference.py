"""Reference values of the eight metrics, computed with pandas straight from generator output.

Independent of the pipeline by design: it reads `data/sources/` (what the source systems hold) and
the generator's ground truth, never Bronze, Silver or Gold. Definitions are in GLOSSARY.md.
"""

from pathlib import Path

import pandas as pd

from clinic_chain.sources import contracts

READMISSION_DAYS = 30


def load(sources: Path, specs: dict, name: str) -> pd.DataFrame:
    header, rows = contracts.read(sources, specs[name])
    return pd.DataFrame(rows, columns=header)


def compute(sources: Path, specs: dict, window: dict) -> dict:
    start = pd.Timestamp(window["start"])
    stop = pd.Timestamp(window["end"]) + pd.Timedelta(days=1)
    days = (stop - start).days
    years = days / 365

    beds = load(sources, specs, "sharepoint.beds").groupby("clinic_id").size()
    events = load(sources, specs, "adt.events")
    events["event_time"] = pd.to_datetime(events["event_time"])
    ed = load(sources, specs, "adt.ed_visits")
    claims = load(sources, specs, "billing.claim")
    claims["service_start"] = pd.to_datetime(claims["service_start"])
    claims["paid_amount"] = claims["paid_amount"].astype(float)
    links = load(sources, specs, "ground_truth.patient_links")
    person = links[links["system"] == "adt"].set_index("local_patient_id")["person_id"]

    # Bed segments: A01/A02 to the stay's next event, or to the window's end.
    events["event_id"] = events["event_id"].astype(int)
    events = events.sort_values(["stay_id", "event_time", "event_id"])
    events["segment_end"] = events.groupby("stay_id")["event_time"].shift(-1)
    segments = events[events["event_type"].isin(["A01", "A02"])].copy()
    seg_start = segments["event_time"].clip(lower=start)
    seg_end = segments["segment_end"].fillna(stop).clip(upper=stop)
    segments["hours"] = (seg_end - seg_start).dt.total_seconds().clip(lower=0) / 3600
    bed_hours = segments.groupby("clinic_id")["hours"].sum()

    admit = events[events["event_type"] == "A01"].set_index("stay_id")
    discharge = events[events["event_type"] == "A03"].set_index("stay_id")["event_time"]
    stays = pd.DataFrame(
        {
            "clinic_id": admit["clinic_id"],
            "person_id": admit["adt_patient_id"].map(person),
            "admitted_at": admit["event_time"],
            "discharged_at": discharge,
        }
    )
    discharged = stays[(stays["discharged_at"] >= start) & (stays["discharged_at"] < stop)]
    los_days = (discharged["discharged_at"] - discharged["admitted_at"]).dt.total_seconds() / 86400

    # Readmission: another admission of the same person, at any clinic, within 30 days after
    # discharge; index stays are those discharged early enough for 30 days to be observed.
    horizon = pd.Timedelta(days=READMISSION_DAYS)
    index = discharged[discharged["discharged_at"] < stop - horizon]
    admissions = stays[["person_id", "admitted_at"]]
    pairs = index.reset_index().merge(admissions, on="person_id", suffixes=("", "_next"))
    after = pairs["admitted_at_next"] > pairs["discharged_at"]
    within = pairs["admitted_at_next"] <= pairs["discharged_at"] + horizon
    readmitted = set(pairs.loc[after & within, "stay_id"])
    index = index.assign(readmitted=index.index.isin(readmitted))

    ed["arrival_at"] = pd.to_datetime(ed["arrival_at"])
    ed["provider_seen_at"] = pd.to_datetime(ed["provider_seen_at"])
    ed = ed[(ed["arrival_at"] >= start) & (ed["arrival_at"] < stop)]
    # Whole minutes, as T-SQL DATEDIFF(MINUTE) counts minute boundaries crossed.
    wait = (
        ed["provider_seen_at"].dt.floor("min") - ed["arrival_at"].dt.floor("min")
    ).dt.total_seconds() / 60

    claims = claims[(claims["service_start"] >= start) & (claims["service_start"] < stop)]

    def per_clinic(clinic: str | None) -> dict:
        def pick(df: pd.DataFrame) -> pd.DataFrame:
            return df if clinic is None else df[df["clinic_id"] == clinic]

        n_beds = int(beds.sum() if clinic is None else beds[clinic])
        hours = float(bed_hours.sum() if clinic is None else bed_hours.get(clinic, 0.0))
        c = pick(claims)
        mix = c["payer"].value_counts(normalize=True).sort_index()
        return {
            "beds": n_beds,
            "occupancy_rate": hours / (n_beds * 24 * days),
            "alos_days": float(los_days[pick(discharged).index].mean()),
            "bed_turnover_per_year": len(pick(discharged)) / n_beds / years,
            "readmission_30d_rate": float(pick(index)["readmitted"].mean()),
            "ed_wait_median_minutes": float(wait[pick(ed).index].median()),
            "revenue_per_bed_per_year": float(c["paid_amount"].sum()) / n_beds / years,
            "claim_denial_rate": float((c["status"] == "denied").mean()),
            "payer_mix": {payer: float(share) for payer, share in mix.items()},
        }

    return {
        "window": window,
        "overall": per_clinic(None),
        "by_clinic": {clinic: per_clinic(clinic) for clinic in sorted(beds.index)},
    }
