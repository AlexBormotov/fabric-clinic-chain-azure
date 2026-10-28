-- Gold star schema. Runs unchanged on Fabric Data Warehouse and on local SQL Server 2022, so it
-- uses only types and statements both support: varchar not nvarchar, datetime2(6), no tinyint,
-- and no key constraints (Fabric accepts them only as NOT ENFORCED, which SQL Server cannot
-- parse; key uniqueness is tested instead). See docs/adr/0002-lakehouse-warehouse.md.

IF SCHEMA_ID('gold') IS NULL EXEC ('CREATE SCHEMA gold');
GO

DROP TABLE IF EXISTS gold.dim_date;
CREATE TABLE gold.dim_date (
    date_key int NOT NULL,
    calendar_date date NOT NULL,
    calendar_year smallint NOT NULL,
    calendar_month smallint NOT NULL,
    month_start date NOT NULL,
    day_of_week smallint NOT NULL,
    is_weekend bit NOT NULL
);

DROP TABLE IF EXISTS gold.dim_clinic;
CREATE TABLE gold.dim_clinic (
    clinic_id varchar(50) NOT NULL,
    clinic_name varchar(200) NOT NULL
);

DROP TABLE IF EXISTS gold.dim_ward;
CREATE TABLE gold.dim_ward (
    ward_key varchar(100) NOT NULL,
    clinic_id varchar(50) NOT NULL,
    ward_id varchar(50) NOT NULL,
    ward_name varchar(200) NOT NULL,
    beds int NOT NULL
);

DROP TABLE IF EXISTS gold.dim_bed;
CREATE TABLE gold.dim_bed (
    bed_id varchar(50) NOT NULL,
    ward_key varchar(100) NOT NULL,
    clinic_id varchar(50) NOT NULL
);

-- PHI: names, birth date, phone and postal code (masked in U16).
DROP TABLE IF EXISTS gold.dim_patient;
CREATE TABLE gold.dim_patient (
    master_patient_id varchar(32) NOT NULL,
    given_name varchar(200) NULL,
    family_name varchar(200) NULL,
    birth_date date NULL,
    sex char(1) NULL,
    phone varchar(20) NULL,
    postal_code varchar(20) NULL,
    home_clinic_id varchar(50) NULL,
    source_records int NOT NULL
);

DROP TABLE IF EXISTS gold.dim_payer;
CREATE TABLE gold.dim_payer (
    payer varchar(200) NOT NULL
);

DROP TABLE IF EXISTS gold.dim_diagnosis;
CREATE TABLE gold.dim_diagnosis (
    diagnosis_code varchar(50) NOT NULL,
    diagnosis_name varchar(500) NULL
);

DROP TABLE IF EXISTS gold.fact_encounter;
CREATE TABLE gold.fact_encounter (
    encounter_id varchar(100) NOT NULL,
    master_patient_id varchar(32) NOT NULL,
    clinic_id varchar(50) NOT NULL,
    start_date_key int NOT NULL,
    start_at datetime2(6) NOT NULL,
    end_at datetime2(6) NULL,
    class_code varchar(20) NULL,
    type_code varchar(50) NULL,
    type_name varchar(500) NULL,
    diagnosis_code varchar(50) NULL,
    length_of_stay_hours decimal(12, 2) NULL
);

-- One row per ADT stay (A01 admission to A03 discharge; discharged_at NULL while open).
DROP TABLE IF EXISTS gold.fact_stay;
CREATE TABLE gold.fact_stay (
    stay_id varchar(50) NOT NULL,
    master_patient_id varchar(32) NOT NULL,
    clinic_id varchar(50) NOT NULL,
    admit_date_key int NOT NULL,
    admitted_at datetime2(6) NOT NULL,
    discharged_at datetime2(6) NULL,
    length_of_stay_days decimal(12, 6) NULL
);

-- One row per stay segment (admission or transfer to a bed) and calendar day it covers.
DROP TABLE IF EXISTS gold.fact_bed_day;
CREATE TABLE gold.fact_bed_day (
    stay_id varchar(50) NOT NULL,
    segment_start datetime2(6) NOT NULL,
    date_key int NOT NULL,
    master_patient_id varchar(32) NOT NULL,
    clinic_id varchar(50) NOT NULL,
    ward_key varchar(100) NOT NULL,
    bed_id varchar(50) NOT NULL,
    occupied_hours decimal(12, 6) NOT NULL,
    is_open_stay bit NOT NULL
);

DROP TABLE IF EXISTS gold.fact_claim;
CREATE TABLE gold.fact_claim (
    claim_id varchar(50) NOT NULL,
    master_patient_id varchar(32) NOT NULL,
    clinic_id varchar(50) NOT NULL,
    payer varchar(200) NOT NULL,
    claim_type varchar(50) NOT NULL,
    service_date_key int NOT NULL,
    service_start datetime2(6) NOT NULL,
    service_end datetime2(6) NOT NULL,
    billed_amount decimal(12, 2) NOT NULL,
    paid_amount decimal(12, 2) NOT NULL,
    status varchar(50) NOT NULL,
    denial_reason varchar(200) NULL
);

DROP TABLE IF EXISTS gold.fact_lab_result;
CREATE TABLE gold.fact_lab_result (
    result_id varchar(50) NOT NULL,
    master_patient_id varchar(32) NOT NULL,
    clinic_id varchar(50) NOT NULL,
    collected_date_key int NOT NULL,
    collected_at datetime2(6) NOT NULL,
    loinc_code varchar(50) NOT NULL,
    test_name varchar(500) NOT NULL,
    value_numeric decimal(20, 8) NULL,
    value_text varchar(500) NULL,
    unit varchar(50) NULL
);

DROP TABLE IF EXISTS gold.fact_ed_visit;
CREATE TABLE gold.fact_ed_visit (
    ed_visit_id varchar(50) NOT NULL,
    master_patient_id varchar(32) NOT NULL,
    clinic_id varchar(50) NOT NULL,
    arrival_date_key int NOT NULL,
    arrival_at datetime2(6) NOT NULL,
    minutes_to_triage int NOT NULL,
    minutes_to_provider int NOT NULL,
    length_of_stay_minutes int NOT NULL,
    disposition varchar(50) NOT NULL,
    is_admitted bit NOT NULL,
    stay_id varchar(50) NULL
);
