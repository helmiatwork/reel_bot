# ATM Creator Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn reelbot into one creator workflow (Amati → Blueprint → Jadwal → Evaluasi → Pantau → Belajar) on top of the existing content_items / learnings / performance / Telegram pieces.

**Architecture:** New backend package `pipeline-api/atm/` exposes one FastAPI `APIRouter` (prefix `/atm`) included by `main.py`. ATM modules call shared helpers lazily through `import main` inside functions (so tests that `patch("main._db_conn")` keep working and there is no import cycle). Frontend adds five Svelte pages and a regrouped sidebar. A launchd job calls `POST /atm/cron/tick` every 15 minutes for reminders and monitoring (replaces n8n).

**Tech Stack:** FastAPI, psycopg (PostgreSQL only), pytest + TestClient with mocked `_db_conn`, Svelte 5 + Vite, svelte-i18n, claude-bridge (`claude -p`), yt-dlp, faster-whisper, ffmpeg, ElevenLabs via `voiceover/voiceover.py`.

**Spec:** `docs/superpowers/specs/2026-10-31-atm-creator-studio-design.md`

## Global Constraints

- PostgreSQL only; all migrations additive (`ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`), run from `startup_event`, non-fatal on failure.
- No render, no auto-upload, no platform interaction (comment/like/subscribe). Voice MP3s are not merged into video.
- Monitoring uses yt-dlp **without cookies** (`--no-cookies`), max 20 URLs per tick, 2–5 s random sleep between calls.
- Main-channel cookies are never used; only the existing `scrape` role cookies for downloads (unchanged code).
- Models: `ATM_MODEL` env, default `claude-sonnet-5-5` (blueprint, evaluations); `ATM_LIGHT_MODEL`, default `claude-haiku-5-5` (alerts, learnings).
- Routine defaults (single channel): weekdays Mon/Wed/Fri (`[0, 2, 4]`, Monday = 0), `19:00`, `Asia/Jakarta`, 3 per week, format `short`, alert ratio `0.5`.
- Statuses, in order: `idea, blueprint, shoot, edit, review, ready, scheduled, posted, monitored`. Legacy stages map `script→blueprint`, `prep→shoot`; `idea/scheduled/posted` unchanged.
- Monitor checkpoints (hours after `published_at`): `1, 6, 24, 48, 168`. Post-evaluation at 168.
- Draft upload: video exts from `main._SOURCE_UPLOAD_VIDEO_EXTS`, max 300 MB, stored as `data/drafts/<item_id>/<uuid><ext>`.
- UI copy Indonesian first, every string in both `locales/id.json` and `locales/en.json`.
- Every frontend change: `npm run build` and commit the rebuilt `analytics-dashboard/` bundle.
- `/atm/cron/tick` is gated by `main.verify_admin_key` (same as `/dash/restart-all`).

## Review Focus

1. Claude returns prose or truncated JSON for a blueprint/evaluation → item gets `blueprint_status='error'` with a readable message, nothing half-written. (Task 3, Task 8 tests.)
2. claude-bridge or cliproxy down → endpoints answer 503/clear error, tick keeps going, Telegram alert still sent without the diagnosis line. (Task 1, Task 9 tests.)
3. Tick runs twice or late → no duplicate Telegram reminders/alerts, a missed early checkpoint is skipped not back-filled with later numbers. (Task 6, Task 9 tests.)
4. Upload of a non-video, oversized, or path-traversal filename → 400/413, nothing written outside `data/drafts/<item_id>/`. (Task 7 tests.)
5. Fewer than 3 posted videos → baseline falls back to the fixed target curve instead of dividing by zero or alerting on everything. (Task 9 tests.)

---

## Phase A — Foundation + Blueprint (spec P0, P1)

### Task 1: `atm` package skeleton, DB migrations, statuses

**Files:**
- Create: `pipeline-api/atm/__init__.py`, `pipeline-api/atm/common.py`, `pipeline-api/atm/db.py`
- Modify: `pipeline-api/main.py` (startup_event list near line 80: call `atm.db.init_atm_db()` after `_studio_init_db()`; `_VALID_STAGES` at ~13331 becomes `frozenset(atm.common.STATUSES)`; `/studio/board` groups use `STATUSES`; `app.include_router(atm.router)` after app creation)
- Test: `pipeline-api/tests/test_atm_common.py`, update `pipeline-api/tests/test_studio.py` stage names

