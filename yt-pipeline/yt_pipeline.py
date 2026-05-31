# ═══════════════════════════════════════════════════════════════
# YouTube Content Inspiration Pipeline
#
# Flow:
#   1. You send a YouTube URL
#   2. Agent 1 (Analyzer)  — downloads + analyzes the video
#   3. Agent 2 (Story)     — writes original script inspired by it
#   4. Agent 3 (Footage)   — finds related stock footage
#   5. Agent 4 (Music)     — finds suitable background music
#   6. Saves everything to Google Doc
#
# Uses:
#   yt-dlp      — download video + extract metadata
#   video-analyzer — analyze frames via vision AI
#   OpenAI-compatible API via CLIProxyAPI → Sumopod
# ═══════════════════════════════════════════════════════════════

import os
import json
import subprocess
import httpx
from pathlib import Path
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────
CLIPROXY_URL = os.getenv("CLIPROXY_URL", "http://cliproxy:8317/v1")
CLIPROXY_KEY = os.getenv("CLIPROXY_KEY", "local-proxy-key")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")      # free at pexels.com/api
FREESOUND_KEY = os.getenv("FREESOUND_API_KEY", "")    # free at freesound.org

ANALYZER_MODEL = "gemini/gemini-2.5-flash-lite"  # vision — for frame analysis
WRITER_MODEL   = "gemini/gemini-2.5-flash"        # best writing quality
CHEAP_MODEL    = "deepseek-v4-flash"              # text-only, cheap

VIDEOS_DIR = Path("/videos")
OUTPUT_DIR = Path("/output")


# ══════════════════════════════════════════════════════════════════
# STEP 1 — Download video info + audio using yt-dlp
# ══════════════════════════════════════════════════════════════════

def get_video_info(youtube_url: str) -> dict:
    """
    Extract video metadata without downloading the full video.
    Returns: title, description, duration, view_count, tags, etc.
    """
    print(f"\n[Step 1a] Fetching video info: {youtube_url}")

    result = subprocess.run([
        "yt-dlp",
        "--dump-json",              # metadata only, no download
        "--no-playlist",            # single video only
        youtube_url
    ], capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"yt-dlp error: {result.stderr}")

    info = json.loads(result.stdout)

    return {
        "id":          info.get("id"),
        "title":       info.get("title"),
        "description": info.get("description", "")[:1000],  # first 1000 chars
        "duration":    info.get("duration"),                 # seconds
        "view_count":  info.get("view_count"),
        "like_count":  info.get("like_count"),
        "channel":     info.get("uploader"),
        "tags":        info.get("tags", [])[:20],
        "categories":  info.get("categories", []),
        "upload_date": info.get("upload_date"),
        "thumbnail":   info.get("thumbnail"),
        "webpage_url": info.get("webpage_url"),
    }


def download_video(youtube_url: str, output_path: str) -> str:
    """
    Download the video file for frame analysis.
    Downloads best quality up to 720p (saves bandwidth + storage).
    Returns: path to downloaded file
    """
    print(f"\n[Step 1b] Downloading video...")

    output_template = f"{output_path}/source_video.%(ext)s"

    result = subprocess.run([
        "yt-dlp",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--no-playlist",
        "--progress",
        youtube_url
    ], capture_output=False)   # show progress in terminal

    if result.returncode != 0:
        raise Exception("Video download failed")

    # Find the downloaded file
    for f in Path(output_path).glob("source_video.*"):
        print(f"Downloaded: {f}")
        return str(f)

    raise Exception("Downloaded file not found")


def download_audio_only(youtube_url: str, output_path: str) -> str:
    """
    Download audio only — much faster, used for transcription.
    Returns: path to mp3 file
    """
    print(f"\n[Step 1c] Downloading audio for transcription...")

    output_template = f"{output_path}/source_audio.%(ext)s"

    result = subprocess.run([
        "yt-dlp",
        "-x",                        # extract audio only
        "--audio-format", "mp3",
        "--audio-quality", "5",      # medium quality, smaller file
        "-o", output_template,
        "--no-playlist",
        youtube_url
    ], capture_output=False)

    audio_file = f"{output_path}/source_audio.mp3"
    if Path(audio_file).exists():
        print(f"Audio saved: {audio_file}")
        return audio_file

    raise Exception("Audio download failed")


