-- PHI protection for SQL readers of Gold (AC9). Runs on Fabric Data Warehouse and on SQL Server.
-- Masks are declared on the columns in 00_tables.sql. Two roles:
--   gold_reader      reads Gold with PHI masked; phone is denied (column-level security);
--   gold_phi_reader  reads Gold in clear.
-- DENY outranks GRANT, so a member of both roles still loses phone: keep the roles exclusive.
-- Workspace Admin, Member and Contributor hold CONTROL and bypass both; readers get item Read
-- only. Role membership is Fabric only (sql/fabric/security_members.sql).

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
DENY SELECT (phone) ON gold.dim_patient TO gold_reader;
GRANT UNMASK ON gold.dim_patient TO gold_phi_reader;