**Interfaces:**
- Produces (`atm/common.py`):
  - `STATUSES: tuple[str, ...]`, `LEGACY_STAGE_MAP = {"script": "blueprint", "prep": "shoot"}`
  - `ATM_MODEL: str`, `ATM_LIGHT_MODEL: str`
  - `run_claude(prompt: str, *, agent: str, model: str = ATM_MODEL, frames: list[str] | None = None, subdir: str | None = None, timeout_s: int = 300) -> str | None` — POST `{main.CLAUDE_BRIDGE_URL}/run`, returns `result` text, `None` on transport error or `ok: false`; logs via `main._log_api_usage(agent, model, raw_usage, cost_usd)`.
  - `parse_json(text: str | None) -> dict | None` — strips ```json fences, returns first top-level JSON object, `None` if absent/invalid.
  - `item_row(cur_description, row) -> dict` — serializes datetimes to ISO.
- Produces (`atm/db.py`): `init_atm_db() -> None`
  - `content_items` add: `reference_url TEXT, reference_source_id BIGINT, blueprint JSONB, blueprint_version INT NOT NULL DEFAULT 0, blueprint_status TEXT NOT NULL DEFAULT 'none', blueprint_error TEXT, format TEXT NOT NULL DEFAULT 'short', voice_mode TEXT NOT NULL DEFAULT 'self', scheduled_at TIMESTAMPTZ, published_url TEXT, published_at TIMESTAMPTZ, draft_video_path TEXT, reminded_d1_at TIMESTAMPTZ, reminded_d0_at TIMESTAMPTZ, post_eval_done BOOLEAN NOT NULL DEFAULT false`
  - one-time stage migration: `UPDATE content_items SET stage = %s WHERE stage = %s` for each `LEGACY_STAGE_MAP` pair
  - `content_evaluations(id BIGSERIAL PK, content_item_id BIGINT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('draft','post')), round INT NOT NULL, video_ref TEXT, scores JSONB, findings JSONB, fixes JSONB, summary TEXT, resolved_prev JSONB, human_notes JSONB, model TEXT, status TEXT NOT NULL DEFAULT 'ready', error TEXT, created_at TIMESTAMPTZ DEFAULT now(), UNIQUE (content_item_id, kind, round))`
  - `routine_settings(id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1), weekdays INT[] NOT NULL DEFAULT '{0,2,4}', post_time TEXT NOT NULL DEFAULT '19:00', tz TEXT NOT NULL DEFAULT 'Asia/Jakarta', per_week INT NOT NULL DEFAULT 3, niche TEXT NOT NULL DEFAULT 'general', format TEXT NOT NULL DEFAULT 'short', alert_ratio REAL NOT NULL DEFAULT 0.5)` + `INSERT ... ON CONFLICT DO NOTHING` default row
  - `monitor_snapshots(id BIGSERIAL PK, content_item_id BIGINT NOT NULL, url TEXT NOT NULL, checkpoint_h INT NOT NULL, views BIGINT, likes BIGINT, comments BIGINT, alerted BOOLEAN NOT NULL DEFAULT false, captured_at TIMESTAMPTZ DEFAULT now(), UNIQUE (content_item_id, checkpoint_h))`
- Produces (`atm/__init__.py`): `router: APIRouter(prefix="/atm")` aggregating sub-routers from later tasks.

- [ ] **Step 1: Failing tests** in `tests/test_atm_common.py`:
  - `test_parse_json_fenced`: `parse_json('x ```json\n{"a": 1}\n``` y') == {"a": 1}`
  - `test_parse_json_invalid_returns_none`: `parse_json("no json") is None`, `parse_json(None) is None`, `parse_json('{"a": ') is None`
  - `test_run_claude_bridge_down_returns_none`: patch `httpx.post` to raise `httpx.ConnectError` → `None`
  - `test_run_claude_not_ok_returns_none`: bridge JSON `{"ok": false, "error": "x"}` → `None`
  - `test_statuses_order`: `STATUSES == ("idea","blueprint","shoot","edit","review","ready","scheduled","posted","monitored")`
- [ ] **Step 2:** `cd pipeline-api && .venv/bin/python -m pytest -q tests/test_atm_common.py` → FAIL (module missing)
- [ ] **Step 3:** Implement `atm/common.py`, `atm/db.py`, `atm/__init__.py`, wire into `main.py`; update `tests/test_studio.py` expectations to new stage names.
- [ ] **Step 4:** `.venv/bin/python -m pytest -q tests/test_atm_common.py tests/test_studio.py` → PASS
- [ ] **Step 5:** Commit `feat(atm): package skeleton, migrations and statuses`

### Task 2: Item CRUD + routine settings API

**Files:**
- Create: `pipeline-api/atm/items.py`
- Test: `pipeline-api/tests/test_atm_items.py`

**Interfaces:**
- Consumes: `STATUSES`, `item_row`, `main._db_conn`, `main._validate_source_url`, `main._json`
- Produces endpoints:
  - `GET /atm/items?status=` → `{"items": [item...]}` ordered `scheduled_at NULLS LAST, id DESC`
  - `POST /atm/items` body `ItemCreate{title: str (1..200), niche: str = "", reference_url: str | None, format: Literal["short","long"] = "short", voice_mode: Literal["self","ai"] = "self"}` → item; `reference_url` validated with `_validate_source_url` and `reference_source_id` looked up from `sources.youtube_url`; status `idea`, or `blueprint` is NOT set here.
  - `GET /atm/items/{id}` → item + `"evaluations": [{id, kind, round, summary, created_at}]`; 404 when missing
  - `PATCH /atm/items/{id}` body `ItemPatch{title?, status?, blueprint?, scheduled_at?, published_url?, voice_mode?, format?, niche?}`; status must be in `STATUSES` (422 otherwise); `published_url` validated; setting it sets `status='posted'` and `published_at = COALESCE(published_at, now())`; editing `blueprint` bumps `blueprint_version`.
  - `DELETE /atm/items/{id}`
  - `GET /atm/settings`, `PUT /atm/settings` body `Settings{weekdays: list[int] (each 0..6, 1..7 items), post_time: "HH:MM", tz: str (must load in zoneinfo), per_week: int 1..21, niche: str, format, alert_ratio: float 0.1..1.0}`

- [ ] **Step 1: Failing tests:** `test_create_item_minimal`, `test_create_item_bad_reference_url_400`, `test_patch_invalid_status_422`, `test_patch_published_url_sets_posted`, `test_get_missing_404`, `test_settings_put_rejects_bad_tz`, `test_settings_put_rejects_weekday_7` (mock `_db_conn` the way `tests/test_studio.py` does).
- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Implement `atm/items.py`, include router in `atm/__init__.py`.
- [ ] **Step 4:** `.venv/bin/python -m pytest -q tests/test_atm_items.py` → PASS
- [ ] **Step 5:** Commit `feat(atm): content items and routine settings API`

### Task 3: Blueprint generation

**Files:**
- Create: `pipeline-api/atm/blueprint.py`
- Test: `pipeline-api/tests/test_atm_blueprint.py`

**Interfaces:**
- Consumes: `run_claude`, `parse_json`, tables `video_analysis` (by `reference_url`), `source_ideas.detail/candidates`, `source_effects.effects`, `songs` (kind in ('song','clip'), order `is_viral DESC, created_at DESC`, limit 20), `learnings` (niche, top 10 by hits), `keywords` (top 10 by score for niche, best-effort)
- Produces:
  - `BLUEPRINT_SECTIONS = ("atm","titles","hook","narration","shots","audio","assets","capcut_steps","thumbnail","upload","recording_tips")`
  - `validate_blueprint(bp: dict, song_ids: set[int]) -> list[str]` — errors: missing section; `len(titles) != 5`; `len(thumbnail.concepts) != 3`; each concept needs `prompt`, `overlay_text` (≤ 4 words), `why_ctr`; `shots` and `narration.beats` non-empty; `audio.bgm_song_id` not in `song_ids` → set to `None` (not an error).
  - `build_blueprint_prompt(item: dict, ctx: dict, section: str | None = None) -> str` — Indonesian instructions; JSON-only output with the schema above; includes the originality rule "jangan memakai footage referensi sebagai materi"; for `voice_mode='self'` require `recording_tips`.
  - `POST /atm/items/{id}/blueprint` body `{section?: str}` → 409 `"Referensi belum dianalisa"` when no `video_analysis` row for `reference_url` and no `reference_url` analysis context at all (items without reference_url are allowed: blueprint from niche + learnings only); otherwise sets `blueprint_status='building'`, runs in `BackgroundTasks`, returns `{"status": "building"}`. Background: on success writes `blueprint` (full or merged single section), `blueprint_version+1`, `blueprint_status='ready'`, `stage` → `blueprint` if it was `idea`; on failure `blueprint_status='error'`, `blueprint_error` = short message, existing blueprint untouched.

- [ ] **Step 1: Failing tests:** `test_validate_blueprint_ok` (fixture `tests/fixtures/atm_blueprint_ok.json`), `test_validate_blueprint_wrong_title_count`, `test_validate_unknown_song_id_nulls`, `test_blueprint_409_without_analysis`, `test_blueprint_background_error_keeps_old` (patch `run_claude` → `"not json"`; assert UPDATE sets `blueprint_status='error'` and no UPDATE of `blueprint`), `test_blueprint_section_merge` (existing bp + section `hook` → only `hook` replaced).
- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `.venv/bin/python -m pytest -q tests/test_atm_blueprint.py` → PASS
- [ ] **Step 5:** Commit `feat(atm): blueprint generation`

### Task 4: AI voice per beat

**Files:**
- Create: `pipeline-api/atm/voice.py`
- Modify: `pipeline-api/main.py` `_SONG_KINDS` → `("song", "clip", "voiceover")` (Songs page filters by kind, so voiceovers stay out of both menus)
- Test: `pipeline-api/tests/test_atm_voice.py`

**Interfaces:**
- Consumes: `voiceover.voiceover.text_to_speech(text, output_path, ...)`, item `blueprint.narration.beats[].vo`
- Produces:
  - `GET /atm/items/{id}/voice/estimate` → `{"chars": int, "beats": int, "provider": "elevenlabs" | "gtts"}`
  - `POST /atm/items/{id}/voice` body `{beat?: int}` → 400 unless `voice_mode == 'ai'` and blueprint has beats; writes `data/songs/voiceover/<item_id>/beat_<NN>.mp3`, inserts/replaces `songs` rows (`kind='voiceover'`, `source='tts'`, `title='<item title> · beat N'`, `tags='["voiceover","item:<id>"]'`); returns `{"files": [{"beat", "song_id", "url": "/songs/<id>/download"}]}`
- [ ] **Step 1: Failing tests:** `test_voice_requires_ai_mode`, `test_voice_estimate_counts_chars`, `test_voice_generates_per_beat` (patch `text_to_speech` to write a dummy file; assert 2 inserts for 2 beats).
- [ ] **Step 2–4:** FAIL → implement → `.venv/bin/python -m pytest -q tests/test_atm_voice.py tests/test_songs.py` PASS (test_songs pre-existing import error is known; report if unchanged)
- [ ] **Step 5:** Commit `feat(atm): per-beat AI voiceover`

### Task 5: Frontend — navigation, Plan and Production pages

**Files:**
- Create: `dashboard-svelte/src/pages/Plan.svelte`, `dashboard-svelte/src/pages/Production.svelte`
- Modify: `dashboard-svelte/src/App.svelte` (NAV_GROUPS + routes), `src/lib/stores.js` (VALID_PAGES + `atmItemId` writable persisted to localStorage), `src/lib/api.js` (`atm*` functions), `src/locales/{id,en}.json` (`atm.*`, new `nav.*`)

**Interfaces:**
- Consumes: Task 2–4 endpoints
- Produces: page ids `today, plan, production, monitor, learn` (today/monitor/learn pages arrive in later tasks; routes registered there)
- NAV_GROUPS:
  - `nav.today` (Hari Ini): `today`
  - `nav.plan` (Rencana): `plan`
  - `nav.observe` (Amati): `discover, seo, creators, analysis, decompose, clipper`
  - `nav.production` (Produksi): `production`
  - `nav.monitor` (Pantau): `monitor`
  - `nav.library` (Pustaka): `songs, audio-clips, sources, prep`
  - `nav.learn` (Belajar): `learn`
  - `nav.settings` (Pengaturan): `cookies`
  - Default page becomes `today` (old `dashboard` stays routable).
- Plan page: routine settings form (PUT /atm/settings); "Konten baru" form (title, niche, reference URL, format, voice_mode); kanban columns = `STATUSES`; card click sets `atmItemId` and opens `production`.
- Production page: header (title, status select, scheduled_at, published_url input); tabs `Blueprint · Shot list · Narasi · Audio · Thumbnail · Upload · Evaluasi`; "Buat blueprint" + per-section "Buat ulang" (polls item every 3 s while `blueprint_status=='building'`); 409 shows "Analisa referensi dulu" button calling `api.analyzeClaudeAsync(reference_url)`; Thumbnail tab has copy buttons per prompt; Narasi tab: teleprompter for `self`, generate/preview per beat for `ai` with estimate shown first; Evaluasi tab placeholder filled in Task 8.

- [ ] **Step 1:** Implement; `cd dashboard-svelte && npm run build` → `✓ built`
- [ ] **Step 2:** Manual check with pipeline-api running: create item → appears in Plan → open Production → tabs render without console errors.
- [ ] **Step 3:** Commit including `analytics-dashboard/` bundle: `feat(atm): plan and production pages`

## Phase B — Schedule, Today, Evaluation (spec P2, P3)

### Task 6: Slots, autofill, Today, reminders, cron tick

**Files:**
- Create: `pipeline-api/atm/schedule.py`, `pipeline-api/atm/cron.py`, `scripts/com.reelbot.atm-tick.plist`
- Test: `pipeline-api/tests/test_atm_schedule.py`

**Interfaces:**
- Produces:
  - `next_slots(weekdays: list[int], post_time: str, tz: str, after: datetime, n: int, taken: set[datetime]) -> list[datetime]` (aware datetimes; skips `taken`)
  - `today_tasks(items: list[dict], now: datetime) -> list[dict]` — rules: `scheduled_at` within 3 days and status in (`idea`,`blueprint`,`shoot`) → `shoot`; status `edit` → `edit`; status `review` → `evaluate`; status in (`ready`,`scheduled`) and scheduled date == today (settings tz) → `upload`. Each `{item_id, title, action, scheduled_at}`.
  - `POST /atm/schedule/autofill` → assigns next free slots (14-day horizon) to items with status in (`blueprint`,`shoot`,`edit`,`review`,`ready`) and `scheduled_at IS NULL`, oldest first; `ready` → `scheduled`. Returns `{"assigned": [{item_id, scheduled_at}]}`
  - `GET /atm/today` → `{"tasks": [...], "alerts": [last 10 monitor_snapshots with alerted], "upcoming": [next 7 days scheduled items]}`
  - `send_reminders(now) -> int` — H-1 (scheduled_at between now+20h and now+28h, `reminded_d1_at IS NULL`) and day-of (scheduled_at today, `reminded_d0_at IS NULL`); marks column before sending; uses `main._telegram_notify`.
  - `POST /atm/cron/tick` (Depends `verify_admin_key`) → `{"reminders": int, "monitor": {...}, "post_evals": int}`; each job in its own try/except. Monitor/post-eval jobs are added in Task 9/10 (no-op until then).
  - plist: `StartInterval 900`, runs `/usr/bin/curl -s -X POST http://localhost:8000/atm/cron/tick` (adds `-H X-API-Key` only if `PIPELINE_API_KEY` set — document in plist comment).
