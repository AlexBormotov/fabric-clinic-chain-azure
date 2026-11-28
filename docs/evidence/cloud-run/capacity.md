# Capacity smoothing and throttling (AC11)

Observed on 2026-11-28 in the Microsoft Fabric Capacity Metrics app, runbook step 13. The capacity
is the Fabric trial, SKU `FTL4` (F4: 4 capacity units, so 120 CU·s per 30-second timepoint and
345,600 CU·s per day), Sweden Central. The trial was already F4, so no resize was needed.

## Workload

- **Interactive.** 2026-11-28 14:46–15:03 UTC: 360 `executeQueries` calls on the Test
  `sm_clinic_chain`, each a `SUMX` over the date × bed cross join of `occupancy_rate`, `alos_days`
  and `bed_turnover_per_year`. 339 returned 200; the rest failed on the client network and never
  reached the service.
- **Background.** `nb_silver` ran 15:05–15:07 UTC. Earlier runs on 2026-11-27 also count: the
  `pl_land_sources` pipeline, the dataflow, the Gold reload and the replay.
- **Always on.** `eh_beds`, the Eventhouse in Test and the one in Prod.

## What the app shows

| Reading | Value | Screenshot |
|---|---|---|
| Avg utilization, today / last 7 days | 70.23% / 31.77% | `capacity-health.png` |
| Throttled and interactive-rejected capacities, last 7 days | 0 / 0 | `capacity-health.png` |
| P95 interactive delay / interactive rejection / background rejection | 74.97% / 73.82% / 37.31% | `capacity-health.png` |
| 14 days: avg / peak utilization | 31.88% / 76.51% | `capacity-compute.png` |
| Peak timepoint 2026-11-27 19:50 | background 74.92%, 89.90 of 120 CU·s, interactive 0 | `capacity-compute.png` |
| 1 day: avg / peak utilization | 53.67% / 76.28% | `capacity-throttling.png` |
| Interactive delay over 2026-11-28 | rises from about 20% at 00:00 to about 75% by 18:00; never 100% | `capacity-throttling.png` |

**Smoothing.** Background work is spread over the next 24 hours. The CU % chart is therefore flat
and almost all background from the evening of 2026-11-27 onwards, at about 75%. It shows no spike
at the moment a pipeline or notebook ran. The interactive-delay percentage climbs during the day
for the same reason: each 30-second timepoint carries the smoothed share of earlier background
work forward.

**Throttling.** Fabric throttles once the smoothed future usage passes 100%: 10 minutes ahead for
interactive delay, 60 minutes for interactive rejection, 24 hours for background rejection. The
highest reading was 74.97%, so nothing was delayed or rejected (rejected count 0 for every item).
Throttling was observed as a reading below its limit. That is the outcome the runbook allows.

**Where the capacity goes.** On 2026-11-28 each `eh_beds` consumed 107,400 CU·s. The operation is
"EventHouse UpTime": the Eventhouse is billed while it is up, whether or not it is queried. The two
Eventhouses together used 214,801 CU·s, about 62% of the F4 daily budget. Over 14 days they used
212,388 CU·s (Test) and 197,147 CU·s (Prod). The next largest items were `pl_land_sources` with
16,148 CU·s, `wh_gold` with 6,558 CU·s and `df_sharepoint` with 5,588 CU·s. The DAX loop does not
appear among the top items (`capacity-timepoint.png`, operations of the Prod `eh_beds`).

Two consequences:

1. An idle Eventhouse is the main load on a small capacity. The Prod one carries no data from this
   run, yet it used about 31% of F4.
2. On F2 (172,800 CU·s per day), one Eventhouse alone would use about 62%. Step 14 assigns F2 to no
   workspace, so this does not affect the F2 check.
