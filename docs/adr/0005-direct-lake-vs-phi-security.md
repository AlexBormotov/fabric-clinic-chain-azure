# ADR 0005: Direct Lake versus PHI security

- Status: accepted 2026-10-29 (PLAN-U17, approach A); cloud behaviour verified in U20
- Unit: U17

## Context

PHI is protected in three places (AC9): Gold SQL readers (U16: column DENY and masks on
`gold.dim_patient`), Silver files in OneLake, and the Power BI model, where a clinic user must see
only their clinic. The model is Direct Lake on OneLake over the Gold Warehouse tables, without PHI
columns, with one dynamic RLS role `clinic` (U10).

Read in Microsoft Learn on 2026-10-29 ("Integrate Direct Lake security", updated 2026-09-09;
"OneLake security roles, permissions, and scopes", dated 2026-08-28):

- Direct Lake on OneLake reads Delta files through OneLake as an effective identity: the current
  user (SSO, the default) or the fixed identity of a bound cloud connection with SSO off.
- With SSO, a report user needs read access to the source item, so they can query it directly and
  bypass the model's RLS. With a fixed identity, users need no permission on the source.
- Model RLS is not enforced for users with Write on the model: workspace Admin, Member, Contributor.
- When the source has OneLake security, Direct Lake on OneLake applies the effective identity's
  OneLake roles first, then the model roles. It never falls back to DirectQuery: a denied table or
  an exceeded guardrail is an error in the visual.
- OneLake security roles exist for lakehouses and mirrored items, not warehouses. Admin, Member and
  Contributor bypass them. `DefaultReader` gives everyone with ReadAll all data unless narrowed.
- A lakehouse with OneLake security keeps its SQL analytics endpoint in delegated (owner) mode by
  default; user identity mode makes Direct Lake on SQL fall back to DirectQuery always.

## Decision

- **The model uses a fixed identity.** It is bound to a cloud connection (workspace identity or
  service principal) with SSO off. The identity holds Read and ReadAll on `wh_gold`. Clinic users
  get Read on the model (or the app) only: no workspace role, no permission on `wh_gold` or the
  lakehouses. So the only path to Gold data is the model, and model RLS holds.
- **Clinic scope is data, the role has one member.** The role `clinic` has one member, the Entra
  group of all clinic users, assigned in the model's Security settings after deploy. The clinics a
  user sees are rows in `gold.user_clinic`, written per environment from a git-ignored copy of
  `sql/fabric/user_clinic.example.sql`. No UPN is committed.
- **Measures never look across RLS.** RLS on `dim_clinic` also filters facts of other clinics, so a
  measure that needs another clinic's rows reads a column Gold precomputes over all rows.
  `readmission_30d_rate` averages `gold.fact_stay.readmitted_30d`.
- **OneLake security on `lh_silver`, in Terraform** (`fabric_onelake_data_access_security`, preview
  in provider 1.14.0). `DefaultReader` is narrowed to the non-PHI tables; `PhiReader` reads every
  table and has one Entra group as member. Table classes are in
  `infra/modules/fabric/lh_silver_roles.json`: PHI = `patient_record` and `staff`. A reader who must
  not see PHI holds item Read and ReadAll on `lh_silver`, never a workspace role.
- **The model is unaffected by `lh_silver` roles**: it reads `wh_gold`, which has no OneLake roles.
  Gold's reload reads Silver through the `lh_silver` SQL endpoint, which stays in delegated mode.

## Rejected

- SSO on the model: users would need read on `wh_gold`, and with it the Delta files of
  `dim_patient`, which DDM and CLS do not cover.
- RLS in OneLake security instead of the model: not available on a Warehouse source.
- Lakehouse Git integration for the roles (`data-access-roles.json`): preview, opt-in, and Entra
  members are not tracked.

## Planned fallback experiment (U20)

Run in this order and record the outcome in `docs/evidence/`:

1. Bind the fixed identity, refresh, open the report as a clinic user. Expect only their clinic, and
   `readmission_30d_rate` per clinic equal to `gold.metric_summary`.
2. If visuals fail with a framing or access error, the fixed identity or the model owner lacks Read
   or ReadAll on `wh_gold`: grant it, refresh, repeat 1.
3. If Direct Lake on OneLake over the Warehouse fails on the trial or F2 capacity (unsupported source
   or guardrail), switch the shared expression to Direct Lake on SQL (`Sql.Database` on the `wh_gold`
   endpoint) with the same fixed identity. First set `directLakeBehavior: directLakeOnly`, so a query
   that would fall back to DirectQuery errors instead. The model has no PHI column, no view and no
   SQL RLS table, so no fallback is expected. Then compare the measures with step 1.
4. If any query still needs DirectQuery, keep `automatic`, record which tables fall back
   (Performance Analyzer, `DirectQuery` events) and accept it at this data size.
5. If the Gold reload fails after the `lh_silver` roles are applied, check that the SQL endpoint is
   in delegated mode; if user identity mode is required, add the pipeline identity to `PhiReader`.

## Consequences

- A clinic user who is also a workspace Contributor sees every clinic; operators and report users
  are different identities.
- Role and group changes take minutes to an hour to apply; U20 waits before checking.
- `terraform destroy` deletes `DefaultReader` on `lh_silver`; ReadAll then grants no data.