def search_youtube(query: str, max_results: int = 5) -> list:
    """
    Search YouTube for related videos using yt-dlp.
    Returns list of video metadata (no download).
    """
    print(f"\n[Footage Search] Searching YouTube: '{query}'")

    result = subprocess.run([
        "yt-dlp",
        f"ytsearch{max_results}:{query}",   # yt-dlp built-in search
        "--dump-json",
        "--flat-playlist",                   # metadata only, no download
        "--no-playlist"
    ], capture_output=True, text=True)

    videos = []
    for line in result.stdout.strip().split("\n"):
        if line:
            try:
                info = json.loads(line)
                videos.append({
                    "title":    info.get("title"),
                    "url":      info.get("url") or f"https://youtube.com/watch?v={info.get('id')}",
                    "duration": info.get("duration"),
                    "channel":  info.get("uploader") or info.get("channel"),
                    "id":       info.get("id"),
                })
            except:
                pass

    print(f"Found {len(videos)} related videos")
    return videos


# ══════════════════════════════════════════════════════════════════
# STEP 2 — Analyze the video (frames + transcript)
# ══════════════════════════════════════════════════════════════════

def analyze_video(video_path: str, video_info: dict) -> dict:
    """
    Run video-analyzer on the downloaded video.
    Returns: scene descriptions + transcript + style analysis
    """
    print(f"\n[Step 2] Analyzing video frames...")

    output_file = str(OUTPUT_DIR / "source_analysis.json")

    result = subprocess.run([
        "video-analyzer", video_path,
        "--client",       "openai_api",
        "--api-key",      CLIPROXY_KEY,
        "--api-url",      CLIPROXY_URL,
        "--model",        ANALYZER_MODEL,
        "--whisper-model","base",
        "--output",       output_file,
        "--max-frames",   "40",          # limit for speed on 4GB VPS
    ], capture_output=False)

    if Path(output_file).exists():
        with open(output_file) as f:
            analysis = json.load(f)
        print(f"Analysis complete: {len(analysis.get('frames', []))} frames analyzed")
        return analysis
    else:
        # Fallback: use metadata only if video-analyzer fails
        print("video-analyzer failed, using metadata only")
        return {"description": video_info.get("description", ""), "frames": []}


# ══════════════════════════════════════════════════════════════════
# STEP 3 — AI call helper
# ══════════════════════════════════════════════════════════════════

def call_ai(system_prompt: str, user_message: str, model: str) -> str:
    """Generic AI call via CLIProxyAPI → Sumopod."""

    response = httpx.post(
        f"{CLIPROXY_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {CLIPROXY_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        },
        timeout=120
    )

    return response.json()["choices"][0]["message"]["content"]


# ══════════════════════════════════════════════════════════════════
# STEP 4 — Story Writer Agent
# ══════════════════════════════════════════════════════════════════

def story_writer_agent(video_info: dict, analysis: dict, user_topic: str) -> dict:
    """
    Writes an original script INSPIRED by the source video.
    NOT a copy — a new story with a fresh angle.
    """
    print(f"\n[Step 4] Story Writer Agent generating script...")

    system_prompt = """
You are a creative video scriptwriter and storyteller.

Your job: analyze a source video's style and structure, then write a 
completely ORIGINAL script on the same topic but from a fresh angle.

Rules:
- NEVER copy or paraphrase the source video
- Create original narration, examples, and structure
- Match the emotional tone and pacing style of the source
- Write in a warm, engaging, conversational style
- Format: intro hook + 3-5 main segments + conclusion with CTA
- Include [B-ROLL SUGGESTION] notes for each segment

Output as JSON:
{
  "title": "video title",
  "hook": "opening line that grabs attention",
  "estimated_duration_min": 8,
  "tone": "warm/educational/dramatic/etc",
  "segments": [
    {
      "segment": 1,
      "title": "segment title",
      "narration": "full narration text",
      "broll_suggestion": "what footage to show here",
      "duration_sec": 60
    }
  ],
  "conclusion": "closing narration",
  "cta": "call to action",
  "instagram_caption": "caption for Instagram",
  "tiktok_caption": "caption for TikTok (150 chars max)",
  "twitter": "tweet (280 chars max)",
  "tags": ["tag1", "tag2"]
}
"""

    source_summary = f"""
Source video title: {video_info['title']}
Source channel: {video_info['channel']}
Duration: {video_info['duration']} seconds
Description: {video_info['description'][:500]}

Video analysis summary:
{analysis.get('description', 'No analysis available')[:1000]}

User's topic/angle: {user_topic}
"""

    content = call_ai(system_prompt, source_summary, WRITER_MODEL)

    # Parse JSON output
    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except:
        return {"title": "Script", "narration": content, "error": "parse_failed"}


