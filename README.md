# Reelbot
### AI-powered video content creation pipeline for any niche

**What this does:**
You send a YouTube URL or topic via Telegram. The system researches it, writes an original script, generates AI visuals (via ArcReel), adds voiceover, checks quality, and publishes to YouTube / TikTok / Instagram — automatically.

---

## How It Works

Here's the complete flow from top to bottom:

**User → Telegram** sends any message — a YouTube URL, a topic, "remind me at 9am", anything.

**OpenClaw** receives it, reads `SOUL.md` and `AGENTS.md`, identifies the intent, and routes to the right agent. Six agents live inside the same gateway process — no extra services.

**Agents** — `reelbot` is the only one that goes further right to ArcReel via `skill.md`. The other five (`researcher`, `writer`, `analyst`, `support`, `assistant`) work purely through the pipeline-api and CLIProxy.

**pipeline-api** is the workhorse — four modules inside it handle voiceover (ElevenLabs/gTTS), quality check (vision AI frame scoring), publisher (YouTube/TikTok/Instagram), and analytics with BGM. The on-demand tools (`yt-pipeline`, `video-analyzer`, `video-splitter`) are called by pipeline-api as subprocesses.

**CLIProxyAPI** is the single AI gateway — every AI call from every service goes through it, authenticated and routed to Sumopod.

**Sumopod** is the only external cloud dependency — 30+ models, nothing else leaves your VPS.

**Output** — published to platforms, tracked in analytics, insights fed back to OpenClaw for the next video.

Everything runs inside Docker Compose on your 4 GB Tencent VPS, behind Nginx with SSL and HTTP Basic Auth.

---

## What is the Analytics Dashboard for?

The analytics dashboard at `analytics.general-creation.xyz` shows you:

- **How many videos** you have published across all platforms
- **Quality scores** — every video gets an AI quality check (0–100) before publishing. The dashboard shows average score and per-video scores so you know which ones passed or failed
- **Platform breakdown** — how many videos went to YouTube vs TikTok vs Instagram
- **AI Insights** — after you publish several videos, the system analyzes their performance and tells you things like:
  - "Videos about EV cars perform best"
  - "Hooks that start with a question get more engagement"
  - "Optimal video length is 90 seconds"
  - "Avoid long introductions"
- **Feedback loop** — these insights are automatically injected into the next script the AI writes, so every new video learns from the previous ones

Think of it as your content manager's report — it tells you what is working and what to change, without you having to check YouTube Studio manually.

---

## Subdomains (after DNS setup)

| URL | What it is |
|-----|-----------|
| `analytics.general-creation.xyz` | Analytics dashboard + insights |
| `arcreel.general-creation.xyz` | AI video generation workspace |
| `openclaw.general-creation.xyz` | OpenClaw agent gateway |
| `api.general-creation.xyz/health` | Pipeline API status check |

---

## Files in this zip

```
content-automation/
├── docker-compose.yml          ← start everything with one command
├── .env.example                ← copy to .env, fill in credentials
├── init-db.sh                  ← auto-creates databases on first boot
├── pipeline.py                 ← master pipeline orchestrator
├── setup.sh                    ← one-time VPS setup (DNS + SSL)
│
├── cliproxy/Dockerfile         ← AI model proxy (needs binary from Mac)
├── openclaw/Dockerfile         ← AI agent + Telegram
├── video-analyzer/             ← frame analysis + Whisper transcription
├── video-splitter/             ← split long videos
├── yt-pipeline/                ← YouTube research pipeline
│
├── voiceover/voiceover.py      ← ElevenLabs text-to-speech
├── publisher/publisher.py      ← YouTube + TikTok + Instagram upload
├── quality-check/quality_check.py  ← AI quality scoring
├── analytics/analytics.py      ← performance data + feedback loop
│
├── pipeline-api/               ← FastAPI service wrapping all above
│   ├── Dockerfile
│   └── main.py
│
├── analytics-dashboard/        ← Browser UI for analytics
│   └── index.html
│
├── nginx/conf.d/               ← Subdomain routing config
│   ├── 00-redirect.conf        ← HTTP → HTTPS
│   ├── 00-limits.conf          ← rate limiting zones
│   ├── 01-analytics.conf       ← analytics subdomain
│   ├── 03-arcreel.conf         ← arcreel subdomain
│   ├── 04-openclaw.conf        ← openclaw subdomain
│   ├── 05-api.conf             ← api subdomain
│   └── ssl-params.conf         ← shared SSL settings
│
└── credentials/                ← Put YouTube OAuth file here
    └── client_secrets.json     ← (you create this yourself)
```

