# Local-Native Installer — Design Spec

**Date:** 2026-07-01
**Status:** Approved (design), pending implementation plan
**Topic:** Replace the Docker-based bootstrap with a fully native local installer; keep Docker as a rollback path.

## 1. Goal

`npx reelbot-installer` stands up the entire Reelbot stack **natively** on a fresh machine — no Docker daemon required to run the stack. The installer detects the OS (macOS / Linux / Windows), installs native prerequisites, configures every controllable service to run as a host process, rewires service discovery to `localhost`, and supervises everything through a cross-platform Procfile.

The existing `docker-compose` files remain in the repo **untouched** as a documented rollback path. Native is the default and recommended path; Docker is the fallback.

## 2. Scope

### Services run natively (10)
| Service | Stack | Port | Native start |
|---|---|---|---|
| postgres | PostgreSQL 16 | 5432 | OS package + cluster init |
| cliproxy | Go binary (cli-proxy-api) | 8317 | prebuilt binary (fallback: `go build`) |
| openclaw | Node | 18789 | `npm ci` → start script |
| pipeline-api | Python 3 / FastAPI (uvicorn) | 8000 | `uv` venv → `uvicorn` |
| trends | Python / FastAPI | 8200 | `uv` venv → `uvicorn` |
| arcreel | Python 3.12 / FastAPI + React 19 frontend | 1241 | clone source → `uv sync` → build frontend → `uvicorn` |
| n8n | Node (npm package) | 5678 | `n8n` via global npm install |
| video-analyzer | Python (ffmpeg + whisper) | — (on-demand) | `uv` venv |
| video-splitter | Python (ffmpeg) | — (on-demand) | `uv` venv |
| yt-pipeline | Python (ffmpeg) | — (on-demand) | `uv` venv |

### Excluded from the local installer
- **nginx** — reverse proxy / subdomain routing is a public-VPS concern. Locally, each service is reachable directly on `localhost:PORT`.
- **certbot** — Let's Encrypt SSL, server-only.

Both remain in `docker-compose.yml` for the server/rollback path.

## 3. Architecture

The installer is a single Node script (`installer/index.js`, Node built-ins only — keeps `npx reelbot-installer` dependency-free). It grows from "clone + docker compose up" into a native provisioner with these stages:

1. **OS detection** — `process.platform` → `mac` | `linux` | `windows`, dispatching per-OS prereq logic.
2. **Prerequisite install** — via the native package manager only; never silently install a package manager itself, report and exit if missing:
   - **macOS:** Homebrew → `postgresql@16`, `node`, `python@3.12`, `uv`, `ffmpeg`, supervisor.
   - **Linux:** distro package manager (apt first; report if unsupported) → equivalents.
   - **Windows:** `winget` (fallback `choco`) → equivalents. Print a WSL2 recommendation (see §6).
3. **`.env` seeding** — extend the existing pure `seedEnv()`:
   - Keep secret auto-generation (`POSTGRES_PASSWORD`, `DASHBOARD_PASSWORD`, `N8N_ENCRYPTION_KEY`, `N8N_PASSWORD`) and the "still empty" API-key warnings.
   - **New native transform:** rewrite Docker service hostnames to `localhost` (`postgres:5432`→`localhost:5432`, `cliproxy:8317`→`localhost:8317`, `openclaw:18789`→`localhost:18789`, `pipeline-api:8000`→`localhost:8000`, `arcreel:1241`→`localhost:1241`, `trends:8200`→`localhost:8200`), and remap named-volume mounts to local directories (`./data/videos`, `./data/output`, `./data/<service>` …).
4. **Per-service provisioning** (idempotent — re-runnable):
   - **postgres:** ensure cluster, create `admin` user, create the three databases `arcreel`, `n8n`, `content_automation` (replicates `init-db.sh` / `POSTGRES_MULTIPLE_DATABASES`).
   - **Node services (openclaw):** `npm ci`.
   - **Python services (pipeline-api, trends, video-*, yt-pipeline):** `uv` venv + sync.
   - **arcreel:** clone `github.com/ArcReel/ArcReel` (pinned ref) → `uv sync` → build the React frontend → serve static + uvicorn.
   - **n8n:** install via npm.
   - **cliproxy:** download prebuilt binary for the OS/arch; fallback to `go build` if Go is present.
5. **Procfile generation** — write a `Procfile` with one entry per long-running service (postgres, cliproxy, openclaw, pipeline-api, trends, arcreel, n8n), each invoking its native start command with the right `PORT`. On-demand tools are excluded (invoked ad hoc).
6. **Supervision** — `node-foreman` runs the Procfile (cross-platform, works on Windows). `overmind` is offered as a Mac/Linux nicety but is never the default (it needs tmux).
7. **Health + done** — poll each service's health endpoint, then print the `localhost` URL map. `--skip-up` stops after provisioning without launching.

## 4. Data flow

- **Service discovery:** all inter-service URLs resolve to `localhost:PORT` (was Docker DNS hostnames). The `.env` native transform is the single source of truth for this mapping.
- **Shared storage:** `shared_videos` / `shared_output` Docker volumes become `./data/videos` / `./data/output` local dirs, referenced by every service that previously mounted them.
- **Database:** services connect to `localhost:5432` with the seeded `POSTGRES_PASSWORD`; three logical DBs as today.

## 5. Error handling

- Missing package manager (brew/winget/apt) → clear message with install link, exit non-zero. Never auto-install a package manager.
- Prereq install failure → surface the underlying command output, exit non-zero; installer is re-runnable (idempotent provisioning).
- Port already in use → detect before launch and report which service/port conflicts (host ports now bind directly; 80/443 are freed since nginx is excluded).
- API keys still empty after seeding → warn (as today), don't block — features degrade rather than fail the install.

## 6. Known caveats (carried into the plan)

- **ArcReel on Windows-native is partial** — upstream notes POSIX-only isolation degrades; basic workflows run but production wants WSL2. Installer prints a WSL2 recommendation on Windows.
- **`pipeline-api` "restart service" feature** currently calls the Docker socket (`/var/run/docker.sock`) to restart sibling containers. In native mode there is no socket; this must call the process supervisor (foreman/pm2) instead, or be disabled in native mode. Flagged for the plan.
- **cliproxy** native is a Go binary — prefer a pinned prebuilt release; `go build` only as fallback (avoids requiring Go on every machine).

## 7. Rollback

`docker-compose.yml`, `docker-compose.mac.yml`, the per-service `Dockerfile`s, `init-db.sh`, and the nginx/certbot configs are left intact. Reverting to Docker is `docker compose up -d` as before. The native installer adds files (Procfile, native provisioning in `index.js`, `data/` dirs) and does not delete the Docker path.

## 8. Out of scope

- Production/public serving (nginx, SSL, subdomains) — Docker/server path keeps these.
- Auto-installing OS package managers.
- A GUI; the installer is CLI.
