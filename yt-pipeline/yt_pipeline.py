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
import sys
import json
import subprocess
import httpx
import time
from pathlib import Path
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────
CLIPROXY_URL = os.getenv("CLIPROXY_URL", "http://cliproxy:8317/v1")
CLIPROXY_KEY = os.getenv("CLIPROXY_KEY", "local-proxy-key")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")      # free at pexels.com/api
FREESOUND_KEY = os.getenv("FREESOUND_API_KEY", "")    # free at freesound.org

# Model ids as exposed by cliproxy → Sumopod (NO "gemini/" provider prefix —
# the proxy rejects prefixed names with "unknown provider").
ANALYZER_MODEL = os.getenv("ANALYZER_MODEL", "gemini-2.5-flash-lite")  # vision — frame analysis
WRITER_MODEL   = os.getenv("WRITER_MODEL", "gemini-2.5-flash")          # best writing quality
CHEAP_MODEL    = os.getenv("CHEAP_MODEL", "deepseek-v4-flash")          # text-only, cheap

VIDEOS_DIR = Path("/videos")
OUTPUT_DIR = Path("/output")

# ── Pipeline progress persistence (postgres — optional, never fatal) ──
# pipeline-api sets RUN_ID + DATABASE_URL; standalone CLI runs leave them blank
# and every helper below becomes a no-op, so the pipeline still works.
DATABASE_URL = os.getenv("DATABASE_URL", "")
RUN_ID = os.getenv("RUN_ID", "")

# ── Whisper model singleton ────────────────────────────────────
# Caches the loaded Whisper model per-process to avoid expensive reloads.
_whisper_model = None

def _get_whisper_model():
    """Lazy-load and cache the Whisper 'base' model. Returns None if unavailable."""
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            _whisper_model = whisper.load_model("base")
        except ImportError:
            # Cache ImportError permanently — the package won't change in-process
            _whisper_model = False
        except Exception:
            # For other transient failures, return None without caching so retry is possible
            return None
    # Return the model, or None if loading failed (represented by False in cache)
    return _whisper_model if _whisper_model is not False else None


def _db():
    """psycopg connection or None — DB is optional; we never crash the pipeline over it."""
    if not (DATABASE_URL and RUN_ID):
        return None
    try:
        import psycopg
        return psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=5)
    except Exception as e:
        print(f"  [progress] DB unavailable ({e}); continuing without persistence")
        return None


def db_init_run(youtube_url: str, topic: str):
    conn = _db()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pipeline_runs (run_id, youtube_url, topic, status) "
                "VALUES (%s,%s,%s,'running') "
                "ON CONFLICT (run_id) DO UPDATE SET status='running', error=NULL, finished_at=NULL",
                (RUN_ID, youtube_url, topic))
    except Exception as e:
        print(f"  [progress] init_run failed: {e}")
    finally:
        conn.close()


def db_step_start(step: str):
    conn = _db()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pipeline_run_steps (run_id, step, status, started_at) "
                "VALUES (%s,%s,'running', now()) "
                "ON CONFLICT (run_id, step) DO UPDATE SET status='running', "
                "  started_at=COALESCE(pipeline_run_steps.started_at, now()), "
                "  error=NULL, finished_at=NULL",
                (RUN_ID, step))
            cur.execute("UPDATE pipeline_runs SET current_step=%s WHERE run_id=%s", (step, RUN_ID))
    except Exception as e:
        print(f"  [progress] step_start({step}) failed: {e}")
    finally:
        conn.close()


def db_step_done(step: str, output=None):
    conn = _db()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pipeline_run_steps SET status='done', output=%s, finished_at=now() "
                "WHERE run_id=%s AND step=%s",
                (json.dumps(output, ensure_ascii=False, default=str) if output is not None else None, RUN_ID, step))
    except Exception as e:
        print(f"  [progress] step_done({step}) failed: {e}")
    finally:
        conn.close()


def db_step_error(step: str, err: str):
    conn = _db()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pipeline_run_steps SET status='error', error=%s, finished_at=now() "
                "WHERE run_id=%s AND step=%s", (str(err)[:4000], RUN_ID, step))
    except Exception as e:
        print(f"  [progress] step_error({step}) failed: {e}")
    finally:
        conn.close()


def db_finish_run(status: str, result=None, error: str = None):
    conn = _db()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pipeline_runs SET status=%s, result=%s, error=%s, finished_at=now() "
                "WHERE run_id=%s",
                (status, json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
                 (str(error)[:4000] if error else None), RUN_ID))
    except Exception as e:
        print(f"  [progress] finish_run failed: {e}")
    finally:
        conn.close()


