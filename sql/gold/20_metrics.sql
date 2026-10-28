-- The eight metrics of AC3 over the whole window, per clinic and for the chain (scope 'ALL').
-- Definitions: GLOSSARY.md. Each fact row is counted for its clinic and for 'ALL' via CROSS APPLY.
-- A test compares these views with docs/evidence/metric-reference.json, computed independently.

CREATE OR ALTER VIEW gold.metric_summary AS
WITH period AS (
    SELECT
        COUNT(*) AS window_days,
        DATEADD(DAY, 1, CAST(MAX(calendar_date) AS datetime2(6))) AS window_stop
    FROM gold.dim_date
),

beds AS (
    SELECT
        s.scope,
        COUNT(*) AS beds
    FROM gold.dim_bed AS b
    CROSS APPLY (VALUES (b.clinic_id), ('ALL')) AS s(scope)
    GROUP BY s.scope
),

occupancy AS (
    SELECT
        s.scope,
        SUM(CAST(f.occupied_hours AS float)) AS bed_hours
    FROM gold.fact_bed_day AS f
    CROSS APPLY (VALUES (f.clinic_id), ('ALL')) AS s(scope)
    GROUP BY s.scope
),

discharged AS (
    SELECT
        s.scope,
        COUNT(*) AS discharges,
        AVG(CAST(f.length_of_stay_days AS float)) AS alos_days
    FROM gold.fact_stay AS f
    CROSS JOIN period AS p
    CROSS APPLY (VALUES (f.clinic_id), ('ALL')) AS s(scope)
    WHERE f.discharged_at < p.window_stop
    GROUP BY s.scope
),

index_stay AS (
    SELECT
        f.clinic_id,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM gold.fact_stay AS n
                WHERE
                    n.master_patient_id = f.master_patient_id
                    AND n.admitted_at > f.discharged_at
                    AND n.admitted_at <= DATEADD(DAY, 30, f.discharged_at)
            ) THEN CAST(1 AS float)
            ELSE CAST(0 AS float)
        END AS readmitted
    FROM gold.fact_stay AS f
    CROSS JOIN period AS p
    WHERE f.discharged_at < DATEADD(DAY, -30, p.window_stop)
),

readmission AS (
    SELECT
        s.scope,
        AVG(i.readmitted) AS readmission_30d_rate
    FROM index_stay AS i
    CROSS APPLY (VALUES (i.clinic_id), ('ALL')) AS s(scope)
    GROUP BY s.scope
),

ed_wait AS (
    SELECT DISTINCT
        s.scope,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.minutes_to_provider)
        OVER (PARTITION BY s.scope) AS ed_wait_median_minutes
    FROM gold.fact_ed_visit AS f
    CROSS APPLY (VALUES (f.clinic_id), ('ALL')) AS s(scope)
),

claims AS (
    SELECT
        s.scope,
        SUM(CAST(f.paid_amount AS float)) AS paid,
        AVG(CASE WHEN f.status = 'denied' THEN CAST(1 AS float) ELSE 0 END) AS claim_denial_rate
    FROM gold.fact_claim AS f
    CROSS APPLY (VALUES (f.clinic_id), ('ALL')) AS s(scope)
    GROUP BY s.scope
)

SELECT
    b.scope,
    b.beds,
    d.alos_days,
    r.readmission_30d_rate,
    e.ed_wait_median_minutes,
    c.claim_denial_rate,
    o.bed_hours / (b.beds * 24.0 * p.window_days) AS occupancy_rate,
    d.discharges / (b.beds * (p.window_days / 365.0)) AS bed_turnover_per_year,
    c.paid / (b.beds * (p.window_days / 365.0)) AS revenue_per_bed_per_year
FROM beds AS b
CROSS JOIN period AS p
LEFT JOIN occupancy AS o ON b.scope = o.scope
LEFT JOIN discharged AS d ON b.scope = d.scope
LEFT JOIN readmission AS r ON b.scope = r.scope
LEFT JOIN ed_wait AS e ON b.scope = e.scope
LEFT JOIN claims AS c ON b.scope = c.scope;
GO

CREATE OR ALTER VIEW gold.metric_payer_mix AS
SELECT
    s.scope,
    f.payer,
    CAST(COUNT(*) AS float) / SUM(COUNT(*)) OVER (PARTITION BY s.scope) AS claim_share
FROM gold.fact_claim AS f
CROSS APPLY (VALUES (f.clinic_id), ('ALL')) AS s(scope)
GROUP BY s.scope, f.payer;
