# Antigravity ← Reelbot MCP Integration

Reelbot exposes a **Model Context Protocol (MCP) server** so Antigravity (an MCP client) can pull corpus analysis and generate shot-prompts + production briefs via Claude, feeding those into Gemini for media generation.

## Architecture

```
telegram / user input
     ↓
  reelbot pipeline-api (analyze + store)
     ↓
  sources, video_analysis, video_segments tables
     ↓
Antigravity (MCP client)
  ├─ list_sources() ← fetch recent corpus
  ├─ get_analysis(url) ← pull analysis (hook, structure, retention_score, tags)
  ├─ get_segments(source_id) ← pull clip timecodes
  ├─ generate_shot_prompts(script) ← Claude → Imagen/Veo prompts
  └─ make_brief(analysis) ← Claude → Production Brief
     ↓
  Gemini (Imagen → Veo) + CapCut
     ↓
  final short-form video
```

**Scope:**
- Reelbot: analyze + corpus prep + shot-prompt/brief generation (Claude via bridge)
- Antigravity: orchestration, Gemini Imagen/Veo invocation, asset management
- Human: final edit in CapCut or external editor

## MCP Server Configuration

### Location
```
/path/to/reelbot/mcp/reelbot_mcp.py
```

### Environment Setup (Antigravity host)

```bash
# Set before running Antigravity
export DATABASE_URL="postgresql://user:pass@localhost:5432/reelbot"
export CLAUDE_BRIDGE_URL="http://localhost:9999"  # optional; defaults to localhost:9999
```

### Claude.ai / Antigravity Settings

