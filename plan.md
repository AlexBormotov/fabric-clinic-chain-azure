---
id: PLAN-U20-trial
spec: SPEC-001 / U20 (capacity of the cloud run)
owner: AlexBormotov
status: >-
  the owner asked on 2026-11-24 for the trial if a 60-day one can be had by changing the region, and
  planned against it on 2026-11-25; the F2 proof needs a separate go-ahead
previous: PLAN-U20-f2 (#24); see git history of this file
---

# PLAN-U20-trial: the Fabric trial in Sweden Central is the capacity again

PLAN-U20-f2 rested on "the tenant is refused a Fabric trial". That proved false: on 2026-11-24 the
owner got one by choosing Sweden Central.

## Facts

- `GET https://api.fabric.microsoft.com/v1/capacities`, run by the owner on 2026-11-25:
  `Trial-20261124T214353Z-…`, SKU `FTL4`, Sweden Central, Active.
- Learn "Fabric trial capacity" (`ms.date` 2026-08-12, read 2026-11-25): 60 days; F4 or F64; one trial
  serves several workspaces; Copilot, AI experiences, Trusted Workspace Access and Private Link are not
  supported; at the end the workspaces go to Pro and the items stay in OneLake for 7 days.
- Learn "Fabric features by SKU" (`ms.date` 2026-06-30, read 2026-11-25): viewing with a Fabric free
  licence is marked as supported on a trial; the F4 size is not named. Checked in step 12.
- Region, quota and F2 price facts of PLAN-U20-f2 still hold.
- With #24 in place, `enable_f2 = true` moved every workspace to the F2, so a short F2 proof next to a
  trial would have moved them.

## Approaches

- **A (taken). Trial for the workspaces; the F2 created and destroyed once, about 15 minutes.** Back to
  PLAN-U20-prep, with Sweden Central.
- **B. Keep the F2 as the capacity.** About $4-8 of credit, pauses between sittings. Rejected: the trial
  is free.
- **C. Trial only, no F2.** Fails the "apply and destroy F2" part of U20. Rejected.

## Files

Revert of #24 except the region, the second-subscription note, the alert recipient and the recorded
evidence: `infra/`, `docs/runbook-cloud.md`, `docs/evidence/cloud-run.md`, `docs/adr/0006`,
`intent.md`, `README.md`, `plan.md`.

## Invariants and checks

- `enable_f2` adds two resources and changes no workspace: the workspaces take their capacity only from
  `fabric_capacity_name` (`make tf-check`; the plan of step 14 shows 2 to add, 0 to change).
- `enable_f2` stays false by default: no paid resource without an explicit choice.
- Links in the docs resolve (`tests/test_doc_links.py`); no secret in the diff (`make secrets`).

## Reversal

Revert the PR. Nothing is applied by it; the owner applies from the infra container.
