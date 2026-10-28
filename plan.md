---
id: PLAN-U18
spec: SPEC-001 / U18
owner: AlexBormotov
status: approach A taken 2026-10-28 under the owner's standing go-ahead; built
previous: PLAN-U07 (approach A, landed in #10; see git history of this file)
---

# PLAN-U18 — Terraform

## Facts this plan rests on (read 2026-10-28)

- **Providers (Terraform Registry API).** `microsoft/fabric` 1.14.0 (2026-09-17) is the latest.
  `hashicorp/azurerm` latest is 5.11.0 (2026-10-23) and 5.10.0 (2026-10-15); both are younger than two
  weeks, so 5.9.0 (2026-10-08) is pinned. `Azure/azapi` 2.13.0 (2026-09-28). `hashicorp/random` 3.9.1
  (2026-09-11).
- **Tools (GitHub releases).** Terraform 1.16.6 (2026-10-14; 1.17.x is younger than two weeks).
  tflint 0.64.0 (2026-07-17; 0.65.0 is 6 days old). `tflint-ruleset-azurerm` 0.32.0 (2026-04-25; 0.33.0
  is 3 days old). SHA-256 sums taken from the vendors' published checksum files.
- **Fabric resources (provider docs at tag v1.14.0).** GA, no `preview` flag: `fabric_workspace`
  (`capacity_id`), `fabric_workspace_git` (GitHub needs `git_credentials.source =
  "ConfiguredConnection"` and a `connection_id`; `initialization_strategy` `PreferRemote` or
  `PreferWorkspace`), `fabric_deployment_pipeline` (2–10 stages, each optionally bound to a
  workspace), `fabric_lakehouse` (`configuration.enable_schemas`), `fabric_warehouse`,
  `fabric_eventhouse`, `fabric_eventstream`, `fabric_workspace_role_assignment`, data source
  `fabric_capacity` (by `display_name`). The provider authenticates with the Azure CLI (`use_cli`).
- **Capacity.** `azurerm_fabric_capacity` in azurerm 5.9.0: `sku { name = "F2", tier = "Fabric" }`,
  `administration_members` (UPN for users). No API or Terraform creates a trial capacity
  (`docs/research/fabric-facts-2026-10-21.md`).
- **Azure SQL free offer.** azurerm 5.9.0, 5.11.0 and `main` have **no** free-offer arguments on
  `azurerm_mssql_database`. Issue hashicorp/terraform-provider-azurerm#23438 is open; PR #32055 (adds
  `use_free_limit`, `free_limit_exhaustion_behavior`) is open; PR #32277 closed unmerged. The ARM
  API `Microsoft.Sql/servers/databases@2025-01-01` (stable) has `useFreeLimit` (bool; the schema text still says one database
  per subscription, the free-offer page says ten) and `freeLimitExhaustionBehavior` (`AutoPause`,
  `BillOverUsage`), so the database is an `azapi_resource`. Free offer terms (Learn, updated
  2026-10-12): per database 100,000 vCore-seconds, 32 GB data, 32 GB backup per month; up to 10 per
  subscription; General Purpose serverless Gen5 2 vCores; auto-pause after 15 min idle (fixed);
  `AutoPause` on exhaustion stops charges, `BillOverUsage` cannot be switched back; free offer only on
  a new database; most subscription types, not Azure for Students Starter.
- **Prices (Azure Retail Prices API, West Europe, USD).** Every Fabric capacity meter is $0.22 per
  CU-hour, so **F2 (2 CU) is $0.44/h** pay-as-you-go, billed per second while it exists and is not
  paused. Blob Hot LRS: $0.0196/GB-month, writes $0.054 per 10k, reads $0.0043 per 10k.
- **Fabric trial (Learn, 2026-08-12).** Free for 60 days, F4 or F64; no Copilot, no Trusted
  Workspace Access, no Private Link; at expiry workspaces fall back to Pro and Fabric items are kept
  7 days. Trial count per tenant is limited.
- **Repository.** Notebooks write `Tables/<name>` (no schema segment), so lakehouses are created
  without schemas. Local stand names: database `clinic_billing`, containers `fhir`, `lab`, `adt`.
  The Dockerfile pins tool versions but does not verify checksums today.

## Settings for every approach

- **Layout.** One root in `infra/` with modules `infra/modules/azure-sources`,
  `infra/modules/fabric`, `infra/modules/capacity`. Local state, git-ignored. Lock file committed.
- **Auth.** No secret in Terraform: the owner's `az login` (Azure CLI) serves azurerm, azapi and
  fabric. SQL server is Entra-only (no SQL password in state); the storage account has shared keys
  disabled. A git-ignored `terraform.tfvars` holds IDs and names only.
- **Cheapest path by default.** `enable_f2 = false`; Git integration and the deployer role only when
  their IDs are set; SQL free offer with `AutoPause`; Blob LRS.
- **Ownership boundary.** Terraform owns workspaces and the stateful item shells (lakehouses
  `lh_bronze`, `lh_silver`, warehouse `wh_gold`, eventhouse `eh_beds`); code items (notebooks,
  pipelines, dataflow, eventstream, model, report, dashboard, Activator) come from Git via
  `fabric-cicd` (U19). Eventstream stays out because its topology is code bound to item IDs.
- **Checks.** `make tf-check`: `terraform fmt -check -recursive`, `terraform init -backend=false`,
  `terraform validate`, `tflint --recursive` (terraform recommended preset + azurerm ruleset).
  `make lint` runs it, so the CI `lint` job covers it. No cloud call in any check.

## The choice: how the F2 capacity is proven

### Approach A — one root, F2 behind a toggle (taken)

`enable_f2` (default `false`) gates the `capacity` module. Proof: `apply -var enable_f2=true`, check,
`apply -var enable_f2=false` (destroys only F2). Workspaces stay on the trial throughout.

- Files: `infra/**`, `docker/dev.Dockerfile`, `docker-compose.yml`, `Makefile`, `.gitignore`,
  `README.md`, `CLAUDE.md`, `plan.md`.
- Invariants: no secret in any committed file; F2 never assigned to a workspace, so destroying it
  breaks nothing; defaults create no billed capacity.
- Red check: `make tf-check` (fmt, validate, tflint) in CI `lint`; `make secrets`.
- Cost: F2 runs only between two applies, about 15 min, about $0.11.
- Reverse: `terraform destroy`, then delete `infra/` and the Dockerfile lines.

### Approach B — separate roots per module

Three state files; F2 has its own root and is destroyed with `terraform destroy`.

- Cleaner blast radius, but three inits, three tfvars and outputs wired by hand; slower for one
  operator.

### Approach C — F2 hosts the workspaces

Workspaces point at F2 instead of the trial.

- Rejected: F2 must run for the whole cloud run ($0.44/h, ~$10 for a day), viewers need Pro, and
  destroying it orphans the workspaces.

## Implementation notes (2026-10-28)

- azapi carries the SQL database until azurerm ships the free-offer arguments. Moving it later means
  `terraform state rm` plus `import`, since the free offer applies only at creation.
- The dev image gains Terraform and tflint (checksums verified). A separate `infra` image target adds
  Azure CLI 2.91.0 for the owner's `az login`; CI never builds it.
- Open: whether an Azure free account's credit covers an F2 meter is not stated in the documents
  read; the F2 apply/destroy may be billed to the card (about $0.11).
