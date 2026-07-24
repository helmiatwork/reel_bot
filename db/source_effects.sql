-- source_effects.sql
-- Stores detected editing effects and techniques from a source video (Effects Breakdown flow).
-- One row per source (upsert keyed by youtube_url).
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   psql "$DATABASE_URL" -f db/source_effects.sql

CREATE TABLE IF NOT EXISTS source_effects (
    id          BIGSERIAL PRIMARY KEY,
    source_id   BIGINT REFERENCES sources(id) ON DELETE CASCADE,
    youtube_url TEXT NOT NULL,
    effects     JSONB,          -- array of {ts_start, ts_end, effect, capcut_tool, how_to, intensity}
    effects_at  TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS source_effects_url_uidx ON source_effects (youtube_url);
CREATE INDEX IF NOT EXISTS source_effects_source_idx ON source_effects (source_id);
