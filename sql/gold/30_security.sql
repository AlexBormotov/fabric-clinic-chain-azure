-- PHI protection for SQL readers of Gold (AC9). Runs on Fabric Data Warehouse and on SQL Server.
-- Masks are declared on the columns in 00_tables.sql. Two roles:
--   gold_reader      reads Gold without PHI: every PHI column is denied (column-level security);
--   gold_phi_reader  reads Gold in clear.
-- The DENY is the access control. A mask alone leaks through predicates (WHERE birth_date = ...);
-- masks protect principals outside both roles, such as a Fabric Viewer (ReadData), who can still
-- infer PHI that way: give non-PHI readers gold_reader and item Read, never Viewer.
-- DENY outranks GRANT, so a member of both roles loses PHI: keep the roles exclusive.
-- Workspace Admin, Member and Contributor hold CONTROL and bypass both.
-- Role membership is Fabric only (sql/fabric/security_members.sql).

IF
    NOT EXISTS (
        SELECT 1 FROM sys.database_principals
        WHERE name = 'gold_reader' AND type = 'R'
    )
    EXEC ('CREATE ROLE gold_reader');
IF
    NOT EXISTS (
        SELECT 1 FROM sys.database_principals
        WHERE name = 'gold_phi_reader' AND type = 'R'
    )
    EXEC ('CREATE ROLE gold_phi_reader');
GO

GRANT SELECT ON SCHEMA::gold TO gold_reader;
GRANT SELECT ON SCHEMA::gold TO gold_phi_reader;
-- 00_tables.sql recreates the table on each build, which drops object permissions; set them again.
DENY SELECT (given_name, family_name, birth_date) ON gold.dim_patient TO gold_reader;
DENY SELECT (phone, postal_code) ON gold.dim_patient TO gold_reader;
GRANT UNMASK ON gold.dim_patient TO gold_phi_reader;
