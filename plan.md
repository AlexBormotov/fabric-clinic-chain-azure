---
id: PLAN-U20-prep
spec: SPEC-001 / U20 (runbook and evidence template), U21 (link check, residency ADR)
owner: AlexBormotov
status: approach A taken 2026-10-30 under the owner's standing go-ahead
previous: PLAN-U17 (#21), PLAN-U19 (#19), PLAN-U16 (#18), PLAN-U12 (#20), PLAN-U14 (#22); see git history of this file
---

# PLAN-U20-prep — Cloud runbook, evidence template, residency ADR, link check

Prepares the single cloud run (U20) so the owner can do it in one or two sittings, and lands the
parts of U21 that need no cloud: the data residency ADR and the scripted README link check. No
cloud call, login or secret is part of this change.

## Facts this plan rests on

All read 2026-10-30 unless marked.

- **Fabric trial** (Learn "Fabric trial capacity", `ms.date` 2026-08-12, updated 2026-09-29):
  - 60 days free, F4 or F64; F4 may be raised to F64 if eligible, and F64 lowered to F4 ("Change
    size"). Remaining days do not reset.
  - The trial region is picked from a drop-down at activation; the default is the home region.
  - Ends by Account manager > **Cancel trial**, or OneLake catalog > Govern > Capacities > Trials.
    Fabric items become unusable and may be deleted after 7 days.
  - The tenant has a limited number of trials; another trial is not guaranteed.
  - No Copilot, no Trusted Workspace Access, no Private Link. The Capacity Metrics app is supported.
  - Needs tenant settings "Users can create Fabric items" and "Users can try Microsoft Fabric paid
    features".
- **Microsoft 365 business trial** (Learn "Try or buy a Microsoft 365 for business subscription",
  `ms.date` 2026-04-23):
  - Free for one month, 25 licences, card required. A trial-only tenant is limited to 30 days and
    300 GB.
  - "At the end of your trial period, your subscription renews to an annual term subscription by
    default, unless you turn off recurring billing from inside of Billing > Your products."
  - To cancel: turn off recurring billing; "The trial automatically expires when your month ends,
    and your credit card isn't charged."
- **Recurring billing** (Learn "Manage recurring billing", `ms.date` 2026-09-03): admin center >
  Billing > Your products > subscription > **Edit recurring billing** > Off > Save. Turning it off
  does not cancel the subscription; it stays active until it expires.
- **Teams in Business Basic.** Microsoft sells "(no Teams)" suites in the EEA and Switzerland as an
  alternative to the suites with Teams (Microsoft licensing news, read via search 2026-10-30).
  Serbia is outside the EEA. Not confirmed on a trial page for Serbia: the owner checks that the
  trial plan lists Teams before signing up.
- **Azure free account** (azure.microsoft.com "Azure free account", read 2026-10-30): $200 credit
  for 30 days; card (non-prepaid) and phone required, a temporary $1 verification hold; "We'll
  never charge you unless you decide to move to pay-as-you-go pricing." Without an upgrade the
  account is disabled after 30 days. Whether the credit covers the Fabric capacity meter is not
  stated (open since PLAN-U18).
- **F2 price** (Azure Retail Prices API, West Europe, USD, read 2026-10-30): Fabric capacity
  usage is $0.22 per CU-hour, so F2 (2 CU) is $0.44/h, $10.56/day while it exists and is not paused.
  "Capacity Overage Capacity Usage CU" is $0.66 per CU-hour (three times).
- **Capacity overage** (Learn "Capacity overage in Microsoft Fabric", `ms.date` 2026-08-26):
  "Capacity overage is enabled by default when you create a Fabric capacity." It bills only when
  smoothed usage would otherwise throttle. The Fabric blog (2026-04-20) says off by default for
  existing capacities: the two sources differ on defaults. The F2 here hosts no workspace, so no
  usage reaches it.
- **Fabric quotas** (Learn "Microsoft Fabric quotas", `ms.date` 2025-04-06): quota depends on the
  subscription type; register `Microsoft.Fabric` before the first capacity or when quota is 0;
  portal > Quotas > Microsoft Fabric shows and raises it.
- **Region availability** (Learn "Fabric region availability", `ms.date` 2026-10-26): West Europe
  and North Europe run all Fabric workloads (only "Observability in Fabric" is missing in West
  Europe). Power BI-only European regions: Austria East, Belgium Central, Denmark East, France
  South, Germany North, Norway West.
- **Home region** (Learn "Find your Fabric home region", `ms.date` 2025-08-04): chosen when the
  tenant is created; shown at Help > About > "Your data is stored in". The country-to-region
  mapping is not published (the Power BI "where is my tenant located" page now redirects here).
- **Multi-Geo** (Learn "Multi-Geo support for Fabric", `ms.date` 2026-08-13): a capacity outside
  the home region keeps compute and storage, OneLake included, in its region; permissions, report
  and dashboard metadata, semantic model credentials and refresh service buses stay in the home
  region. Data at rest is replicated to another region in the same geography. A trial takes its
  region at activation.
- **Fabric SQL query editor** (Learn, `ms.date` 2026-09-09): DDL, DML and DCL run; "the `GO` SQL
  command creates a new independent batch in a new session". So `sql/gold/` runs there as is.
- **Repository facts.**
  - `scripts/load_stand.py` loads billing and blobs into the local stand only: `stand.sql()`
    connects as `sa` with a password, `stand.blobs()` uses the Azurite key. The Terraform sources
    are Entra-only (no SQL password, shared keys off), so the cloud sources have no loader yet.
  - `mssql_python` 1.16.0 (in `uv.lock`) accepts `token_provider=AzureCliCredential()`, and its
    bulk copy fetches a fresh token per call (`connection.py`, read in the dev image).
  - `azure-identity` 1.26.0 and `azure-storage-blob` 12.31.0 are already dependencies.
  - The `infra` image is the dev image plus the Azure CLI, so it runs the loader after `az login`.
  - The pipeline `pl_land_sources` does not build Gold. Gold is the `sql/` scripts run on
    `wh_gold`.
  - Eventstream is not in Git (PLAN-U18): the owner creates it in the UI.
  - ADR numbers on `origin/main` and `origin/u14-live-map` end at 0005; the next is 0006.
  - `README.md` and `AGENTS.md` still describe the project as "foundation in progress" and
    "Pre-intent"; the `README.md` command table is split by three blank lines.

## Approaches

- **A (taken). Runbook in the repository, plus the one missing loader.**
  - `docs/runbook-cloud.md`: 18 ordered steps with owner/agent, command or UI path, expected
    result, evidence file, cost and time. Cost table first; every billing point marked.
  - `docs/evidence/cloud-run.md`: one checklist item per AC and per "U20 verifies" item of
    PLAN-U12, U14, U16, U17, U18 and U19, each with an empty evidence slot.
  - `docs/adr/0006-data-residency.md`.
  - `scripts/load_stand.py --sql-server … --blob-endpoint …`: loads the same data into the
    Terraform sources with the owner's `az login` token. No password or key path is added.
  - Link checker `src/clinic_chain/doc_links.py`, `scripts/check_links.py`, fast test.
- **B. Runbook only; the owner loads Azure SQL by hand.** There is no portal path for bulk-loading
  three tables into an Entra-only database; it would cost the owner time mid-sitting. Rejected.
- **C. Runbook as an Artifact or external page.** The spec names `docs/runbook-cloud.md` and it must
  version with the code. Rejected.

## Files

- New: `docs/runbook-cloud.md`, `docs/evidence/cloud-run.md`, `docs/evidence/cloud-run/.gitkeep`,
  `docs/adr/0006-data-residency.md`, `src/clinic_chain/doc_links.py`, `scripts/check_links.py`,
  `tests/test_doc_links.py`, `tests/test_load_cloud.py`.
- Changed: `src/clinic_chain/stand.py` (optional Entra-token connections), `scripts/load_stand.py`
  (cloud flags), `README.md` (status, table, runbook link, ADR 0006), `AGENTS.md` (Status),
  `tasks/todo.md`, `plan.md`.

## Invariants and the checks that go red

- Every relative link and image in `README.md` and `docs/**/*.md` resolves to a file or directory
  (`test_docs_links_resolve`). External URLs and in-page anchors are not fetched or checked.
  Links inside code spans and fenced blocks are ignored.
- The checker itself finds a broken link, a broken image and a broken reference-style link in a
  fixture, and ignores code and URLs (`test_checker_finds_broken_links`).
- The local stand keeps working unchanged: `stand.sql()` without `server` still connects as `sa`
  (`stand` tests, unchanged).
- The cloud loader never takes a password or key: it connects with `AzureCliCredential` only
  (`test_cloud_connections_use_the_cli_login`, with the driver and the blob client mocked).
- No secret in any changed path (`gitleaks dir`).

Negative control for the link checker: break one README link (`docs/adr/0001-mpi-approach.md` →
`0001-mpi.md`), run the test, see it name the file and target, restore, see it pass.

## Reversal

Revert the PR. Nothing in the cloud depends on it; the loader flags are unused unless passed.

## Implementation notes (2026-10-30)

- Rebased onto `main` after U14 (#22) merged, so the runbook names `rtd_beds`,
  `act_ward_occupancy` and `nb_bed_reference` as deployed items.
- ruff formats Python blocks inside Markdown: `make lint` reformatted the DAX stress cell in the
  runbook once.
- Negative control: a `README.md` link to `docs/adr/0001-mpi.md` made `test_docs_links_resolve`
  fail with `README.md: docs/adr/0001-mpi.md`; restored, it passes and `scripts/check_links.py`
  exits 0.
- `make lint` and `make test` (120 passed) green. In a worktree `make secrets` scans 0 commits;
  `gitleaks dir --config .gitleaks.toml` on the changed paths found no leaks.
- Not verified here (U20): the cloud loader against Azure SQL and Blob, and every step of the
  runbook.
