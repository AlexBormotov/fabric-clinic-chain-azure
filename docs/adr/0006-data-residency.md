# ADR 0006: Data residency

- Status: accepted 2026-10-30 (PLAN-U20-prep); the home region is recorded in U20
- Unit: U20, U21

## Context

AC15 asks for a decision record on data residency. The intent fixes the tenant country (Serbia),
West Europe for the capacity, Azure SQL and Blob storage, and synthetic data only. Four places hold
data: the Fabric home region of the tenant, the Fabric capacity region (OneLake), the Azure
sources, and the developer's machine and GitHub.

Read in Microsoft Learn on 2026-10-30:

- "Find your Fabric home region" (`ms.date` 2025-08-04): the home region is "chosen when your
  tenant was created" and shown under Help > About > "Your data is stored in". Microsoft does not
  publish which region a sign-up country maps to, and a tenant cannot move itself ("Fabric trial
  capacity", `ms.date` 2026-08-12: moving needs Microsoft support).
- "Fabric region availability" (`ms.date` 2026-10-26): West Europe and North Europe run every
  Fabric workload this project uses (Data Factory, Data Engineering, Warehouse, Real-Time
  Intelligence, Activator, Power BI). West Europe lacks only "Observability in Fabric". Austria
  East, Belgium Central, Denmark East, France South, Germany North and Norway West are Power BI-only.
- "Fabric trial capacity": the trial region is picked from a drop-down at activation and defaults to
  the home region. Workspaces with non-Power BI Fabric items cannot later move to another region
  without deleting those items.
- "Multi-Geo support for Fabric" (`ms.date` 2026-08-13): with a capacity outside the home region,
  "compute and storage (including OneLake and experience-specific storage) is located in the
  multi-geo region". Permissions, report and dashboard metadata, semantic model credentials and
  refresh service buses stay in the home region; some features, such as data alerts, process data
  in the home region. Data at rest is replicated to another region of the same geography.

## Decision

- **Everything that stores project data runs in West Europe.** The Fabric trial capacity is
  activated in West Europe, whatever the home region turns out to be. Terraform's `location`
  defaults to `westeurope` for the Blob account, the Azure SQL server and the F2 capacity.
- **The home region is recorded, not chosen.** Right after the tenant exists the owner reads
  Help > About in Fabric and writes the value into `docs/evidence/cloud-run.md`. If it is a full
  Fabric region in Europe, nothing changes. If it is outside Europe or Power BI-only, the trial
  still goes to West Europe (Multi-Geo), and the record lists the metadata that stays in the home
  region.
- **No real personal data exists anywhere.** Patients, staff and users of the report are Synthea
  or generator output. Test users are accounts of the throwaway tenant. So residency is shown, not
  required by law: the run proves the setup a real clinic chain would need, not compliance.
- **Ground truth never reaches the cloud.** `data/sources/ground_truth/` stays local; only the MPI
  scores computed from it are committed.
- **One geography, one copy per source.** No geo-replication is configured: Blob is LRS, Azure SQL
  backups are locally redundant (`requestedBackupStorageRedundancy = "Local"`). OneLake replicates
  within the Europe geography by default.
- **Teardown removes the data.** `terraform destroy` deletes the Azure sources and the workspaces;
  cancelling the trial leaves Fabric items to be deleted after 7 days; ending the Microsoft 365
  trial retires the tenant.

## Rejected

- North Europe: also full Fabric and slightly cheaper for F2 (PLAN-U18 read $0.38/h), but the intent
  fixes West Europe, and the F2 runs for minutes.
- Picking the home region through the sign-up country: the mapping is not published, so it cannot
  be planned; a record of the actual value is honest and enough.
- Private Link and customer-managed keys: out of scope (intent) and unavailable on the trial.

## Consequences

- If the home region is outside Europe, some metadata (permissions, report metadata, credentials)
  lives outside Europe even though all data rows stay in West Europe. A real deployment would then
  need a tenant created with a European sign-up country, or a support-assisted move.
- The data residency claim covers Microsoft's regions only. The local machine holds the synthetic
  data, GitHub the code and the evidence; neither is part of the residency boundary.
