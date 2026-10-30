# Cloud runbook (U20)

The single cloud run: create the accounts, apply Terraform, deploy, run every cloud check, capture
evidence, tear down, check spend. Follow the steps in order, in one or two sittings. Every result
goes into [`docs/evidence/cloud-run.md`](evidence/cloud-run.md); files go into
`docs/evidence/cloud-run/` under the names given here.

**Who.** *Owner* does everything that signs in, types a password, token or card number, or spends
money. *Agent* prepares commands, reads pasted output (never a secret), compares numbers and fills
the evidence file. No step gives the agent a password, key, connection string or token.

**Markers.**
- 💲 **SPEND**: this step can cost money.
- ⏱️ **BILLS UNTIL REMOVED**: this resource keeps billing (or renews) if forgotten. Each one has a
  matching removal step.

Facts behind the prices and terms were read on 2026-10-30; sources are in
[`plan.md`](../plan.md) (PLAN-U20-prep) and [ADR 0006](adr/0006-data-residency.md).

## Cost

Cheapest path (the default): trials and free offers only; the F2 lives for about 15 minutes.

| Item | Terms (read 2026-10-30) | Cheapest path | Expected | If forgotten |
|---|---|---|---|---|
| Microsoft 365 Business Basic trial | 1 month free, 25 licences, card required. **Renews to an annual paid term by default.** | Recurring billing **Off** on day one (step 1.2) | $0 | ⏱️ annual term starts at day 30 |
| Fabric trial | 60 days free, F4 or F64. Items deleted 7 days after it ends | Start in West Europe (step 1.4) | $0 | no charge; cancel anyway (step 16) |
| Power BI individual trial | Comes with the Fabric trial | — | $0 | no charge |
| Azure free account | $200 credit for 30 days; $1 card hold; "never charge you unless you decide to move to pay-as-you-go" | Do **not** upgrade to pay-as-you-go | $0 cash; credit used | account disabled at day 30 |
| Azure SQL free offer | 100,000 vCore-s, 32 GB data, 32 GB backup per month free; `AutoPause` at the limit | Keep `sql_free_limit_exhaustion = "AutoPause"` | $0 | ⏱️ only if switched to `BillOverUsage` (irreversible) |
| Blob storage, Hot LRS | $0.0196/GB-month; ~1 GB | — | < $0.05 | ⏱️ cents per month |
| F2 capacity | **$0.44/h = $10.56/day** while it exists (2 CU × $0.22) | Apply, check, destroy in the same sitting (step 14) | ~$0.11 | ⏱️ **$10.56 per day** |
| F2 capacity overage | 3× rate ($0.66/CU-h); on by default for new capacities (Learn) | F2 hosts no workspace, so nothing runs on it | $0 | only with a workspace on F2 |
| Eventstream, Eventhouse, Activator, Spark, Warehouse | Run on the trial capacity | — | $0 | Activator polling keeps the Eventhouse busy: stop the rule (step 10) |
| GitHub Actions | Public repository | — | $0 | — |
| **Total** | | | **$0 cash, ≈ $0.20 of Azure credit** | |

Worst case on the cheapest path: the free credit does not cover the Fabric meter (not stated by
Microsoft) and the F2 apply fails or must be paid: then about $0.11 on the card after an upgrade.
The budget breaks only if a ⏱️ item is forgotten: the F2 alone burns the $10 target in under a day.

**Guard rails, set in step 1.6:** a $5 Azure budget alert, and a calendar reminder for the
Microsoft 365 trial end date.

## Time

| Sitting | Steps | Owner time |
|---|---|---|
| 1 | 0–7: accounts, identities, Terraform, connections, deploy, pipelines, Gold | ~4.5 h |
| 2 | 8–18: real time, checks, F2, screenshots, teardown, cost | ~4.5 h |
| +2 days | 17: final cost check (Azure cost data lags up to 48 h) | 10 min |

Do steps 14 and 16 in the same sitting as anything that created them. Never end a sitting with the
F2 present.

---

## 0. Prerequisites (local, free)

- **Who:** owner (the agent can run them on request).
- **Do:** in the main checkout, with Docker running:
  ```sh
  make setup
  make synth sources          # only if data/raw/fhir/ or data/sources/sharepoint/ is missing
  make metric-reference       # refreshes docs/evidence/metric-reference.json
  git switch main && git pull # deploy.yml runs from main only
  ```
- **Expect:** `data/sources/sharepoint/beds.xlsx`, `rosters.xlsx`, `data/sources/adt/events.csv`,
  `data/raw/fhir/{boston,worcester,springfield}/fhir/*.json` exist. All units, U14 included, are
  merged on `main`.
