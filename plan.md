---
id: PLAN-U20-f2
spec: SPEC-001 / U20 (capacity and region of the cloud run)
owner: AlexBormotov
status: approach A approved by the owner 2026-11-24
previous: PLAN-U20-prep (#23); see git history of this file
---

# PLAN-U20-f2: F2 in Sweden Central instead of the Fabric trial

PLAN-U20-prep rested on a Fabric trial in West Europe. Both facts proved false on 2026-11-24.

## Facts

- Start trial answers "Fabric trial is not available for your account"; no capacity exists. Tenant
  settings allow Fabric items and paid-feature trials. Community threads report that tenants younger
  than 90 days are refused; Microsoft Learn does not state it.
- The free subscription (`FreeTrial_2014-09-01`, spending limit On) has Fabric quota 0 in West Europe,
  North Europe, Germany West Central and UK South, where SQL provisioning is also restricted. Sweden
  Central, Spain Central and France Central: quota 4 CU, SQL available. Free subscriptions cannot
  raise quotas (Learn "Azure subscription and service limits").
- Azure Retail Prices API, read 2026-11-24: $0.19 per CU-hour in Sweden Central and Spain Central,
  $0.20 in France Central.
- Learn "Fabric region availability": Sweden Central runs all Fabric workloads.
- Learn "Pause and resume": smoothed and carried-forward usage is billed on pause.
- Learn "Enable capacity overage": on by default for new capacities, 25% threshold, three times the
  rate, not a hard cap.
- Learn "Fabric licenses": below F64 each viewer needs Pro, PPU or an individual trial.
- Not stated by Microsoft: that the $200 credit covers the Fabric meter.

## Approaches

- **A (taken). F2 in Sweden Central on the free subscription.** The spending limit stays on.
- **B. Upgrade to pay-as-you-go and request quota in West Europe.** Removes the spending limit.
  Rejected.
- **C. No cloud run.** Fails AC3 to AC5 and AC9 to AC12. Rejected.

## Files

`infra/` (region default, `fabric_capacity_name` optional, workspaces take the F2 name from the
capacity resource), `docs/runbook-cloud.md`, `docs/evidence/cloud-run.md`, `docs/adr/0006`,
`intent.md`, `infra/README.md`, `README.md`, `plan.md`.

## Invariants and checks

- Workspaces depend on the F2, so it is created first and destroyed last (reference through
  `module.capacity`; `make tf-check`).
- `enable_f2` stays false by default: no paid resource without an explicit choice.
- Links in the docs resolve (`tests/test_doc_links.py`); no secret in the diff (`make secrets`).

## Reversal

Revert the PR. Nothing is applied by it; the owner applies from the infra container.
