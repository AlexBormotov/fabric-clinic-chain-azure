# Direct Lake fallback experiment (AC10, ADR 0005)

Run on 2026-11-27 in the Test workspace (trial capacity), runbook step 11.

**Cause.** A SQL row-level security policy on the Warehouse. `probe.fallback_probe` added the filter
predicate `probe.boston_only(clinic_id)` on `gold.fact_stay` (`STATE = ON`).

**Setting.** A throwaway model `sm_fallback_probe` was created from `wh_gold` with the ribbon's
**New semantic model**. That makes it Direct Lake on SQL, with the default behaviour Automatic. It
held `gold.fact_stay` and `gold.dim_clinic`, without a relationship between them. One table visual
showed `dim_clinic[clinic_id]` and the count of `fact_stay[stay_id]`.

**Observation** (`docs/screenshots/fallback-perf-analyzer.png`):

- Performance Analyzer listed a **Direct query** line under each refresh of the visual, so the
  model fell back to DirectQuery.
  - First refresh: 150 ms.
  - After an edit: 3110 ms.
  - Second refresh: 185 ms.
- The total was 1603 stays: Boston only, with the policy applied by SQL. Without the policy the
  table holds 6374 stays.
- Every clinic row also showed 1603. This is because the probe model had no relationship, so it
  does not change the result.

**Not done.** Step 4, setting the model's Direct Lake behaviour to *Direct Lake only*, was not run.
This is why `fallback-directlakeonly-error.png` is missing.

**Production model.** `sm_clinic_chain` is Direct Lake on OneLake, which never falls back. It reads
the Delta files directly and does not pass through the SQL endpoint's RLS. Clinic scoping is done
by the model role `clinic` (step 12).

**Cleanup.** The policy, function and schema were dropped. Afterwards `SELECT COUNT(*) FROM
gold.fact_stay` returned 6374. The probe model and its report are deleted in the Fabric UI.
