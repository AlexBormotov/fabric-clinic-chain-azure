---
id: INT-001
title: Clinic chain analytics and real-time bed monitoring on Microsoft Fabric
owner: AlexBormotov
status: approved by owner 2026-10-21
review_date: 2026-11-21
---

# INT-001 — Clinic chain analytics and real-time bed monitoring on Microsoft Fabric

## Outcome, and who wants it

The chief physician and the CFO of a small clinic chain see three things in one report: live bed
occupancy, quality of care and economics. Today these live in separate systems (EHR/HIS, a bed
management system, billing) and are reconciled by hand once a month.

This is a portfolio project. It is built on synthetic data, run end to end in the cloud **once**,
captured in screenshots and a written walkthrough, then torn down. "Done" means a reproducible
repository plus evidence of one successful cloud run, not a continuously operated system.
Microsoft Fabric is the primary platform; every other tool adapts to it, not the other way round.

## Acceptance criteria

1. **Synthetic estate.** Generators produce data for 3 clinics with 300, 400 and 500 patients over
   2 years, across five deliberately different sources: FHIR R4 JSON (Synthea), an ADT event stream,
   billing and insurance claims in Azure SQL, lab results as CSV, and staff rosters plus bed
   reference data as Excel on SharePoint. Each source system carries its own local patient
   identifiers and realistic noise (name typos, day/month swaps, phone formats, ~5% duplicates); the
   generator keeps the ground truth.
2. **Batch path.** Data Pipelines (Azure SQL, Blob CSV, Blob FHIR) and Dataflows Gen2 (SharePoint
   Excel) land data in OneLake; PySpark notebooks build Lakehouse Bronze and Silver; a Warehouse holds
   the Gold star schema. Row counts reconcile from source to Gold, with every difference explained.
3. **Metrics.** A Direct Lake semantic model and a Power BI report show occupancy rate, ALOS, bed
   turnover, 30-day readmissions, emergency department wait time, revenue per bed, claim denial rate
   and payer mix. Each metric matches a reference value computed independently from generator output.
4. **Real time.** ADT events replayed at 10–50 events/s (accelerated time over the 2-year history,
   including late and duplicate events) flow through Eventstream into Eventhouse, and a live bed map
   reflects an event within seconds. The measured latency is reported.
5. **Alerting.** Activator posts a Teams channel message when a ward's occupancy exceeds 90%.
6. **Bed state history.** Late ADT events produce a correct SCD2 history of bed state, proven by tests.
7. **Patient matching (MPI).** Patients are matched across systems; precision and recall against the
   generator's ground truth are reported.
8. **Data quality.** Soda Core checks run on Silver in Fabric notebooks, including referential
   integrity between patients and encounters. A deliberately broken record makes the check fail.
9. **PHI protection.** In the Warehouse, a non-privileged SQL user sees PHI masked (dynamic data
   masking, column-level security). In Power BI, a clinic-scoped user sees only their clinic (RLS).
   The Direct Lake model carries no PHI columns. OneLake security is configured.
10. **Direct Lake fallback.** A deliberate experiment shows a model falling back from Direct Lake to
    DirectQuery, with the evidence and the cause recorded.
11. **Capacity behaviour.** Capacity smoothing and throttling are observed on a real workload and
    recorded from the capacity metrics.
12. **Delivery.** Dev workspace is Git-integrated with GitHub; GitHub Actions deploys to Test and Prod
    with `fabric-cicd`; one promotion through a Fabric deployment pipeline is demonstrated for
    comparison. Terraform creates the workspaces and the Azure sources, and creates and destroys an F2
    capacity once.
13. **Local first.** Everything that can run without Fabric (generators, transforms, SQL, KQL, event
    producer, data quality checks) runs and is tested locally; `make test` passes without cloud access.
    CI runs the same make targets.
14. **Cost.** Total cloud spend stays at or under $10, with a hard ceiling of $20. All cloud
    resources are deleted after the run and no subscription is left to renew.
15. **Documentation.** An English README with architecture, run instructions, screenshots of the
    cloud run and decision records covering at least: the Lakehouse/Warehouse boundary, Direct Lake
    vs PHI security, data quality tooling, MPI approach, CI/CD promotion, data residency.

## Out of scope

- Real patient data of any kind.
- A continuously running production system, SLAs, on-call.
- External orchestrators (Airflow, ADF outside Fabric); orchestration is Fabric Data Pipelines only.
- Copilot and AI features of Fabric (not available on trial capacity).
- Private networking (Private Link, managed VNets).
- Multi-tenant or multi-region deployment beyond what the residency decision record describes.

## Constraints

- **Budget:** target ≤ $10, ceiling $20 for the entire cloud run.
- **Accounts:** none exist yet. They are created only when the project is ready for the cloud run,
  because the Microsoft 365 trial lasts 30 days: Microsoft 365 Business Basic trial (recurring
  billing switched off on day one) → Fabric trial (60 days) → Azure free account with its subscription
  in the same tenant. Tenant country: Serbia.
- **Region:** West Europe for capacity, Azure SQL and Blob storage.
- **Platform versions:** current Fabric Spark runtime (Runtime 2.0, Spark 4.1); no downgrade to work
  around a library.
- **Repository:** public, `fabric-clinic-chain-azure`, English only.

## Settled during grilling, carried into the spec

These are design inputs, recorded here so they are not lost; each is confirmed or revised in
`spec.md` and the decision records.

- Delivery in vertical slices: batch → real time → quality and security → CI/CD and IaC. Paid cloud
  features are exercised only in the final cloud run.
- Local stand in Docker: Spark 4.1 + Delta, SQL Server 2022 (billing source and Gold approximation),
  Azure Event Hubs emulator, Kusto emulator; Power BI model and report as PBIP in Git.
- Fabric trial is the main capacity; F2 is applied and destroyed once to prove the Terraform module.
- Data quality: Soda v4 (`soda-sparkdf`) made to work on Runtime 2.0.
- Semantic model: Direct Lake on OneLake over Gold tables without PHI; RLS in the model; DDM and CLS
  in the Warehouse for SQL consumers.
- MPI: own PySpark scoring (blocking, Jaro-Winkler, exact-field agreement, review band); Splink noted
  as the next step.
- Raw FHIR and lab files land in Azure Blob Storage; Blob and Azure SQL come from one Terraform module.
- Tooling: `uv`, `ruff`, `pytest`, `sqlfluff`, `terraform fmt/validate`, `tflint`, `gitleaks`;
  everything through the `Makefile`.

Fact checks behind these inputs: `docs/research/fabric-facts-2026-10-21.md`,
`docs/research/tenant-options-2026-10-21.md`.
