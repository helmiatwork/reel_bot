-- sources.sql
-- Stores YouTube sources (videos) analyzed by the system.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/sources.sql

CREATE TABLE IF NOT EXISTS sources (
    id                BIGSERIAL PRIMARY KEY,
    youtube_url       TEXT UNIQUE,
    title             TEXT,
    platform          TEXT DEFAULT 'youtube',
    channel           TEXT,
    views_at_analysis BIGINT,
    status            TEXT DEFAULT 'analyzed',
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sources_created_at_idx ON sources (created_at DESC);
