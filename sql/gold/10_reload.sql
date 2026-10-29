-- Full reload of Gold from the `silver` schema: views over lh_silver in Fabric
-- (sql/fabric/silver_views.sql), tables copied from Delta locally (scripts/gold.py).
-- Facts keep the analytical window only; every fact row carries the master patient from
-- silver.patient_xref.

CREATE OR ALTER PROCEDURE gold.reload
    @window_start date = '2024-10-01',
    @window_end date = '2026-09-30'
AS
BEGIN
    DECLARE @window_stop datetime2(6) = DATEADD(DAY, 1, CAST(@window_end AS datetime2(6)));

    TRUNCATE TABLE gold.dim_date;
    WITH digit AS (
        SELECT v FROM (VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9)) AS d(v)
    ),

    day_offset AS (
        SELECT a.v + 10 * b.v + 100 * c.v + 1000 * e.v AS day_number
        FROM digit AS a
        CROSS JOIN digit AS b
        CROSS JOIN digit AS c
        CROSS JOIN digit AS e
    ),

    calendar AS (
        SELECT DATEADD(DAY, day_number, @window_start) AS calendar_date
        FROM day_offset
        WHERE day_number <= DATEDIFF(DAY, @window_start, @window_end)
    )

    INSERT INTO gold.dim_date
    SELECT
        YEAR(calendar_date) * 10000 + MONTH(calendar_date) * 100 + DAY(calendar_date) AS date_key,
        calendar_date,
        YEAR(calendar_date) AS calendar_year,
        MONTH(calendar_date) AS calendar_month,
        DATEFROMPARTS(YEAR(calendar_date), MONTH(calendar_date), 1) AS month_start,
        -- ISO weekday, independent of SET DATEFIRST: 1 = Monday.
        (DATEDIFF(DAY, '19000101', calendar_date) % 7) + 1 AS day_of_week,
        CASE WHEN DATEDIFF(DAY, '19000101', calendar_date) % 7 >= 5 THEN 1 ELSE 0 END AS is_weekend
    FROM calendar;

    TRUNCATE TABLE gold.dim_clinic;
    INSERT INTO gold.dim_clinic
    SELECT DISTINCT
        clinic_id,
        clinic_name
    FROM silver.bed;

    TRUNCATE TABLE gold.dim_ward;
    INSERT INTO gold.dim_ward
    SELECT
        CONCAT(clinic_id, '|', ward_id) AS ward_key,
        clinic_id,
        ward_id,
        MIN(ward_name) AS ward_name,
        COUNT(*) AS beds
    FROM silver.bed
    GROUP BY clinic_id, ward_id;

    TRUNCATE TABLE gold.dim_bed;
    INSERT INTO gold.dim_bed
    SELECT
        bed_id,
        CONCAT(clinic_id, '|', ward_id) AS ward_key,
        clinic_id
    FROM silver.bed;

    -- Demographics of each master patient come from its preferred record:
    -- EHR, then billing, ADT, lab.
    TRUNCATE TABLE gold.dim_patient;
    WITH ranked AS (
        SELECT
            x.master_patient_id,
            p.given_name,
            p.family_name,
            p.birth_date,
            p.sex,
            p.phone,
            p.postal_code,
            p.clinic_id,
            COUNT(*) OVER (PARTITION BY x.master_patient_id) AS source_records,
            ROW_NUMBER() OVER (
                PARTITION BY x.master_patient_id
                ORDER BY
                    CASE p.system
                        WHEN 'ehr' THEN 1 WHEN 'billing' THEN 2 WHEN 'adt' THEN 3 ELSE 4
                    END,
                    p.local_patient_id
            ) AS preference
        FROM silver.patient_xref AS x
        INNER JOIN silver.patient_record AS p
            ON x.system = p.system AND x.local_patient_id = p.local_patient_id
    )

    INSERT INTO gold.dim_patient
    SELECT
        master_patient_id,
        given_name,
        family_name,
        birth_date,
        sex,
        phone,
        postal_code,
        clinic_id,
        source_records
    FROM ranked
    WHERE preference = 1;

    TRUNCATE TABLE gold.dim_payer;
    INSERT INTO gold.dim_payer
    SELECT DISTINCT payer FROM silver.claim;

    TRUNCATE TABLE gold.dim_diagnosis;
    INSERT INTO gold.dim_diagnosis
    SELECT
        code AS diagnosis_code,
        MIN(display) AS diagnosis_name
    FROM silver.condition
    GROUP BY code;

    -- The encounter's diagnosis is its earliest recorded condition.
    TRUNCATE TABLE gold.fact_encounter;
    WITH diagnosis AS (
        SELECT
            encounter_id,
            code,
            ROW_NUMBER() OVER (PARTITION BY encounter_id ORDER BY onset_at, condition_id) AS rn
        FROM silver.condition
        WHERE encounter_id IS NOT NULL
    )

    INSERT INTO gold.fact_encounter
    SELECT
        e.encounter_id,
        x.master_patient_id,
        e.clinic_id,
        YEAR(e.start_at) * 10000 + MONTH(e.start_at) * 100 + DAY(e.start_at) AS start_date_key,
        e.start_at,
        e.end_at,
        e.class_code,
        e.type_code,
        e.type_display AS type_name,
        d.code AS diagnosis_code,
        CAST(DATEDIFF(SECOND, e.start_at, e.end_at) / 3600.0 AS decimal(12, 2))
            AS length_of_stay_hours
    FROM silver.encounter AS e
    INNER JOIN silver.patient_xref AS x
        ON x.system = 'ehr' AND e.fhir_patient_id = x.local_patient_id
    LEFT JOIN diagnosis AS d ON e.encounter_id = d.encounter_id AND d.rn = 1
    WHERE e.start_at >= @window_start AND e.start_at < @window_stop;

    TRUNCATE TABLE gold.fact_stay;
    WITH admission AS (
        SELECT
            stay_id,
            clinic_id,
            adt_patient_id,
            event_time
        FROM silver.adt_event
        WHERE event_type = 'A01'
    ),

    discharge AS (
        SELECT
            stay_id,
            event_time
        FROM silver.adt_event
        WHERE event_type = 'A03'
    ),

    stay AS (
        SELECT
            a.stay_id,
            x.master_patient_id,
            a.clinic_id,
            a.event_time AS admitted_at,
            d.event_time AS discharged_at
        FROM admission AS a
        INNER JOIN silver.patient_xref AS x
            ON x.system = 'adt' AND a.adt_patient_id = x.local_patient_id
        LEFT JOIN discharge AS d ON a.stay_id = d.stay_id
        WHERE a.event_time >= @window_start AND a.event_time < @window_stop
    )

    -- readmitted_30d looks at every stay of the window, at any clinic (GLOSSARY.md).
    INSERT INTO gold.fact_stay
    SELECT
        s.stay_id,
        s.master_patient_id,
        s.clinic_id,
        YEAR(s.admitted_at) * 10000 + MONTH(s.admitted_at) * 100 + DAY(s.admitted_at)
            AS admit_date_key,
        s.admitted_at,
        s.discharged_at,
        CAST(DATEDIFF(SECOND, s.admitted_at, s.discharged_at) / 86400.0 AS decimal(12, 6))
            AS length_of_stay_days,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM stay AS n
                WHERE
                    n.master_patient_id = s.master_patient_id
                    AND n.admitted_at > s.discharged_at
                    AND n.admitted_at <= DATEADD(DAY, 30, s.discharged_at)
            ) THEN CAST(1 AS bit)
            ELSE CAST(0 AS bit)
        END AS readmitted_30d
    FROM stay AS s;

    -- A01 and A02 start a segment in a bed; the stay's next event ends it. Open stays end at the
    -- window's end. Each segment is cut at midnights into calendar days.
    TRUNCATE TABLE gold.fact_bed_day;
    WITH segment AS (
        SELECT
            stay_id,
            event_type,
            clinic_id,
            ward_id,
            bed_id,
            adt_patient_id,
            event_time AS segment_start,
            LEAD(event_time) OVER (
                PARTITION BY stay_id ORDER BY event_time, event_id
            ) AS segment_end
        FROM silver.adt_event
    ),

    bounded AS (
        SELECT
            *,
            COALESCE(segment_end, @window_stop) AS segment_stop
        FROM segment
        WHERE event_type IN ('A01', 'A02')
    ),

    split AS (
        SELECT
            b.stay_id,
            b.segment_start,
            d.date_key,
            b.adt_patient_id,
            b.clinic_id,
            b.ward_id,
            b.bed_id,
            CASE WHEN b.segment_end IS NULL THEN 1 ELSE 0 END AS is_open_stay,
            DATEDIFF(
                SECOND,
                GREATEST(b.segment_start, CAST(d.calendar_date AS datetime2(6))),
                LEAST(b.segment_stop, DATEADD(DAY, 1, CAST(d.calendar_date AS datetime2(6))))
            ) AS occupied_seconds
        FROM bounded AS b
        INNER JOIN gold.dim_date AS d
            ON
                d.calendar_date >= CAST(b.segment_start AS date)
                AND d.calendar_date <= CAST(b.segment_stop AS date)
    )

    INSERT INTO gold.fact_bed_day
    SELECT
        s.stay_id,
        s.segment_start,
        s.date_key,
        x.master_patient_id,
        s.clinic_id,
        CONCAT(s.clinic_id, '|', s.ward_id) AS ward_key,
        s.bed_id,
        CAST(s.occupied_seconds / 3600.0 AS decimal(12, 6)) AS occupied_hours,
        s.is_open_stay
    FROM split AS s
    INNER JOIN silver.patient_xref AS x
        ON x.system = 'adt' AND s.adt_patient_id = x.local_patient_id
    WHERE s.occupied_seconds > 0;

    TRUNCATE TABLE gold.fact_claim;
    INSERT INTO gold.fact_claim
    SELECT
        c.claim_id,
        x.master_patient_id,
        c.clinic_id,
        c.payer,
        c.claim_type,
        YEAR(c.service_start) * 10000 + MONTH(c.service_start) * 100 + DAY(c.service_start)
            AS service_date_key,
        c.service_start,
        c.service_end,
        c.billed_amount,
        c.paid_amount,
        c.status,
        c.denial_reason
    FROM silver.claim AS c
    INNER JOIN silver.patient_xref AS x
        ON x.system = 'billing' AND c.account_id = x.local_patient_id
    WHERE c.service_start >= @window_start AND c.service_start < @window_stop;

    TRUNCATE TABLE gold.fact_lab_result;
    INSERT INTO gold.fact_lab_result
    SELECT
        r.result_id,
        x.master_patient_id,
        r.clinic_id,
        YEAR(r.collected_at) * 10000 + MONTH(r.collected_at) * 100 + DAY(r.collected_at)
            AS collected_date_key,
        r.collected_at,
        r.loinc_code,
        r.test_name,
        r.value_numeric,
        r.value_text,
        r.unit
    FROM silver.lab_result AS r
    INNER JOIN silver.patient_xref AS x
        ON x.system = 'lab' AND r.lab_patient_id = x.local_patient_id
    WHERE r.collected_at >= @window_start AND r.collected_at < @window_stop;

    TRUNCATE TABLE gold.fact_ed_visit;
    INSERT INTO gold.fact_ed_visit
    SELECT
        v.ed_visit_id,
        x.master_patient_id,
        v.clinic_id,
        YEAR(v.arrival_at) * 10000 + MONTH(v.arrival_at) * 100 + DAY(v.arrival_at)
            AS arrival_date_key,
        v.arrival_at,
        DATEDIFF(MINUTE, v.arrival_at, v.triage_at) AS minutes_to_triage,
        DATEDIFF(MINUTE, v.arrival_at, v.provider_seen_at) AS minutes_to_provider,
        DATEDIFF(MINUTE, v.arrival_at, v.departure_at) AS length_of_stay_minutes,
        v.disposition,
        CASE WHEN v.disposition = 'admitted' THEN 1 ELSE 0 END AS is_admitted,
        v.stay_id
    FROM silver.ed_visit AS v
    INNER JOIN silver.patient_xref AS x
        ON x.system = 'adt' AND v.adt_patient_id = x.local_patient_id
    WHERE v.arrival_at >= @window_start AND v.arrival_at < @window_stop;
END;
