# PR Review Feedback — Cumulative July Work

Retroactive Oracle + Code-Reviewer sweep over every PR merged since **2026-07-01**
(#109–#149), none of which carried a `Reviewed By` sign-off at merge time.

- **Base:** `f193ac2` (PR #108) · **Head:** `main`
- **Diff reviewed:** ~7.9k insertions / 909 deletions across 36 non-test files
- **Reviewers:** code-reviewer × 3 (backend / frontend / mcp+automation) + oracle (architecture + security)
- **Method:** cumulative diff split by domain, findings mapped back to originating PR. Only issues live on `main` now are listed — anything fixed mid-session is excluded.

**Tally:** 2 Critical · 10 Important · 11 Minor. Clean-area confirmations at the bottom.

---

## 🔴 Critical

### C1 — Duplicate-URL confirm never renders in Gemini mode → "Ambil instruksi Gemini" hangs
- **PR:** #149 · **File:** `dashboard-svelte/src/lib/SourceUploadModal.svelte:652`
- **Cause:** `fetchGeminiBrief()` awaits `ensureNotDuplicate()`, which sets `dupConfirm` and returns a Promise resolved only by `overrideExisting()`/`cancelDup()`. Those buttons live inside the `{:else}` branch (line 621) that is active **only when `analysisMode === 'claude'`**. In `gemini_mcp` mode the template is in the sibling `{#if}` branch (line 473), so the confirm UI never mounts. The Promise never settles; `loading` is set *after* the `await`, so the button stays clickable and each new click leaks another dangling resolver.
- **Fix:** hoist `{#if dupConfirm}…{/if}` out of the Claude-only `{:else}` (place it above the mode branch, or duplicate it inside the gemini section).

### C2 — Auto-post has no per-platform idempotency guard → double-publish
- **PR:** #145 · **File:** `pipeline-api/main.py:10478-10484`
- **Cause:** `_publish_scheduled_post` reads `posted` (line 10462) but then uploads for every platform in `wanted` regardless of whether `posted["youtube"]` already holds a URL. `schedule_publish_due` is a sync def on uvicorn's threadpool. n8n's 10-min HTTP timeout fires while a large upload is still running; the next hourly trigger re-reads `platform_urls = '{}'` and starts a **second** upload → two public YouTube videos, one lost DB URL.
- **Fix:** guard per platform — `if posted.get("youtube"): continue` before each upload block; ideally `SELECT … FOR UPDATE SKIP LOCKED` on the row so concurrent callers don't race.

---

## 🟠 Important

### I1 — `content_ref` accepts any local path → arbitrary file uploaded to YouTube / exfil
- **PR:** #145/#146 · **File:** `pipeline-api/main.py:10389-10391`
- `_resolve_content_to_file` accepts any path passing `exists() and is_file()`. `content_ref` is user-supplied via `POST /schedule` / `PATCH /schedule/{id}` with no validation. A value like `/credentials/youtube_token_1.json` or `../../../etc/passwd` gets submitted to `MediaFileUpload`. Combined with I3 (API on `0.0.0.0`, unauthenticated), any LAN device can exfiltrate local files.
- **Fix:** `p = Path(ref).resolve(); if not str(p).startswith(str((_REPO_ROOT/"data").resolve()) + os.sep): raise Exception("content_ref must be inside data/")`.

### I2 — GDrive API download has no size cap
- **PR:** #146 · **File:** `pipeline-api/main.py:10320-10328`
- `_download_url_to_file` enforces a 4 GB cap; the Drive API path (`_download_gdrive_api`) runs the chunk loop unbounded. A large/hostile file fills the disk.
- **Fix:** byte-counter in the `next_chunk()` loop mirroring the 4 GB `MAX_DOWNLOAD` guard.

### I3 — Publishing / deletion endpoints unauthenticated + API bound to all interfaces
- **PR:** #132/#145 · **Files:** `scripts/start-pipeline-api.sh`, `pipeline-api/main.py:285-299`
- Startup binds `--host 0.0.0.0`. `verify_admin_key` is wired to only the two restart endpoints. None of `POST /schedule/{id}/publish`, `POST /schedule/publish-due`, `POST /performance/check-targets`, `DELETE /sources/{id}`, `POST /accounts/{id}/connect-youtube`, `DELETE /brands/{id}` require it. Any device on the LAN can publish or wipe the source library with one call.
- **Fix:** default `--host 127.0.0.1` unless overridden; add `Depends(verify_admin_key)` to the destructive/publishing endpoints.

### I4 — `POST /performance/refresh` is synchronous and spawns yt-dlp per (post × platform) inline
- **PR:** #141 · **File:** `pipeline-api/main.py:10044-10048`
- ~10 posted videos ≈ 100 s blocking the uvicorn worker, stalling all concurrent requests. The existing ponytail comment already flags "add BackgroundTasks if latency matters" — it matters above ~3 videos.
- **Fix:** convert to `BackgroundTasks` / return a run_id (same pattern as `/analyze/claude/async`).

### I5 — OAuth token refresh writes via `write_text` without explicit `0o600`
- **PR:** #132 · **File:** `pipeline-api/main.py:10320, 10412`
- Initial write at line 3137 correctly uses `os.open(…, 0o600)`. The two refresh paths use `token_file.write_text(...)`. If the token file was deleted and the refresh branch recreates it, it lands at umask perms (often world-readable), exposing the refresh token to any local process.
- **Fix:** mirror the `os.open` 0o600 pattern in both refresh paths.

### I6 — Dead `agents/reelbot/SOUL.md` was modified and is now 2 features behind `agents/main/`
- **PR:** #138/#139 · **File:** `openclaw/agents/reelbot/SOUL.md` (whole file; line 49)
- `entrypoint.sh` reads `agents/main/`, not `agents/reelbot/`, so this file is dead — yet it was edited in this diff and lacks the `/learnings` read-first layer and learn-back POST. It also documents `GET /pipeline/research` while the backend is `@app.post` (`main.py:1600`) → 405/404 at runtime. Leaving it is a maintenance trap.
- **Fix:** delete the dead file, or fully sync it with `agents/main/SOUL.md` and change the endpoint to `POST`.

### I7 — n8n workflows have no error branch → silent failure
- **PR:** #141/#144/#145 · **Files:** `n8n/workflows/perf-daily.json`, `schedule-reminder.json`, `auto-post.json`
- No error-output connection on the HTTP nodes. If pipeline-api is down / returns 5xx / times out, n8n halts and downstream nodes never fire — posts silently missed, no alert. (`auto-post.json` ships `"active": false`, so no live risk yet, but the gap must close before it is ever enabled.)
- **Fix:** add an error-output branch from each HTTP node to a Telegram notify node.

### I8 — Modal close never stops storyboard polling + `$effect` reset skips 8 state vars
- **PR:** #128–#130 · **File:** `dashboard-svelte/src/lib/SourceUploadModal.svelte:150, 97-119`
- `closeModal()` never calls `stopStoryboardPolling()`; closing mid-poll leaks a 3 s interval hammering `api.storyboardStatus('')` until the ~200-poll cap (~10 min). The reset `$effect` never clears `storyboardPhase`, `storyboardReady`, `storyboardScenes`, `prepStage`, `prepPollCount`, `geminiStarted`, `dupConfirm`, `dupResolve` → stale UI and an orphaned resolver on reopen.
- **Fix:** call `stopStoryboardPolling()` in `closeModal()` and in the `isOpen` reset branch; add the missing resets.

### I9 — `Drawer.subscribe()` unsubscribe handle discarded → `procPoll` leak on unmount
- **PR:** #116 · **File:** `dashboard-svelte/src/lib/Drawer.svelte:317`
- Subscription created at module scope with no lifecycle wrapper; the unsubscribe fn is dropped. If the component is ever unmounted, `procPoll` keeps firing `pollProcessing()` every 3 s with no way to stop.
- **Fix:** wrap in `$effect(() => drawer.subscribe(...))` so the teardown runs on destroy.

### I10 — `GET /sources/exists` full table scan
- **PR:** #149 · **File:** `pipeline-api/main.py:7712`
- Fetches every `sources` row and matches the canonical key in Python — O(n) per dedup check, degrading at 10k+ rows.
- **Fix:** add an indexed `canonical_key TEXT` column populated on insert; `SELECT id … WHERE canonical_key = %s LIMIT 1`.

---

## 🟡 Minor

| # | PR | File:line | Issue | Fix |
|---|----|-----------|-------|-----|
| M1 | #147/#135 | `SourceUploadModal.svelte:276` | Escape/backdrop close while `dupConfirm` shows (Claude mode) leaves the `ensureNotDuplicate` coroutine suspended | `closeModal()` calls `cancelDup()` when `dupResolve` is non-null |
| M2 | #142 | `main.py:10212` | `_check_performance_targets` does bare `conn.close()` outside try/finally → leak on loop exception | wrap loop in `try/finally: conn.close()` |
| M3 | #132 | `main.py:37, 2916, 3117` | `_oauth_flows` never evicts abandoned flows → unbounded dict growth | timestamp + prune stale (>10 min) entries at `/youtube-callback` |
| M4 | #132 | `main.py:297` | `verify_admin_key` compares with `!=` (timing side-channel) | `hmac.compare_digest(x_api_key or "", env_key)` |
| M5 | #145/#146 | `main.py:141-178` | DNS-rebinding gap: validation-time `getaddrinfo` ≠ request-time DNS | pin the resolved IP on the connection (custom transport); low risk on localhost |
| M6 | #111 | `Drawer.svelte:177` | Dead `else if` for YouTube Shorts — unreachable, works only by fallback accident | move shorts `match()` inside the first `if` before the fallback |
| M7 | #131 | `mcp/reelbot_mcp.py:830` | Docstring says limit "clamped 1–500"; `_clamp_limit()` caps at 100 | fix docstring to "1–100" |
| M8 | #128 | `mcp/reelbot_mcp.py:229` | `get_analysis` skips the `_valid_url()` check every other URL tool runs | add the guard before DB connect |
| M9 | #130 | `mcp/reelbot_mcp.py:568-573` | Tags pre-serialized with `json.dumps()` into a JSONB column; relies on implicit TEXT→JSONB cast | pass the list directly; let psycopg3's Json adapter handle it |
| M10 | #135 | `mcp/reelbot_mcp.py:722-723` | `_suno_audio_path()` does `mkdir` as a side effect inside a path-compute helper | move `mkdir` into `get_audio_for_suno`; keep the helper pure |
| M11 | — | `main.py:885` | `OPENCLAW_SESSIONS_DIR` still defaults to the Docker path `/openclaw-data/agents/reelbot/sessions` | harmless in native mode; align to `agents/main/sessions` if Docker is ever revived |

---

## ✅ Clean areas (reviewed, no findings)

- **SQL injection** — every user value parameterized; f-strings build only hardcoded column names.
- **Subprocess injection** — `shell=True` appears once (static `pkill` allowlist); all user URLs are list args to yt-dlp, never shell-interpolated.
- **`shutil.rmtree` depth guards** — `DELETE /sources/{id}` (7758) and temp-dir cleanups check exact parent equality; `..` paths fail the check and are left alone.
- **SSRF core guard** — `_validate_source_url` (106–178) checks scheme, blocks localhost, resolves all A/AAAA and rejects private/reserved/CGNAT/IPv4-mapped/multicast; post-redirect re-validation (10342-10349) closes the redirect bypass.
- **DB migration idempotency** — `brands.sql`, `keywords.sql`, `learnings.sql` all `IF NOT EXISTS` + `DO $$` FK guards.
- **Initial OAuth token write** — `os.open(O_CREAT|O_TRUNC, 0o600)` + `chmod` (3137); `account_id` is an int from DB, not user text.
- **`--download-sections`** — `audio_start`/`audio_end` cast to `float` before building the section string; `cmd` is a list.
- **`max_tokens=1200`** for `_perf_improvement_suggestion` — intentional and documented (deepseek-v4-pro reasoning tokens consume budget first).
- **Google Ads adapter** — no hardcoded creds; lazy init raises `GoogleAdsNotConfigured` cleanly; competition_index clamped to [0,100].
- **`auto-post.json`** — safely `"active": false` with a meta note; no live activation risk today.

---

## Suggested fix order

1. **C1** (macet — user-facing, blocks the Gemini flow today) and **C2** (double-publish — before auto-post is trusted).
2. **I1 + I3** together (they compound into remote file-exfil), then **I2, I5** (download/token hardening).
3. **I4** (blocking refresh), **I7** (n8n silent failure), **I8/I9** (frontend interval leaks).
4. Minors as a cleanup batch.
