# ADR 0001: Master patient index by own Fellegi–Sunter scoring in PySpark

- Status: accepted 2026-10-28 (PLAN-U07, approach A)
- Unit: U07

## Context

Four systems hold patient records under their own local IDs: EHR (FHIR), lab, ADT and billing.
Records carry typos, day/month swaps, reformatted, missing or outdated phones, and within-system
duplicates (`config/sources.yaml`). Gold (U08) needs one master patient per person. The generator's
ground truth measures the result, but never reaches Fabric and must not tune the matcher.

The matcher runs as a Fabric notebook on Runtime 2.0 (Spark 4.1). Spark has `soundex` but no
Jaro-Winkler function. Splink does the same job with EM-trained weights, but adds a dependency and
a learning curve that the time box does not allow.

## Decision

`fabric/nb_mpi.Notebook` scores record pairs with Fellegi–Sunter weights:

- **Blocking:** a pair is compared when it agrees on (birth year, surname soundex), on the exact
  birth date or on the phone.
- **Comparisons and levels:**
  - given and family name: Jaro-Winkler ≥ 0.92 / ≥ 0.80 / lower;
  - birth date: exact / day and month swapped / same year / other;
  - sex, phone, postal code and clinic: agree or disagree.
  A value missing on either side gives no level and weighs 0.
- **Weights:** log2(m/u) per level.
  - m, the share of true matches at a level, is set a priori in the notebook (`M`) from typical
    data-entry error rates, not fitted.
  - u, the share of chance agreement, is measured on all pairs of a fixed sample of 600 records,
    with add-one smoothing. That needs no ground truth.
- **Decision:** a pair scoring at least `MATCH` is merged. A pair between `REVIEW` and `MATCH` is
  written to `patient_match_review` and not merged. Merged pairs form connected components (min-label
  propagation), and `master_patient_id` is a hash of the smallest record key in each component.
- **Thresholds** come from the score distribution of candidate pairs, not from ground truth.
- **Jaro-Winkler** is a plain-Python function used as a Spark UDF. It has no dependency and is tested
  against Winkler's published values. Candidate pairs number about 65,000, so per-row Python cost
  is small.

## Consequences

- Each weight can be explained field by field. Precision and recall against ground truth are
  reported by `make mpi-eval` in `docs/evidence/mpi.json` and gated in CI (precision ≥ 0.98,
  recall ≥ 0.95).
- Transitive merging can chain two persons through one wrong pair. The review band and the high
  `MATCH` threshold limit this; the evaluation measures it.
- Master IDs change when a component's smallest record changes, so they are stable only while the
  records are. Gold reloads fully, so this is acceptable for now.
- On the generated data the result is near perfect: precision 1.0 and recall 0.9998 on 2026-10-28.
  The noise is light (one error per field at most, no name changes such as after marriage), so
  this measures the pipeline more than the limits of the scoring.
- No term-frequency adjustment: agreeing on a rare surname counts the same as on a common one.
- **Next step: Splink.** It brings EM-estimated m and u, term-frequency adjustment and cluster
  diagnostics on the same Spark backend. The comparisons and levels above map one to one onto
  Splink comparison levels.
