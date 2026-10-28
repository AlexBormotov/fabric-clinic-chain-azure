-- Users and the clinics they may see, read by the semantic model's RLS role `clinic` (U10).
-- Created once and never dropped or reloaded: rows are maintained per environment (U17) and are
-- never committed.

IF OBJECT_ID('gold.user_clinic') IS NULL
    CREATE TABLE gold.user_clinic (
        user_principal_name varchar(320) NOT NULL,
        clinic_id varchar(50) NOT NULL
    );