# ══════════════════════════════════════════════════════════════════
# STEP 5 — Footage Finder Agent
# ══════════════════════════════════════════════════════════════════

def footage_finder_agent(script: dict, video_info: dict) -> dict:
    """
    Finds related footage from:
    1. YouTube search (reference only — links, not downloads)
    2. Pexels stock footage (free to use)
    """
    print(f"\n[Step 5] Footage Finder Agent searching...")

    # ── Ask AI to generate search queries ───────────────────────
    search_query_prompt = """
Based on this video script, generate 5 specific search queries to find
relevant footage. Output JSON only:
{
  "youtube_queries": ["query1", "query2", "query3"],
  "stock_queries": ["query1", "query2"]
}
"""
    script_summary = f"Title: {script.get('title')}\nTopic: {video_info['title']}"
    queries_raw = call_ai(search_query_prompt, script_summary, CHEAP_MODEL)

    try:
        queries_raw = queries_raw.strip().strip("```json").strip("```")
        queries = json.loads(queries_raw)
    except:
        queries = {
            "youtube_queries": [video_info['title'], "rice history Indonesia"],
            "stock_queries": ["rice field", "Indonesia food"]
        }

    results = {"youtube_references": [], "stock_footage": []}

    # ── Search YouTube for reference videos ─────────────────────
    for query in queries.get("youtube_queries", [])[:2]:
        videos = search_youtube(query, max_results=3)
        results["youtube_references"].extend(videos)

    # ── Search Pexels for stock footage ─────────────────────────
    if PEXELS_API_KEY:
        for query in queries.get("stock_queries", [])[:2]:
            pexels_results = search_pexels_video(query)
            results["stock_footage"].extend(pexels_results)
    else:
        print("[Footage] No Pexels API key — skipping stock footage")
        results["stock_footage"] = [
            {
                "source": "Pexels",
                "note": "Add PEXELS_API_KEY to get free stock footage",
                "search_url": f"https://www.pexels.com/search/videos/{q.replace(' ', '%20')}/"
            }
            for q in queries.get("stock_queries", [])
        ]

    return results


