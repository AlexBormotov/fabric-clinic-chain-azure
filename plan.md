---
id: PLAN-U09
spec: SPEC-001 / U09
owner: AlexBormotov
status: approach A taken 2026-10-28 under the owner's standing go-ahead; the metric definitions in
  GLOSSARY.md still await the owner's review (spec routing: person approves definitions)
previous: PLAN-U13 (landed in #15), PLAN-U08 (#11); see git history of this file
---

# PLAN-U09 — Metric definitions and reference values

## Facts this plan rests on

- Generator output, measured 2026-10-28 from `data/sources/`: 6,374 ADT stays (A01), 6,338
  discharges (36 open at the window's end), 413 transfers; 32,722 claims (2,161 denied); 11,446 ED
  visits; 48 beds in 3 clinics.
- pandas 3.0.6 (PyPI, released 2026-09-17; 3.1.0 of 2026-10-22 is under two weeks old).
- T-SQL rejects an aggregate over an expression with a subquery (`AVG(CASE WHEN EXISTS …)`), and
  `AVG` over `decimal` literals keeps only 6 decimal places; both measured on SQL Server 2022.

## Approaches

- **A (taken).** The reference is computed with pandas from `data/sources/` and ground truth, never
  from Bronze, Silver or Gold. Gold exposes the metrics as views (`sql/gold/20_metrics.sql`) over a
  new `gold.fact_stay`, per clinic and for the chain. A stand test compares them.
- B. Reference from Silver with Spark. Rejected: it shares the pipeline's parsing, so a Silver bug
  would hide in both sides.

## Files

`GLOSSARY.md`, `src/clinic_chain/metric_reference.py`, `scripts/metric_reference.py`,
`docs/evidence/metric-reference.json`, `sql/gold/00_tables.sql` and `10_reload.sql` (`fact_stay`),
`sql/gold/20_metrics.sql`, `tests/test_metrics.py`, `Makefile` (`metric-reference`),
`pyproject.toml` and `uv.lock` (pandas), `.gitignore` (agent worktrees), `README.md`, `CLAUDE.md`.

## Invariants and the checks that go red

- Gold metrics equal the reference to a relative 1e-6 for every scope (`test_gold_metrics_match_the_reference`,
  `test_gold_payer_mix_matches_the_reference`). There is no looser tolerance for readmissions: the
  measured MPI-vs-ground-truth gap is 0.0.
- Every metric is defined in `GLOSSARY.md` (`test_glossary_defines_every_metric`).

Negative control, run 2026-10-28: a 31-day readmission window in the SQL moved the chain rate by
0.00049 and Worcester by 0.0015. The original tolerance of 0.005 let this pass, so it was removed;
with the exact check the test fails (`ALL readmission_30d_rate 0.10347 vs 0.10298`).

## Measured

Chain over the window: occupancy 0.7998, ALOS 4.40 days, turnover 66.0 per bed-year, 30-day
readmission 0.1030, ED wait median 45 min, revenue 717,462 per bed-year, denial rate 0.0660; payer
mix led by Medicare 0.287. `make test-stand` metric tests pass in about 3 s.

## Reversal

Revert the PR. `gold.fact_stay` and the views are dropped and recreated by `make gold`.
