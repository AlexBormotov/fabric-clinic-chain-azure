---
id: PLAN-U03
spec: SPEC-001 / U03
owner: AlexBormotov
status: approved (approach B) by owner 2026-10-23
previous: PLAN-U02 (approach A + option 3a, landed in #4; see git history of this file)
---

# PLAN-U03 — Source derivation and noise

## Facts this plan rests on (measured 2026-10-23 on `make synth` output, window 2024-10-01 … 2026-09-30)

| Clinic | Patients | Inpatient stays (`IMP`) | Mean / median LOS | ED visits (`EMER`) | Lab observations |
|---|---|---|---|---|---|
| Boston | 300 | 33 | 8.9 / 3.9 d | 85 | 9,183 |
| Worcester | 400 | 68 | 7.5 / 4.1 d | 120 | 21,637 |
| Springfield | 500 | 72 | 7.4 / 4.1 d | 204 | 28,297 |

- 173 inpatient stays over 2 years ≈ 1,300 bed-days ≈ **1.8 occupied beds on average across the
  whole chain**. Bed occupancy, the >90% alert (AC5) and a live bed map (AC4) need far more.
- Every `ExplanationOfBenefit.outcome` is `complete`: Synthea produces no denials. Claim denial rate
  (AC3) must be generated in the billing derivation.
- Synthea's `Encounter` has no ED arrival or triage time (already in SPEC-001); `period.start` is
  taken as arrival.
- Each run references ~156 real Massachusetts organizations/locations. They are ignored: every
  encounter of a run belongs to that run's clinic.
- Payers present: Medicare, Medicaid, Dual Eligible, NO_INSURANCE and commercial (Humana, Aetna, BCBS,
  Cigna, Anthem, …) — enough for payer mix as delivered.

## Settings for every approach

- **Code:** `src/clinic_chain/sources/` (FHIR reader, IDs and noise, one module per system),
  entry point `scripts/derive_sources.py`, `make sources`. Plain Python + `openpyxl` for Excel; data
  volume (≈60k lab rows) needs no dataframe engine.
- **Config:** `config/sources.yaml` — wards and beds per clinic, noise rates, denial rates by payer,
  ED triage/wait distributions, seed.
- **Outputs** (git-ignored) under `data/sources/`: `billing/*.csv` (loaded into SQL Server in U04),
  `lab/*.csv`, `adt/adt_events.csv` (history; replay is U11), `sharepoint/rosters.xlsx`,
  `sharepoint/beds.xlsx`, `ground_truth/patient_links.csv`.
- **Contracts:** `docs/contracts/<system>.yaml` — column name, type, nullability, key, per output
  table; a small validator checks outputs against them.
- **Local IDs:** each system (EHR = FHIR, billing, lab, ADT) assigns its own patient ID format;
  ground truth maps every local record to the Synthea patient UUID.
- **Noise** per patient-bearing system (billing, lab, ADT): name typos, day/month swaps in birth date,
  phone format variants, ~5% duplicate patient records with a new local ID. Rates are applied as
  exact counts (`round(rate × n)` chosen by seeded sampling), not per-record coin flips, so the ±1 pp
  check is deterministic.
- **ED:** for each ED visit, arrival = `period.start`; triage and provider-seen times drawn from
  configured distributions; a share of ED visits leads to admission.
- **Billing:** claims and claim lines from `Claim`/`ExplanationOfBenefit`; denials generated at a
  configured rate per payer; SQL Server DDL in `docs/contracts/billing.sql`.
- **Rosters:** staff from `Practitioner` (per clinic, subsampled) plus generated nurses; shifts per
  ward.

## The choice: where inpatient volume comes from

### Approach A — Synthea stays only, small wards

ADT = the 173 Synthea inpatient stays (+ ED-to-admission links); bed counts sized to that volume
(e.g. 2 wards × 2–3 beds per clinic).

- **Pros:** every stay is clinically consistent with FHIR, claims and labs; nothing invented.
- **Cons:** ~520 ADT events in 2 years: replay at 10–50 events/s lasts seconds; occupancy mostly
  0–1 beds per ward; >90% alert = "both beds taken", rare. The bed map looks like a toy.
- **Spec impact:** none.

### Approach B — referred inpatients added to the bed and billing systems (recommended)

The 1,200 Synthea patients are the chain's registered (outpatient/EHR) population. The wards also
take referred inpatients who are not in the EHR export. The ADT generator adds them to reach a
configured occupancy (mean ~80%, winter peaks above 90%) on realistic ward sizes (e.g. Boston 12,
Worcester 16, Springfield 20 beds over ICU / medical / surgical wards). Referred patients get
generated demographics, appear in ADT and billing (with noise) but not in FHIR or lab; their claims
and readmissions follow configured rates. Synthea stays keep their FHIR/claims link.

- **Pros:** occupancy, turnover, alert and live map behave like a real hospital (~6,000 stays,
  ~20,000 ADT events → replay of minutes at 10–50 events/s); MPI gets true non-matches (patients in
  ADT and billing with no EHR record), which a real MPI must handle.
- **Cons:** ~97% of stays have no FHIR clinical record; clinical metrics (labs, diagnoses) cover
  registered patients only. More generator code (demographics, stays, claims for referred patients).
- **Spec impact:** INT-001/AC1 "3 clinics with 300, 400 and 500 patients" is read as "registered
  patients"; referred inpatients are added to the bed and billing systems. Wording added to
  `intent.md` and `spec.md` on approval.

### Approach C — larger Synthea population

Raise the population until Synthea's own stays fill realistic wards.

- **Numbers:** ~0.14 stays per patient per 2 years → ~30,000 patients for ~40 beds at 75%:
  ~22 GB of FHIR and ~100 min per `make synth`.
- **Cons:** contradicts AC1 (300/400/500); heavy for CI and the Fabric trial; slow tests.
- **Spec impact:** intent change.

## Tests (any approach)

- Fast (`make test`), on a small committed FHIR fixture (a few hand-trimmed bundles):
  ID assignment, each noise function, contract validator, denial and ED-time generation.
- Slow (`make test-slow`, full population):
  - every noisy and duplicate record resolves through ground truth to exactly one Synthea patient
    (or, in B, one referred patient);
  - each noise rate within ±1 pp of config;
  - every output file matches its contract (columns, types, nullability, keys);
  - ADT: no bed holds two patients at once; every admission has a discharge by 2026-09-30 or is
    open at the end; transfers keep the patient in one stay;
  - B only: mean occupancy per clinic within ±5 pp of target, at least one ward-day above 90%.

## Files touched

`src/clinic_chain/sources/*`, `scripts/derive_sources.py`, `config/sources.yaml`,
`docs/contracts/*`, `tests/test_sources*.py`, `tests/fixtures/fhir/*`, `Makefile` (`sources`),
`pyproject.toml`/`uv.lock` (`openpyxl`), README, CLAUDE.md; for B also `intent.md` and `spec.md`
(AC1 wording).

## Invariants

- Derivation is deterministic: same FHIR + config → identical outputs (checked like U02).
- Ground truth is the only place where local IDs meet the Synthea UUID.
- No real PHI: names and phones are generated or from Synthea.

## Reversal

Ordinary revert; outputs are regenerated by `make sources`.

## Files outside this set

Any other file touched stops work and returns this plan to the owner.
