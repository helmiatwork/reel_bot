# Reelbot — Native Setup & Config (AI-readable)

This document lets an AI agent (or a human) understand and operate the Reelbot stack
**natively** (no Docker), and includes a ready-to-use operator prompt.

> The Docker path (`docker-compose*.yml`) still exists as a rollback. This doc is the
> **native** path. Since 2026-11-01 the stack is **two** launchd services: postgres and
> pipeline-api. The `claude` CLI runs inside pipeline-api (`pipeline-api/claude_runner.py`);
> there is no bridge, cliproxy, n8n, openclaw or arcreel process.

## 1. Services (ports + launchd jobs)

Run from the repo root (`~/Documents/repo/helmi/reelbot`). `.env` must exist (secrets seeded).

| Service | Port | launchd job (plist in `scripts/launchd/`) | Health |
|---|---|---|---|
| postgres | 5432 | `com.reelbot.postgres` (`postgres -D ./data/pg -p 5432`, foreground) | `psql -h localhost -U admin -l` |
| pipeline-api | 8000 | `com.reelbot.pipeline-api` (`sh scripts/start-pipeline-api.sh`, loads `.env`, serves `analytics-dashboard/` UI at `/`) | `curl localhost:8000/health` |
| dashboard (dev, optional) | 5180 | `cd dashboard-svelte && npm run dev` (Vite; proxies API → :8000) | open `localhost:5180` |

Optional: `scripts/com.reelbot.atm-tick.plist` calls `POST /atm/cron/tick` every 15 min (Telegram reminders, monitoring).

Dashboard health widget: `GET localhost:8000/dash/services` → `{live, total, services[]}` (postgres + pipeline-api).

### Install / start / restart (launchctl)

```bash
mkdir -p ~/Library/Logs/reelbot               # plists log here
pg_ctl -D data/pg -m fast stop                 # stop a hand-started postgres first
cp scripts/launchd/*.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.reelbot.postgres.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.reelbot.pipeline-api.plist

launchctl kickstart -k gui/$(id -u)/com.reelbot.pipeline-api   # restart pipeline-api
launchctl kickstart -k gui/$(id -u)/com.reelbot.postgres       # restart postgres
launchctl print gui/$(id -u)/com.reelbot.pipeline-api | head   # status
launchctl bootout gui/$(id -u)/com.reelbot.pipeline-api        # stop + unload
tail -f ~/Library/Logs/reelbot/pipeline-api.log ~/Library/Logs/reelbot/postgres.log
```

Foreground (no launchd): `sh scripts/start-pipeline-api.sh`.

## 2. Prerequisites (macOS)

- Homebrew packages: `postgresql@18` (must match `data/pg/PG_VERSION`), `node`, `python@3.12`, `uv`, `ffmpeg`.
- `claude` CLI **logged in** (`claude` → `/login`) — required for every Claude path (Clipper, analysis, ATM). The pipeline-api plist puts `~/.local/bin` and `/opt/homebrew/bin` on PATH; set `CLAUDE_BIN` in `.env` to pin another binary.
- Per-service deps: `npm ci` (dashboard), `uv sync` (pipeline-api). **pipeline-api venv**: `pip install scenedetect` for video decompose scene-cut detection, `pip install "mcp[cli]"` for the MCP server (Antigravity integration).

## 3. Config gotchas

1. **All service discovery = `localhost`**, not Docker hostnames.
2. **`DATABASE_URL`** must be in `.env`: `postgresql://admin:$POSTGRES_PASSWORD@localhost:5432/content_automation` (else postgres shows "down" and DB features no-op).
3. **SumoPod** (OpenAI-compatible gateway for the Gemini calls: SEO synthesis, audio tagging, Suno audio analysis): `.env` `SUMOPOD_KEY` (required) and `SUMOPOD_URL` (default `https://ai.sumopod.com/v1`). Models: `gemini/gemini-3.5-flash-lite` and `gemini/gemini-3.1-pro-preview` (the 2.5 models are no longer served). SumoPod is live/billable, no sandbox.
4. **claude runner** (`pipeline-api/claude_runner.py`): runs `claude -p … --model <claude-*-5-5> --output-format json` on the user's Claude subscription, inside the pipeline-api process. Only the 5.5 models are allowed. `CLAUDE_MAX_CONCURRENT` (default 2) caps parallel `claude` runs; extra callers wait for a slot with no time limit (`timeout_s` covers only the `claude` run). The cap is shared across processes (flock'd slot files in `tmp/claude-slots/`), so pipeline-api and every Antigravity MCP process together run at most `CLAUDE_MAX_CONCURRENT`. Set the same value in every process; if they differ, the largest one wins. Frames are read from `ANALYZE_FRAME_DIR` only. Do NOT pass unsupported flags (the CLI version must accept them).
5. **pipeline-api subprocess paths**: use `sys.executable` + repo paths (`yt-pipeline/yt_pipeline.py`), not `/app/...`. `yt_pipeline.py` uses `OUTPUT_DIR`/`VIDEOS_DIR` env (native default `./data/output`, `./data/videos`).
6. **macOS TCC**: the repo is under `~/Documents`, so a launchd job may hit "Operation not permitted". If a log in `~/Library/Logs/reelbot/` shows it, grant Full Disk Access to `/bin/sh`, the venv python (`realpath pipeline-api/.venv/bin/python`) and `/opt/homebrew/opt/postgresql@18/bin/postgres`. Fallback: start both by hand (`pg_ctl -D data/pg -w start`, `nohup sh scripts/start-pipeline-api.sh &`).

## 4. Flows

- **Clipper** (`/clips/find-claude`): fetch transcript (yt_pipeline, native) → `claude -p` Sonnet via `claude_runner` → ranked clips (each has `rank`; one `recommended:true`). Needs a captioned video + `claude` logged in.

## 5. AI operator prompt (paste into an agent)

```
You operate the Reelbot native stack (repo: ~/Documents/repo/helmi/reelbot). It runs
WITHOUT Docker as two launchd services: postgres (:5432) and pipeline-api (:8000).
Read docs/NATIVE_SETUP.md for the service table, launchctl commands, and config gotchas.

Rules:
- Everything is localhost; never use Docker hostnames (postgres, host.docker.internal).
- pipeline-api uses its own venv python + repo paths (no /app/...).
- Claude calls run in-process via pipeline-api/claude_runner.py (`claude -p`, needs the
  claude CLI logged in). Gemini calls go to SumoPod (SUMOPOD_URL / SUMOPOD_KEY).
- Before claiming a service is up, verify via `GET localhost:8000/dash/services` or the port.
- To bring the stack up: bootstrap com.reelbot.postgres then com.reelbot.pipeline-api with
  launchctl (commands in §1). Then confirm 2/2 live.
- Secrets live in .env (gitignored) — never commit them.

When asked to clip a video: POST /clips/find-claude {"youtube_url":"..."}.
```
