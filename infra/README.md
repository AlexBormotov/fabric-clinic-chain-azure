# infra

Terraform for the cloud run (U18): Azure sources, Fabric workspaces and the F2 they run on. Local state,
git-ignored. CI runs `make tf-check` (fmt, validate, tflint) only; nothing here plans or applies in CI.

| Module | Creates |
|---|---|
| `modules/azure-sources` | Resource group, Blob storage (`fhir`, `lab`, `adt`), Azure SQL server (Entra-only) and database `clinic_billing` on the free offer, firewall rules |
| `modules/fabric` | Workspaces `clinic-chain-dev/test/prod` on the F2 (or on `fabric_capacity_name`); `lh_bronze`, `lh_silver`, `wh_gold`, `eh_beds` in each; Git integration for Dev; deployment pipeline Dev → Test → Prod; Contributor for the deployer on Test and Prod; OneLake security roles on `lh_silver` (`DefaultReader` narrowed to non-PHI tables, `PhiReader` for `phi_reader_group_id`; preview resource, ADR 0005) |
| `modules/capacity` | F2 capacity in its own resource group; created only with `enable_f2` |

Code items (notebooks, pipelines, dataflow, eventstream, model, report, dashboard, Activator) are
deployed from Git by `fabric-cicd` (U19), not by Terraform.

## Who logs in

Only the owner, with the Azure CLI inside the `infra` container. azurerm, azapi and fabric all use
that login; no key, password or token is stored in Terraform or the repository. The SQL server
accepts Entra logins only and the storage account has shared keys disabled.

```sh
docker compose --profile cloud build infra
docker compose run --rm infra            # shell in /workspace/infra
az login --use-device-code
cp terraform.tfvars.example terraform.tfvars   # fill in IDs and names; git-ignored
```

## Apply order

1. Accounts per `intent.md`; the subscription stays on Free Trial.
2. In Fabric, create a GitHub connection (fine-grained token, this repository only) and note its ID
   for `git_connection_id`. The token stays in Fabric.
3. `terraform init`, then `terraform apply -target=module.capacity` (the F2 alone). Turn its capacity
   overage off in the Fabric admin portal.
4. `terraform apply`. Workspaces, items, Azure sources. Pause the F2 between sittings
   (`docs/runbook-cloud.md`, step 4.2).

## Cost (F2 in Sweden Central read 2026-11-24, the rest 2026-10-28)

| Piece | Price | Expected |
|---|---|---|
| F2 (`enable_f2`) | $0.38/h (2 CU × $0.19), per second while it runs; usage owed is billed on pause | ~$3.4 for 9 h, from the free credit |
| Azure SQL free offer | 100k vCore-s, 32 GB data, 32 GB backup per month free; `AutoPause` at the limit | $0 |
| Blob Hot LRS | $0.0196/GB-month, $0.054 per 10k writes | < $0.05 |

Sources: Azure Retail Prices API; Learn "Try Azure SQL Database for free" (2026-10-12).
`sql_free_limit_exhaustion = "BillOverUsage"` cannot be undone; leave
the default.

## Teardown

```sh
terraform destroy
az logout
exit
docker volume rm "$(basename "$PWD")_azure-config"   # from the repository root, on the host
```

Then check that Azure cost analysis and the resource list are empty (U20).
