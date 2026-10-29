---
id: PLAN-U17
spec: SPEC-001 / U17
owner: AlexBormotov
status: approach A taken 2026-10-29 under the owner's standing go-ahead
previous: PLAN-U10 (#17), PLAN-U18 (#13), PLAN-U11 (#14), PLAN-U15 (#12), PLAN-U09 (#16); see git history of this file
---

# PLAN-U17 — OneLake security and model RLS

## Facts this plan rests on

All read 2026-10-29.

- **OneLake data access roles REST API** (Learn "OneLake Data Access Security - Create Or Update
  Data Access Roles", updated 2026-09-15): `PUT /v1/workspaces/{ws}/items/{item}/dataAccessRoles`
  replaces the full role set; a role has `decisionRules` (`effect: Permit`, exactly two `permission`
  scopes `Path` and `Action`, optional row/column `constraints`) and `members`
  (`fabricItemMembers` with `itemAccess` + `sourcePath`, `microsoftEntraMembers` with
  `objectId`/`objectType`/`tenantId`). Single-role upsert and delete exist. Paths look like
  `/Tables/<name>`.
- **Terraform** (`microsoft/fabric` 1.14.0, pinned in `infra/versions.tf`; provider docs at tag
  `v1.14.0`): resource `fabric_onelake_data_access_security`, one role per resource (`workspace_id`,
  `item_id`, `role_name`, `decision_rules`, `members`), **preview**: needs `preview = true` on the
  provider. Import id `<ws>/<item>/<role>`.
- **Lakehouse Git integration** (Learn "Lakehouse git integration and deployment pipelines", dated
  2026-10-13): data access roles are tracked in `data-access-roles.json`, **preview**, off by
  default (`alm.settings.json`); Entra member IDs are not tracked; only Admin/Member can sync them.
- **OneLake security model** (Learn "OneLake security roles, permissions, and scopes", dated
  2026-08-28): deny by default; roles are grant-only and combine as a union; a lakehouse starts with
  `DefaultReader` (Read on everything for users with ReadAll); with OneLake security, ReadAll grants
  data only through `DefaultReader`; Admin, Member and Contributor bypass roles (Write). Role
  changes take about 5 minutes, group changes about an hour.
- **Role names** (Learn "OneLake security roles: create and manage", dated 2026-09-25):
  alphanumeric, start with a letter, case-insensitive.
- **Direct Lake security** (Learn "Integrate Direct Lake security", updated 2026-09-09): Direct Lake
  on OneLake checks OneLake security for the effective identity (current user with SSO, or the fixed
  identity of a bound cloud connection); it never falls back to DirectQuery, failures are errors.
  Model RLS is not enforced for users with Write on the model (Admin, Member, Contributor). For
  model-only rules, bind a fixed identity with SSO off and give users no permission on the source.
  With OneLake security on a lakehouse, its SQL analytics endpoint defaults to delegated (owner)
  identity; switching it to user identity forces Direct Lake on SQL to DirectQuery.
- **Engines that enforce OneLake RLS/CLS** (Learn "Read data secured with OneLake security", dated
  2026-08-28): Direct Lake on OneLake models, Spark, Lakehouse, SQL endpoint in user identity mode.
- **Silver tables** (this repo): `nb_silver` writes `TABLES`, `FHIR_TABLES`, `patient_record` and
  `reconciliation`; `nb_mpi` writes `patient_xref`, `patient_match_review`; `nb_bed_history` writes
  `bed_state_history`, `bed_event`. 17 tables.

## PHI classification of Silver

PHI class (readable only by `PhiReader`): `patient_record` (names, birth date, phone, postal code)
and `staff` (staff names; personal data, kept with PHI so no name column is in the open class).
Everything else is non-PHI, by the rule U16 uses for Gold: local patient IDs, `master_patient_id`
and event dates do not identify a person without the demographics in `patient_record`.

## Approaches

- **A (taken).** Terraform `fabric_onelake_data_access_security` on each environment's `lh_silver`,
  role contents from `infra/modules/fabric/lh_silver_roles.json` (table classes `phi`/`non_phi`,
  roles listing classes). `DefaultReader` is narrowed to `non_phi` (members: everyone with ReadAll),
  `PhiReader` reads both classes (members: one Entra group, optional variable). Provider `preview`
  turned on.
- B. Lakehouse Git integration (`data-access-roles.json`). Rejected: preview and opt-in; the
  lakehouse shells are Terraform-owned and not in `fabric/`; members are not tracked, so a second
  mechanism is needed anyway.
- C. JSON plus a script calling `PUT dataAccessRoles`. Rejected: Terraform supports the resource,
  and a script adds a second deployment path and a credential flow.

RLS membership: one Entra group is the member of the model role `clinic`, assigned after deploy
(U20); per-user clinic scope is a row in `gold.user_clinic`, written from a git-ignored copy of
`sql/fabric/user_clinic.example.sql` (placeholder UPNs on `example.com`).

Readmission fix: `gold.fact_stay.readmitted_30d` (bit) computed in `gold.reload` over every stay of
the window via `master_patient_id`; the DAX measure and `gold.metric_summary` average the flag.

## Files

- `infra/versions.tf` (provider `preview = true`), `infra/main.tf`, `infra/variables.tf`,
  `infra/terraform.tfvars.example`, `infra/modules/fabric/{main,variables}.tf`,
  `infra/modules/fabric/lh_silver_roles.json`.
- `sql/gold/00_tables.sql`, `sql/gold/10_reload.sql`, `sql/gold/20_metrics.sql`.
- `fabric/sm_clinic_chain.SemanticModel/definition/tables/fact_stay.tmdl`.
- `sql/fabric/user_clinic.example.sql`, `.gitignore`.
- `tests/test_onelake_security.py`, `tests/test_semantic_model.py`.
- `docs/adr/0005-direct-lake-vs-phi-security.md`, `README.md`, `GLOSSARY.md`, `tasks/todo.md`,
  `plan.md`.

## Invariants and the checks that go red

Fast (`make test`), `tests/test_onelake_security.py`:

- Every Silver table written by a notebook is in exactly one class
  (`test_every_silver_table_is_in_exactly_one_class`).
- A Silver table with a name, birth, phone, address or postal column is in `phi`
  (`test_tables_with_phi_columns_are_phi`).
- Only `PhiReader` reads the `phi` class; `DefaultReader` exists and reads `non_phi`
  (`test_only_the_phi_role_reads_phi`).
- Every role in the JSON has a Terraform resource reading the JSON, and role names are valid
  (`test_terraform_defines_every_role`).
- The RLS membership template has only `example.com` UPNs and known clinics, and its real copy is
  git-ignored (`test_user_clinic_template_has_no_real_upns`).

Fast, `tests/test_semantic_model.py`: `readmission_30d_rate` averages `fact_stay[readmitted_30d]`
and has no cross-stay lookup that RLS would cut (`test_readmission_uses_the_precomputed_flag`).

Stand (`make test-stand`): `tests/test_metrics.py::test_gold_metrics_match_the_reference` (Gold
equals the U09 reference to a relative 1e-6), with `gold.metric_summary` reading the flag.

`make lint` runs `terraform validate` against the provider schema.

Negative controls, run 2026-10-29, then reverted:

- `patient_record` moved from `phi` to `non_phi` in the JSON: `test_tables_with_phi_columns_are_phi`
  failed (`{'patient_record'}`), the other four passed.
- The U10 measure (cross-stay lookup) restored in `fact_stay.tmdl`:
  `test_readmission_uses_the_precomputed_flag` failed, the other ten passed.

Stand result, 2026-10-29: `make gold`, then the `stand` tests of `test_gold.py` and
`test_metrics.py`: 7 passed. On the current synthetic data every 30-day readmission is at the same
clinic (any clinic / same clinic: boston 162/162, springfield 270/270, worcester 211/211), so the
U10 bug was latent here; the flag makes the measure correct when a patient moves between clinics.

## Verified in U20 (cloud)

- Terraform creates both roles; overriding `DefaultReader` by name works (else import it first).
- A user with only ReadAll on `lh_silver` reads `encounter` but gets access denied on
  `patient_record` (Spark and OneLake API); a `PhiReader` member reads it.
- Gold reload still reads `silver.patient_record` through the SQL endpoint (delegated mode).
- A clinic user (model Read only, fixed-identity connection) sees only their clinic, and
  `readmission_30d_rate` per clinic equals `gold.metric_summary`.
- Redeploying the model keeps the `clinic` role member.
- ADR 0005's fallback experiment, if Direct Lake on OneLake fails.

## Reversal

Revert the PR. `terraform apply` then deletes `PhiReader` and the managed `DefaultReader`; recreate
`DefaultReader` with all data in the portal. `make gold` rebuilds `fact_stay` without the column.
