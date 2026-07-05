-- songs.sql
-- Stores song audio files extracted from analyzed YouTube videos.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/songs.sql

CREATE TABLE IF NOT EXISTS songs (
    id           BIGSERIAL PRIMARY KEY,
    youtube_url  TEXT UNIQUE,
    title        TEXT,
    audio_path   TEXT,
    duration_sec INTEGER,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS songs_created_at_idx ON songs (created_at DESC);
