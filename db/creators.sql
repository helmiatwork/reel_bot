-- creators.sql
-- Stores video creators extracted from analyzed YouTube videos.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/creators.sql

CREATE TABLE IF NOT EXISTS creators (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      TEXT UNIQUE,
    channel         TEXT,                -- channel handle/title
    creator_name    TEXT,                -- uploader name
    total_followers BIGINT,
    gender          TEXT,                -- AI-inferred: 'male' | 'female' | 'unknown'
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_updated    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS creators_last_updated_idx
    ON creators (last_updated DESC);