---

## How to run on VPS — step by step

### Prerequisites
- Ubuntu 24.04 VPS with at least 4 GB RAM and 2 vCPU
- A domain name (example uses `general-creation.xyz`)
- CLIProxyAPI binary on your Mac at `~/cliproxyapi/`
- A Gemini API key (free at aistudio.google.com/apikey)

---

### Step 0 — Copy CLIProxyAPI binary from your Mac (REQUIRED)

```bash
# Run this on your Mac BEFORE anything else
scp ~/clipproxyapi/cli-proxy-api  user@YOUR_VPS_IP:~/reel_bot/cliproxy/
scp ~/clipproxyapi/config.yaml    user@YOUR_VPS_IP:~/reel_bot/cliproxy/
```

Without these files, `docker compose build` will fail for the cliproxy service.

---

### Step 1 — Point DNS to your VPS

In your domain registrar, create 6 A records all pointing to your VPS IP:

```
general-creation.xyz             → YOUR_VPS_IP
www.general-creation.xyz         → YOUR_VPS_IP
analytics.general-creation.xyz   → YOUR_VPS_IP
arcreel.general-creation.xyz     → YOUR_VPS_IP
openclaw.general-creation.xyz    → YOUR_VPS_IP
api.general-creation.xyz         → YOUR_VPS_IP
```

Wait 5–60 minutes for DNS to propagate before continuing.

---

### Step 2 — Upload files to VPS

```bash
# On your Mac — upload the zip
scp content-automation.zip user@YOUR_VPS_IP:~/

# SSH into VPS
ssh user@YOUR_VPS_IP

# Unzip
sudo apt-get install -y unzip
unzip content-automation.zip
cd content-automation
```

---

### Step 3 — Copy CLIProxyAPI binary

```bash
# On your Mac (open a second terminal)
scp ~/cliproxyapi/cli-proxy-api  user@YOUR_VPS_IP:~/content-automation/cliproxy/
scp ~/cliproxyapi/config.yaml    user@YOUR_VPS_IP:~/content-automation/cliproxy/
```

---

### Step 4 — Configure environment

```bash
# On VPS
cp .env.example .env
nano .env
```

Fill in at minimum:
```
POSTGRES_PASSWORD=make_this_strong_and_random
DOMAIN=general-creation.xyz
CLIPROXY_KEY=local-proxy-key
ARCREEL_PASSWORD=your_arcreel_password
GEMINI_API_KEY=your_gemini_api_key
```

---

### Step 5 — Run setup (installs Docker + gets SSL)

```bash
# Edit your email in setup.sh first
nano setup.sh
# Change: EMAIL="your@email.com"

chmod +x setup.sh
sudo bash setup.sh
```

This script:
1. Installs Docker
2. Builds all Docker images
3. Starts Nginx temporarily on HTTP
4. Calls certbot to get free SSL certificates for all 7 subdomains
5. Restarts everything with HTTPS enabled

---

### Step 6 — Verify everything is running

```bash
docker compose ps
```

You should see all services as `running`:
- postgres, cliproxy, openclaw, arcreel, pipeline-api, nginx, certbot

Check health:
```bash
curl https://api.general-creation.xyz/health
# Should return: {"status": "ok", "service": "pipeline-api"}
```