- [ ] **Step 1: Failing tests:** `test_next_slots_mon_wed_fri_jakarta` (after Fri 2026-10-30 20:00 WIB → Mon 11-02 19:00, Wed 11-04 19:00, Fri 11-06 19:00 +07:00), `test_next_slots_skips_taken`, `test_today_tasks_rules` (one item per rule), `test_reminders_not_sent_twice` (second call returns 0), `test_tick_survives_job_exception`.
- [ ] **Step 2–4:** FAIL → implement → `.venv/bin/python -m pytest -q tests/test_atm_schedule.py` PASS
- [ ] **Step 5:** Commit `feat(atm): routine slots, today tasks, reminders, cron tick`

### Task 7: Draft upload

**Files:**
- Create: `pipeline-api/atm/evaluate.py` (upload part)
- Test: `pipeline-api/tests/test_atm_evaluate.py`

**Interfaces:**
- Produces: `POST /atm/items/{id}/draft` (multipart `file`) → ext check (400), size > 300 MB (413, partial file removed), filename ignored (UUID name), saves under `data/drafts/<id>/`, sets `draft_video_path`, status `review`; returns `{"draft_video_path": str}`. Streams to disk in 1 MB chunks.
- [ ] **Step 1: Failing tests:** `test_draft_rejects_txt_400`, `test_draft_rejects_oversize_413` (patch limit to 10 bytes), `test_draft_ignores_traversal_filename` (`../../x.mp4` saved inside `data/drafts/<id>/`), `test_draft_sets_review`.
- [ ] **Step 2–4:** FAIL → implement → PASS
- [ ] **Step 5:** Commit `feat(atm): draft upload`

