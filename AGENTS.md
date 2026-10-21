# AGENTS.md

Working agreement for every agent and engineer in this repository. Vendor-neutral; runtime wiring
lives in `CLAUDE.md`.

## What this is

Pet project: end-to-end analytics and real-time bed monitoring for a network of 5–10 clinics on
Microsoft Fabric (Azure). The original brief (`TASK.md`) and the grilling transcript (`GRILL.md`)
are local only and not committed; once approved, `intent.md` supersedes both. Repository name:
`fabric-clinic-chain-azure`.

Shape, from the brief: Data Pipelines (Azure SQL billing, lab CSV, Synthea FHIR JSON) and
Dataflows Gen2 (Excel on SharePoint) land in OneLake; PySpark notebooks build Lakehouse
Bronze/Silver; T-SQL Warehouse holds the Gold star schema; a Direct Lake semantic model feeds
Power BI. ADT events stream through Eventstream into Eventhouse (KQL) for the live bed map, with
Data Activator alerting above 90% ward occupancy. Soda Core checks Silver. PHI is masked in the
Warehouse (DDM, CLS), RLS by clinic in Power BI. CI/CD: GitHub Git integration, deployment
pipelines Dev → Test → Prod, `fabric-cicd`; capacity and workspaces via the Fabric Terraform
provider. Orchestration is native Data Pipelines only.

The brief states that Fabric prices and feature status (Terraform provider, Direct Lake limits on
small capacities) are unverified. Verify each against current Microsoft documentation, with the
date read, before a decision depends on it.

## Status

Pre-intent. No code exists yet. Nothing is built before the approval chain below reaches an
approved `plan.md`.

## How work proceeds (AI Factory method)

The method source is `ai-factory-kit/` (local, not committed). Its rule sets are installed in
`.agents/skills/`; `.claude/skills` is a symlink to it and must never become a second copy.

1. **Grill** the brief (`grilling`) until the design tree has no open branch.
2. **`intent.md`**: what is being built and why. Approved by the owner before anything else.
3. **`spec.md`**: bounded task with a checkable completion condition (gate G1). Approved by the owner.
4. **`plan.md`**: written after research. For each plausible approach: files touched, invariants
   kept, the check that goes red when each breaks, how it is reversed. The owner picks one (G6).
5. **Build** against the approved plan. A fact in the plan found false, or a diff touching a file
   outside the approved set, stops work and returns the plan to the owner.

Settled domain terms go to `GLOSSARY.md`, hard-to-reverse decisions to `docs/adr/`
(`domain-modeling`). Corrections from the user go to `tasks/lessons.md`.

## Rules that apply throughout

- Language: the owner writes in Russian; everything committed to the repository is in English.
- No real PHI anywhere. Patient data is Synthea synthetic only.
- Cloud spend is the owner's money: no capacity is created, resumed or left running without the
  owner's explicit go-ahead, and every session that starts one ends by pausing it.
- A failing test is never edited to pass in the same change as the fix it unblocks.
