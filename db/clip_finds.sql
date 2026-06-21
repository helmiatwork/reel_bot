-- clip_finds.sql
-- Stores results of claude-powered clip-finder from /clips/find-claude.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/clip_finds.sql

CREATE TABLE IF NOT EXISTS clip_finds (
    id          BIGSERIAL PRIMARY KEY,
    youtube_url TEXT,
    clips       JSONB,
    model       VARCHAR(48),
    cost_usd    NUMERIC(10, 5),
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS clip_finds_created_at_idx
    ON clip_finds (created_at DESC);