def db_done_step_output(step: str):
    """Return a finished step's stored output (for crash-resume), or None."""
    conn = _db()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT output FROM pipeline_run_steps WHERE run_id=%s AND step=%s AND status='done'",
                (RUN_ID, step))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()


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

    # Prefer mp4-native (h264+m4a) so the merge never has to remux av1/opus → mp4.
    # 480p is plenty for frame analysis + keeps downloads fast (less YT throttling).
    result = subprocess.run([
        "yt-dlp",
        "-f", "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/"
              "best[ext=mp4][height<=480]/best[height<=480]/best",
        "--merge-output-format", "mp4",
        "--retries", "5", "--fragment-retries", "5",
        "--socket-timeout", "30",
        "-o", output_template,
        "--no-playlist",
        youtube_url
    ], capture_output=False)

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
    Search YouTube for related videos. Tries v3 API first (via REST httpx),
    falls back to yt-dlp.
    Returns list of video metadata (no download).
    """
    print(f"\n[Footage Search] Searching YouTube: '{query}'")

    # Try v3 API first (using httpx REST call to avoid SDK dependency in yt-pipeline)
    youtube_api_key = os.getenv("YOUTUBE_API_KEY", "")
    if youtube_api_key:
        try:
            print(f"  [v3 API] Searching with: {query}")
            response = httpx.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "q": query,
                    "part": "snippet",
                    "type": "video",
                    "order": "relevance",
                    "maxResults": min(max_results, 50),
                    "key": youtube_api_key,
                },
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                videos = []
                for item in data.get("items", []):
                    snippet = item.get("snippet", {})
                    videos.append({
                        "title":    snippet.get("title", ""),
                        "url":      f"https://www.youtube.com/watch?v={item.get('id', {}).get('videoId', '')}",
                        "duration": None,  # v3 search doesn't include duration
                        "channel":  snippet.get("channelTitle", ""),
                        "id":       item.get("id", {}).get("videoId", ""),
                    })
                if videos:
                    print(f"  Found {len(videos)} videos (v3)")
                    return videos
            elif response.status_code == 403:
                print(f"  [v3 API] Quota exceeded, falling back to yt-dlp")
            else:
                print(f"  [v3 API] HTTP {response.status_code}, falling back to yt-dlp")
        except Exception as e:
            print(f"  [v3 API] Error: {e}, falling back to yt-dlp")
    else:
        print(f"  [v3 API] No YOUTUBE_API_KEY, using yt-dlp")

    # Fallback to yt-dlp
    try:
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
                except (json.JSONDecodeError, ValueError, KeyError):
                    print(f"  [yt-dlp] Skipped malformed entry: {line[:100]}", file=sys.stderr)

        if videos:
            print(f"  Found {len(videos)} videos (yt-dlp)")
            return videos
    except Exception as e:
        print(f"  [yt-dlp] Error: {e}")

    print(f"Found 0 videos")
    return []


# ══════════════════════════════════════════════════════════════════
# VTT Subtitle Parser (used by get_timecoded_transcript)
# ══════════════════════════════════════════════════════════════════

def _parse_vtt(vtt_path: str) -> list:
    """
    Parse a VTT subtitle file into segments: [{"start": float, "end": float, "text": str}, ...]
    Times are in seconds. Returns empty list if parsing fails.
    """
    segments = []
    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [transcript] VTT read failed: {e}", file=sys.stderr)
        return []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for timecode line (HH:MM:SS.mmm --> HH:MM:SS.mmm)
        if '-->' in line:
            try:
                parts = line.split('-->')
                start_str = parts[0].strip()
                end_str = parts[1].strip().split()[0]  # strip cue settings after end time

                # Convert HH:MM:SS.mmm to seconds
                def time_to_sec(t):
                    parts = t.split(':')
                    h = int(parts[0]) if len(parts) > 2 else 0
                    m = int(parts[-2])
                    s = float(parts[-1])
                    return h * 3600 + m * 60 + s

                start = time_to_sec(start_str)
                end = time_to_sec(end_str)

                # Next non-empty line(s) are the subtitle text
                text_lines = []
                i += 1
                while i < len(lines):
                    content = lines[i].strip()
                    if not content or '-->' in content:
                        break
                    text_lines.append(content)
                    i += 1

                text = ' '.join(text_lines)
                if text:
                    segments.append({"start": round(start, 2), "end": round(end, 2), "text": text})
            except Exception as e:
                print(f"  [transcript] VTT line parse failed: {e}", file=sys.stderr)
                i += 1
        else:
            i += 1

    return segments


def _run_yt_dlp_transcript_attempt(youtube_url: str, tmp_dir: str, extra_args: list) -> tuple:
    """
    Run one yt-dlp subtitle fetch attempt with given extra arguments.
    Returns (returncode, stderr, stdout).
    Uses 60s timeout per attempt.
    """
    args = [
        "yt-dlp",
        "--write-auto-sub",
        "--write-sub",
        "--sub-langs", "en.*,en",
        "--sub-format", "vtt",
        "--skip-download",
        "-o", f"{tmp_dir}/subs",
        "--no-playlist",
        "--socket-timeout", "60",
        *extra_args,
        youtube_url
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=70)
    return (result.returncode, result.stderr, result.stdout)


def get_timecoded_transcript(youtube_url: str) -> list:
    """
    Fetch timecoded transcript for a YouTube video using auto-generated subtitles.
    Hardened to survive YouTube 429 throttle and JS runtime issues.

    Strategy:
    1. Try with --impersonate to avoid bot detection (curl_cffi backend)
    2. Fallback: try multiple player_client options (android, ios, web)
    3. Retry with exponential backoff on 429 errors (2s, 4s, 8s)
    4. Optional: use cookies from env YTDLP_COOKIES_FILE if set

    Returns: [{"start": float (seconds), "end": float (seconds), "text": str}, ...]
    Returns [] gracefully if all attempts fail, with diagnostic prints.
    """
    import tempfile
    import shutil

    print(f"\n[Transcript] Fetching auto-generated subtitles: {youtube_url}", file=sys.stderr)

    tmp_dir = tempfile.mkdtemp(prefix="vtt_")
    try:
        # Check for cookies env var and copy to writable temp location if read-only
        cookies_args = []
        cookies_file = os.getenv("YTDLP_COOKIES_FILE", "")
        if cookies_file and Path(cookies_file).exists():
            # Copy cookies to a writable temp file (yt-dlp writes refreshed cookies)
            # if the original is read-only, this avoids OSError: [Errno 30] Read-only file system
            original_cookies = Path(cookies_file)
            writable_cookies = Path(tmp_dir) / "cookies_writable.txt"
            shutil.copy(str(original_cookies), str(writable_cookies))
            cookies_args = ["--cookies", str(writable_cookies)]
            print(f"  [transcript] Using cookies from {cookies_file} (copied to writable temp)", file=sys.stderr)

        # Define attempt strategies: impersonate + player_client combos
        # Each tuple is (attempt_name, extra_args_list)
        strategies = [
            ("impersonate-chrome", ["--impersonate", "chrome"] + cookies_args),
            ("android-client", ["--extractor-args", "youtube:player_client=android"] + cookies_args),
            ("ios-client", ["--extractor-args", "youtube:player_client=ios"] + cookies_args),
            ("web-client", ["--extractor-args", "youtube:player_client=web"] + cookies_args),
        ]

        last_error = None
        for attempt_idx, (strategy_name, extra_args) in enumerate(strategies, start=1):
            for retry_idx in range(3):  # 3 retries per strategy
                retry_delay = 2 ** retry_idx if retry_idx > 0 else 0
                if retry_delay:
                    print(f"  [transcript] Retry attempt {retry_idx}, waiting {retry_delay}s...", file=sys.stderr)
                    time.sleep(retry_delay)

                print(f"  [transcript] Strategy {attempt_idx}/4 ({strategy_name}), attempt {retry_idx + 1}/3", file=sys.stderr)

                returncode, stderr, stdout = _run_yt_dlp_transcript_attempt(youtube_url, tmp_dir, extra_args)

                if returncode == 0:
                    print(f"  [transcript] Success with {strategy_name}", file=sys.stderr)
                    vtt_files = list(Path(tmp_dir).glob("subs*.vtt"))
                    if vtt_files:
                        vtt_path = vtt_files[0]
                        segments = _parse_vtt(str(vtt_path))
                        print(f"  [transcript] Parsed {len(segments)} segments from {vtt_path.name}", file=sys.stderr)
                        return segments
                    else:
                        print(f"  [transcript] No .vtt file found after successful fetch", file=sys.stderr)
                        last_error = "no_vtt_file"
                        continue

                # Check for 429 (throttle) vs other errors
                if "429" in stderr or "Too Many Requests" in stderr:
                    print(f"  [transcript] HTTP 429 (throttled) on {strategy_name}, will retry with backoff", file=sys.stderr)
                    last_error = "http_429"
                    # Continue to retry loop (backoff happens above)
                elif "No supported JavaScript runtime" in stderr or "impersonate target" in stderr:
                    print(f"  [transcript] JS runtime error on {strategy_name}, trying next strategy", file=sys.stderr)
                    last_error = "js_runtime"
                    break  # Break retry loop, try next strategy
                else:
                    print(f"  [transcript] yt-dlp error on {strategy_name}: {stderr[:200]}", file=sys.stderr)
                    last_error = f"yt_dlp_error: {stderr[:100]}"
                    break  # Break retry loop, try next strategy

        print(f"  [transcript] All strategies exhausted (last error: {last_error})", file=sys.stderr)
        return []

    except Exception as e:
        print(f"  [transcript] Unexpected error: {e}", file=sys.stderr)
        return []
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


def _is_youtube_url(url: str) -> bool:
    """
    Check if a URL is a YouTube URL.
    Returns True for youtube.com, youtu.be, music.youtube.com, etc.
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    youtube_hosts = {
        "youtube.com", "www.youtube.com", "m.youtube.com",
        "music.youtube.com", "youtu.be"
    }
    return hostname in youtube_hosts


