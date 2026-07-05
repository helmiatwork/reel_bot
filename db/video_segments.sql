-- video_segments.sql
-- Stores metadata for segments extracted from compiled videos via /decompose.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   psql "$DATABASE_URL" -f db/video_segments.sql

CREATE TABLE IF NOT EXISTS video_segments (
    id             BIGSERIAL PRIMARY KEY,
    source_id      BIGINT REFERENCES sources(id),
    clip_index     INTEGER,
    start_sec      NUMERIC(10,3),
    end_sec        NUMERIC(10,3),
    credit_handle  TEXT,
    original_url   TEXT,
    origin_status  TEXT,
    confidence     NUMERIC(4,3),
    segment_path   TEXT,
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS video_segments_source_idx ON video_segments (source_id, clip_index);
