# Plan: Music & Content Hierarchy with Audio, Video, and Lyrics Scraper

## Pillar S: Situation & Statutory Context
Reelbot processes audio clips for Suno music generation and visual storyboard workflows. Currently, audio tracks in the `songs` table are flat, loosely tagged, and lack hierarchical organization (Category -> Artist/Band -> Song). Furthermore, there is no automated scraper that bundles audio extraction, video reference caching, and lyrics scraping (raw text + synchronized LRC timestamps) together for ingestion by AI agents.

This feature introduces a structured hierarchical content architecture:
- `categories` (e.g. "music", "podcast", "asmr")
- `artists` (musicians/bands belonging to a category)
- `songs` (individual tracks belonging to an artist and category, with audio, video, and lyrics assets)
- Automated scraping engine for YouTube / external sources that extracts audio (`.mp3`), reference video (`.mp4`), and lyrics (`lyrics_raw` + `lyrics_lrc` format).
- Fast, secure API endpoints in `pipeline-api/main.py` and native MCP tools in `mcp/reelbot_mcp.py` so AI agents can query and trigger scraping.

## Pillar T: Task & Boundary (GitNexus Perimeter)
- **Target Files**:
  - `pipeline-api/main.py`: DB schema migrations, models/helpers, scraper implementation (audio, video, lyrics via yt-dlp / LRCLIB API / captions), API endpoints (`/content/categories`, `/content/artists`, `/content/scrape`).
  - `mcp/reelbot_mcp.py`: New MCP tools `scrape_music_content`, `list_content_hierarchy`, `get_song_details`.
  - `mcp/test_reelbot_mcp.py` & `pipeline-api/test_content_scraper.py`: Comprehensive test suites.
- **Boundaries**:
  - In-tree changes only within `pipeline-api/` and `mcp/`.
  - Non-breaking additive DB migrations for existing `songs` table and new tables `categories` & `artists`.
  - Must not break existing `/songs` endpoints or `get_audio_for_suno` flow.

## Pillar A: RFC 2119 Invariants
1. The system **MUST** provide non-destructive additive migrations (`CREATE TABLE IF NOT EXISTS categories`, `CREATE TABLE IF NOT EXISTS artists`, and `ALTER TABLE songs ADD COLUMN IF NOT EXISTS`).
2. The scraper **MUST** support scraping:
   - Audio file (extracted or downloaded via yt-dlp/ffmpeg into `data/songs/audio/` or existing song storage).
   - Video reference file (cached or linked into `data/songs/video/`).
   - Lyrics in raw text (`lyrics_raw`) and timestamped LRC format (`lyrics_lrc`) if available from captions or lyrics provider.
3. The scraper **MUST NOT** fail catastrophically if lyrics are unavailable; it **SHALL** gracefully save audio/video and leave lyrics null or empty.
4. All file downloads **MUST** prevent path traversal attacks; target directories **SHALL** be sanitized and restricted to safe paths under `data/`.
5. External network calls (yt-dlp, lyric APIs) **MUST** enforce timeouts (default: 60s for metadata/lyrics, bounded for media) and fail closed with descriptive error messages.
6. Database operations **MUST** use parameterized queries to prevent SQL injection.
7. Concurrency guards: duplicate scrape requests for the same `youtube_url` **MUST** be idempotent (upsert or return existing record).
