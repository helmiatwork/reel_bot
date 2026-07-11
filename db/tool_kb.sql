-- tool_kb.sql
-- Tool Knowledge Base — per-tool, per-version map of editing features so the
-- system can generate version-accurate step-by-step guides (e.g. CapCut effects).
-- Learned by feeding UI screenshots (vision extract) or manual entry.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/tool_kb.sql
--   (native: psql "$DATABASE_URL" < db/tool_kb.sql)

CREATE TABLE IF NOT EXISTS tool_kb (
    id          BIGSERIAL PRIMARY KEY,
    tool        TEXT NOT NULL,                       -- 'capcut', 'premiere', 'davinci', ...
    version     TEXT NOT NULL DEFAULT 'unknown',     -- '8.7.0'
    platform    TEXT NOT NULL DEFAULT 'desktop',     -- 'desktop' | 'mobile' (CapCut UI differs)
    category    TEXT NOT NULL,                        -- effect|text|audio|transition|speed|export|general
    name        TEXT NOT NULL,                        -- exact feature/effect label, e.g. 'Chromatic Aberration'
    menu_path   TEXT,                                 -- 'Effects > Video effects > Glitch'
    settings    JSONB DEFAULT '{}'::jsonb,            -- {"scale":"100-115%","intensity":"0-1"}
    notes       TEXT,                                 -- tips / gotchas
    source      TEXT,                                 -- screenshot filename or doc URL it was learned from
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- One row per feature within a tool/version/platform/category — enables upsert on re-learn.
CREATE UNIQUE INDEX IF NOT EXISTS tool_kb_unique_feature_idx
    ON tool_kb (tool, version, platform, category, name);

-- Fast lookup when generating a guide for a specific tool version.
CREATE INDEX IF NOT EXISTS tool_kb_lookup_idx
    ON tool_kb (tool, version, platform);

-- Full-text-ish search on feature names / notes (guide matching by keyword).
CREATE INDEX IF NOT EXISTS tool_kb_name_idx ON tool_kb (lower(name));

-- Keep updated_at fresh on upsert.
CREATE OR REPLACE FUNCTION tool_kb_touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tool_kb_touch ON tool_kb;
CREATE TRIGGER tool_kb_touch
    BEFORE UPDATE ON tool_kb
    FOR EACH ROW EXECUTE FUNCTION tool_kb_touch_updated_at();

-- Upsert pattern (for the future ingest endpoint):
--   INSERT INTO tool_kb (tool, version, platform, category, name, menu_path, settings, notes, source)
--   VALUES (...)
--   ON CONFLICT (tool, version, platform, category, name)
--   DO UPDATE SET menu_path = EXCLUDED.menu_path,
--                 settings  = EXCLUDED.settings,
--                 notes     = EXCLUDED.notes,
--                 source    = EXCLUDED.source;
