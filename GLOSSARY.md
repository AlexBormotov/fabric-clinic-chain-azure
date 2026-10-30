# Glossary

Settled domain terms. Metric definitions are the contract between Gold (`sql/gold/20_metrics.sql`),
the semantic model (U10) and the independent reference (`src/clinic_chain/metric_reference.py`,
`docs/evidence/metric-reference.json`). Drafted in U09 under the owner's standing go-ahead; the
owner reviews them before the cloud run.

## Terms

- **Window**: 2024-10-01 00:00 to 2026-10-01 00:00 UTC (730 days, `config/sources.yaml`). Silver
  keeps history; Gold facts and every metric use the window only.
- **System of record**: the one source a fact is taken from (FHIR for clinical events, the lab
  system for results, billing for claims, ADT for stays and ED visits, SharePoint for beds and
  staff), so that no fact is counted twice.
- **Patient record**: one source system's row for a patient, with that system's local ID.
- **Master patient**: the person behind one or more patient records, as matched by the MPI (U07);
  `master_patient_id` in Gold.
- **Stay**: an inpatient stay in ADT, from its A01 admission to its A03 discharge. A stay still open
  at the window's end has no discharge.
- **Stay segment**: the part of a stay spent in one bed, from an A01 or A02 event to the stay's next
  event (or the window's end when open).
- **Bed-day row**: a stay segment cut at midnights; it carries the hours the bed was occupied that
  day (`gold.fact_bed_day`).
- **Scope**: a clinic, or `ALL` for the whole chain. Metrics are reported per scope over the whole
  window.
- **PHI table**: a Silver table holding names, birth dates, phone numbers or postal codes
  (`patient_record`, and `staff` for staff names). Only the OneLake role `PhiReader` reads it
  (`infra/modules/fabric/lh_silver_roles.json`, ADR 0005).
- **Clinic user**: a report user scoped to the clinics listed for their UPN in `gold.user_clinic`.

## Metrics

| Metric | Definition |
|---|---|
| `occupancy_rate` | Occupied bed-hours in the window ÷ (beds × 24 × days in the window). Occupied hours come from stay segments, clipped to the window. |
| `alos_days` | Average length of stay: mean of (discharge − admission) in days over stays discharged in the window. Open stays are excluded. |
| `bed_turnover_per_year` | Stays discharged in the window ÷ beds ÷ (days in the window ÷ 365). |
| `readmission_30d_rate` | Index stays are those discharged in the window at least 30 days before its end. The rate is the share of index stays followed by another admission of the same master patient, at any clinic, within 30 days after discharge. The clinic is the index stay's clinic. |
| `ed_wait_median_minutes` | Median of whole minutes from ED arrival to being seen by a provider, over ED visits arriving in the window. Minutes count minute boundaries crossed, as T-SQL `DATEDIFF(MINUTE)` does. |
| `revenue_per_bed_per_year` | Paid amount of claims with service start in the window ÷ beds ÷ (days ÷ 365). All claim types count; denied claims have zero paid. |
| `claim_denial_rate` | Denied claims ÷ all claims, by count, service start in the window. |
| `payer_mix` | Each payer's share of claims, by count, service start in the window. `NO_INSURANCE` is a payer. |

The reference computes the same definitions from `data/sources/`, using ground truth for person
identity instead of the MPI. Every metric must match Gold to a relative 1e-6; an MPI error that
links or splits a readmission shows up as a mismatch.