- **Evidence:** none.
- **Cost / time:** $0 / 10 min (20 min if `make synth` runs).

## 1. Accounts

Order fixed by `intent.md`: Microsoft 365 trial → Fabric trial → Azure free account, all in one
tenant.

### 1.1 Microsoft 365 Business Basic trial — 💲 card ⏱️ renews

- **Who:** owner.
- **Do:** <https://www.aka.ms/office365signup> → Microsoft 365 Business Basic → **Try free for 1
  month**. Country **Serbia**. Check that the plan lists Microsoft Teams before paying anything
  (EEA "no Teams" suites exist; Serbia is outside the EEA). Pick a tenant name, for example
  `clinicchainYYMM`; the admin account is `admin@<tenant>.onmicrosoft.com`.
- **Expect:** admin center at <https://admin.microsoft.com> opens; Teams and SharePoint licences
  assigned to the admin.
- **Evidence:** none yet (step 1.2 covers billing).
- **Cost / time:** $0, card on file / 20 min.

### 1.2 Turn off recurring billing — do it now ⏱️

- **Who:** owner.
- **Do:** admin center → **Billing** → **Your products** (Simplified view: **Billing**) → Microsoft
  365 Business Basic → **Edit recurring billing** → **Off** → **Save**.
- **Expect:** the subscription shows recurring billing off and an expiry date 30 days out. "The
  trial automatically expires when your month ends, and your credit card isn't charged."
- **Evidence:** `m365-recurring-billing-off.png` (the product page with the expiry date).
- **Cost / time:** $0 / 5 min. Skipping it starts an annual paid term at day 30.

### 1.3 Home region

- **Who:** owner.
- **Do:** sign in to <https://app.fabric.microsoft.com> as the admin → **?** (Help) → **About**.
- **Expect:** "Your data is stored in …".
- **Evidence:** `fabric-home-region.png`; write the value into the checklist (ADR 0006).
- **Cost / time:** $0 / 2 min.

### 1.4 Fabric trial

- **Who:** owner.
- **Do:** Fabric → Account manager (photo, top right) → **Start trial** → region **West Europe**
  (change it if the default differs) → **Activate**. Then **OneLake catalog** → **Govern** →
  **Capacities** → **Trial** tab: note the capacity name and size (F4 or F64).
- **Expect:** a trial capacity in West Europe; you are its Capacity administrator.
- **Evidence:** `fabric-trial.png` (Trial tab: name, region, size, days left).
- **Cost / time:** $0 / 5 min.
- **If the button is missing:** tenant settings **Users can try Microsoft Fabric paid features**
  and **Users can create Fabric items** must be on (Admin portal → Tenant settings).
  If the tenant cannot start a trial at all, stop and decide: an F2 for the whole run costs
  $0.44/h while not paused (budget threat; see the end of this file).

### 1.5 Azure free account in the same tenant — 💲 card hold

- **Who:** owner.
- **Do:** <https://azure.microsoft.com/free> signed in as `admin@<tenant>.onmicrosoft.com` (not a
  personal account). Card and phone verification. Do **not** choose pay-as-you-go.
- **Expect:** <https://portal.azure.com> → **Subscriptions** shows "Azure subscription 1" (Free
  Trial) in the tenant; **Cost Management + Billing** → **Azure credits** shows $200.
- **Evidence:** `azure-subscription.png` (subscription type and directory; crop the card).
- **Cost / time:** $0 ($1 hold, released) / 15 min.

### 1.6 Guard rails

- **Who:** owner.
- **Do:** Azure portal → **Cost Management** → **Budgets** → **Add**: scope the subscription,
  monthly, $5, alert at 50% and 100% to your e-mail. Add the Microsoft 365 trial end date to your
  calendar.
- **Evidence:** `azure-budget.png`.
- **Cost / time:** $0 / 5 min.

## 2. Entra: deployer app, federated credentials, groups, test users

### 2.1 Sign in for the CLI

- **Who:** owner (types the device code).
- **Do:** on the host, in the repository root:
  ```sh
  docker compose --profile cloud build infra
  docker compose run --rm infra                 # shell in /workspace/infra
  az login --use-device-code --tenant <tenant>.onmicrosoft.com
  az account show --query "{subscription:id, tenant:tenantId, user:user.name}" -o table
  ```
- **Expect:** the Free Trial subscription and your admin UPN. Keep this shell open for steps 2–4.
- **Cost / time:** $0 / 5 min.

### 2.2 Deployer app and federated credentials (no secret)

