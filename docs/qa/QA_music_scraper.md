# QA Threat Model & Verification Scenarios: Music & Content Scraper

## Threat Model
- Input Vector: Malicious or malformed YouTube URLs, extremely long artist/title strings, shell injection attempts via query parameters into `yt-dlp`.
- Filesystem: Path traversal via song ID or filename to read arbitrary host files.
- Network Exhaustion: Hanging network requests on slow/unreachable external lyric servers or YouTube streams.
- Database: SQL injection via category, artist, or lyric fields.

---

## Positive Scenarios (Happy Path)
- **POS-01 (End-to-End Scrape)**: Scrape a valid music video with category "music", artist "Rhoma Irama", title "Begadang". Creates category and artist if missing, downloads audio and video, extracts subtitles/lyrics, records into database, and returns payload.
- **POS-02 (Hierarchy Query)**: Query categories returns list of categories with artist counts. Querying artist returns associated songs.
- **POS-03 (LRC Parsing)**: Parsing valid synced subtitle / LRC file correctly preserves millisecond timestamps and text lines.
- **POS-04 (MCP Tool Execution)**: Invoking `scrape_music_content` via MCP server returns structured JSON containing song ID, audio path, video path, and lyrics snippet.

---

## Universal 6-Category Verification Framework

### 1. Adversarial & Abuse
- **ADV-01 (Command Injection Prevention)**: Passing shell metacharacters (`; rm -rf /`, `$(whoami)`, `| cat /etc/passwd`) in URL or artist/title arguments must not execute arbitrary shell commands; yt-dlp arguments must use argument lists, not raw shell strings.
- **ADV-02 (Path Traversal)**: Attempting to fetch or download files using `../../etc/passwd` or encoded `%2e%2e` must be rejected with 400/403.

### 2. Concurrency & Race Conditions
- **CON-01 (Idempotent Scrapes)**: Concurrent scrape calls for the exact same YouTube URL must not create duplicate song rows; the second call must return the existing record or safely upsert.
- **CON-02 (Simultaneous Category/Artist Creation)**: Two workers attempting to insert the same category or artist name simultaneously must resolve via `ON CONFLICT` or unique constraint without crashing.

### 3. Resiliency & Chaos
- **RES-01 (Lyric Server Offline / 404)**: If lyrics cannot be found or the external lyrics endpoint returns 500 / 404 / timeout, audio and video must still be saved successfully, with `lyrics_raw` set to empty/null.
- **RES-02 (yt-dlp Network Timeout)**: If YouTube throttles or disconnects during extraction, the scraper must fail closed with a clean error message and cleanup any orphaned temp files.

### 4. Boundary Value Analysis (BVA) & Extreme Inputs
- **BVA-01 (Empty / Whitespace Inputs)**: Submitting empty string or only whitespace for `youtube_url`, `artist_name`, or `title` must return validation error (HTTP 422/400).
- **BVA-02 (Extreme Length Inputs)**: Extremely long artist names (>1000 characters) or lyrics (>500KB) must be handled without truncating vital memory or breaking database transactions.

### 5. Data Integrity & Privacy
- **DIP-01 (SQL Injection Defense)**: Inputs containing SQL syntax (`' OR '1'='1`, `'; DROP TABLE songs;--`) must be sanitized using parameterized queries (%s placeholders).
- **DIP-02 (Encoding & Unicode)**: Non-ASCII characters (e.g., Japanese, Arabic, accented characters, emojis in song titles) must be stored and retrieved with UTF-8 fidelity.

### 6. Finite State Machine (FSM) & Lifecycle
- **FSM-01 (Asset Lifecycle)**: Deleting or re-scraping a song must properly update state without leaving inconsistent dangling foreign keys in artists or categories.
