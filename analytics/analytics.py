# ═══════════════════════════════════════════════════════════════
# analytics.py — Gap 4: Analytics feedback loop
# Fetches performance data from platforms
# Feeds insights back to script writer to improve future videos
# ═══════════════════════════════════════════════════════════════

import os, json, httpx
from datetime import datetime, timedelta
from pathlib import Path

CLIPROXY_URL = os.getenv("CLIPROXY_URL", "http://cliproxy:8317/v1")
CLIPROXY_KEY = os.getenv("CLIPROXY_KEY", "local-proxy-key")
ANALYTICS_DB = Path(os.getenv("ANALYTICS_DB", "/output/analytics.json"))


# ── Fetch YouTube analytics ───────────────────────────────────

def fetch_youtube_analytics(video_id: str, credentials_file: str = None) -> dict:
    """
    Fetch video performance from YouTube Analytics API.
    Returns views, watch time, CTR, likes, comments.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise Exception("Install: pip install google-api-python-client")

    token_file = credentials_file or "youtube_token.json"
    if not Path(token_file).exists():
        return {"error": "No YouTube credentials found"}

    creds = Credentials.from_authorized_user_file(token_file)
    youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)
    youtube_data = build("youtube", "v3", credentials=creds)

    # Get basic video stats
    video_r = youtube_data.videos().list(
        part="statistics,snippet",
        id=video_id
    ).execute()

    if not video_r.get("items"):
        return {"error": f"Video {video_id} not found"}

    item = video_r["items"][0]
    stats = item["statistics"]

    # Get analytics (views, watch time over last 7 days)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        analytics_r = youtube_analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments",
            filters=f"video=={video_id}"
        ).execute()

        rows = analytics_r.get("rows", [[0, 0, 0, 0, 0]])
        row = rows[0] if rows else [0, 0, 0, 0, 0]
    except:
        row = [0, 0, 0, 0, 0]

    total_views = int(stats.get("viewCount", 0))
    avg_view_sec = row[2] if len(row) > 2 else 0

    return {
        "platform": "youtube",
        "video_id": video_id,
        "title": item["snippet"]["title"],
        "views": total_views,
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
        "watch_time_minutes": row[1] if len(row) > 1 else 0,
        "avg_view_duration_sec": avg_view_sec,
        "avg_view_percentage": round((avg_view_sec / max(1, int(stats.get("duration", 60)))) * 100, 1),
        "fetched_at": datetime.now().isoformat()
    }


def fetch_tiktok_analytics(video_id: str, access_token: str = None) -> dict:
    """Fetch TikTok video performance metrics."""
    token = access_token or os.getenv("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        return {"error": "No TikTok token"}

    r = httpx.post(
        "https://open.tiktokapis.com/v2/video/query/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "filters": {"video_ids": [video_id]},
            "fields": ["id", "title", "view_count", "like_count",
                       "comment_count", "share_count", "reach", "average_time_watched"]
        },
        timeout=15
    )

    if r.status_code != 200:
        return {"error": f"TikTok API error: {r.status_code}"}

    videos = r.json().get("data", {}).get("videos", [])
    if not videos:
        return {"error": f"Video {video_id} not found"}

    v = videos[0]
    return {
        "platform": "tiktok",
        "video_id": video_id,
        "views": v.get("view_count", 0),
        "likes": v.get("like_count", 0),
        "comments": v.get("comment_count", 0),
        "shares": v.get("share_count", 0),
        "avg_watch_sec": v.get("average_time_watched", 0),
        "fetched_at": datetime.now().isoformat()
    }


# ── Save + load analytics database ───────────────────────────

def save_analytics(run_id: str, platform_data: dict):
    """Persist analytics to local JSON database."""
    ANALYTICS_DB.parent.mkdir(parents=True, exist_ok=True)

    db = {}
    if ANALYTICS_DB.exists():
        try:
            db = json.loads(ANALYTICS_DB.read_text())
        except:
            db = {}

    if run_id not in db:
        db[run_id] = {}

    db[run_id].update(platform_data)
    db[run_id]["updated_at"] = datetime.now().isoformat()
    ANALYTICS_DB.write_text(json.dumps(db, indent=2))


def load_recent_analytics(limit: int = 20) -> list:
    """Load recent analytics for feedback to AI."""
    if not ANALYTICS_DB.exists():
        return []

    db = json.loads(ANALYTICS_DB.read_text())
    items = list(db.values())

    # Sort by date descending
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items[:limit]


# ── AI feedback agent ─────────────────────────────────────────

def generate_insights(analytics_data: list) -> dict:
    """
    Send analytics to AI to extract actionable insights.
    These insights are injected into future script prompts.
    """
    if not analytics_data:
        return {"insights": [], "best_performing": [], "avoid": []}

    summary = json.dumps(analytics_data[:10], indent=2)[:3000]

    response = httpx.post(
        f"{CLIPROXY_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {CLIPROXY_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek-v4-flash",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a social media analytics expert. Analyze video performance data and extract actionable insights for a content creator. Output JSON only."
                },
                {
                    "role": "user",
                    "content": f"""
Analyze this video performance data:
{summary}

Return JSON:
{{
  "insights": ["insight1", "insight2"],
  "best_performing_topics": ["topic1", "topic2"],
  "best_performing_format": "what works best",
  "optimal_duration_sec": 60,
  "best_hook_style": "what type of hooks perform",
  "avoid": ["what to avoid"],
  "script_improvements": ["specific improvement for next video"]
}}
"""
                }
            ]
        },
        timeout=30
    )

    content = response.json()["choices"][0]["message"]["content"]
    content = content.strip().replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(content)
    except:
        return {"insights": [content], "error": "parse_failed"}


def get_feedback_for_script(topic: str) -> str:
    """
    Get analytics-based feedback string to inject into script prompt.
    Called by content writer agent before generating each script.
    """
    recent = load_recent_analytics(limit=15)
    if not recent:
        return ""

    insights = generate_insights(recent)

    feedback_parts = []

    if insights.get("best_performing_topics"):
        feedback_parts.append(
            f"High-performing topics recently: {', '.join(insights['best_performing_topics'][:3])}"
        )
    if insights.get("best_hook_style"):
        feedback_parts.append(f"Best hook style: {insights['best_hook_style']}")
    if insights.get("optimal_duration_sec"):
        feedback_parts.append(f"Optimal video duration: {insights['optimal_duration_sec']}s")
    if insights.get("script_improvements"):
        feedback_parts.append(
            f"Improvements for next video: {'; '.join(insights['script_improvements'][:2])}"
        )
    if insights.get("avoid"):
        feedback_parts.append(f"Avoid: {', '.join(insights['avoid'][:2])}")

    if not feedback_parts:
        return ""

    return "\n\nAnalytics feedback from previous videos:\n" + "\n".join(f"- {p}" for p in feedback_parts)


if __name__ == "__main__":
    print("Analytics service ready.")
    print(f"Database: {ANALYTICS_DB}")
    recent = load_recent_analytics()
    print(f"Stored analytics records: {len(recent)}")
    if recent:
        insights = generate_insights(recent)
        print(json.dumps(insights, indent=2))
