# Todo

Owner follow-ups. Steps refer to [`docs/runbook-cloud.md`](../docs/runbook-cloud.md).

- [ ] After the last unit lands: add the CI jobs `synth` and `stand` to the required status checks
  on `main` (owner decision 2026-10-23; kept optional while units are in development to keep PRs
  fast).
- [ ] Review the metric definitions in `GLOSSARY.md` (U09; spec open point 3).
- [ ] Open `fabric/rpt_clinic_chain.Report/definition.pbir` in Power BI Desktop once and check the
  three pages render against the model (U10).
- [ ] U19 one-time setup, during the cloud run: federated credentials (step 2.2), Fabric admin
  setting for service principals (step 5.1), Fabric connections (step 5.2), GitHub environments and
  variables including `ALERT_TEAMS_RECIPIENT` from U14 (step 3).
- [ ] Run `make republish ENVIRONMENT=<env>` after every deploy that changes `df_sharepoint`
  (step 6).
- [ ] Switch `act_ward_occupancy` to a Teams channel post in the UI after each first deploy (U14,
  step 6).
- [ ] Run the cloud run (U20) and fill `docs/evidence/cloud-run.md`; then U21 (README screenshots
  and results).