def transcribe_with_whisper(audio_path: str) -> list:
    """
    Transcribe an audio file locally with the cached Whisper 'base' model.
    Returns timecoded segments in the same shape as get_timecoded_transcript:
      [{"start": float (seconds), "end": float (seconds), "text": str}, ...]
    Returns [] gracefully on any failure (whisper missing, bad audio, etc.).
    """
    print(f"\n[Transcript] Whisper fallback transcribing: {audio_path}", file=sys.stderr)
    try:
        model = _get_whisper_model()
        if model is None:
            print(f"  [whisper] Model unavailable", file=sys.stderr)
            return []
        result = model.transcribe(audio_path)
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": str(seg.get("text", "")).strip(),
            })
        print(f"  [whisper] Transcribed {len(segments)} segments", file=sys.stderr)
        return segments
    except Exception as e:
        print(f"  [whisper] Transcription failed: {e}", file=sys.stderr)
        return []


def _whisper_fallback_from_audio(url: str) -> list:
    """
    Fallback to Whisper for URLs that don't have YouTube subtitles available.
    Downloads audio and transcribes locally. Cleans up temp files.
    """
    import tempfile
    import shutil
    tmp_dir = tempfile.mkdtemp(prefix="whisper_")
    try:
        audio_path = download_audio_only(url, tmp_dir)
        return transcribe_with_whisper(audio_path)
    except Exception as e:
        print(f"  [transcript] Whisper fallback failed: {e}", file=sys.stderr)
        return []
    finally:
        try:
            shutil.rmtree(tmp_dir)
        except Exception as e:
            print(f"  [transcript] Failed to clean up temp dir {tmp_dir}: {e}", file=sys.stderr)


def get_transcript_or_fallback(url: str) -> list:
    """
    Fetch a timecoded transcript with source-specific routing.

    - YouTube URLs: try get_timecoded_transcript first (auto-generated subtitles),
                    then fall back to Whisper if no subtitles available.
    - Non-YouTube URLs: skip subtitle fetch; go straight to download_audio_only + Whisper.

    Same return shape as get_timecoded_transcript:
      [{"start": float (seconds), "end": float (seconds), "text": str}, ...]
    """
    if _is_youtube_url(url):
        # YouTube: try subtitles first, then Whisper fallback
        segments = get_timecoded_transcript(url)
        if segments:
            return segments

        print(f"\n[Transcript] No subtitles — falling back to Whisper for: {url}", file=sys.stderr)
        return _whisper_fallback_from_audio(url)
    else:
        # Non-YouTube: skip subtitles, go straight to Whisper
        print(f"\n[Transcript] Non-YouTube source detected — using Whisper for: {url}", file=sys.stderr)
        return _whisper_fallback_from_audio(url)