### Task 8: Draft evaluation rounds

**Files:**
- Modify: `pipeline-api/atm/evaluate.py`
- Test: `pipeline-api/tests/test_atm_evaluate.py`

**Interfaces:**
- Consumes: `main._extract_frames_timed(video_path, out_dir, n=16)`, `main.ANALYZE_FRAME_DIR`, `run_claude(frames=[names], subdir="atm_<id>_r<round>")`
- Produces:
  - `transcribe(path: str) -> list[dict]` — faster-whisper `tiny`, `[{start, end, text}]`, `[]` on any failure
  - `audio_levels(path: str) -> dict` — ffmpeg `volumedetect` → `{"mean_db": float, "max_db": float}`, `{}` on failure
  - `EVAL_ASPECTS = ("hook","pacing","story","audio","text","thumbnail_fit","blueprint_fit","originality")`
  - `validate_evaluation(d: dict) -> list[str]` — every aspect score int 1..10; `findings` items need `t_start`, `t_end`, `aspect`, `issue`; `fixes` items need `no`, `instruction`; `summary` non-empty.
  - `POST /atm/items/{id}/evaluate` → 400 without `draft_video_path`; inserts `content_evaluations` row (`kind='draft'`, `round = max+1`, `status='building'`) and returns `{"evaluation_id", "round", "status": "building"}`; background fills scores/findings/fixes/summary/resolved_prev (prompt includes blueprint + previous round fixes) or sets `status='error'` + `error`.
  - `GET /atm/items/{id}/evaluations` → full rows, newest first
  - `PATCH /atm/evaluations/{eval_id}/notes` body `{"notes": [{"finding_index": int, "agree": bool, "note": str}]}`
  - Production page Evaluasi tab: upload, run, list rounds (Evaluasi 1, 2, …), scores, timestamped findings, fixes checklist, agree/disagree + note per finding, "resolved from previous round" line.
