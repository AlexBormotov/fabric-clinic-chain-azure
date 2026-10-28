# ADR 0004: fabric-cicd from GitHub Actions for Test and Prod, deployment pipeline for comparison only

- Status: accepted 2026-10-28 (PLAN-U19, approach A)
- Unit: U19

## Context

AC12 asks for both: GitHub Actions deploying to Test and Prod with `fabric-cicd`, and one promotion
through a Fabric deployment pipeline. Only one can own Test and Prod. The two differ:

| | fabric-cicd 1.4.0 | Fabric deployment pipeline |
|---|---|---|
| Source of a release | a Git commit (`fabric/`) | whatever is in the previous stage's workspace |
| Environment values | `fabric/parameter.yml`, reviewed in PRs | deployment rules, set per stage in the portal |
| Identity | service principal via GitHub OIDC, no secret | user in the portal, or the API |
| Approval | GitHub environment protection on Prod | stage access in Fabric |
| Removing items | `unpublish_all_orphan_items`, limited to code item types | not done by a deployment |

## Decision

- Test and Prod are deployed only by `.github/workflows/deploy.yml`, which runs `make deploy`
  (`fabric-cicd`) on manual dispatch. Prod needs Test to pass first and the Prod environment's
  approval.
- The deployment pipeline that Terraform creates (U18) is used once in the cloud run (U20) to promote
  Dev to Test for comparison. The next fabric-cicd run then overwrites Test from Git.
- `fabric-cicd` deploys code items only: notebooks, pipeline, dataflow, semantic model, report.
  Lakehouses, warehouse and eventhouse stay with Terraform. Their types are not in scope, so the
  orphan cleanup cannot delete them.

## Consequences

- A release is a commit, and a review of `parameter.yml` is a review of every environment value.
  No ID is committed: the values come from the target workspace or from GitHub environment
  variables.
- Dataflows Gen2 need an "apply changes" job after their definition changes. That job does not
  accept service principals (Microsoft Learn, read 2026-10-28), so the owner runs
  `make republish` after a deploy. Release is not fully hands-off while that limit stands.
- Items deployed by the service principal are owned by it. Some runs started under that ownership,
  such as a dataflow refresh from the pipeline, may need a user owner. U20 checks this.
- The deployment pipeline comparison leaves Test briefly on content that came from Dev, not from Git.