# ══════════════════════════════════════════════════════════════════
# Frame extraction at explicit timestamps
# ══════════════════════════════════════════════════════════════════

def extract_frames_at(video_path: str, timestamps: list) -> list:
    """
    Extract frames at specific timestamps (in seconds).
    Returns: [{"time": float, "path": str}, ...]
    Reuses ffmpeg -ss approach from _extract_frames. Gracefully skips failed frames.
    Cap timestamps to avoid CPU overload (max 12 frames).
    """
    import tempfile

    if not timestamps:
        return []

    # Cap to protect the container
    if len(timestamps) > 12:
        print(f"  [frames] Capping {len(timestamps)} timestamps to 12")
        timestamps = timestamps[:12]

    tmp = tempfile.mkdtemp(prefix="frames_at_")
    paths = []

    for i, t in enumerate(sorted(timestamps)):
        try:
            t_float = float(t)
            out = f"{tmp}/frame_{i:02d}_{t_float:.1f}s.jpg"
            r = subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-ss", str(t_float),
                 "-i", video_path, "-frames:v", "1", "-vf", "scale=360:-1", out],
                capture_output=True, text=True, timeout=30)
            if Path(out).exists():
                paths.append({"time": round(t_float, 2), "path": out})
        except Exception as e:
            print(f"  [frames] Frame at {t}s failed: {e}")

    return paths


def describe_frames(frames: list, model: str = ANALYZER_MODEL) -> list:
    """
    Run vision AI on a list of frames, return per-frame visual descriptions.
    Frames: [{"time": float, "path": str}, ...]
    Returns: [{"time": float, "visual_description": str}, ...]
    Gracefully handles failures (returns empty description).
    """
    if not frames:
        return []

    print(f"\n[Vision] Analyzing {len(frames)} frames...")

    results = []
    for frame in frames:
        try:
            time = frame.get("time")
            path = frame.get("path")
            if not path or not Path(path).exists():
                results.append({"time": time, "visual_description": ""})
                continue

            # Convert to base64 for vision call
            import base64
            b = base64.b64encode(Path(path).read_bytes()).decode()
            content = [
                {"type": "text", "text": "Describe what is on screen in one concise sentence. Be neutral and objective."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}}
            ]

            response = httpx.post(
                f"{CLIPROXY_URL}/chat/completions",
                headers={"Authorization": f"Bearer {CLIPROXY_KEY}", "Content-Type": "application/json"},
                json={"model": model,
                      "messages": [{"role": "user", "content": content}],
                      "temperature": 0.3, "max_tokens": 200},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            desc = data["choices"][0]["message"]["content"]
            db_log_usage(model, data.get("usage", {}), "clipfinder_frames")
            results.append({"time": time, "visual_description": desc})
        except Exception as e:
            print(f"  [vision] Frame {frame.get('time')}s failed: {e}")
            results.append({"time": frame.get("time"), "visual_description": ""})

    return results


# ══════════════════════════════════════════════════════════════════
# STEP 2 — Analyze the video (frames + transcript)
# ══════════════════════════════════════════════════════════════════

def _extract_frames(video_path: str, n: int = 8) -> list:
    """Extract n evenly-spaced frames (360px wide) via ffmpeg. Returns list of paths."""
    import tempfile
    dur = float(video_info_duration(video_path))
    tmp = tempfile.mkdtemp(prefix="frames_")
    paths = []
    for i in range(n):
        t = round(i * dur / (n + 0.5), 2) if dur else i
        out = f"{tmp}/f_{i:02d}.jpg"
        r = subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-ss", str(t),
             "-i", video_path, "-frames:v", "1", "-vf", "scale=360:-1", out],
            capture_output=True, text=True)
        if Path(out).exists():
            paths.append((t, out))
    return paths


def video_info_duration(video_path: str) -> float:
    """Probe a media file's duration in seconds (0.0 on failure)."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video_path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def db_log_usage(model: str, usage: dict, step: str = ""):
    """Log one LLM call's token usage to api_usage. No-op without DB/RUN_ID or usage."""
    if not usage:
        return
    conn = _db()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_usage (run_id, step, model, prompt_tokens, completion_tokens, total_tokens) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (RUN_ID or None, step or None, model,
                 int(usage.get("prompt_tokens", 0) or 0),
                 int(usage.get("completion_tokens", 0) or 0),
                 int(usage.get("total_tokens", 0) or 0)))
    except Exception as e:
        print(f"  [usage] log failed: {e}")
    finally:
        conn.close()