def search_pexels_video(query: str, per_page: int = 3) -> list:
    """Search Pexels for free stock video footage."""
    try:
        response = httpx.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": per_page, "orientation": "landscape"},
            timeout=10
        )
        data = response.json()
        return [
            {
                "source":   "Pexels",
                "title":    v.get("url", "").split("/")[-2],
                "url":      v.get("url"),
                "duration": v.get("duration"),
                "preview":  v.get("image"),
                "download": v["video_files"][0]["link"] if v.get("video_files") else None,
                "license":  "Free to use (Pexels license)"
            }
            for v in data.get("videos", [])
        ]
    except Exception as e:
        print(f"Pexels search failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════
# STEP 6 — Music Finder Agent
# ══════════════════════════════════════════════════════════════════

def music_finder_agent(script: dict, analysis: dict) -> dict:
    """
    Finds suitable background music from Freesound.org (free API).
    Analyzes the video mood and finds matching tracks.
    """
    print(f"\n[Step 6] Music Finder Agent searching...")

    # ── Ask AI to describe the music needed ─────────────────────
    music_brief_prompt = """
Based on this video script, describe the ideal background music.
Output JSON only:
{
  "mood": "calm/uplifting/dramatic/nostalgic/etc",
  "tempo": "slow/medium/fast",
  "genre": "ambient/orchestral/folk/electronic/etc",
  "instruments": ["piano", "strings", "etc"],
  "freesound_query": "specific search term for freesound.org",
  "description": "one sentence describing the ideal music"
}
"""
    script_text = f"Title: {script.get('title')}\nTone: {script.get('tone')}\nHook: {script.get('hook', '')}"
    music_brief_raw = call_ai(music_brief_prompt, script_text, CHEAP_MODEL)

    try:
        music_brief_raw = music_brief_raw.strip().strip("```json").strip("```")
        music_brief = json.loads(music_brief_raw)
    except:
        music_brief = {
            "mood": "calm",
            "genre": "ambient",
            "freesound_query": "calm documentary background music",
            "description": "Calm, warm ambient music"
        }

    tracks = []

    # ── Search Freesound.org ─────────────────────────────────────
    if FREESOUND_KEY:
        tracks = search_freesound(music_brief.get("freesound_query", "ambient"))
    else:
        print("[Music] No Freesound API key — providing search links")
        query = music_brief.get("freesound_query", "ambient documentary")
        tracks = [
            {
                "source": "Freesound.org",
                "note": "Add FREESOUND_API_KEY to get automatic music search",
                "search_url": f"https://freesound.org/search/?q={query.replace(' ', '+')}&f=duration%3A%5B30+TO+300%5D+type%3Amp3",
                "license": "Various Creative Commons licenses"
            },
            {
                "source": "Pixabay Music",
                "note": "Free music, no API key needed",
                "search_url": f"https://pixabay.com/music/search/{query.replace(' ', '-')}/",
                "license": "Free to use commercially"
            },
            {
                "source": "YouTube Audio Library",
                "note": "Free music for YouTube videos",
                "search_url": "https://studio.youtube.com/channel/audio",
                "license": "Free for YouTube use"
            }
        ]

    return {
        "music_brief": music_brief,
        "suggested_tracks": tracks
    }


def search_freesound(query: str, max_results: int = 5) -> list:
    """Search Freesound.org for royalty-free music."""
    try:
        response = httpx.get(
            "https://freesound.org/apiv2/search/text/",
            params={
                "query": query,
                "token": FREESOUND_KEY,
                "fields": "id,name,duration,license,previews,url",
                "filter": "duration:[30 TO 300]",   # 30 sec to 5 min
                "page_size": max_results
            },
            timeout=10
        )
        data = response.json()
        return [
            {
                "source":   "Freesound.org",
                "name":     s.get("name"),
                "duration": s.get("duration"),
                "license":  s.get("license"),
                "preview":  s.get("previews", {}).get("preview-hq-mp3"),
                "url":      s.get("url"),
            }
            for s in data.get("results", [])
        ]
    except Exception as e:
        print(f"Freesound search failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════
# MAIN PIPELINE — runs all agents sequentially
# ══════════════════════════════════════════════════════════════════

def run_pipeline(youtube_url: str, user_topic: str = "") -> dict:
    """
    Full pipeline: analyze source → write story → find footage → find music
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(" YouTube Content Inspiration Pipeline")
    print(f" URL   : {youtube_url}")
    print(f" Topic : {user_topic or 'same as source'}")
    print(f" Output: {run_dir}")
    print("=" * 60)

    # ── Step 1: Get video metadata ───────────────────────────────
    video_info = get_video_info(youtube_url)
    print(f"\n✓ Video: '{video_info['title']}' by {video_info['channel']}")
    print(f"  Duration: {video_info['duration']}s | Views: {video_info['view_count']:,}")

    # ── Step 1b: Download video for analysis ────────────────────
    video_path = download_video(youtube_url, str(run_dir))
    print(f"\n✓ Video downloaded: {video_path}")

    # ── Step 2: Analyze video ────────────────────────────────────
    analysis = analyze_video(video_path, video_info)
    print(f"\n✓ Analysis complete")

    # ── Step 3: Write original story ────────────────────────────
    topic = user_topic or f"inspired by: {video_info['title']}"
    script = story_writer_agent(video_info, analysis, topic)
    print(f"\n✓ Script written: '{script.get('title', 'Untitled')}'")

    # ── Step 4: Find footage ─────────────────────────────────────
    footage = footage_finder_agent(script, video_info)
    print(f"\n✓ Found {len(footage.get('youtube_references', []))} YouTube references")
    print(f"  Found {len(footage.get('stock_footage', []))} stock footage clips")

    # ── Step 5: Find music ───────────────────────────────────────
    music = music_finder_agent(script, analysis)
    print(f"\n✓ Music: {music['music_brief'].get('mood')} {music['music_brief'].get('genre')}")

    # ── Compile final output ────────────────────────────────────
    final_output = {
        "pipeline_run": timestamp,
        "source_video": video_info,
        "analysis_summary": analysis.get("description", ""),
        "script": script,
        "footage": footage,
        "music": music
    }

    # Save JSON
    output_file = run_dir / "pipeline_output.json"
    with open(output_file, "w") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    # Save human-readable summary
    summary_file = run_dir / "summary.md"
    save_summary(final_output, summary_file)

    print(f"\n{'=' * 60}")
    print(f"✅ Pipeline complete!")
    print(f"   JSON  : {output_file}")
    print(f"   Summary: {summary_file}")
    print(f"{'=' * 60}")

    return final_output


def save_summary(output: dict, path: Path):
    """Save human-readable markdown summary."""
    script = output.get("script", {})
    music = output.get("music", {})
    footage = output.get("footage", {})
    source = output.get("source_video", {})

    md = f"""# Content Inspiration Pipeline Output
Generated: {output['pipeline_run']}

---

## Source Video
- **Title:** {source.get('title')}
- **Channel:** {source.get('channel')}
- **URL:** {source.get('webpage_url')}
- **Duration:** {source.get('duration')}s

---

## Generated Script: {script.get('title', 'Untitled')}

**Hook:** {script.get('hook', '')}

**Tone:** {script.get('tone', '')} | **Duration:** ~{script.get('estimated_duration_min', '?')} min

### Segments
"""
    for seg in script.get("segments", []):
        md += f"""
#### {seg.get('segment')}. {seg.get('title')}
{seg.get('narration', '')}

> 🎬 B-Roll: {seg.get('broll_suggestion', '')}
"""

    md += f"""
### Conclusion
{script.get('conclusion', '')}

**CTA:** {script.get('cta', '')}

---

## Platform Captions

**Instagram:** {script.get('instagram_caption', '')}

**TikTok:** {script.get('tiktok_caption', '')}

**Twitter/X:** {script.get('twitter', '')}

---

## Footage Suggestions

### YouTube References
"""
    for v in footage.get("youtube_references", [])[:5]:
        md += f"- [{v.get('title')}]({v.get('url')}) — {v.get('channel')}\n"

    md += "\n### Stock Footage (Free)\n"
    for v in footage.get("stock_footage", [])[:5]:
        md += f"- [{v.get('source')}]({v.get('url') or v.get('search_url')}) — {v.get('license', '')}\n"

    md += f"""
---

## Music Suggestion

**Mood:** {music.get('music_brief', {}).get('mood')}
**Genre:** {music.get('music_brief', {}).get('genre')}
**Description:** {music.get('music_brief', {}).get('description')}

### Tracks
"""
    for t in music.get("suggested_tracks", [])[:3]:
        md += f"- [{t.get('name') or t.get('source')}]({t.get('url') or t.get('search_url')}) — {t.get('license', '')}\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(md)


# ══════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python yt_pipeline.py <youtube_url> [topic]")
        print('Example: python yt_pipeline.py "https://youtube.com/watch?v=xxx" "Why Indonesians eat rice"')
        sys.exit(1)

    url   = sys.argv[1]
    topic = sys.argv[2] if len(sys.argv) > 2 else ""

    result = run_pipeline(url, topic)
