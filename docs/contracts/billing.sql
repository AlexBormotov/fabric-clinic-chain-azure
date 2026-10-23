-- Billing source schema (SQL Server). Kept in step with billing.yaml by tests/test_sources.py.
CREATE SCHEMA billing;
GO

CREATE TABLE billing.patient_account (
    account_id varchar(16) NOT NULL PRIMARY KEY,
    clinic_id varchar(16) NOT NULL,
    given_name nvarchar(100) NOT NULL,
    family_name nvarchar(100) NOT NULL,
    birth_date date NOT NULL,
    sex char(1) NOT NULL,
    phone varchar(32) NULL,
    postal_code varchar(10) NULL
);

CREATE TABLE billing.claim (
    claim_id varchar(16) NOT NULL PRIMARY KEY,
    account_id varchar(16) NOT NULL REFERENCES billing.patient_account (account_id),
    clinic_id varchar(16) NOT NULL,
    claim_type varchar(16) NOT NULL,
    payer nvarchar(100) NOT NULL,
    service_start datetime2(0) NOT NULL,
    service_end datetime2(0) NOT NULL,
    billed_amount decimal(12, 2) NOT NULL,
    paid_amount decimal(12, 2) NOT NULL,
    status varchar(8) NOT NULL,
    denial_reason nvarchar(100) NULL
);

CREATE TABLE billing.claim_line (
    claim_id varchar(16) NOT NULL REFERENCES billing.claim (claim_id),
    line_no int NOT NULL,
    service_code varchar(32) NOT NULL,
    service_name nvarchar(400) NOT NULL,
    amount decimal(12, 2) NOT NULL,
    PRIMARY KEY (claim_id, line_no)
);
