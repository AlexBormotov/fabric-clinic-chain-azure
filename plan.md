---
id: PLAN-U13
spec: SPEC-001 / U13
owner: AlexBormotov
status: approach B taken 2026-10-28 under the owner's standing go-ahead
previous: PLAN-U08 (landed in #11; see git history of this file)
---

# PLAN-U13 — Bed state history (SCD2)

## Facts this plan rests on

- `silver.adt_event` (U06) holds A01 admit, A02 transfer (`from_ward_id`/`from_bed_id` set) and A03
  discharge; `event_id` is the contract's primary key. Stays open at the horizon have no A03.
- U03 never double-books a bed, but a bed can be freed and taken at the same instant (a discharge
  and an admit, or an ICU-to-MED transfer, at one timestamp).
- nb_silver overwrites `adt_event` on every run and drops exact duplicate rows. Late and duplicate
  events come from the U11 producer; a duplicate is the same `event_id` sent again.
- Delta 4.2 MERGE supports `whenNotMatchedBySource` with a condition on the target.

## Model

`silver.bed_state_history`: one row per bed and interval. Columns `clinic_id`, `ward_id`, `bed_id`,
`valid_from`, `valid_to` (NULL = current), `is_current`, `occupied`, `stay_id`, `adt_patient_id`
(NULL when free), `event_id` (the event that opened the interval), `_run_id` (the run that last
wrote the row).

- A01 occupies `bed_id`; A02 occupies `bed_id` and frees `from_bed_id`; A03 frees `bed_id`.
- Per bed, state changes are ordered by (event time, free before occupied, `event_id`); each
  interval ends where the next change starts. Zero-length intervals (freed and taken at one
  instant) are dropped; consecutive changes with the same state merge into one interval.
- History starts at a bed's first event; there is no interval before it.
- `silver.bed_event`: the log of every distinct `event_id` the notebook has seen.

## Settings for every approach

- **Code:** notebook `fabric/nb_bed_history.Notebook/notebook-content.py` (U06/U07 pattern),
  parameters `run_id`, `silver_root`; `scripts/bed_history.py` and `make bed-history` run it
  locally; `pl_land_sources` gains `run_nb_bed_history` after `run_nb_silver`; CI `stand` job runs
  `make bed-history` before `make test-stand`.
- **Duplicates:** events are deduplicated by `event_id` (first copy kept) before anything else; the
  log is written with MERGE insert-when-not-matched, so a resent event is never new.
- **Tests (fast):** fixture events for two transfers and a same-instant discharge/admit, fed in
  batches: in order; a late transfer that re-splits an open interval; duplicates within and across
  batches; batches in reverse time order. Each yields the expected intervals with no gaps or
  overlaps per bed. A bed with no new events is not rewritten.
- **Test (`stand`):** on the full population: no gaps or overlaps, one current row per bed, every
  bed exists in `silver.bed`, and occupied intervals equal the stay segments derived from
  `adt_event` (both directions).

## The choice: how a late event updates the history

### Approach A — Interval surgery by MERGE

Each new event is located in the existing intervals of its bed: the interval containing its time
is closed at that time and a new interval inserted, then the following interval's start is fixed.

- Every event type and every collision (two late events in one batch, a late event at an existing
  boundary, a late event that makes two neighbours equal) is its own MERGE case.
- Cost: hard to prove complete; out-of-order batches multiply the cases.

### Approach B — Recompute affected beds, apply by MERGE (taken)

New events = deduplicated events not yet in `bed_event`. Affected beds = their `bed_id` and
`from_bed_id`. The intervals of affected beds are recomputed from all their logged events plus the
new ones, then applied with one MERGE on (`bed_id`, `valid_from`): changed rows updated, new rows
inserted, rows of affected beds absent from the recomputation deleted (`whenNotMatchedBySource`
with `bed_id IN (affected)`). Then the new events are merged into `bed_event`.

- Why it is correct: the history of a bed is a pure function of its event set, so a late,
  duplicate or out-of-order event gives the same result as an in-order run by construction.
- Why it is cheap enough: a bed has a few hundred events a year; a batch touches only its beds.
  Unaffected beds are not rewritten (MERGE only touches matched files).
- Crash safety: history is written before the log. A failure between the two leaves the events
  "new" and the next run recomputes the same beds to the same result.
- Files: `fabric/nb_bed_history.Notebook/{notebook-content.py,.platform}`,
  `fabric/pl_land_sources.DataPipeline/pipeline-content.json`, `scripts/bed_history.py`,
  `tests/test_bed_history.py`, `tests/test_bronze.py` (pipeline activity set), `Makefile`,
  `.github/workflows/ci.yml`, `README.md`, `CLAUDE.md`, `plan.md`.
- Invariants: per bed, intervals are contiguous and non-overlapping, only the last is open; the
  result does not depend on batch order or duplicates; a stay's occupied intervals equal its
  segments in `adt_event`.
- Red checks: fast scenario tests; `stand` test on the full population.
- Reverse: delete the notebook, script, test and pipeline activity; drop `bed_state_history` and
  `bed_event`. Nothing downstream reads them yet (U08 may later).

### Approach C — Full rebuild each run

Overwrite the whole table from all events every run. Simplest and correct, but no MERGE, every
bed rewritten each run, and the history loses `_run_id` lineage. Rejected against the spec scope
("PySpark merge").

## Implementation notes (2026-10-28)

- Full population (`adt_event`): 13,125 events (A01 6,374, A02 413, A03 6,338), all `event_id`s
  distinct, 6,374 stays (36 open), 48 beds, all in `silver.bed`. One bed has two events at one
  instant.
- `make bed-history` on it: 13,537 intervals in 22 s; a second run finds 0 new events (12 s).
  The `stand` test passes: no gaps or overlaps, one current row per bed, occupied intervals equal
  the stay segments both ways.
- Negative control 1: recomputing from new events only (log ignored) fails the late and
  out-of-order tests; restored, they pass.
- Negative control 2: taking a bed before freeing it at one instant gives 13,536 intervals and
  fails the `stand` test; restored, it passes.
- A duplicate is the same `event_id` resent. If U11 resends under a new id with the same time, the
  copy merges into the existing interval (islands of equal state); a resend with a different time
  would move the start of the interval to the earliest copy.