- **Who:** owner runs; agent can prepare the IDs.
- **Do:** in the infra shell:
  ```sh
  APP_ID=$(az ad app create --display-name clinic-chain-deployer --query appId -o tsv)
  SP_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
  for ENV in Test Prod; do
    az ad app federated-credential create --id "$APP_ID" --parameters "{
      \"name\": \"github-$ENV\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"repo:AlexBormotov/fabric-clinic-chain-azure:environment:$ENV\",
      \"audiences\": [\"api://AzureADTokenExchange\"]}"
  done
  echo "AZURE_CLIENT_ID=$APP_ID deployer_principal_id=$SP_ID"
  az account show --query tenantId -o tsv      # AZURE_TENANT_ID
  ```
- **Expect:** two federated credentials on the app; no client secret exists (`az ad app credential
  list --id "$APP_ID"` is empty).
- **Evidence:** `entra-federated-credentials.png` (app → Certificates & secrets → Federated
  credentials).
- **Cost / time:** $0 / 10 min.

### 2.3 Groups

- **Who:** owner.
- **Do:**
  ```sh
  for G in clinic_chain_deployers clinic_chain_analysts clinic_chain_phi_readers clinic_chain_clinic_users; do
    az ad group create --display-name "$G" --mail-nickname "$G" --query id -o tsv
  done
  az ad group member add --group clinic_chain_deployers --member-id "$SP_ID"
  ```
  Note the object ID of `clinic_chain_phi_readers`: it is `phi_reader_group_id`.
- **Cost / time:** $0 / 5 min.

### 2.4 Test users

- **Who:** owner (passwords stay with you; create them in the UI, not on a command line).
- **Do:** admin center → **Users** → **Add a user**, three times, each with a Business Basic licence:
  - `clinic.boston` → add to `clinic_chain_clinic_users`. No workspace role, no item permission
    except Read on the report and model (step 12).
  - `analyst` → add to `clinic_chain_analysts`.
  - `phi.reader` → add to `clinic_chain_phi_readers`.
  Sign in once as each in a private window and accept the Fabric (Free) licence; start a Power BI
  individual trial if a report asks for one.
- **Cost / time:** $0 / 20 min.

## 3. GitHub environments and variables

- **Who:** owner (variables are IDs, not secrets; the agent may run the `gh` lines if asked).
- **Do:** after step 4 gives the workspace IDs, and step 5 the connection IDs:
  - GitHub → Settings → Environments → **New environment** `Test` and `Prod`. Both: deployment
    branches **Selected branches** `main`. `Prod`: **Required reviewers** = you.
  - Variables, per environment:
    ```sh
    for ENV in Test Prod; do
      gh variable set AZURE_TENANT_ID --env $ENV --body <tenant id>
      gh variable set AZURE_CLIENT_ID --env $ENV --body <app id>
      gh variable set FABRIC_SQL_CONNECTION_ID --env $ENV --body <step 5.2>
      gh variable set FABRIC_BLOB_CONNECTION_ID --env $ENV --body <step 5.2>
      gh variable set SHAREPOINT_SITE_URL --env $ENV --body https://<tenant>.sharepoint.com/sites/clinic-chain
      gh variable set ALERT_TEAMS_RECIPIENT --env $ENV --body admin@<tenant>.onmicrosoft.com
    done
    gh variable set FABRIC_WORKSPACE_ID --env Test --body <workspace_ids.test>
    gh variable set FABRIC_WORKSPACE_ID --env Prod --body <workspace_ids.prod>
    ```
- **Expect:** `gh variable list --env Test` shows seven variables; `gh secret list --env Test` is
  empty.
- **Evidence:** `github-environments.png` (Prod protection rules and variable names).
- **Cost / time:** $0 / 15 min.

## 4. Terraform apply

### 4.1 Variables and providers

- **Who:** owner.
- **Do:** on the host, `curl -s https://api.ipify.org` gives your public IP. Copy
  `infra/terraform.tfvars.example` to `infra/terraform.tfvars` (git-ignored) and fill:
  `subscription_id`, `owner_upn`, `fabric_capacity_name` (step 1.4), `client_ip_addresses`,
  `deployer_principal_id` (`$SP_ID`), `phi_reader_group_id`. Leave `git_connection_id` and
  `enable_f2` commented. In the infra shell:
  ```sh
  for NS in Microsoft.Storage Microsoft.Sql Microsoft.Fabric; do az provider register --namespace $NS --wait; done
  ```
- **Cost / time:** $0 / 10 min.

### 4.2 Apply — 💲 (Blob cents; SQL free offer)

- **Who:** owner.
- **Do:**
  ```sh
  terraform init
  terraform plan -out tf.plan       # review: no fabric_capacity, sql useFreeLimit = true
  terraform apply tf.plan
  terraform output
  ```
