-- Fabric only: the Warehouse reads Silver through views over the lh_silver SQL analytics
-- endpoint (three-part names within one workspace). Locally scripts/gold.py loads tables with
-- these names.

IF SCHEMA_ID('silver') IS NULL EXEC ('CREATE SCHEMA silver');
GO

CREATE OR ALTER VIEW silver.patient_record AS
SELECT * FROM lh_silver.dbo.patient_record;  -- noqa: AM04
GO

CREATE OR ALTER VIEW silver.patient_xref AS
SELECT * FROM lh_silver.dbo.patient_xref;  -- noqa: AM04
GO

CREATE OR ALTER VIEW silver.encounter AS
SELECT * FROM lh_silver.dbo.encounter;  -- noqa: AM04
GO

CREATE OR ALTER VIEW silver.condition AS
SELECT * FROM lh_silver.dbo.condition;  -- noqa: AM04
GO

CREATE OR ALTER VIEW silver.claim AS
SELECT * FROM lh_silver.dbo.claim;  -- noqa: AM04
GO

CREATE OR ALTER VIEW silver.lab_result AS
SELECT * FROM lh_silver.dbo.lab_result;  -- noqa: AM04
GO

CREATE OR ALTER VIEW silver.adt_event AS
SELECT * FROM lh_silver.dbo.adt_event;  -- noqa: AM04
GO

CREATE OR ALTER VIEW silver.ed_visit AS
SELECT * FROM lh_silver.dbo.ed_visit;  -- noqa: AM04
GO

CREATE OR ALTER VIEW silver.bed AS
SELECT * FROM lh_silver.dbo.bed;  -- noqa: AM04
GO
