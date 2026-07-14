-- db/keywords.sql
-- Keywords table for Google Ads and YouTube Suggest keyword research
-- Idempotent — safe to run multiple times
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/keywords.sql

CREATE TABLE IF NOT EXISTS keywords (
    id                  BIGSERIAL PRIMARY KEY,
    seed                TEXT,                          -- input seed text (e.g. "video editing")
    keyword             TEXT NOT NULL,                 -- normalized keyword (e.g. "video editing tutorial")
    source              TEXT NOT NULL,                 -- 'google_ads' or 'youtube_suggest'
    search_volume_min   BIGINT,                        -- min search volume (unused for now, null)
    search_volume_max   BIGINT,                        -- max search volume (unused for now, null)
    avg_monthly_searches BIGINT,                       -- Google Ads avg_monthly_searches or YouTube estimate
    competition         TEXT,                          -- 'LOW', 'MEDIUM', 'HIGH' (from Google Ads)
    competition_index   INT,                           -- 0-100 competition score from Google Ads
    cpc_low_micros      BIGINT,                        -- lowest CPC estimate in micros (1/1,000,000 USD)
    cpc_high_micros     BIGINT,                        -- highest CPC estimate in micros
    region              TEXT NOT NULL,                 -- geo+lang code, e.g. 'ID:id', 'US:en'
    niche               TEXT,                          -- nullable: niche slug if matched (e.g. 'restoration')
    score               DOUBLE PRECISION,              -- composite score = avg_monthly_searches * (1 - competition_index/100) * niche_fit
    raw                 JSONB,                         -- full raw response from source API
    fetched_at          TIMESTAMPTZ DEFAULT now()
);

-- Indexes for filtering and ordering
CREATE INDEX IF NOT EXISTS keywords_score_idx ON keywords (score DESC);
CREATE INDEX IF NOT EXISTS keywords_niche_idx ON keywords (niche);
CREATE INDEX IF NOT EXISTS keywords_source_idx ON keywords (source);
CREATE INDEX IF NOT EXISTS keywords_region_idx ON keywords (region);
CREATE INDEX IF NOT EXISTS keywords_keyword_idx ON keywords (keyword);
CREATE INDEX IF NOT EXISTS keywords_fetched_at_idx ON keywords (fetched_at DESC);

-- Unique constraint to prevent duplicates on re-fetch same keyword+region+source
-- If a keyword is fetched again for the same region/source, it UPSERT (update existing)
CREATE UNIQUE INDEX IF NOT EXISTS keywords_upsert_key
    ON keywords (keyword, region, source);
