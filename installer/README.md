# reelbot-installer

One command to stand up the Reelbot stack on a new machine. **Default: native mode** (no Docker required to run the stack). Fallback: Docker Compose.

```bash
npx reelbot-installer
```

## Native mode (default)

Runs the entire Reelbot stack as host processes (PostgreSQL, Node services, Python services, ArcReel, n8n) using a cross-platform Procfile supervisor. Docker is not required — the stack runs natively on your machine.

```bash
npx reelbot-installer --native      # explicitly use native (default)
npx reelbot-installer --dry-run     # preview the provisioning plan
npx reelbot-installer --skip-up     # install prereqs + build but don't launch supervisor
```

## Docker rollback

If native provisioning fails or you prefer Docker:

```bash
npx reelbot-installer --docker      # use docker compose (legacy path)
```

This runs the existing `docker compose up -d --build` path unchanged. Note: nginx and SSL (certbot) are Docker-only features; native mode runs each service directly on `localhost:PORT`.

## Usage

```bash
npx reelbot-installer [dir]            # default dir: ./reelbot; uses native mode
npx reelbot-installer --dir myapp
npx reelbot-installer --ref some-branch
npx reelbot-installer --repo git@host:owner/repo.git
npx reelbot-installer --native --dry-run     # preview without making changes
npx reelbot-installer --native --skip-up     # install + build, don't launch
npx reelbot-installer --docker               # fallback to docker compose
```

## Prerequisites on a fresh machine (native mode)

- macOS: **Homebrew** (https://brew.sh)
- Linux: **apt-get** (Debian/Ubuntu)
- Windows: **winget** or WSL2 recommended for ArcReel

For Docker mode:
- **Docker Desktop** (or colima) running
- **git + SSH access** to the private repo

## Service ports (native mode)

After `npx reelbot-installer`, the stack runs as:

- http://localhost:8000 — Pipeline API (dashboard + voiceover + publisher)
- http://localhost:5678 — n8n (automation)
- http://localhost:1241 — ArcReel (video editing)
- http://localhost:18789 — Openclaw (telegram integration)
- http://localhost:8200 — Trends (keyword research)
- http://localhost:5432 — PostgreSQL (local cluster in `./data/pg`)
- http://localhost:8317 — Cliproxy (forward proxy)

## Develop / verify

```bash
npm run selfcheck   # asserts the .env seeding logic
```

## Publish

```bash
cd installer
npm publish --access public
```
