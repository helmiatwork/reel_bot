# pipeline-api/youtube_v3.py
# YouTube Data API v3 client — read-only search, metadata, trending, uploads, captions
# Falls back gracefully when API key is missing or quota is exceeded.
# Tracks quota usage in postgres (best-effort, non-blocking).

import os
import json
from pathlib import Path
from typing import List, Optional, Dict
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_CREDENTIALS = os.getenv("YOUTUBE_CREDENTIALS", "client_secrets.json")
DATABASE_URL = os.getenv("DATABASE_URL", "")


class YouTubeNotConfigured(Exception):
    """Raised when YOUTUBE_API_KEY is not set."""
    pass


class YouTubeQuotaError(Exception):
    """Raised when YouTube API quota is exceeded (403 with quotaExceeded/dailyLimitExceeded)."""
    pass


class YouTubeOAuthNotConfigured(Exception):
    """Raised when OAuth credentials (youtube_token.json or client_secrets.json) are not available."""
    pass


def _get_service():
    """Build YouTube v3 service. Raises YouTubeNotConfigured if key is missing."""
    if not YOUTUBE_API_KEY:
        raise YouTubeNotConfigured("YOUTUBE_API_KEY not configured")
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def _parse_iso8601_duration(duration_str: str) -> int:
    """Convert ISO 8601 duration (e.g., 'PT1H2M3S') to seconds.
    Returns 0 on parse failure."""
    if not duration_str or not duration_str.startswith("PT"):
        return 0
    try:
        import re
        pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
        match = re.match(pattern, duration_str)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return 0


