-- video_analysis.sql
-- Stores results of claude-powered video analysis from /analyze/claude.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/video_analysis.sql

CREATE TABLE IF NOT EXISTS video_analysis (
    id          BIGSERIAL PRIMARY KEY,
    youtube_url TEXT,
    intent      TEXT,
    hook        TEXT,
    structure   TEXT,
    retention   TEXT,
    tags        JSONB,
    raw_result  TEXT,
    model       VARCHAR(48),
    cost_usd    NUMERIC(10, 5),
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Retention score (1-10), added later — idempotent.
ALTER TABLE video_analysis ADD COLUMN IF NOT EXISTS retention_score INTEGER;

CREATE INDEX IF NOT EXISTS video_analysis_created_at_idx
    ON video_analysis (created_at DESC);
