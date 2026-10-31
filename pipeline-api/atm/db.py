"""ATM schema: additive migrations only, safe to re-run."""
from .common import LEGACY_STAGE_MAP

_ITEM_COLUMNS = [
    "reference_url TEXT", "reference_source_id BIGINT", "blueprint JSONB",
    "blueprint_version INT NOT NULL DEFAULT 0", "blueprint_status TEXT NOT NULL DEFAULT 'none'",
    "blueprint_error TEXT", "format TEXT NOT NULL DEFAULT 'short'",
    "voice_mode TEXT NOT NULL DEFAULT 'self'", "scheduled_at TIMESTAMPTZ", "published_url TEXT",
    "published_at TIMESTAMPTZ", "draft_video_path TEXT", "reminded_d1_at TIMESTAMPTZ",
    "reminded_d0_at TIMESTAMPTZ", "post_eval_done BOOLEAN NOT NULL DEFAULT false",
]


def init_atm_db() -> None:
    import main
    conn = main._db_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            for col in _ITEM_COLUMNS:
                cur.execute(f"ALTER TABLE content_items ADD COLUMN IF NOT EXISTS {col}")
            # idempotent: after the first run no row has a legacy stage
            for old, new in LEGACY_STAGE_MAP.items():
                cur.execute("UPDATE content_items SET stage = %s WHERE stage = %s", (new, old))
            cur.execute("""CREATE TABLE IF NOT EXISTS content_evaluations (
                id BIGSERIAL PRIMARY KEY,
                content_item_id BIGINT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('draft','post')),
                round INT NOT NULL,
                video_ref TEXT, scores JSONB, findings JSONB, fixes JSONB, summary TEXT,
                resolved_prev JSONB, human_notes JSONB, model TEXT,
                status TEXT NOT NULL DEFAULT 'ready', error TEXT,
                created_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (content_item_id, kind, round)
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS routine_settings (
                id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                weekdays INT[] NOT NULL DEFAULT '{0,2,4}',
                post_time TEXT NOT NULL DEFAULT '19:00',
                tz TEXT NOT NULL DEFAULT 'Asia/Jakarta',
                per_week INT NOT NULL DEFAULT 3,
                niche TEXT NOT NULL DEFAULT 'general',
                format TEXT NOT NULL DEFAULT 'short',
                alert_ratio REAL NOT NULL DEFAULT 0.5
            )""")
            cur.execute("INSERT INTO routine_settings (id) VALUES (1) ON CONFLICT DO NOTHING")
            cur.execute("""CREATE TABLE IF NOT EXISTS monitor_snapshots (
                id BIGSERIAL PRIMARY KEY,
                content_item_id BIGINT NOT NULL,
                url TEXT NOT NULL,
                checkpoint_h INT NOT NULL,
                views BIGINT, likes BIGINT, comments BIGINT,
                alerted BOOLEAN NOT NULL DEFAULT false,
                captured_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (content_item_id, checkpoint_h)
            )""")
        conn.commit()
    except Exception as e:
        print(f"[atm] init db error: {e}")
    finally:
        conn.close()
