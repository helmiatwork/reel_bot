-- source_ideas.sql
-- Stores candidate ideas and expanded detail for a source video (Idea Generator 2-stage flow).
-- One row per source (upsert keyed by youtube_url).
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   psql "$DATABASE_URL" -f db/source_ideas.sql

CREATE TABLE IF NOT EXISTS source_ideas (
    id            BIGSERIAL PRIMARY KEY,
    source_id     BIGINT REFERENCES sources(id) ON DELETE CASCADE,
    youtube_url   TEXT NOT NULL,
    candidates    JSONB,          -- array of 5: {title, description, premise, why_viral, cover_caption}
    selected_index INTEGER,       -- which candidate user picked (NULL until picked)
    detail        JSONB,          -- {naskah, edit_cues:[{ts_start,ts_end,aksi,sfx,teks_layar}], caption, hashtags:[]}
    candidates_at TIMESTAMPTZ,
    detail_at     TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS source_ideas_url_uidx ON source_ideas (youtube_url);
CREATE INDEX IF NOT EXISTS source_ideas_source_idx ON source_ideas (source_id);
