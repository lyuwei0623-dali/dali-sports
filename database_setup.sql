-- Execute once using the database owner's SQL console (e.g. Supabase).
-- This schema is NOT exposed via the public REST API. No anonymous grants.
CREATE SCHEMA IF NOT EXISTS dali_private;
REVOKE ALL ON SCHEMA dali_private FROM PUBLIC;
CREATE TABLE IF NOT EXISTS dali_private.database_images (
    sport text PRIMARY KEY CHECK (sport IN ('mlb', 'football')),
    payload bytea,
    revision bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON dali_private.database_images FROM PUBLIC;
INSERT INTO dali_private.database_images(sport) VALUES ('mlb'), ('football')
ON CONFLICT DO NOTHING;
-- DATABASE_URL must use an authorised server-side PostgreSQL role.
-- Never put DATABASE_URL into GitHub, browser code, or a member-facing page.