def call_ai_vision(system_prompt: str, user_text: str, image_paths: list, model: str) -> str:
    """Vision AI call via CLIProxyAPI → Sumopod (frames as base64 image_url parts)."""
    import base64
    content = [{"type": "text", "text": user_text}]
    for _, p in image_paths:
        b = base64.b64encode(Path(p).read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}})
    response = httpx.post(
        f"{CLIPROXY_URL}/chat/completions",
        headers={"Authorization": f"Bearer {CLIPROXY_KEY}", "Content-Type": "application/json"},
        json={"model": model,
              "messages": [{"role": "system", "content": system_prompt},
                           {"role": "user", "content": content}],
              "temperature": 0.4, "max_tokens": 2000},
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    db_log_usage(model, data.get("usage", {}), "analyze")
    return data["choices"][0]["message"]["content"]


def analyze_video(video_path: str, video_info: dict) -> dict:
    """
    Analyze the downloaded video INLINE (no external video-analyzer container):
    ffmpeg extracts frames → cliproxy vision model describes them.
    Returns: {description, frames:[{time, visual}], model}.
    Falls back to metadata-only description if the vision call fails.
    """
    print(f"\n[Step 2] Analyzing video frames (inline vision)...")

    frames = _extract_frames(video_path, n=8)
    if not frames:
        print("  no frames extracted; metadata-only fallback")
        return {"description": video_info.get("description", ""), "frames": [], "model": None}

    times = ", ".join(f"{t}s" for t, _ in frames)
    system = ("You are a short-form video analyst. Describe what is on screen objectively. "
              "Keep person attributes neutral (gender presentation, rough age bracket, clothing, "
              "activity) — never describe body shape or rate attractiveness. Do not flag copyright "
              "or monetization.")
    prompt = (f"These are {len(frames)} evenly-spaced frames (at {times}) from a "
              f"{video_info.get('duration')}s short titled '{video_info.get('title')}'. "
              "For EACH frame give one line: '<time> — <what's on screen + any caption text>'. "
              "Then a 3-4 sentence OVERALL description: genre, hook, narrative arc, faceless or not.")
    try:
        text = call_ai_vision(system, prompt, frames, ANALYZER_MODEL)
        # split per-frame lines from the overall paragraph (best-effort)
        frame_rows = [{"time": t} for t, _ in frames]
        analysis = {"description": text, "frames": frame_rows, "model": ANALYZER_MODEL}
        print(f"Analysis complete: {len(frames)} frames via {ANALYZER_MODEL}")
        return analysis
    except Exception as e:
        print(f"  vision analysis failed ({e}); metadata-only fallback")
        return {"description": video_info.get("description", ""), "frames": [], "model": None, "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# STEP 2b — Audio DSP analysis (deterministic, ffmpeg — no model)
# ══════════════════════════════════════════════════════════════════

def analyze_audio_dsp(media_path: str) -> dict:
    """
    Measure audio properties with ffmpeg/ffprobe (no model 'hearing').
    Runs on any media file that has an audio track (the downloaded video works).
    Returns: lufs, true_peak_dbtp, lra, max/mean volume, dynamic_range label,
             silence segments, sound onsets, audio_hook_ms, loop_seam_ok.
    Never raises — returns {"available": False, "error": ...} on failure so the
    pipeline keeps going.
    """
    import re

    # Cap analysis to the first DSP_MAX_SEC of audio so long videos don't stall the
    # CPU-throttled container (we only need a representative loudness/onset profile;
    # Shorts under this cap are analyzed in full).
    DSP_MAX_SEC = 90

    def _run(args):
        # ffmpeg writes its measurements to stderr
        return subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-t", str(DSP_MAX_SEC),
             "-i", media_path, *args, "-f", "null", "-"],
            capture_output=True, text=True
        ).stderr

    print("\n[Step 2b] Audio DSP analysis (ffmpeg)...")
    try:
        # 1. loudness — loudnorm prints a JSON block to stderr
        loud = _run(["-af", "loudnorm=print_format=json"])
        m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", loud, re.S)
        lufs = tp = lra = None
        if m:
            j = json.loads(m.group(0))
            lufs = _to_float(j.get("input_i"))
            tp   = _to_float(j.get("input_tp"))
            lra  = _to_float(j.get("input_lra"))

        # 2. peak / mean amplitude
        vol = _run(["-af", "volumedetect"])
        max_v  = _to_float(_grep1(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", vol))
        mean_v = _to_float(_grep1(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", vol))

        # 3. silence / sound onsets
        sil = _run(["-af", "silencedetect=noise=-30dB:d=0.2"])
        sil_starts = [float(x) for x in re.findall(r"silence_start:\s*(-?\d+(?:\.\d+)?)", sil)]
        sil_ends   = [float(x) for x in re.findall(r"silence_end:\s*(\d+(?:\.\d+)?)", sil)]

        # duration (for loop-seam tail check)
        dur = _to_float(_grep1(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", sil, groups=3, as_hms=True))

        # sound onsets = points where sound resumes after silence; if the clip
        # opens with sound (no silence at 0), 0.0 is the first onset.
        onsets = sorted(sil_ends)
        opens_silent = any(s <= 0.15 for s in sil_starts)
        if not opens_silent:
            onsets = [0.0] + onsets
        audio_hook_ms = int(round(onsets[0] * 1000)) if onsets else 0

        # loop seam: clean if the clip ends in silence (a silence_start near the end
        # with no later silence_end), giving a quiet tail to loop back from.
        loop_seam_ok = None
        if dur and sil_starts:
            last_start = max(sil_starts)
            tail_is_silent = last_start >= (dur - 0.4) or (sil_starts and max(sil_starts) > (sil_ends[-1] if sil_ends else 0))
            loop_seam_ok = bool(tail_is_silent)

        # dynamic-range label from LRA (loudness range)
        dyn = None
        if lra is not None:
            dyn = "natural" if lra >= 9 else ("compressed" if lra >= 4 else "brickwalled")

        # is there sustained sound (music bed) vs sparse events?
        # heuristic: many short silences + low mean = sparse/raw; few silences = continuous bed.
        n_sil = len(sil_starts)

        return {
            "available": True,
            "lufs": lufs,
            "true_peak_dbtp": tp,
            "lra": lra,
            "max_volume_db": max_v,
            "mean_volume_db": mean_v,
            "dynamic_range": dyn,
            "duration_s": dur,
            "silence_starts_s": sil_starts,
            "silence_ends_s": sil_ends,
            "sound_onsets_s": onsets,
            "audio_hook_ms": audio_hook_ms,
            "loop_seam_ok": loop_seam_ok,
            "silence_count": n_sil,
            "is_silent": (max_v is not None and max_v < -60),
            # model fills these from transcript + this data (don't guess here):
            "music_bed": None, "speech": None, "sfx": None,
        }
    except Exception as e:
        print(f"  audio DSP failed: {e}")
        return {"available": False, "error": str(e)}


def _to_float(v, groups=1, as_hms=False):
    if v is None:
        return None
    try:
        if as_hms and isinstance(v, tuple):
            h, m, s = v
            return round(int(h) * 3600 + int(m) * 60 + float(s), 2)
        return float(v)
    except (ValueError, TypeError):
        return None


def _grep1(pattern, text, groups=1, as_hms=False):
    import re
    m = re.search(pattern, text)
    if not m:
        return None
    return m.groups() if (groups > 1 or as_hms) else m.group(1)


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
            "max_tokens": 8000
        },
        timeout=180
    )

    data = response.json()
    db_log_usage(model, data.get("usage", {}), "")
    return data["choices"][0]["message"]["content"]


def extract_json(text: str):
    """Robustly pull a JSON object/array out of an LLM reply (handles ```json fences,
    leading prose, trailing text). Returns the parsed object, or None if unparseable."""
    if not text:
        return None
    t = text.strip()
    # strip code fences
    if "```" in t:
        import re as _re
        m = _re.search(r"```(?:json)?\s*(.*?)```", t, _re.S)
        if m:
            t = m.group(1).strip()
    # slice from first { or [ to its matching last } or ]
    start = min([i for i in (t.find("{"), t.find("[")) if i != -1], default=-1)
    if start == -1:
        return None
    end = max(t.rfind("}"), t.rfind("]"))
    if end <= start:
        return None
    try:
        return json.loads(t[start:end + 1])
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
# STEP 4 — Story Writer Agent
# ══════════════════════════════════════════════════════════════════

# Compact viral-formula library — the writer clones a STRUCTURE, never wording.
FORMULA_LIBRARY = """
- process-reveal: visual hook → before/condition → process beats ×4-6 → payoff money-shot held ~75% → soft CTA. (kuliner, repair, making)
- price-reveal: tebak harga → proses/isi → reveal harga di akhir. (jajan, modal-untung)
- did-you-know-fact: pertanyaan/klaim mengejutkan → bukti cepat ×3 → twist fakta → CTA komen.
- why-explainer: "kenapa X?" hook → 3 sebab cepat ber-visual → kesimpulan punchy.
- listicle-countdown: "3 hal …" → item 3→1, terkuat terakhir → CTA.
- before-after: kondisi awal → transisi cepat → hasil dramatis di ~70%.
- pov-storytime: "POV: …" caption → in-medias-res → eskalasi → punchline/loop.
- expectation-vs-reality: ekspektasi → potong → realita lucu/satisfying.
- street-food-tour / mukbang: money-shot makanan terus-menerus, ASMR, no dead air.
- satisfying-asmr: tutup mata pun enak — suara + visual ritmis, loop mulus.
"""


def story_writer_agent(video_info: dict, analysis: dict, user_topic: str, audio: dict = None) -> dict:
    """
    Writes ONE ready-to-shoot SHORT-FORM script (30-45s) by CLONING a viral
    formula's structure onto the user's topic. Not long-form, not a copy.
    """
    print(f"\n[Step 4] Story Writer Agent generating SHORT script (formula-driven)...")

    system_prompt = f"""
You are a short-form (TikTok/Reels/Shorts) scriptwriter for faceless content.

Your job: pick the BEST-FIT viral FORMULA from the library below for this topic,
then CLONE ITS STRUCTURE (never the wording) into one ready-to-shoot Short.

FORMULA LIBRARY:
{FORMULA_LIBRARY}

HARD RULES:
- 30-45 seconds total. NOT long-form. No 8-minute narration, no chapters.
- Write in the SAME LANGUAGE as the user's topic (Indonesian topic → Indonesian, natural & conversational, no AI-sounding phrases).
- Hook in the first 0-3s: open a curiosity gap or pattern interrupt.
- Beat-by-beat: each beat = a VISUAL to film + a VO line + a hard-sub CAPTION (≤4-5 words) + timecode.
- Hold the money-shot / payoff longest, around 70-80% of the runtime.
- Cold-open: which moment to splice at second 0 (usually the payoff first).
- Soft CTA only (engagement or "modal Xrb jual Yrb"). Vary the hook style.
- Do NOT flag copyright or monetization.

Output JSON ONLY (this exact shape):
{{
  "title": "judul singkat",
  "formula": "<formula slug yang dipakai>",
  "hook": "VO line 0-3s",
  "hook_caption": "≤5 kata hard-sub",
  "cold_open": "momen/visual di detik 0",
  "target_duration_sec": 35,
  "beats": [
    {{"t": "0-3s", "visual": "apa yang difilm", "vo": "baris voiceover", "caption": "≤5 kata"}}
  ],
  "cta": "CTA penutup soft",
  "hashtags": ["#..", ".."],
  "tiktok_caption": "caption ≤150 char"
}}
"""

    audio_note = ""
    if audio and audio.get("available"):
        audio_note = (f"\nAudio of source: LUFS {audio.get('lufs')}, sound onsets at "
                      f"{audio.get('sound_onsets_s')}, loop-seam {audio.get('loop_seam_ok')}. "
                      "Place the hero SFX near the first onset; use a quiet beat before the payoff.")

    source_summary = f"""
Source video: {video_info['title']} ({video_info['duration']}s, by {video_info['channel']})
Source description: {video_info['description'][:300]}

What's in the source (frame analysis):
{analysis.get('description', 'No analysis available')[:1200]}
{audio_note}

User's topic/angle for the NEW short: {user_topic}
Pick the best formula for THIS topic and clone its structure.
"""

    content = call_ai(system_prompt, source_summary, WRITER_MODEL)

    parsed = extract_json(content)
    if parsed:
        return parsed
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

    queries = extract_json(queries_raw)
    if not queries:
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

    music_brief = extract_json(music_brief_raw)
    if not music_brief:
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

def discover_videos(niche: str, topic: str = "", top_n: int = 3, per_query: int = 8) -> dict:
    """
    Given a NICHE/keyword (no URL), let the AI find + rank candidate videos:
    1. AI generates search queries  2. yt-dlp searches each  3. AI ranks by viral potential.
    Returns {queries, candidate_count, picks:[{url,title,duration,channel,score,reason}]}.
    """
    print(f"\n[Discover] niche='{niche}' topic='{topic}'")

    # 1. AI → search queries
    q_prompt = ('Generate 5 YouTube search queries to find viral SHORT-FORM videos for this niche. '
                'Vary angle/wording. Output JSON only: {"queries":["..",".."]}')
    qj = extract_json(call_ai(q_prompt, f"Niche: {niche}\nTopic angle: {topic}", CHEAP_MODEL)) or {}
    queries = [q for q in (qj.get("queries") or []) if isinstance(q, str)][:5] or [niche]
    print(f"  queries: {queries}")

    # 2. search + dedup by video id
    seen = {}
    for q in queries:
        for v in search_youtube(q, per_query):
            vid = v.get("id")
            if vid and vid not in seen:
                seen[vid] = v
    candidates = list(seen.values())
    print(f"  candidates: {len(candidates)}")
    if not candidates:
        return {"queries": queries, "candidate_count": 0, "picks": []}

    # 3. AI ranks by viral potential
    lines = "\n".join(
        f"{i}. {c.get('title')} | {c.get('duration')}s | {c.get('channel')} | {c.get('url')}"
        for i, c in enumerate(candidates))
    rank_prompt = (f'Pick the TOP {top_n} candidate videos for VIRAL short-form potential in the niche. '
                   'Reward: clear hook in title, clippable, strong topic fit, freshness. '
                   f'Return ONLY the top {top_n}, best first. JSON only: '
                   '{"ranked":[{"index":<n>,"score":1-10,"reason":"singkat"}]}')
    rj = extract_json(call_ai(rank_prompt, f"Niche: {niche}\nCandidates:\n{lines}", WRITER_MODEL)) or {}
    ranked = rj.get("ranked") or [{"index": i, "score": 0, "reason": ""} for i in range(len(candidates))]

    picks = []
    for r in ranked:
        i = r.get("index")
        if isinstance(i, int) and 0 <= i < len(candidates):
            picks.append({**candidates[i], "score": r.get("score"), "reason": r.get("reason")})
        if len(picks) >= top_n:
            break
    return {"queries": queries, "candidate_count": len(candidates), "picks": picks}


def discover_and_produce(niche: str, topic: str = "", top_n: int = 3) -> dict:
    """Discover candidate videos for a niche, then run the full pipeline on the top pick.
    Persists a 'discover' step + the normal 8 production steps under one run_id."""
    db_init_run(f"[discover] {niche}", topic)
    db_step_start("discover")
    try:
        disc = discover_videos(niche, topic, top_n)
    except Exception as e:
        db_step_error("discover", str(e))
        db_finish_run("error", error=str(e))
        raise
    db_step_done("discover", disc)

    picks = disc.get("picks") or []
    if not picks:
        db_finish_run("error", error="no candidate videos found")
        return {"discover": disc, "chosen": None, "produced": None}

    top = picks[0]
    print(f"\n✓ Discover picked #1: {top.get('title')} → {top.get('url')}")
    produced = run_pipeline(top["url"], topic or niche)  # adds metadata..save under same run_id
    return {"discover": disc, "chosen": top, "produced": produced}


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
    print(f" Run   : {RUN_ID or '(standalone, no DB)'}")
    print("=" * 60)

    db_init_run(youtube_url, user_topic)

    try:
        # ── Step 1: Get video metadata ───────────────────────────
        db_step_start("metadata")
        video_info = get_video_info(youtube_url)
        db_step_done("metadata", {"title": video_info.get("title"), "channel": video_info.get("channel"),
                                  "duration": video_info.get("duration"), "views": video_info.get("view_count")})
        print(f"\n✓ Video: '{video_info['title']}' by {video_info['channel']}")
        print(f"  Duration: {video_info['duration']}s | Views: {video_info['view_count']:,}")

        # ── Step 1b: Download video (resume-aware) ───────────────
        prev = db_done_step_output("download")
        if prev and prev.get("video_path") and Path(prev["video_path"]).exists():
            video_path = prev["video_path"]
            print(f"\n↩ Resumed: video already downloaded → {video_path}")
        else:
            db_step_start("download")
            video_path = download_video(youtube_url, str(run_dir))
            db_step_done("download", {"video_path": video_path})
        print(f"\n✓ Video downloaded: {video_path}")

        # ── Step 2: Analyze video (resume-aware) ─────────────────
        prev = db_done_step_output("analyze")
        if prev:
            analysis = prev
            print("\n↩ Resumed: analysis from DB")
        else:
            db_step_start("analyze")
            analysis = analyze_video(video_path, video_info)
            db_step_done("analyze", analysis)
        print(f"\n✓ Analysis complete")

        # ── Step 2b: Audio DSP (resume-aware) ────────────────────
        prev = db_done_step_output("audio_dsp")
        if prev:
            audio = prev
            print("\n↩ Resumed: audio DSP from DB")
        else:
            db_step_start("audio_dsp")
            audio = analyze_audio_dsp(video_path)
            db_step_done("audio_dsp", audio)
        if audio.get("available"):
            print(f"  audio: {audio.get('lufs')} LUFS, hook @ {audio.get('audio_hook_ms')}ms, "
                  f"{audio.get('silence_count')} silence segs")

        # ── Step 3: Write original story ─────────────────────────
        db_step_start("script")
        topic = user_topic or f"inspired by: {video_info['title']}"
        script = story_writer_agent(video_info, analysis, topic, audio=audio)
        db_step_done("script", script)
        print(f"\n✓ Script written: '{script.get('title', 'Untitled')}'")

        # ── Step 4: Find footage ─────────────────────────────────
        db_step_start("footage")
        footage = footage_finder_agent(script, video_info)
        db_step_done("footage", footage)
        print(f"\n✓ Found {len(footage.get('youtube_references', []))} YouTube references")
        print(f"  Found {len(footage.get('stock_footage', []))} stock footage clips")

        # ── Step 5: Find music ───────────────────────────────────
        db_step_start("music")
        music = music_finder_agent(script, analysis)
        db_step_done("music", music)
        print(f"\n✓ Music: {music['music_brief'].get('mood')} {music['music_brief'].get('genre')}")

        # ── Compile final output ─────────────────────────────────
        db_step_start("save")
        final_output = {
            "pipeline_run": timestamp,
            "source_video": video_info,
            "analysis_summary": analysis.get("description", ""),
            "audio": audio,
            "script": script,
            "footage": footage,
            "music": music
        }
        output_file = run_dir / "pipeline_output.json"
        with open(output_file, "w") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)
        summary_file = run_dir / "summary.md"
        save_summary(final_output, summary_file)
        db_step_done("save", {"output_file": str(output_file), "summary_file": str(summary_file)})

        db_finish_run("done", result={"pipeline_run": timestamp, "output_file": str(output_file)})

        print(f"\n{'=' * 60}")
        print(f"✅ Pipeline complete!")
        print(f"   JSON  : {output_file}")
        print(f"   Summary: {summary_file}")
        print(f"{'=' * 60}")

        return final_output

    except Exception as e:
        # mark the in-flight step + the run as errored so nothing is lost
        cur_step = None
        conn = _db()
        if conn:
            try:
                with conn.cursor() as c:
                    c.execute("SELECT current_step FROM pipeline_runs WHERE run_id=%s", (RUN_ID,))
                    r = c.fetchone()
                    cur_step = r[0] if r else None
            except Exception:
                pass
            finally:
                conn.close()
        if cur_step:
            db_step_error(cur_step, str(e))
        db_finish_run("error", error=str(e))
        print(f"\n❌ Pipeline failed at step '{cur_step}': {e}")
        raise


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

def main():
    """CLI entry point for yt_pipeline.py."""
    if len(sys.argv) < 2:
        print("Usage: python yt_pipeline.py <youtube_url> [topic]")
        print("       python yt_pipeline.py --discover <niche> [topic]")
        print("       python yt_pipeline.py --transcript <youtube_url>")
        print("       python yt_pipeline.py --frames <video_path> <timestamps_csv>")
        print("       python yt_pipeline.py --v3-search <query> [max_results]")
        print("       python yt_pipeline.py --v3-video <youtube_url>")
        sys.exit(1)

    if sys.argv[1] == "--discover":
        # discovery mode: AI finds + ranks videos for a niche, then produces the top pick
        niche = sys.argv[2] if len(sys.argv) > 2 else ""
        topic = sys.argv[3] if len(sys.argv) > 3 else ""
        result = discover_and_produce(niche, topic)
    elif sys.argv[1] == "--transcript":
        # Fetch timecoded transcript from a YouTube URL
        url = sys.argv[2] if len(sys.argv) > 2 else ""
        if not url:
            print("Usage: python yt_pipeline.py --transcript <youtube_url>")
            sys.exit(1)
        segments = get_transcript_or_fallback(url)
        print(json.dumps({"segments": segments}, indent=2, ensure_ascii=False))
    elif sys.argv[1] == "--frames":
        # Extract frames at specific timestamps and describe them
        if len(sys.argv) < 4:
            print("Usage: python yt_pipeline.py --frames <video_path> <timestamps_csv>")
            print("Example: python yt_pipeline.py --frames /path/video.mp4 5.2,10.5,15.0")
            sys.exit(1)
        video_path = sys.argv[2]
        timestamps_str = sys.argv[3]
        try:
            timestamps = [float(t.strip()) for t in timestamps_str.split(',')]
        except ValueError:
            print("Error: timestamps must be comma-separated floats (e.g., 5.2,10.5,15.0)")
            sys.exit(1)
        frames = extract_frames_at(video_path, timestamps)
        descriptions = describe_frames(frames)
        print(json.dumps({"frames": descriptions}, indent=2, ensure_ascii=False))
    elif sys.argv[1] == "--v3-search":
        # Search YouTube using v3 API (for fallback from pipeline-api)
        query = sys.argv[2] if len(sys.argv) > 2 else ""
        max_results = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        if not query:
            print("Usage: python yt_pipeline.py --v3-search <query> [max_results]")
            sys.exit(1)
        # Route the helper's diagnostic prints to stderr so stdout is pure JSON
        # (pipeline-api parses stdout with json.loads).
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            videos = search_youtube(query, max_results)
        print(json.dumps(videos, indent=2, ensure_ascii=False))
    elif sys.argv[1] == "--v3-video":
        # Get video metadata (for fallback from pipeline-api)
        url = sys.argv[2] if len(sys.argv) > 2 else ""
        if not url:
            print("Usage: python yt_pipeline.py --v3-video <youtube_url>")
            sys.exit(1)
        try:
            import contextlib
            with contextlib.redirect_stdout(sys.stderr):
                info = get_video_info(url)
            print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
            sys.exit(1)
    else:
        url   = sys.argv[1]
        topic = sys.argv[2] if len(sys.argv) > 2 else ""
        result = run_pipeline(url, topic)


if __name__ == "__main__":
    main()