def search(query: str, max_results: int = 10, **filters) -> List[Dict]:
    """
    Search YouTube using v3 search API.

    Returns list of dicts:
    [{
        video_id, title, channel_title, channel_id, published_at, thumbnail
    }, ...]

    Raises YouTubeNotConfigured, YouTubeQuotaError, HttpError on other API errors.
    """
    if not query or not query.strip():
        raise ValueError("query cannot be empty")

    # Clamp max_results (v3 cap is 50)
    max_results = max(1, min(max_results, 50))

    service = _get_service()

    try:
        request = service.search().list(
            q=query,
            part="snippet",
            maxResults=max_results,
            type="video",
            order="relevance",
        )
        result = request.execute()
    except HttpError as e:
        # Check for quota error
        if e.resp.status == 403:
            error_content = e.content.decode("utf-8") if isinstance(e.content, bytes) else str(e.content)
            if "quotaExceeded" in error_content or "dailyLimitExceeded" in error_content:
                raise YouTubeQuotaError("YouTube API quota exceeded") from e
        # Never leak raw Google error bodies to HTTP clients
        raise HttpError(e.resp, e.content)

    videos = []
    for item in result.get("items", []):
        snippet = item.get("snippet", {})
        videos.append({
            "video_id": item.get("id", {}).get("videoId", ""),
            "title": snippet.get("title", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "channel_id": snippet.get("channelId", ""),
            "published_at": snippet.get("publishedAt", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
        })

    # Record quota cost (best-effort, non-blocking)
    _record_quota("search.list", _QUOTA_COSTS["search.list"])

    return videos


def video_details(video_id_or_list) -> Dict:
    """
    Fetch detailed metadata for one or more video IDs.

    Args:
        video_id_or_list: str (single) or list (up to 50)

    Returns dict or list of dicts:
    {
        video_id, title, description, duration_iso, duration_s, view_count,
        like_count, comment_count, channel_title, tags, published_at
    }

    Raises YouTubeNotConfigured, YouTubeQuotaError, HttpError.
    """
    # Normalize input
    if isinstance(video_id_or_list, str):
        video_ids = [video_id_or_list]
        return_single = True
    else:
        video_ids = list(video_id_or_list)
        return_single = False

    if not video_ids:
        raise ValueError("video_id_or_list cannot be empty")

    # v3 cap is 50 per request
    video_ids = video_ids[:50]

    service = _get_service()

    try:
        request = service.videos().list(
            id=",".join(video_ids),
            part="snippet,contentDetails,statistics",
        )
        result = request.execute()
    except HttpError as e:
        if e.resp.status == 403:
            error_content = e.content.decode("utf-8") if isinstance(e.content, bytes) else str(e.content)
            if "quotaExceeded" in error_content or "dailyLimitExceeded" in error_content:
                raise YouTubeQuotaError("YouTube API quota exceeded") from e
        raise HttpError(e.resp, e.content)

    videos = []
    for item in result.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        videos.append({
            "video_id": item.get("id", ""),
            "title": snippet.get("title", ""),
            "description": snippet.get("description", "")[:1000],
            "duration_iso": content.get("duration", ""),
            "duration_s": _parse_iso8601_duration(content.get("duration", "")),
            "view_count": int(stats.get("viewCount", 0) or 0),
            "like_count": int(stats.get("likeCount", 0) or 0),
            "comment_count": int(stats.get("commentCount", 0) or 0),
            "channel_title": snippet.get("channelTitle", ""),
            "tags": snippet.get("tags", [])[:20],
            "published_at": snippet.get("publishedAt", ""),
        })

    # Record quota cost (best-effort, non-blocking)
    _record_quota("videos.list", _QUOTA_COSTS["videos.list"])

    return videos[0] if return_single else videos


def trending(region_code: str = "US", max_results: int = 10, category_id: Optional[str] = None) -> List[Dict]:
    """
    Fetch trending videos for a region.

    Args:
        region_code: ISO 3166-1 alpha-2 code (e.g., 'US', 'GB', 'JP')
        max_results: 1-50 (v3 cap)
        category_id: optional YouTube category ID to filter by

    Returns list of dicts (same shape as search()).

    Raises YouTubeNotConfigured, YouTubeQuotaError, HttpError.
    """
    max_results = max(1, min(max_results, 50))
    region_code = (region_code or "US").upper()

    service = _get_service()

    try:
        request = service.videos().list(
            chart="mostPopular",
            regionCode=region_code,
            part="snippet",
            maxResults=max_results,
        )
        if category_id:
            request = service.videos().list(
                chart="mostPopular",
                regionCode=region_code,
                part="snippet",
                maxResults=max_results,
                videoCategoryId=category_id,
            )
        result = request.execute()
    except HttpError as e:
        if e.resp.status == 403:
            error_content = e.content.decode("utf-8") if isinstance(e.content, bytes) else str(e.content)
            if "quotaExceeded" in error_content or "dailyLimitExceeded" in error_content:
                raise YouTubeQuotaError("YouTube API quota exceeded") from e
        raise HttpError(e.resp, e.content)

    videos = []
    for item in result.get("items", []):
        snippet = item.get("snippet", {})
        videos.append({
            "video_id": item.get("id", ""),
            "title": snippet.get("title", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "channel_id": snippet.get("channelId", ""),
            "published_at": snippet.get("publishedAt", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
        })

    # Record quota cost (best-effort, non-blocking)
    _record_quota("videos.list_chart", _QUOTA_COSTS["videos.list_chart"])

    return videos


def channel_uploads(channel_id: str, max_results: int = 10) -> List[Dict]:
    """
    Fetch uploads from a channel.

    Args:
        channel_id: YouTube channel ID (e.g., 'UCxxxx')
        max_results: 1-50 (v3 cap)

    Returns list of dicts (same shape as search()).

    Raises YouTubeNotConfigured, YouTubeQuotaError, HttpError.
    """
    if not channel_id or not channel_id.strip():
        raise ValueError("channel_id cannot be empty")

    max_results = max(1, min(max_results, 50))

    service = _get_service()

    try:
        # Step 1: get channel's uploads playlist ID
        req_channel = service.channels().list(
            id=channel_id,
            part="contentDetails",
        )
        result_channel = req_channel.execute()
        _record_quota("channels.list", _QUOTA_COSTS["channels.list"])

        items = result_channel.get("items", [])
        if not items:
            return []

        uploads_playlist_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
        if not uploads_playlist_id:
            return []

        # Step 2: list videos from that playlist
        req_playlist = service.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet",
            maxResults=max_results,
        )
        result_playlist = req_playlist.execute()
        _record_quota("playlistItems.list", _QUOTA_COSTS["playlistItems.list"])
    except HttpError as e:
        if e.resp.status == 403:
            error_content = e.content.decode("utf-8") if isinstance(e.content, bytes) else str(e.content)
            if "quotaExceeded" in error_content or "dailyLimitExceeded" in error_content:
                raise YouTubeQuotaError("YouTube API quota exceeded") from e
        raise HttpError(e.resp, e.content)

    videos = []
    for item in result_playlist.get("items", []):
        snippet = item.get("snippet", {})
        videos.append({
            "video_id": snippet.get("resourceId", {}).get("videoId", ""),
            "title": snippet.get("title", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "channel_id": snippet.get("channelId", ""),
            "published_at": snippet.get("publishedAt", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
        })

    return videos


# ── OAuth credentials and captions support ──────────────────────────────────

def _get_oauth_service():
    """Build YouTube v3 service with OAuth credentials (for own-channel operations like captions).
    Reuses publisher.py's token-loading pattern: checks youtube_token.json, refreshes if expired,
    else tries InstalledAppFlow with client_secrets_file.
    Raises YouTubeOAuthNotConfigured if neither token nor client_secrets exist.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        import google_auth_oauthlib.flow as flow_module
    except ImportError:
        raise YouTubeOAuthNotConfigured("OAuth libraries not installed")

    token_file = Path("youtube_token.json")
    creds_file = YOUTUBE_CREDENTIALS

    # Check if token exists and is valid
    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file))
        except Exception:
            creds = None

    # If token missing or invalid, try to refresh or re-auth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            # Try to use client_secrets for interactive OAuth
            if not Path(creds_file).exists():
                raise YouTubeOAuthNotConfigured(
                    f"OAuth not configured: youtube_token.json missing and {creds_file} not found"
                )
            try:
                fl = flow_module.InstalledAppFlow.from_client_secrets_file(
                    creds_file,
                    scopes=["https://www.googleapis.com/auth/youtube.force-ssl"]
                )
                # Note: run_local_server() is interactive — not suitable for headless servers.
                # Instead, we raise an exception to signal that manual setup is needed.
                raise YouTubeOAuthNotConfigured(
                    "OAuth flow requires interactive browser login; use youtube_token.json for server-side auth"
                )
            except YouTubeOAuthNotConfigured:
                raise
            except Exception as e:
                raise YouTubeOAuthNotConfigured(f"OAuth setup failed: {e}")

        # Save the refreshed token
        try:
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        except Exception:
            pass  # Best-effort; don't fail if we can't persist

    return build("youtube", "v3", credentials=creds)


def captions_list(video_id: str) -> List[Dict]:
    """
    List available captions for a video (OAuth required — own-channel only).

    Args:
        video_id: YouTube video ID (e.g., 'dQw4w9WgXcQ')

    Returns:
        List of dicts: [{caption_id, language, name, track_kind}, ...]

    Raises YouTubeOAuthNotConfigured, HttpError.
    """
    if not video_id or not video_id.strip():
        raise ValueError("video_id cannot be empty")

    service = _get_oauth_service()

    try:
        request = service.captions().list(
            videoId=video_id,
            part="snippet",
        )
        result = request.execute()
    except HttpError as e:
        if e.resp.status == 403:
            # 403 can mean not authorized for this video (not owned by the channel)
            error_content = e.content.decode("utf-8") if isinstance(e.content, bytes) else str(e.content)
            if "forbidden" in error_content.lower() or "notAuthorizedForVideoId" in error_content:
                # Video not owned by this channel; raise so caller can handle gracefully
                raise HttpError(e.resp, e.content)
        raise HttpError(e.resp, e.content)

    captions = []
    for item in result.get("items", []):
        snippet = item.get("snippet", {})
        captions.append({
            "caption_id": item.get("id", ""),
            "language": snippet.get("language", ""),
            "name": snippet.get("name", ""),
            "track_kind": snippet.get("trackKind", ""),
        })

    # Record quota cost (best-effort, non-blocking)
    _record_quota("captions.list", _QUOTA_COSTS["captions.list"])

    return captions


def captions_download(caption_id: str, fmt: str = "srt") -> Dict:
    """
    Download caption text for a caption track (OAuth required).

    Args:
        caption_id: Caption ID from captions_list()
        fmt: Format — 'srt', 'vtt', or 'ttml' (default 'srt')

    Returns:
        Dict: {caption_id, fmt, content}

    Raises YouTubeOAuthNotConfigured, ValueError, HttpError.
    """
    if not caption_id or not caption_id.strip():
        raise ValueError("caption_id cannot be empty")
    if fmt not in ("srt", "vtt", "ttml"):
        raise ValueError(f"fmt must be one of srt, vtt, ttml; got {fmt}")

    service = _get_oauth_service()

    try:
        request = service.captions().download(
            id=caption_id,
            tfmt=fmt,  # Translate format parameter for the API
        )
        # Note: captions().download() returns binary content directly
        content = request.execute()
        # The response is bytes; decode to string if possible
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        # Record quota cost (best-effort, non-blocking)
        _record_quota("captions.download", _QUOTA_COSTS["captions.download"])
    except HttpError as e:
        raise HttpError(e.resp, e.content)

    return {
        "caption_id": caption_id,
        "fmt": fmt,
        "content": content,
    }


# ── Quota tracking (best-effort postgres persistence) ────────────────────────

_QUOTA_COSTS = {
    # Documented unit costs per YouTube API documentation
    "search.list": 100,
    "videos.list": 1,
    "videos.list_chart": 1,  # Same as videos.list for trending
    "channels.list": 1,
    "playlistItems.list": 1,
    "captions.list": 50,
    "captions.download": 200,
}


def _record_quota(operation: str, units: int) -> None:
    """
    Record quota usage to postgres (best-effort, non-blocking).
    Uses UTC date as the reset period (Pacific time would be more accurate but UTC is simpler).

    Args:
        operation: One of _QUOTA_COSTS.keys()
        units: Number of units (usually _QUOTA_COSTS[operation])
    """
    if not DATABASE_URL or units <= 0:
        return

    try:
        import psycopg
        conn = psycopg.connect(DATABASE_URL, connect_timeout=2)
        with conn.cursor() as cur:
            # Ensure table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS youtube_quota (
                    day DATE PRIMARY KEY,
                    units INT DEFAULT 0
                )
            """)
            # Upsert: increment units for today
            today = datetime.utcnow().date()
            cur.execute("""
                INSERT INTO youtube_quota (day, units) VALUES (%s, %s)
                ON CONFLICT (day) DO UPDATE SET units = youtube_quota.units + EXCLUDED.units
            """, (today, units))
            conn.commit()
    except Exception:
        # Non-blocking: log server-side but don't fail the API call
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_quota() -> Dict:
    """
    Get current day's quota usage from postgres.

    Returns:
        Dict: {used: int, limit: 10000, remaining: int, reset_at: ISO8601, day: date}

    If DB unavailable, returns default (assumes 0 units used).
    """
    DAILY_LIMIT = 10000
    used = 0

    if DATABASE_URL:
        try:
            import psycopg
            conn = psycopg.connect(DATABASE_URL, connect_timeout=2)
            with conn.cursor() as cur:
                today = datetime.utcnow().date()
                cur.execute(
                    "SELECT COALESCE(units, 0) FROM youtube_quota WHERE day = %s",
                    (today,)
                )
                row = cur.fetchone()
                used = int(row[0]) if row else 0
            conn.close()
        except Exception:
            pass

    remaining = max(0, DAILY_LIMIT - used)
    # Next reset is 24h from now (UTC midnight)
    next_reset = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if next_reset <= datetime.utcnow():
        next_reset = next_reset.replace(day=next_reset.day + 1)
        if next_reset.month > 12:
            next_reset = next_reset.replace(year=next_reset.year + 1, month=1)

    return {
        "used": used,
        "limit": DAILY_LIMIT,
        "remaining": remaining,
        "reset_at": next_reset.isoformat() + "Z",
        "day": str(datetime.utcnow().date()),
    }