- **Expect:** resource group `rg-clinic-chain-sources` (storage, SQL server, `clinic_billing`);
  workspaces `clinic-chain-dev/test/prod` on the trial, each with `lh_bronze`, `lh_silver`,
  `wh_gold`, `eh_beds`; deployment pipeline; deployer Contributor on Test and Prod; `DefaultReader`
  and `PhiReader` roles on every `lh_silver`. If the apply fails on `DefaultReader` ("already
  exists"), import it (PLAN-U17) and apply again.
- **Evidence:** `terraform-apply.txt` (the last 40 lines and `terraform output`, IDs are not secret);
  `azure-sql-free-offer.png` (database → Overview shows the free offer).
- **Cost / time:** < $0.05 / 15 min.

### 4.3 Load the Azure sources

- **Who:** owner.
- **Do:** in the infra shell (the token is your `az login`; no password exists):
  ```sh
  cd /workspace && uv sync --frozen --quiet
  PYTHONPATH=src uv run python scripts/load_stand.py \
    --sql-server "$(terraform -chdir=infra output -raw sql_server_fqdn)" \
    --blob-endpoint "$(terraform -chdir=infra output -raw blob_endpoint)"
  cd infra
  ```
- **Expect:** `sql: clinic_billing` and `blob: fhir, lab, adt`. Billing row counts equal the local
  stand's (`make test-stand` locally).
- **Evidence:** `load-sources.txt` (the output).
- **Cost / time:** < $0.01 / 15 min (upload of ~0.9 GB).

### 4.4 SharePoint files

- **Who:** owner.
- **Do:** `https://<tenant>.sharepoint.com` → **Create site** → Team site `clinic-chain`. Upload
  `data/sources/sharepoint/beds.xlsx` and `rosters.xlsx` to **Documents**. Create a team
  `clinic-chain` in Teams with a channel `bed-alerts` (needed in step 10).
- **Cost / time:** $0 / 10 min.

## 5. Fabric connections, tenant setting, Git integration

### 5.1 Service principals in the Fabric API

- **Who:** owner.
- **Do:** Fabric → Settings → **Admin portal** → **Tenant settings** → Developer settings →
  **Service principals can call Fabric public APIs** → Enabled for `clinic_chain_deployers` → Apply.
- **Evidence:** `fabric-sp-setting.png`.
- **Cost / time:** $0 / 5 min (takes up to 15 min to apply).

### 5.2 Source connections

- **Who:** owner (signs in with OAuth; nothing is pasted).
- **Do:** Fabric → Settings → **Manage connections and gateways** → **New** → Cloud:
  - Azure SQL Database: server = `sql_server_fqdn`, database `clinic_billing`, OAuth 2.0.
  - Azure Blob Storage: account = `blob_endpoint`, OAuth 2.0 (shared keys are off).
  For each: **Manage users** → add `clinic-chain-deployer` as User. Copy each **Connection ID** into
  the GitHub variables (step 3).
- **Cost / time:** $0 / 10 min.

### 5.3 GitHub connection and Dev Git integration

- **Who:** owner (creates and types the token; it stays in Fabric).
- **Do:** GitHub → Settings → Developer settings → **Fine-grained token**: only this repository,
  Contents read and write, expiry 7 days. Fabric → Manage connections → **New** → GitHub - Source
  control → paste the token. Put its connection ID in `git_connection_id` in `terraform.tfvars`, then:
  ```sh
  terraform apply      # binds clinic-chain-dev to main, folder fabric/
  ```
- **Expect:** `clinic-chain-dev` → Source control shows "synced" with the latest commit of `main`.
- **Evidence:** `dev-git-integration.png`.
- **Cost / time:** $0 / 15 min. The token expires by itself; delete it in step 16 anyway.

## 6. Deploy

- **Who:** owner (dispatches and approves); agent reads the logs.
- **Do:**
  ```sh
  gh workflow run deploy.yml -f target=Prod      # Test, then Prod after your approval
  gh run watch
  ```
  Then, once, in the Test workspace (the definition API cannot set these):
  - `df_sharepoint` → **Manage connections**: bind the SharePoint source with OAuth; check that the
    destination is `lh_bronze` Files; **Save**.
  - Apply the dataflow changes:
    ```sh
    FABRIC_WORKSPACE_ID=<test id> make republish ENVIRONMENT=Test   # device-code sign-in
    ```
  - `act_ward_occupancy` → rule "Ward occupancy above 90%" → action **Teams** → **Channel post** →
    team `clinic-chain`, channel `bed-alerts` → Save. If the deploy rejected the Reflex, use the
    recipe in README "Live bed map and alert", step 2.
- **Expect:** both jobs green; Test and Prod hold every item of `fabric/`; the OIDC sign-in works
  without a secret; `$items` resolved the Terraform lakehouses (pipeline activities show
  `lh_bronze`, not a zero GUID).
- **Evidence:** `deploy-run.png` (Actions run, both jobs); `deploy-test-log.txt` (the fabric-cicd
  part of the Test job log); `test-workspace-items.png`.
- **Cost / time:** $0 / 30 min.
- **Deployment pipeline comparison (AC12):** Fabric → Deployment pipelines →
  `clinic-chain` → Dev → **Deploy** selected item `nb_quality` to Test. Screenshot
  `deployment-pipeline-promotion.png`. Then re-run the deploy workflow with `target=Test` so Test is
  back on Git content.

## 7. Pipelines and Gold

### 7.1 Batch pipeline

- **Who:** owner runs; agent compares counts.
- **Do:** Test workspace → `pl_land_sources` → **Run**. Watch the activities (~20–40 min).
- **Expect:** every copy, `refresh_df_sharepoint`, and the notebooks `nb_bronze`, `nb_silver`,
  `nb_mpi`, `nb_bed_history`, `nb_quality`, `nb_bed_reference` succeed. `nb_quality` reports 48
  checks passed.
- **Evidence:** `pipeline-run.png` (activity list, all green); `nb-quality-output.png`;
  `silver-reconciliation.csv`: in `lh_silver` SQL endpoint run
  `SELECT * FROM reconciliation ORDER BY 1, 2` and export.
- **Cost / time:** $0 (trial CU) / 45 min.

### 7.2 Gold on `wh_gold`

- **Who:** owner pastes; agent checks.
- **Do:** Test → `wh_gold` → **New SQL query**. Paste and run each file whole, in this order (the
  editor runs each `GO` batch in turn):
  `sql/fabric/silver_views.sql`, `sql/gold/00_tables.sql`, `10_reload.sql`, `20_metrics.sql`,
  `30_access.sql`, `30_security.sql`, then `EXEC gold.reload;`, then
  `sql/fabric/security_members.sql`, then your git-ignored `sql/fabric/user_clinic.sql` (copy of the
  example with `clinic.boston@<tenant>.onmicrosoft.com` → `boston`).
  Row counts:
  ```sql
  SELECT t.name, SUM(p.rows) AS row_count FROM sys.tables AS t
  JOIN sys.partitions AS p ON t.object_id = p.object_id
  WHERE SCHEMA_NAME(t.schema_id) = 'gold' GROUP BY t.name ORDER BY t.name;
  SELECT * FROM gold.metric_summary;
  SELECT * FROM gold.metric_payer_mix;
  ```
- **Expect:** counts equal the local `make gold` output; `metric_summary` equals
  `docs/evidence/metric-reference.json` (agent compares to 1e-6). `ALTER ROLE … ADD MEMBER` with
  the two groups succeeds although no database user existed (PLAN-U16 open point).
- **Evidence:** `gold-row-counts.csv`, `gold-metric-summary.csv`, `gold-metric-payer-mix.csv`.
- **Cost / time:** $0 / 30 min.

### 7.3 Report

- **Who:** owner.
- **Do:** Test → `sm_clinic_chain` → Settings → **Gateway and cloud connections**: bind a cloud
  connection with a fixed identity, SSO off (workspace identity; if it is not offered, OAuth 2.0 as
  yourself, and note the deviation from ADR 0005). Give that identity Read and ReadAll on `wh_gold`.
  **Refresh**. Open `rpt_clinic_chain`.
- **Expect:** three pages (occupancy, quality, economics) render; numbers match
  `gold.metric_summary` (chain scope).
- **Evidence:** `report-occupancy.png`, `report-quality.png`, `report-economics.png`.
- **Cost / time:** $0 / 20 min.

End of sitting 1 is fine here: nothing billable exists except Blob cents. Do not start step 14.

## 8. ADT replay into Eventstream

### 8.1 Eventstream (not in Git)

- **Who:** owner.
- **Do:** Test → **New item** → Eventstream `es_adt` → source **Custom endpoint** → destination
  **Eventhouse**, mode **Direct ingestion**, `eh_beds` / `kqldb_beds`, table `adt_raw`, format JSON,
  mapping `adt_raw_json` (Advanced) → **Publish**. Custom endpoint → **Event Hub** → **SAS key
  authentication** → copy **Connection string-primary key**.
- **Cost / time:** $0 / 15 min.

### 8.2 Replay — the connection string stays in your terminal

- **Who:** owner. Do not paste the connection string into chat, a file in the repository, or the
  agent's session.
- **Do:** on the host, in a terminal of your own:
  ```sh
  read -rs ADT_EVENTHUB_CONNECTION_STRING && export ADT_EVENTHUB_CONNECTION_STRING
  make replay ARGS='--rate 50'          # full two years, ~4.5 min
  ```
  Then in `kqldb_beds` (KQL queryset):
  ```kusto
  adt_raw | count;
  adt_event | summarize sends = count(), events = dcount(event_id), first = min(ingested_at), last = max(ingested_at);
  ward_occupancy() | order by occupancy desc
  ```
- **Expect:** the printed summary (sent, late and duplicate shares, rate 10–50/s); `adt_raw` count =
  sent; `adt_event` distinct `event_id` = rows of `events.csv`; every ward has an occupancy.
- **Evidence:** `replay-summary.json` (the printed line), `eventhouse-counts.png`,
  `rtd-beds.png` (the dashboard during the replay).
- **Cost / time:** $0 / 20 min.

## 9. Latency

- **Who:** owner runs; agent computes.
- **Do:** open `rtd_beds` (live refresh on) and start a screen recording that shows a UTC clock.
  Five times:
  ```sh
  docker compose run --rm dev sh -c 'date -u +%T.%N; PYTHONPATH=src uv run python scripts/replay_adt.py --limit 1 --rate 10; date -u +%T.%N'
  ```
  The send time lies between the two printed times (the second is within the send). Read
  `ingested_at` on the "Newest event" tile and the recording time when the tile first shows it.
- **Expect:** event → Eventhouse = `ingested_at` − send; Eventhouse → dashboard = tile time −
  `ingested_at`. Spec target p95 ≤ 10 s (reported, not gated).
- **Evidence:** `latency.csv` (run, send start, send end, ingested_at, tile time); `latency.mp4` or
  five frames `latency-1.png` … `latency-5.png`.
- **Cost / time:** $0 / 20 min.

## 10. Alert

- **Who:** owner.
- **Do:** if no ward is above 0.90 after the replay, push one over in `kqldb_beds`:
  ```kusto
  .set-or-replace bed <|
    let w = toscalar(ward_occupancy() | top 1 by occupancy | project ward_id);
    bed
    | join kind = leftouter (bed_current() | project bed_id, occupied) on bed_id
    | where not(ward_id == w and occupied != true)
    | project clinic_id, clinic_name, ward_id, ward_name, bed_id
  ```
  Wait up to 2 minutes (the rule polls every 60 s). Then restore the beds: Test → `nb_bed_reference`
  → **Run all**. Then `act_ward_occupancy` → **Stop** the rule (polling keeps the Eventhouse
  active).
- **Expect:** a post in Teams `clinic-chain` / `bed-alerts` naming the ward; the Activator history
  shows one firing on the crossing.
- **Evidence:** `teams-alert.png`, `activator-history.png`.
- **Cost / time:** $0 / 20 min.

## 11. Direct Lake fallback experiment (ADR 0005, AC10)

The production model is Direct Lake on OneLake, which never falls back. The experiment builds a
throwaway Direct Lake on SQL model and gives the Warehouse a SQL RLS policy, a documented cause of
fallback to DirectQuery.

- **Who:** owner; agent writes up the cause.
- **Do:**
  1. `wh_gold` → New SQL query:
     ```sql
     CREATE SCHEMA probe;
     GO
     CREATE FUNCTION probe.boston_only(@clinic_id varchar(50))
     RETURNS TABLE WITH SCHEMABINDING
     AS RETURN SELECT 1 AS allowed WHERE @clinic_id = 'boston';
     GO
     CREATE SECURITY POLICY probe.fallback_probe
     ADD FILTER PREDICATE probe.boston_only(clinic_id) ON gold.fact_stay
     WITH (STATE = ON);
     ```
  2. `wh_gold` ribbon → **New semantic model** `sm_fallback_probe` with `gold.fact_stay` and
     `gold.dim_clinic` (Direct Lake on SQL, behaviour Automatic). Create a report with one table
     visual: `dim_clinic[clinic_id]`, count of `fact_stay[stay_id]`.
  3. Edit the report → **View** → **Performance analyzer** → **Start recording** → **Refresh
     visuals**; expand the visual's row.
  4. If the model settings offer **Direct Lake behavior**, set **Direct Lake only**, refresh: the
     visual errors, which pins the cause on the policy.
  5. Clean up: `DROP SECURITY POLICY probe.fallback_probe; DROP FUNCTION probe.boston_only;
     DROP SCHEMA probe;`, delete `sm_fallback_probe` and its report.
  6. Main model: ADR 0005 steps 1–2 run in step 12; steps 3–5 only if the main model fails.
- **Expect:** Performance Analyzer shows a **DirectQuery** line for the visual; only `boston` rows
  are counted (RLS applied by SQL). Without the policy (after step 5) the main model is unaffected.
- **Evidence:** `fallback-perf-analyzer.png`, `fallback-directlakeonly-error.png` (if step 4 is
  possible), `fallback.md` (agent: cause, setting, observation).
- **Cost / time:** $0 / 40 min.

## 12. RLS and PHI checks (AC9)

Group and role changes take minutes to an hour (ADR 0005). Do item 1 (grants) first and come back.

- **Who:** owner signs in as each test user (private windows); agent checks results.
- **Do:**
  1. **Grants** (as admin): `wh_gold` → Share → `analyst` and `phi.reader`: Read only (no ReadData,
     no ReadAll). `lh_silver` → Share → `analyst` and `phi.reader`: Read + ReadAll.
     `sm_clinic_chain` → Security → role `clinic` → add `clinic_chain_clinic_users`. Share
     `rpt_clinic_chain` with `clinic.boston` (Read).
  2. **SQL masks and CLS** — as `analyst`, in `wh_gold`:
     ```sql
     SELECT TOP 5 master_patient_id, sex, home_clinic_id FROM gold.dim_patient;  -- works
     SELECT TOP 5 given_name FROM gold.dim_patient;                           -- denied
     ```
     As `phi.reader`: `SELECT TOP 5 given_name, birth_date, phone FROM gold.dim_patient;` → clear.
  3. **OneLake security** — as `analyst`, a notebook in a workspace of their own (or the OneLake
     file explorer), with `lh_silver` added:
     `spark.read.table("lh_silver.encounter").count()` works;
     `spark.read.table("lh_silver.patient_record").count()` fails with access denied. As
     `phi.reader` both work.
  4. **Model RLS** — as `clinic.boston`, open `rpt_clinic_chain`: only Boston. Compare
     `readmission_30d_rate` with `gold.metric_summary` for `boston`.
  5. **Redeploy keeps the member:** re-run the deploy workflow with `target=Test`; the role
     `clinic` still lists the group.
- **Expect:** each line as commented above.
- **Evidence:** `phi-analyst-masked.png`, `phi-analyst-denied.png`, `phi-reader-clear.png`,
  `onelake-analyst-denied.png`, `onelake-phireader-ok.png`, `rls-clinic-boston.png`,
  `rls-role-after-redeploy.png`.
- **Cost / time:** $0 / 45 min.

## 13. Capacity smoothing and throttling (AC11)

- **Who:** owner.
- **Do:**
  1. Fabric → **Apps** → **Get apps** → "Microsoft Fabric Capacity Metrics" → install, connect to
     the trial capacity.
  2. If the trial is F64, lower it to F4 (Govern → Capacities → Trial → **Change size**) so the
     workload can exceed it.
  3. Workload: run `pl_land_sources` again (background) and, at the same time, a notebook in Test
     with this cell for 15 minutes (interactive DAX):
     ```python
     import sempy.fabric as fabric, time

     q = """EVALUATE ADDCOLUMNS(CROSSJOIN(VALUES(dim_date[calendar_date]), VALUES(dim_bed[bed_id])),
            "occ", [occupancy_rate], "alos", [alos_days], "turn", [bed_turnover_per_year])"""
     end = time.time() + 15 * 60
     while time.time() < end:
         fabric.evaluate_dax("sm_clinic_chain", q)
     ```
  4. Wait 15–30 minutes for the app to refresh. Open **Compute**: utilization over 100% with
     smoothing; **Throttling**: interactive delay, interactive rejection and background rejection
     percentages; the timepoint drill-through for the peak.
- **Expect:** smoothing visible (background spread over 24 h, interactive over 5 min). Throttling
  shows if interactive delay passes 100%; if it stays below, record the peak percentage as the
  observation. Both outcomes satisfy "observed and recorded".
- **Evidence:** `capacity-compute.png`, `capacity-throttling.png`, `capacity-timepoint.png`,
  `capacity.md` (agent: what the numbers mean).
- **Cost / time:** $0 / 60 min, mostly waiting.

## 14. F2 apply and destroy — 💲 ⏱️ $10.56/day, same sitting

- **Who:** owner.
- **Do:** in the infra shell, write down the time, then:
  ```sh
  az rest --method get --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/providers/Microsoft.Fabric/locations/westeurope/usages?api-version=2023-11-01"
  terraform apply -var enable_f2=true        # quota must leave ≥ 2 CU
  terraform output f2_capacity_id
  ```
  Portal → the F2 → screenshot. Fabric admin portal → Capacity settings → the F2 → **Capacity
  overage**: leave it off (or turn it off). Then at once:
  ```sh
  terraform apply -var enable_f2=false
  az resource list --resource-type Microsoft.Fabric/capacities -o table   # must be empty
  ```
- **Expect:** the F2 exists for about 15 minutes, is assigned to no workspace, and is gone.
- **Evidence:** `f2-created.png`, `f2-destroy.txt` (apply output and the empty listing, with the
  two times).
- **Cost / time:** ~$0.11 / 20 min.
- **If the apply fails** on quota or on the free subscription: request quota (portal → Quotas →
  Microsoft Fabric), or record the error as the evidence and stop. Do not upgrade to pay-as-you-go
  just for this without deciding on the budget first.

## 15. Screenshots for the README

- **Who:** owner takes them; agent places them in the README (U21).
- **Do:** with the data still loaded: `readme-architecture-workspace.png` (Test workspace item
  list), `readme-report.png`, `readme-live-map.png`, `readme-teams-alert.png`,
  `readme-pipeline.png`. Most exist from earlier steps: copy them under these names.
- **Evidence:** the files above in `docs/evidence/cloud-run/`.
- **Cost / time:** $0 / 30 min.

## 16. Full teardown ⏱️

Run in this order, in the same sitting as step 14.

- **Who:** owner.
- **Do:**
  1. Activator rule stopped (step 10). Delete `es_adt` (Eventstream is not in Terraform).
  2. Infra shell: `terraform destroy` (workspaces with every item, Azure sources, roles, pipeline).
  3. `az resource list -o table` → empty. `az group list -o table` → no `rg-clinic-chain-*`.
  4. Fabric → Account manager → **Cancel trial** (or Govern → Capacities → Trials → cog → Cancel).
  5. Fabric → Manage connections: delete the SQL, Blob and GitHub connections. GitHub → delete the
     fine-grained token.
  6. Entra: `az ad app delete --id "$APP_ID"`; delete the four groups; admin center → delete the
     three test users.
  7. GitHub → delete environments `Test` and `Prod`.
  8. `az logout`; `exit`; on the host from the repository root:
     `docker volume rm "$(basename "$PWD")_azure-config"`.
  9. Azure portal → **Subscriptions** → the subscription → **Cancel subscription** (nothing can
     renew or be upgraded by mistake).
- **Expect:** no resource, no workspace, no capacity, no app, no trial.
- **Evidence:** `teardown-resources.txt` (`az resource list` and `az group list` output, empty),
  `fabric-trial-cancelled.png`, `azure-subscription-cancelled.png`.
- **Cost / time:** $0 / 30 min.

## 17. Cost check

- **Who:** owner; agent records.
- **Do:** Azure portal → **Cost Management** → **Cost analysis**, scope the subscription, range from
  sign-up to today, group by meter. **Cost Management + Billing** → **Azure credits**: credit used.
  Repeat two days later (cost data lags).
- **Expect:** total ≤ $10 (target ≈ $0.20 of credit, $0 cash); meters only Fabric capacity (F2),
  Storage, SQL Database (free offer, $0).
- **Evidence:** `cost-analysis-day0.png`, `cost-analysis-day2.png`, `azure-credits.png`.
- **Cost / time:** $0 / 10 min + 10 min after two days.

## 18. Microsoft 365 recurring billing — confirm off ⏱️

- **Who:** owner.
- **Do:** admin center → **Billing** → **Your products** → Business Basic. Confirm recurring billing
  is **Off** and the expiry date is within the 30 days. **Bills & payments** shows no invoice.
  The trial then expires by itself; the tenant goes with it.
- **Evidence:** `m365-recurring-billing-final.png`.
- **Cost / time:** $0 / 5 min.

---

## Budget threats

- **F2 left running:** $10.56 per day. Step 14 applies and destroys in one go; step 16 checks
  `az resource list`. The $5 budget alert is the backstop.
- **Microsoft 365 renewal:** the trial converts to an annual paid term unless recurring billing is
  off (step 1.2, confirmed in step 18).
- **No Fabric trial for the tenant:** trials per tenant are limited and "not guaranteed". Without
  one, the run needs an F2 for every sitting: about $0.44/h, ~$4 for two 4.5-hour sittings if paused
  between them, plus Power BI Pro for every viewer on F2. Decide before continuing.
- **Free credit and the Fabric meter:** Microsoft does not state that the $200 credit covers
  Fabric capacity. If it does not, the F2 step fails on the free subscription; upgrading to
  pay-as-you-go removes the spending protection.
- **Capacity overage:** on by default for new F capacities, at three times the rate. Harmless here
  because the F2 hosts no workspace; never assign a workspace to it.
- **Azure SQL:** `BillOverUsage` cannot be switched back; keep `AutoPause`.
- **Monday's project:** the Azure free account is one per customer, and this tenant is a throwaway
  trial tenant. Do not reuse it for long-lived work.
