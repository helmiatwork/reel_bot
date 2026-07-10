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
    niche             TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sources_created_at_idx ON sources (created_at DESC);
ALTER TABLE sources ADD COLUMN IF NOT EXISTS niche TEXT;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS gen_prompt TEXT;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS gen_prompt_format TEXT;
