-- learnings.sql
-- Distilled learnings the reelbot agent writes back after grounding in the corpus.
-- Layer 2 of the agent's memory:
--   * raw memory  = video_analysis + sources + transcripts (read via /dash/analysis,
--                   /sources/{id}/analysis) — grows automatically on every analyze.
--   * learnings   = distilled patterns (read-FIRST, write-back) so the agent improves
--                   without re-reading every transcript on each question.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/learnings.sql
--   (native: psql "$DATABASE_URL" < db/learnings.sql)

CREATE TABLE IF NOT EXISTS learnings (
    id          BIGSERIAL PRIMARY KEY,
    niche       TEXT NOT NULL DEFAULT 'general',   -- 'kuliner','otomotif',... 'general' = cross-niche
    kind        TEXT NOT NULL,                      -- 'question'|'hook'|'pattern'|'insight'
    content     TEXT NOT NULL,                      -- one distilled idea per row
    source_ids  BIGINT[] NOT NULL DEFAULT '{}',     -- sources.id it was grounded in (provenance)
    hits        INT NOT NULL DEFAULT 1,             -- times reinforced (bumped on re-learn)
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- One row per (niche, kind, content) — enables upsert on re-learn.
CREATE UNIQUE INDEX IF NOT EXISTS learnings_unique_idx
    ON learnings (niche, kind, md5(content));

-- Fast read-first lookup: newest/most-reinforced learnings for a niche+kind.
CREATE INDEX IF NOT EXISTS learnings_lookup_idx
    ON learnings (niche, kind, hits DESC, updated_at DESC);

-- Keep updated_at fresh on upsert.
CREATE OR REPLACE FUNCTION learnings_touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS learnings_touch ON learnings;
CREATE TRIGGER learnings_touch
    BEFORE UPDATE ON learnings
    FOR EACH ROW EXECUTE FUNCTION learnings_touch_updated_at();

-- Upsert pattern (used by POST /learnings):
--   INSERT INTO learnings (niche, kind, content, source_ids)
--   VALUES (%s, %s, %s, %s)
--   ON CONFLICT (niche, kind, md5(content))
--   DO UPDATE SET hits = learnings.hits + 1,
--                 source_ids = (
--                   SELECT ARRAY(SELECT DISTINCT unnest(learnings.source_ids || EXCLUDED.source_ids))
--                 );