- [ ] **Step 1: Failing tests:** `test_validate_evaluation_score_range`, `test_evaluate_requires_draft_400`, `test_evaluate_round_increments` (existing max round 2 → new row round 3), `test_evaluate_bad_json_sets_error`.
- [ ] **Step 2–4:** FAIL → implement (+ frontend tab, `npm run build`) → PASS
- [ ] **Step 5:** Commit incl. bundle: `feat(atm): draft evaluation rounds`

## Phase C — Monitor + Learn (spec P4, P5)

### Task 9: Post-upload monitoring + Telegram alerts

**Files:**
- Create: `pipeline-api/atm/monitor.py`, `dashboard-svelte/src/pages/Monitor.svelte`
- Modify: `atm/cron.py` (call `run_monitor`), App routes for `monitor`
- Test: `pipeline-api/tests/test_atm_monitor.py`

**Interfaces:**
- Produces:
  - `CHECKPOINTS_H = (1, 6, 24, 48, 168)`; `FALLBACK_FRACTION = {1: 0.02, 6: 0.08, 24: 0.25, 48: 0.45, 168: 1.0}` of `main._PERF_TARGETS["youtube"]["views"]` (shorts) — long format uses the same until a long target exists.
  - `due_checkpoint(published_at: datetime, now: datetime, done: set[int]) -> int | None` — largest checkpoint ≤ age not in `done`, but only if it is greater than every checkpoint in `done` (missed earlier ones are skipped).
  - `fetch_public_stats(url: str) -> dict | None` — `yt-dlp --no-cookies --skip-download -J <url>` (timeout 60 s) → `{"views", "likes", "comments"}`; `None` on failure.
  - `baseline_views(checkpoint_h: int, exclude_item: int) -> float | None` — median of `monitor_snapshots.views` at that checkpoint from other items, `None` if < 3 rows.
  - `is_underperforming(views: int, baseline: float, ratio: float) -> bool` — `views < baseline * ratio`
  - `run_monitor(now: datetime) -> dict` — items with status `posted`, `published_url` and `published_at`; at most 20 per tick, random 2–5 s sleep between fetches; inserts snapshot (ON CONFLICT DO NOTHING); when under: Telegram message (title, checkpoint, views, baseline or target, ratio %, optional one-line diagnosis from `run_claude(model=ATM_LIGHT_MODEL)` — omitted if `None`), sets `alerted=true`. At checkpoint 168 sets status `monitored`.
  - `GET /atm/items/{id}/monitor` → snapshots ordered by checkpoint
  - Monitor page: posted/monitored items with checkpoint table + alert badges.
