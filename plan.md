---
id: PLAN-U19
spec: SPEC-001 / U19
owner: AlexBormotov
status: approach A taken 2026-10-28 under the owner's standing go-ahead
previous: PLAN-U09 (landed in #16), PLAN-U13 (#15); see git history of this file
---

# PLAN-U19 — Deployment automation

## Facts this plan rests on (read 2026-10-28)

- `fabric-cicd` 1.4.0 on PyPI, released 2026-10-07 (previous 1.3.0, 2026-08-10). Python <3.15.
  Read from its wheel source:
  - `FabricWorkspace(workspace_id=…, repository_directory=…, item_type_in_scope=…, environment=…,
    token_credential=…)`; `token_credential` is required and is any `TokenCredential`.
  - `publish_all_items`, `unpublish_all_orphan_items`. Unpublish only touches types in
    `item_type_in_scope`.
  - `parameter.yml` sits at the root of `repository_directory`. It has `find_replace` (`is_regex`
    replaces capture group 1 only), `key_value_replace` (JSONPath, `jsonpath_ng.ext`, every match)
    and the filters `item_type`, `item_name`, `file_path`. Environment keys are free-form;
    `_ALL_` is supported.
  - `$workspace.$id` is the target workspace. `$items.<type>.<name>.$id` is looked up in the
    target workspace's item list, so Terraform-created lakehouses resolve too. The docs say
    "repository items"; the code (`_refresh_deployed_items`) lists all items.
  - `$ENV:<name>` needs the feature flag `enable_environment_variable_replacement`. Validation
    fails on an unset variable.
  - Order: key_value_replace, then find_replace, then a built-in swap of zero-GUID `workspaceId`
    values. Publish order: Notebook, SemanticModel, Report, Dataflow, DataPipeline.
- GitHub OIDC (Azure/login README, read 2026-10-28): `azure/login` v3.1.0 (2026-09-10). Subject
  `repo:<owner>/<repo>:environment:<name>` with `id-token: write`. fabric-cicd's authentication
  page lists `AzureCliCredential` after `azure/login`. It does not mention OIDC or
  `DefaultAzureCredential`, which is no longer a fallback.
- Dataflow Gen2 (Microsoft Learn, REST reference updated 2026-09-15):
  - `updateDefinition` accepts service principals.
  - Republish is `POST /v1/workspaces/{ws}/dataflows/{id}/jobs/applyChanges/instances`. It is in
    preview, does not accept service principals, and returns 202 with `Location`.
  - The "Public APIs" page (updated 2026-09-11) says service principals are not supported at all.
    The two pages conflict.
- U18 (`origin/u18-terraform`):
  - Workspaces `clinic-chain-{dev,test,prod}`, each with `lh_bronze`, `lh_silver`, `wh_gold` and
    `eh_beds`.
  - `deployer_principal_id` gets Contributor on Test and Prod.
  - Outputs: `workspace_ids`, `item_ids`.
  - No Fabric connections; the owner creates them.
- Placeholders in `fabric/`: 38 lines with the zero GUID or `example.sharepoint.com`. All are
  identical zero GUIDs, so rules must be anchored on context, not on value. U10 (`origin/
  u10-semantic-model`) adds `expressions.tmdl` with a OneLake URL `<workspace>/<warehouse>`.

## Approaches

- **A (taken).** Use `fabric-cicd` from a manual GitHub workflow in the dev container.
  - Identity: `ClientAssertionCredential` fed with a fresh GitHub OIDC token on each Entra
    exchange. No `azure/login` and no Azure CLI in the image.
  - `parameter.yml` holds no IDs. It uses `$workspace.$id` and `$items` for workspace, lakehouse,
    warehouse, notebook and dataflow IDs. It uses `$ENV:` for the two connection IDs and the
    SharePoint site, set as GitHub environment variables.
  - Dataflow republish: `make republish`, run by the owner with device code sign-in.
- B. Same, but `azure/login` with `AzureCliCredential`. Rejected: the runner's az session does not
  reach the dev container, and az would have to be added to the image. B is the fallback if the
  assertion callback fails in U20.
- C. Committed per-environment GUIDs filled from terraform outputs. Rejected: IDs in Git, a manual
  copy step, and drift when Terraform recreates an item.
- D. Client secret in GitHub secrets. Rejected: OIDC works, and the owner wants no stored secret.

## Files

- New: `fabric/parameter.yml`, `src/clinic_chain/deploy.py`, `scripts/deploy.py`,
  `.github/workflows/deploy.yml`, `tests/test_deploy.py`,
  `docs/adr/0004-fabric-cicd-vs-deployment-pipelines.md`.
- Changed: `Makefile` (`deploy`, `republish`), `docker-compose.yml` (pass-through variables),
  `pyproject.toml` and `uv.lock` (`fabric-cicd`), `README.md`, `CLAUDE.md`, `plan.md`.

## Invariants and the checks that go red

- Every zero GUID and `example.sharepoint.com` in `fabric/` is replaced for Test and for Prod
  (`test_every_placeholder_is_resolved`). The resolver re-implements fabric-cicd's rule semantics
  offline and fails on `$items` names not in `fabric/` or Terraform.
- No dead rule (`test_every_rule_matches_something`). A rule whose `item_name` targets are all
  absent from `fabric/` (the U10 model and the U12 `kqldb_beds`, until they merge) is exempt.
- Every rule has exactly the keys Test and Prod, and fabric-cicd's own validator accepts the file
  for each.
- The orphan cleanup cannot delete Terraform's items (`test_orphan_cleanup_cannot_delete_terraform_items`):
  - Lakehouse, Warehouse and Eventhouse are never in `ITEM_TYPES`;
  - KQLDatabase is in scope for U12's `kqldb_beds`, but fabric-cicd unpublishes it only with
    `enable_kqldatabase_unpublish`, which is never set;
  - `item_name_exclude_regex` also excludes every Terraform name, including the eventhouse's
    default database `eh_beds`.
- `kqldb_beds`'s `parentEventhouseItemId` resolves to `$items.Eventhouse.eh_beds.$id`. With
  `origin/u12-eventhouse` overlaid, the tests pass and that rule matches.
- fabric-cicd uploads every file in an item folder (`os.walk`). `deploy()` first removes the
  git-ignored `__pycache__` that notebook-importing tests leave in `fabric/`.
- `deploy.yml`: `workflow_dispatch` only, no `secrets.`, read-only default permissions, jobs in
  environments Test and Prod (`test_deploy_workflow_is_manual_and_uses_no_secret`). `make lint`
  runs `actionlint` on every workflow.

Negative controls, run 2026-10-28:

- Removing the `run_nb_mpi` notebookId rule fails both environments with
  `pl_land_sources.DataPipeline/pipeline-content.json:491: "notebookId": "00000000-…"`.
- Renaming `lh_silver` to `lh_silvr` in one rule fails with `no such item in fabric/ or Terraform`.
- Restored, all 11 tests pass. With the U10 model and report overlaid from
  `origin/u10-semantic-model`, they also pass: the model rules match and nothing is left.

## Not verified here (U20)

- No deploy was run and no cloud call was made.
- To verify in U20:
  - the OIDC assertion against Entra;
  - `$items` lookup of Terraform items;
  - Dataflow deploy by a service principal (the docs conflict);
  - pipeline runs of items owned by the service principal;
  - the Dataflow's SharePoint connection binding and its destination, which the definition
    API cannot author.

## Reversal

Revert the PR. Nothing in the cloud depends on it. After a deploy:

- delete the deployed code items from Test and Prod, or redeploy an older commit;
- remove the federated credentials and the GitHub environments.