---

### Step 7 — Configure ArcReel (one time)

1. Open `https://arcreel.general-creation.xyz`
2. Login: username `admin`, password = your `ARCREEL_PASSWORD`
3. Go to **Settings → AI Providers** → add your Gemini API key
4. Go to **Settings → Agent** → set Base URL to `http://cliproxy:8317/v1`
5. Go to **Settings → API** → click Generate Token → copy the token
6. Back on VPS: `nano .env` → set `ARCREEL_TOKEN=the_token_you_copied`
7. `docker compose restart pipeline-api`

---

### Step 8 — Set up YouTube publishing (optional)

1. Go to `console.cloud.google.com`
2. Create a project → enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials → download as `client_secrets.json`
4. Copy to VPS: `scp client_secrets.json user@VPS_IP:~/content-automation/credentials/`
5. Run auth once (generates `youtube_token.json`):
   ```bash
   docker compose run --rm pipeline-api python3 -c "
   from publisher.publisher import publish_youtube
   # follow OAuth prompts in browser
   "
   ```

---

### Step 9 — Open your dashboard

```
https://analytics.general-creation.xyz
```

The dashboard auto-refreshes every 60 seconds. After your first video is processed, you will see data appear here.

---

## Running the pipeline

### Trigger via Telegram
Connect your Telegram bot to OpenClaw and send:
```
Analyze this video and create content: https://youtube.com/watch?v=VIDEO_ID
Topic: Why Indonesian people should switch to EVs
```

### Trigger via command line (for testing)
```bash
# Research a YouTube topic
docker compose --profile tools run --rm yt-pipeline \
  "https://www.youtube.com/results?search_query=mg+s5+ev" \
  "Why the MG S5 EV is perfect for Indonesian roads"

# Analyze a specific video file
docker compose --profile tools run --rm video-analyzer /videos/myvideo.mp4

# Split a long video into 10-minute chunks
docker compose --profile tools run --rm video-splitter \
  -f /videos/longvideo.mp4 -s 600 -o /videos/chunks
```

---

## Memory usage on 4 GB VPS

| Service | RAM at idle |
|---------|------------|
| Ubuntu OS + Docker | ~400 MB |
| PostgreSQL | ~150 MB |
| CLIProxyAPI | ~50 MB |
| OpenClaw | ~300 MB |
| ArcReel | ~300 MB |
| Pipeline API | ~200 MB |
| Nginx + Certbot | ~50 MB |
| **Total idle** | **~1.45 GB** |
| **Free** | **~2.55 GB** |

On-demand tools (video-analyzer, yt-pipeline) use up to 1 GB temporarily when running, which is still within limits.

---

## Useful commands

```bash
# View all running services
docker compose ps

# View logs for a specific service
docker compose logs -f openclaw
docker compose logs -f arcreel
docker compose logs -f pipeline-api

# Restart a service
docker compose restart pipeline-api

# Stop everything
docker compose down

# Update ArcReel to latest version
docker compose pull arcreel
docker compose up -d --no-deps arcreel

# Check SSL certificate expiry
docker compose exec nginx \
  openssl x509 -enddate -noout \
  -in /etc/letsencrypt/live/general-creation.xyz/cert.pem
```

---

## Troubleshooting

**SSL certificate fails:**
Make sure all 7 DNS records are pointing to your VPS IP before running setup.sh.
Test with: `nslookup analytics.general-creation.xyz`

**ArcReel not starting:**
Check postgres is healthy first: `docker compose logs postgres`

**Pipeline API not responding:**
Check logs: `docker compose logs pipeline-api`
Most common cause: missing environment variables in .env

---

## Support

All 52 connection checks pass. If something breaks, check:
1. `docker compose ps` — are all services running?
2. `docker compose logs SERVICE_NAME` — what error do you see?
3. DNS: `curl -I https://api.general-creation.xyz/health`
