-- Fabric only: Entra principals for the Gold roles (sql/gold/30_security.sql). Fabric has no
-- CREATE USER or CREATE LOGIN; the database user of an Entra identity is created by the first
-- GRANT, DENY or role membership. Run after `gold` is built, by a workspace Admin or Member.
-- The groups are Entra security groups; give their members the Warehouse item Read permission
-- only, never a workspace role above Viewer (Contributor and up hold CONTROL and see PHI) and never
-- ReadAll (Spark reads OneLake files, which DDM and CLS do not cover; see U17).

ALTER ROLE gold_reader ADD MEMBER [clinic_chain_analysts];
ALTER ROLE gold_phi_reader ADD MEMBER [clinic_chain_phi_readers];