- [ ] **Step 1: Failing tests:** `test_due_checkpoint_skips_missed` (age 30 h, done {1} → 24; done {24}, age 30 → None), `test_baseline_none_under_three`, `test_fallback_used_without_baseline`, `test_alert_sent_once` (second run same checkpoint → no Telegram), `test_alert_without_diagnosis_when_bridge_down`, `test_fetch_public_stats_uses_no_cookies` (assert `--no-cookies` in argv).
- [ ] **Step 2–4:** FAIL → implement (+ page, build) → PASS
- [ ] **Step 5:** Commit incl. bundle: `feat(atm): post-upload monitoring and alerts`

### Task 10: Post evaluation + learnings + Today/Learn pages

**Files:**
- Create: `pipeline-api/atm/learn.py`, `dashboard-svelte/src/pages/Today.svelte`, `dashboard-svelte/src/pages/Learn.svelte`
- Modify: `atm/cron.py` (post-eval job), `atm/evaluate.py` (call `distill_learnings` after a draft eval succeeds), `atm/blueprint.py` (already reads learnings — verify `fix` kind included)
- Test: `pipeline-api/tests/test_atm_learn.py`

**Interfaces:**
- Produces:
  - `run_post_evaluation(item_id: int) -> int | None` — kind `post`, round max+1, prompt with snapshot series, blueprint, draft-eval summaries; no frames; sets `post_eval_done=true`; returns evaluation id.
  - `distill_learnings(item_id: int, evaluation_id: int) -> int` — `run_claude(model=ATM_LIGHT_MODEL)` → `{"learnings": [{"kind": "hook"|"pattern"|"insight"|"fix", "content": str}]}`, max 5, upserted with the existing `ON CONFLICT (niche, kind, md5(content))` statement pattern from `main.py` `/learnings` POST (`source_ids` gets the item id); returns count; 0 on any failure.
  - cron job: items with status `monitored` and `post_eval_done=false` → `run_post_evaluation` then `distill_learnings`.
  - `GET /atm/learn?niche=` → `{"learnings": [...top 50 by hits], "evaluations": [last 50 with item title]}`; `DELETE /atm/learnings/{id}`
  - Today page: tasks grouped by action, alerts, upcoming 7 days, "Isi jadwal otomatis" button (autofill). Learn page: learnings list (delete), evaluation history with links to Production.
