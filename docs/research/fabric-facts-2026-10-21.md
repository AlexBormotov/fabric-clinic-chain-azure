# Fabric fact check, read 2026-10-21

Facts the brief marked as unverified, checked against current vendor documentation. Agent-gathered;
items marked "unconfirmed" still need a check before a decision rests on them.

## Findings that change the plan

- **Trial size.** A new trial may start at F4 (4 CU), not F64; resizing to 64 CU depends on
  eligibility. No API or Terraform creates a trial capacity.
  https://learn.microsoft.com/en-us/fabric/fundamentals/fabric-trial
- **Soda Core vs Spark 4.** `soda-core-spark-df` 3.5.6 (last v3) pins `pyspark<4.0.0`. Fabric
  Runtime 2.0 (Spark 4.1, Python 3.13) is the GA default; Runtime 1.3 (Spark 3.5) is end-of-support.
  v4 package is `soda-sparkdf` 4.28.0 (`pyspark[connect]>=3.5.0`); not yet tested on Fabric.
- **Viewing.** Trial behaves like F64 (free-license viewers allowed). On F2 every viewer needs Pro,
  PPU or an individual trial. https://learn.microsoft.com/en-us/fabric/enterprise/licenses
- **Dataflow Gen2 after Git sync / deploy** must be republished (open and save, or publish-job API)
  before refresh works.
  https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-cicd-and-git-integration

## Reference

| Item | Answer | Status |
|---|---|---|
| Terraform `microsoft/fabric` | 1.14.0 (2026-09-17). GA resources: workspace, workspace_git, deployment_pipeline, lakehouse, warehouse, eventhouse, eventstream, kql_database, notebook, data_pipeline, semantic_model, report, domain, workspace_role_assignment, dataflow. Preview (`preview = true`): activator, onelake_data_access_security, folder, others | GA provider |
| `workspace_git` | Service principal only with `git_credentials.source = "ConfiguredConnection"` | — |
| Capacity | `azurerm_fabric_capacity` (azurerm 5.10.0) | GA |
| F2 PAYG | ~$0.44/h West Europe, ~$0.38/h North Europe (2 × CU-hour meter; unconfirmed in calculator). Pausable; smoothed usage billed on pause | — |
| Direct Lake F2/F4/F8 | 1,000 parquet files/table, 1,000 row groups, 300M rows, 10 GB model, 3 GB memory. DL on OneLake: over limit → fails, no fallback. DL on SQL: falls back to DirectQuery (`DirectLakeBehavior=Automatic`), also on SQL RLS/OLS/DDM and non-materialized views | DL on SQL GA; DL on OneLake GA unconfirmed |
| fabric-cicd | 1.4.0 (2026-10-07). Covers Notebook, DataPipeline, Lakehouse, Warehouse, SemanticModel, Report, Eventhouse, Eventstream, KQLDatabase, KQLQueryset, KQLDashboard, Reflex, Dataflow, Environment, VariableLibrary and more | GA |
| Warehouse RLS/CLS/DDM/OLS | T-SQL only, no Terraform resource | GA |
| OneLake security | Data access roles with RLS/CLS | GA (date unconfirmed) |
| Activator | Sources incl. Eventstream, KQL queryset, Real-Time dashboard; actions email, Teams, Power Automate, pipeline, notebook | GA; Terraform resource preview |
| Eventstream custom endpoint | Event Hubs connection string, AMQP, Kafka; works with `azure-eventhub` SDK | GA |
| SharePoint Excel | SharePoint **folder** connector in Dataflow Gen2 GA; "SharePoint Online File" preview | — |
| Azure SQL free offer | 100k vCore-s, 32 GB per DB/month, up to 10 DBs per subscription, auto-pause | GA |
| Throttling | Interactive smoothing ≥5 min, background 24 h. ≤10 min overage protection; 10–60 min 20 s interactive delay; 60 min–24 h interactive rejection; >24 h all rejected. RTI skips delay stage | current |
