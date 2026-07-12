# Reelbot — Native Setup & Config (AI-readable)

This document lets an AI agent (or a human) understand and operate the Reelbot stack
**natively** (no Docker), and includes a ready-to-use operator prompt. It reflects the
real, verified working configuration.

> The Docker path (`docker-compose*.yml`) still exists as a rollback. This doc is the
> **native** path: every service runs as a host process on `localhost`.

## 1. Services (ports + start commands)

Run from the repo root (`~/Documents/repo/helmi/reelbot`). `.env` must exist (secrets seeded).

| Service | Port | Start command (native, verified) | Health |
|---|---|---|---|
| postgres | 5432 | `pg_ctl -D ./data/pg -o "-p 5432" -w -l ./data/pg/server.log start` | `psql -h localhost -U admin -l` |
| cliproxy | 8317 | `./data/bin/cli-proxy-api -config ./cliproxy/config.yaml` | `curl localhost:8317/v1/models` |
| openclaw | 18789 | `openclaw gateway --port 18789` (Node — brew) | log: `starting provider (@…)` |
| pipeline-api | 8000 | `sh scripts/start-pipeline-api.sh` (loads `.env`, serves `analytics-dashboard/` UI at `/`) | `curl localhost:8000/health` |
| arcreel | 1241 | `cd data/arcreel && ./.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 1241` | `curl localhost:1241` |
| n8n | 5678 | run under **Node 22** with DB env (see §3) | `curl localhost:5678/healthz` |
| claude bridge | 9999 | `CLAUDE_BIN=/opt/homebrew/bin/claude sh scripts/start-bridge.sh` | `curl localhost:9999` |
| dashboard (dev) | 5180 | `cd dashboard-svelte && npm run dev` (Vite; proxies API → :8000) | open `localhost:5180` |

Dashboard health widget: `GET localhost:8000/dash/services` → `{live, total, services[]}` (all probe `localhost`).

## 2. Prerequisites (macOS)

- Homebrew packages: `postgresql@16`, `node`, **`node@22`** (n8n only — see §3), `python@3.12`, `uv`, `ffmpeg`, `go` (optional, cliproxy build).
- `claude` CLI (`/opt/homebrew/bin/claude`) **logged in** (`claude` → `/login`) — required for the Clipper/analysis paths that use `claude -p`.
- Per-service deps: `npm ci`/`install` (openclaw, dashboard, arcreel frontend via **pnpm**), `uv sync` (python services), cliproxy prebuilt binary at `./data/bin/cli-proxy-api`. **pipeline-api venv**: `pip install scenedetect` for video decompose scene-cut detection, `pip install "mcp[cli]"` for MCP server (Antigravity integration).

## 3. Config gotchas (Docker→native — the non-obvious parts)

These are the settings that differ from Docker and MUST be right natively:

1. **All service discovery = `localhost`**, not Docker hostnames. `.env` `nativeEnv` rewrites `postgres:5432`→`localhost:5432`, `cliproxy:8317`→`localhost:8317`, etc. If you see `host.docker.internal` or a bare service name, it will fail natively.
2. **`DATABASE_URL`** must be in `.env`: `postgresql://admin:$POSTGRES_PASSWORD@localhost:5432/content_automation` (else postgres shows "down" and DB features no-op).
3. **`CLAUDE_BRIDGE_URL=http://localhost:9999`** in `.env` (default is `host.docker.internal:9999`, which doesn't resolve for a native process).
4. **n8n runs on Node 22** — its `isolated-vm` dep won't compile on Node 26. Install + run via `/opt/homebrew/opt/node@22/bin`. Inject DB env (NOT in `.env`): `DB_TYPE=postgresdb DB_POSTGRESDB_HOST=localhost DB_POSTGRESDB_PORT=5432 DB_POSTGRESDB_DATABASE=n8n DB_POSTGRESDB_USER=admin DB_POSTGRESDB_PASSWORD=$POSTGRES_PASSWORD`. **`N8N_ENCRYPTION_KEY`** must equal the key in `~/.n8n/config` (read it verbatim), or n8n crashes "Mismatching encryption keys".
5. **openclaw config** (`~/.openclaw/openclaw.json`): agent `workspace` must be under `$HOME` (not `/root/...`); `providers.cliproxy.baseUrl` = `http://localhost:8317/v1`; agent `model` = `cliproxy/deepseek-v4-pro` (all openclaw agents route to deepseek-v4-pro).
6. **cliproxy** (`cliproxy/config.yaml`, gitignored): inbound `api-keys[0]` must equal `.env` `CLIPROXY_KEY` (openclaw sends that); upstream `openai-compatibility` → `base-url: https://ai.sumopod.com/v1` + a valid sumopod key. Sumopod is live/billable, no sandbox.
7. **claude bridge** (`scripts/claude_bridge.py`): runs `claude -p … --model claude-sonnet-4-6 --output-format json` = the user's Claude subscription. Do NOT pass unsupported flags (the CLI version must accept them).
8. **pipeline-api subprocess paths**: use `sys.executable` + repo paths (`yt-pipeline/yt_pipeline.py`), not `/app/...`. `yt_pipeline.py` uses `OUTPUT_DIR`/`VIDEOS_DIR` env (native default `./data/output`, `./data/videos`).

## 4. Flows

- **Telegram bot**: openclaw long-polls Telegram (`getUpdates`, no webhook/ngrok). Message → openclaw agent (deepseek-v4-pro via cliproxy→sumopod) → reply. Bot = @HReelBot.
- **Clipper** (`/clips/find-claude`): fetch transcript (yt_pipeline, native) → `claude -p` Sonnet via bridge → ranked clips (each has `rank`; one `recommended:true`). Needs a captioned video + `claude` logged in.
- **Snoop** (`/snoop/*` + n8n `n8n/workflows/snoop.json`): daily 08:00 → for each watched channel, detect new upload → auto-run Clipper → store results (top clip recommended). Add targets in the Snoop dashboard page; import the n8n workflow once to arm the schedule.

## 5. AI operator prompt (paste into an agent)

```
You operate the Reelbot native stack (repo: ~/Documents/repo/helmi/reelbot). It runs
WITHOUT Docker — every service is a host process on localhost. Read docs/NATIVE_SETUP.md
for the service table, start commands, and config gotchas.

Rules:
- Everything is localhost; never use Docker hostnames (postgres, cliproxy, host.docker.internal).
- n8n only runs on Node 22; its N8N_ENCRYPTION_KEY must match ~/.n8n/config.
- pipeline-api uses its own venv python + repo paths (no /app/...).
- The Clipper and video-analysis paths call `claude -p` via the bridge on :9999 (needs the
  claude CLI logged in). All openclaw chat/agent models = cliproxy/deepseek-v4-pro.
- Before claiming a service is up, verify via `GET localhost:8000/dash/services` or the port.
- To bring the stack up: start postgres, cliproxy, openclaw, pipeline-api, arcreel, n8n
  (Node 22), and the claude bridge, using the exact commands in §1. Then confirm 6/6 live.
- Secrets live in .env / ~/.openclaw / cliproxy/config.yaml (gitignored) — never commit them.

When asked to add a watched channel: POST /snoop/targets {"channel":"@handle-or-url"}.
When asked to clip a video: POST /clips/find-claude {"youtube_url":"..."}.
```