- [ ] **Step 1: Failing tests:** `test_distill_upserts_max_five` (model returns 7 → 5 inserts), `test_distill_bad_json_returns_zero`, `test_post_eval_sets_done`, `test_cron_post_eval_runs_once`.
- [ ] **Step 2–4:** FAIL → implement (+ pages, build) → PASS
- [ ] **Step 5:** Commit incl. bundle: `feat(atm): post evaluation, learnings, today and learn pages`

### Task 11: Docs + end-to-end check

**Files:**
- Modify: `docs/NATIVE_SETUP.md` (postgres@18 path, claude-bridge in service table, atm-tick plist install line, `ATM_MODEL`/`ATM_LIGHT_MODEL`/`ELEVENLABS_API_KEY`/Telegram env names), `CLAUDE.md` if service list mentions n8n as required
- [ ] **Step 1:** Run every new test file: `.venv/bin/python -m pytest -q tests/test_atm_*.py tests/test_studio.py` → PASS
- [ ] **Step 2:** Live smoke with stack up: create item from a reference URL → blueprint ready → upload a short mp4 → Evaluasi 1 stored → set published_url → `curl -X POST localhost:8000/atm/cron/tick` returns JSON.
- [ ] **Step 3:** Commit `docs(atm): native setup for the creator studio`
