-- brands.sql
-- Stores content brands/products that group multiple publish accounts across platforms.
-- Idempotent — safe to run multiple times.
--
-- Apply with:
--   docker exec -i postgres psql -U admin -d content_automation < db/brands.sql

CREATE TABLE IF NOT EXISTS brands (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS brands_name_idx
    ON brands (name);

-- #6: Add brand_id column to accounts and FK constraint with ON DELETE SET NULL
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS brand_id BIGINT;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'accounts_brand_id_fkey') THEN
    ALTER TABLE accounts ADD CONSTRAINT accounts_brand_id_fkey
      FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE SET NULL;
  END IF;
END $$;
