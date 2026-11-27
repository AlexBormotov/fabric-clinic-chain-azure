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