Add this server to your MCP configuration (e.g., in Claude settings or Antigravity's MCP config file):

```json
{
  "mcpServers": {
    "reelbot": {
      "command": "/path/to/reelbot/pipeline-api/.venv/bin/python",
      "args": ["/path/to/reelbot/mcp/reelbot_mcp.py"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/reelbot",
        "CLAUDE_BRIDGE_URL": "http://localhost:9999"
      }
    }
  }
}
```

Or via `~/.claude/models.json` (Claude.ai native MCP):
```json
{
  "tools": [
    {
      "type": "model_context_protocol",
      "name": "reelbot",
      "config": {
        "command": "/absolute/path/to/reelbot/pipeline-api/.venv/bin/python",
        "arguments": ["/absolute/path/to/reelbot/mcp/reelbot_mcp.py"],
        "environment": {
          "DATABASE_URL": "postgresql://...",
          "CLAUDE_BRIDGE_URL": "http://localhost:9999"
        }
      }
    }
  ]
}
```

## API Reference

All tools return JSON. On error, tools return `{"error": "<message>", ...}` rather than raising.

### `list_sources(limit: int = 25) → dict`

List recent sources (videos analyzed and stored in the corpus).

**Args:**
- `limit` (int, optional): number of sources to return, clamped to 1–100. Defaults to 25.

**Returns:**
```json
{
  "sources": [
    {
      "id": 1,
      "youtube_url": "https://youtube.com/watch?v=...",
      "title": "My Viral Video",
      "niche": "tech",
      "platform": "youtube",
      "status": "analyzed",
      "channel": "MyChannel"
    }
  ],
  "count": 5
}
```

**Example:**
```python
result = call_tool("list_sources", {"limit": 10})
for source in result["sources"]:
    print(f"{source['id']}: {source['title']} ({source['niche']})")
```

---

### `get_analysis(youtube_url: str) → dict`

Get the latest analysis for a video (hook, structure, retention score, tags).

**Args:**
- `youtube_url` (str, required): the YouTube URL to look up

**Returns:**
```json
{
  "analysis": {
    "youtube_url": "https://youtube.com/watch?v=...",
    "hook": "Curiosity gap — why did she do this?",
    "structure": "3-beat: setup, reveal, reaction",
    "retention": [45, 60, 80, 75],
    "retention_score": 8,
    "tags": ["viral", "reaction", "mystery"],
    "model": "claude-sonnet-4-6",
    "cost_usd": 0.08
  }
}
```

If not found: `{"error": "analysis not found", "analysis": {}}`

**Example:**
```python
result = call_tool("get_analysis", {"youtube_url": "https://youtube.com/watch?v=abc123"})
analysis = result["analysis"]
if analysis:
    print(f"Hook: {analysis['hook']}")
    print(f"Retention score: {analysis['retention_score']}/10")
    print(f"Tags: {', '.join(analysis['tags'])}")
```

---

### `get_segments(source_id: int) → dict`

Get clip segments (timecoded cuts) for a video.

**Args:**
- `source_id` (int, required): the source ID (from `list_sources`)

**Returns:**
```json
{
  "source_id": 1,
  "segments": [
    {
      "clip_index": 0,
      "start_sec": 2.5,
      "end_sec": 5.0,
      "credit_handle": "@creator",
      "original_url": "https://youtube.com/watch?v=orig1",
      "origin_status": "found",
      "confidence": 0.95,
      "segment_path": "/data/segments/source_1_clip_0.mp4"
    }
  ],
  "count": 3
}
```

If source not found: `{"error": "query failed: ...", "segments": [], "count": 0}`

**Example:**
```python
result = call_tool("get_segments", {"source_id": 1})
for seg in result["segments"]:
    print(f"Clip {seg['clip_index']}: {seg['start_sec']}–{seg['end_sec']}s @ {seg['segment_path']}")
```

---

### `generate_shot_prompts(script_text: str, style_note: str = "") → dict`

Generate per-beat Imagen + Veo prompts from a script using the Shot-Prompt agent methodology.

Reads `openclaw/agents/shotprompt/SOUL.md`, builds a prompt, and calls Claude via the bridge.

**Args:**
- `script_text` (str, required): beat-by-beat script (visual intent + VO + caption + timing per beat)
- `style_note` (str, optional): mood/palette guidance (e.g., "cinematic, blue tones, 35mm film stock")

**Returns:**
```json
{
  "prompts": "STYLE LOCK: cinematic, 9:16 vertical, cool blue tones, 35mm film stock\n\nShot 1 — 0–3s · source: GENERATE\n  🖼️ IMAGE: ...\n  🎞️ ANIMATE: ...\n  💬 caption: ...",
  "model": "claude-sonnet-4-6"
}
```

On error: `{"error": "<reason>", "prompts": ""}`

**Error cases:**
- SOUL file not found → `"shotprompt/SOUL.md not found"`
- Claude bridge unreachable → `"bridge connection error: ..."`
- Bridge returns `ok: false` → `"<bridge error message>"`

**Example:**
```python
script = """
Beat 1 — Hook (0–2s)
  Visual: Close-up of eyes widening in shock
  VO: "Wait, you can do what??"
  Caption: "POV: You just learned a life hack"

Beat 2 — Payoff (2–5s)
  Visual: Quick montage of the hack in action
  VO: "Saves you 10 minutes every single day."
  Caption: "That's 60+ hours a year!"
"""

result = call_tool("generate_shot_prompts", {
    "script_text": script,
    "style_note": "faceless, bright, energetic, quick cuts"
})

if "error" not in result or not result["error"]:
    print(result["prompts"])
    # Now paste these into Gemini to generate with Imagen → Veo
```

---

### `make_brief(analysis_json: str, target: str = "") → dict`

Generate a Production Brief from video analysis using the Content Director methodology.

Reads `openclaw/agents/director/SOUL.md`, builds a prompt with analysis + optional target, and calls Claude via the bridge.

**Args:**
- `analysis_json` (str, required): JSON string of `video_analysis` dict (from `get_analysis`)
- `target` (str, optional): target audience/niche/platform (e.g., "tech-savvy 18–24 / Shorts / high-energy")

**Returns:**
```json
{
  "brief": "🎬 BRIEF: Life Hack Explosion\nFormula: pattern-interrupt → payoff...\nAngle: ...\n...",
  "model": "claude-sonnet-4-6"
}
```

On error: `{"error": "<reason>", "brief": ""}`

**Example:**
```python
# Get analysis
analysis_result = call_tool("get_analysis", {"youtube_url": "https://youtube.com/watch?v=xyz"})
analysis = analysis_result["analysis"]

# Generate brief
brief_result = call_tool("make_brief", {
    "analysis_json": json.dumps(analysis),
    "target": "faceless creators / TikTok / millennial women 20–35"
})

if not brief_result.get("error"):
    print(brief_result["brief"])
    # Scriptwriter and clipfinder agents now have direction
```

---

### `analyze(youtube_url: str, intent: str = "") → dict`

Run a fresh Claude-vision analysis of a YouTube video and save it to the corpus DB.

**Important:** This is a synchronous call that may take 1–2 minutes (video download + frame extraction + Claude vision). Requires the pipeline-api service to be running.

**Args:**
- `youtube_url` (str, required): the YouTube video URL to analyze
- `intent` (str, optional): context or intent for the analysis (e.g., "find viral hooks", "analyze pacing")

**Returns:**
```json
{
  "youtube_url": "https://youtube.com/watch?v=...",
  "hook": "Curiosity gap — why did she do this?",
  "structure": "3-beat: setup, reveal, reaction",
  "retention": [45, 60, 80, 75],
  "retention_score": 8,
  "tags": ["viral", "reaction", "mystery"],
  "model": "claude-sonnet-4-6",
  "cost_usd": 0.08,
  "cached": false
}
```

On error: `{"error": "<reason>"}`

**Error cases:**
- Invalid URL (not http/https) → `"invalid youtube_url"`
- Pipeline API unreachable → `"pipeline-api unreachable: ..."`
- Pipeline API timeout → `"pipeline-api timeout (analysis may still be running): ..."`
- Frame extraction failed → `"Frame extraction failed: ..."`
- Video unreadable → `"No frames could be extracted from the video"`

**Example:**
```python
result = call_tool("analyze", {
    "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "intent": "find the viral hook moment"
})

if "error" not in result or not result["error"]:
    analysis = result
    print(f"Hook: {analysis['hook']}")
    print(f"Retention score: {analysis['retention_score']}/10")
    print(f"Cost: ${analysis['cost_usd']:.2f}")
    print(f"Cached: {analysis.get('cached', False)}")
    # Now use this analysis with get_analysis() or make_brief()
else:
    print(f"Analysis failed: {result['error']}")
```

**Caching:** If the same URL has been analyzed before, pipeline-api returns the cached result with `"cached": true` and skips re-analysis.

**When to use:**
- Fresh video added to corpus that needs analysis
- Re-analyze an existing URL with `force=true` (pass via intent if needed)
- Antigravity wants independent analysis without waiting for batch jobs

---

## Workflow Example

### Step 1: Browse the Corpus

```python
sources_result = call_tool("list_sources", {"limit": 5})
for source in sources_result["sources"]:
    print(f"[{source['id']}] {source['title']} ({source['niche']}) - {source['platform']}")
```

### Step 2: Pull Analysis & Segments for a Source

```python
source_id = 1
youtube_url = "https://youtube.com/watch?v=abc123"

# Get analysis
analysis_result = call_tool("get_analysis", {"youtube_url": youtube_url})
analysis = analysis_result["analysis"]

# Get segments (clips)
segments_result = call_tool("get_segments", {"source_id": source_id})
segments = segments_result["segments"]
```

### Step 3: Generate Production Brief

```python
brief_result = call_tool("make_brief", {
    "analysis_json": json.dumps(analysis),
    "target": "gen-z / Reels / entertainment"
})
brief = brief_result["brief"]
print("Production Brief:")
print(brief)
```

### Step 4: Script & Generate Shot-Prompts

_(Scriptwriter agent writes based on the brief)_

```python
script = """
Beat 1 — Hook (0–2s)
  Visual: Person's confused face
  VO: "This one trick changed everything..."
  Caption: "Wait for the plot twist"

Beat 2 — Payoff (2–5s)
  Visual: Reveal the solution
  VO: "It's actually this simple."
  Caption: "Mind = blown"
"""

prompts_result = call_tool("generate_shot_prompts", {
    "script_text": script,
    "style_note": "bright, 9:16 vertical, trending audio aesthetic"
})
prompts = prompts_result["prompts"]
print("Shot Prompts for Gemini:")
print(prompts)
```

### Step 5: Generate in Gemini

_(Paste prompts into Gemini's Imagen + Veo)_

Then assemble in CapCut or Antigravity's editor.

---

## Troubleshooting

| Issue | Likely cause | Fix |
|-------|--------------|-----|
| `"DATABASE_URL not configured"` | Env var missing | Set `DATABASE_URL` before starting Antigravity |
| `"database connection failed"` | Reelbot DB offline or wrong URL | Check `DATABASE_URL`, verify Postgres is running |
| `"query failed: ..."` | SQL error or schema mismatch | Check DB tables: `sources`, `video_analysis`, `video_segments` exist |
| `"shotprompt/SOUL.md not found"` | Reelbot repo path wrong or file deleted | Verify MCP arg points to correct repo root; check file exists |
| `"bridge connection error"` | Claude bridge offline | Verify `CLAUDE_BRIDGE_URL` is running; default is `http://localhost:9999` |
| `"bridge failed with unknown error"` | Claude bridge returned `ok: false` | Check bridge logs; may be out of API quota or model unavailable |

---

## Notes

- **Timeout:** Bridge calls use a 200s read timeout (generous for long completions). Adjust in `reelbot_mcp.py:_call_claude_bridge()` if needed.
- **Stateless:** MCP server is stateless — every call reads the DB fresh. Safe for concurrent clients.
- **Idempotent:** `list_sources`, `get_analysis`, `get_segments` are read-only and safe to call repeatedly.
- **Paths:** `segment_path` is relative to the Reelbot machine; Antigravity may need to fetch them over the network or mount a shared volume.

---

## Installation Checklist

- [ ] Reelbot running with native Postgres + Claude bridge
- [ ] `.env` in reelbot root has `DATABASE_URL` and (optionally) `CLAUDE_BRIDGE_URL`
- [ ] `mcp/reelbot_mcp.py` exists and is executable
- [ ] `pipeline-api/.venv/bin/python -m mcp` available (MCP SDK installed)
- [ ] Antigravity MCP config points to absolute paths
- [ ] Test: `list_sources()` returns your corpus

Once this checklist passes, Antigravity can pull analysis and generate shot-prompts in one command chain.
