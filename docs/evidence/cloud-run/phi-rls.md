# PHI protection and clinic RLS (AC9, runbook step 12)

Run on 2026-11-27 in the Test workspace.

## Grants (12.1)

- `wh_gold`: `analyst` and `phi.reader` hold Read only, with no ReadData and no ReadAll.
  `SubscribeOneLakeEvents` is added by the share dialog.
- `lh_silver`: `analyst` and `phi.reader` hold Read and ReadAll.
- `sm_clinic_chain`: the role `clinic` has the member `clinic_chain_clinic_users`.
- `rpt_clinic_chain` is shared with `clinic.boston`.
- SQL roles:
  - `gold_reader` has the member `clinic_chain_analysts`. It holds `DENY SELECT` on
    `dim_patient.given_name`, `family_name`, `birth_date`, `phone` and `postal_code`.
  - `gold_phi_reader` has the member `clinic_chain_phi_readers`. It holds `UNMASK` on
    `dim_patient`.

## SQL masks and CLS (12.2)

- `analyst`, `SELECT TOP 5 master_patient_id, sex, home_clinic_id FROM gold.dim_patient`:
  rows returned (`phi-analyst-masked.png`).
- `analyst`, `SELECT TOP 5 given_name FROM gold.dim_patient`:
  `Msg 230 ... The SELECT permission was denied on the column 'given_name' of the object
  'dim_patient'` (`phi-analyst-denied.png`).
- `phi.reader`, `SELECT TOP 5 given_name, birth_date, phone FROM gold.dim_patient`: values in
  clear (`phi-reader-clear.png`).

## OneLake (12.3)

Not run. The test users have no workspace on a capacity, so they cannot run a Spark notebook.

## Model RLS (12.4)

The first attempt as `clinic.boston` failed with `Missing_References`
(`rls-boston-missing-references.png`). The cause was that the model still used the default SSO,
so the report user needed access to `wh_gold`. Step 7.3, the fixed identity, had been skipped.

The fix was made in three steps:

1. Ownership of `sm_clinic_chain` was taken over from the deployer service principal (`TakeOver`).
   Only the owner can bind connections.
2. Workspace identity was tried and failed with `Premium_ASWL_Error`, because the workspace has no
   identity.
3. A cloud connection `cn_sm_clinic_chain_one_lake` was bound, using OAuth 2.0 as the owner with
   SSO off. This is the fallback that ADR 0005 allows.

After the fix:

- `clinic.boston` sees only Boston Clinic (`rls-clinic-boston.png`).
- DAX `SUMMARIZECOLUMNS(dim_clinic[clinic_id], "readmission_30d_rate", [readmission_30d_rate])`
  gives:
  - as the owner: boston 0.10190664036817883, springfield 0.10443037974683544, worcester
    0.10197044334975369;
  - as `clinic.boston` (`impersonatedUserName`): one row, boston 0.10190664036817883, equal to
    `gold.metric_summary`.

## 12.5 Redeploy and the role member

The Prod deploy run 46055987161 also redeployed Test. Afterwards:

1. The owner's DAX still returned three clinics; the `clinic.boston` query failed with
   AnalysisServicesErrorCode 3242524690. The deployed role has no member (ADR 0005 assigns it
   after deploy); this was read as the redeploy removing `clinic_chain_clinic_users`.
2. The owner re-added the group in **Security** (`rls-role-readded.png`). The save triggered a
   refresh at 19:02 UTC that failed with `Premium_ASWL_Error`: the model was bound to
   `cn_sm_clinic_chain_onelake`, an earlier workspace-identity connection with the same OneLake
   path. Every query, the owner's included, then failed.
3. `POST v1/workspaces/{ws}/semanticModels/{id}/bindConnection` to `cn_sm_clinic_chain_one_lake`
   (OAuth 2.0) returned HTTP 200. Both DAX results above came back unchanged.

First reading (2026-11-27), corrected below: a redeploy does not keep the role member.

Correction (2026-11-28). Test redeploy run 46153994863, then only the take-over and
`bindConnection` to `cn_sm_clinic_chain_one_lake`, with no change to **Security**: as the owner,
three clinics; as `clinic.boston`, one row, boston 0.10190664036817883. The redeploy keeps the
role member. It resets the model's connection binding: the owner, a workspace admin, still reads
through SSO, while every other user fails. That explains step 1 above; the re-add in step 2 was not
needed. The workspace-identity connection `cn_sm_clinic_chain_onelake` has been deleted.

Result: after each deploy, take the model over and bind the OAuth 2.0 connection. The role member
stays.
