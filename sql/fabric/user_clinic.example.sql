-- Fabric only: who sees which clinic under the semantic model's RLS role `clinic` (U10, U17).
-- Copy to sql/fabric/user_clinic.sql (git-ignored), replace the placeholder UPNs with real ones,
-- and run it on wh_gold after `gold` is built. Real UPNs are never committed.
-- A user sees the union of their rows; a user without a row sees no clinic.
-- The model role `clinic` itself has one member, the Entra group of all clinic users, assigned in
-- the semantic model's Security settings (ADR 0005). Clinic users get Read on the model or the app
-- only: no workspace role, no permission on wh_gold or the lakehouses.

DELETE FROM gold.user_clinic;

INSERT INTO gold.user_clinic (user_principal_name, clinic_id)
VALUES
('boston.manager@example.com', 'boston'),
('worcester.manager@example.com', 'worcester'),
('springfield.manager@example.com', 'springfield'),
('regional.manager@example.com', 'boston'),
('regional.manager@example.com', 'worcester');
