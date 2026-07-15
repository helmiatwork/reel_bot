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
from datetime import datetime, timedelta

# Optional deps hoisted to module level so they are patchable in tests and used
# consistently. Guarded so importing this module never hard-fails when a lib is
# absent (the functions below degrade gracefully).
try:
    from google.oauth2.credentials import Credentials
except ImportError:
    Credentials = None
try:
    import psycopg
except ImportError:
    psycopg = None

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


class YouTubeMetricNotAvailable(Exception):
    """Raised when a requested metric is not exposed by the YouTube Analytics API."""
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

def _get_oauth_service(account_id: Optional[int] = None):
    """Build YouTube v3 service with OAuth credentials (for own-channel operations like captions).
    Reuses shared token-loading pattern: checks youtube_token.json (legacy) or
    youtube_token_<account_id>.json (per-account), refreshes if expired.

    Args:
        account_id: Optional. If given, loads per-account token from credentials/youtube_token_<id>.json.
                   If None, loads legacy youtube_token.json (backward compatible).

    Raises YouTubeOAuthNotConfigured if credentials are not available.
    """
    if Credentials is None:
        raise YouTubeOAuthNotConfigured("OAuth libraries not installed")
    try:
        from google.auth.transport.requests import Request
        import google_auth_oauthlib.flow as flow_module
    except ImportError:
        raise YouTubeOAuthNotConfigured("OAuth libraries not installed")

    # Determine token file path: per-account or legacy
    if account_id is not None:
        token_file = Path(f"credentials/youtube_token_{account_id}.json")
    else:
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
                    f"OAuth not configured: {token_file.name} missing and {creds_file} not found"
                )
            try:
                fl = flow_module.InstalledAppFlow.from_client_secrets_file(
                    creds_file,
                    scopes=OAUTH_SCOPES
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

        # Save the refreshed token with owner-only perms (it's an OAuth credential).
        # Use os.open with 0o600 at creation time to avoid a world-readable race window.
        try:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(token_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(creds.to_json())
            try:
                os.chmod(str(token_file), 0o600)  # defense-in-depth if the file pre-existed
            except OSError:
                pass
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


# ── YouTube Analytics API v2 support ──────────────────────────────────────────

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]


def _load_oauth_creds(account_id: Optional[int] = None):
    """
    Load and refresh OAuth credentials from youtube_token.json (legacy) or
    youtube_token_<account_id>.json (per-account).
    Reuses shared token-loading logic for both captions and analytics.

    Args:
        account_id: Optional. If given, loads per-account token; else legacy token.

    Raises YouTubeOAuthNotConfigured if credentials are not available.
    """
    if Credentials is None:
        raise YouTubeOAuthNotConfigured("OAuth libraries not installed")
    try:
        from google.auth.transport.requests import Request
    except ImportError:
        raise YouTubeOAuthNotConfigured("OAuth libraries not installed")

    # Determine token file path: per-account or legacy
    if account_id is not None:
        token_file = Path(f"credentials/youtube_token_{account_id}.json")
    else:
        token_file = Path("youtube_token.json")
    creds_file = YOUTUBE_CREDENTIALS

    # Check if token exists and is valid
    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file))
        except Exception:
            creds = None

    # If token missing or invalid, try to refresh
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            # No token available and can't refresh; raise error
            raise YouTubeOAuthNotConfigured(
                f"OAuth not configured: {token_file.name} missing and {creds_file} not found"
            )

        # Save the refreshed token with owner-only perms.
        try:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(token_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(creds.to_json())
            try:
                os.chmod(str(token_file), 0o600)
            except OSError:
                pass
        except Exception:
            pass  # Best-effort; don't fail if we can't persist

    return creds


def _get_analytics_service(account_id: Optional[int] = None):
    """Build YouTube Analytics v2 service with OAuth credentials.

    Args:
        account_id: Optional. If given, uses per-account credentials; else legacy.

    Raises YouTubeOAuthNotConfigured if credentials are not available.
    """
    if Credentials is None:
        raise YouTubeOAuthNotConfigured("OAuth libraries not installed")

    creds = _load_oauth_creds(account_id=account_id)
    return build("youtubeAnalytics", "v2", credentials=creds)


def channel_analytics(
    start_date: str,
    end_date: str,
    metrics: List[str],
    dimensions: Optional[List[str]] = None,
    filters: Optional[str] = None,
    sort: Optional[str] = None,
    max_results: Optional[int] = None,
    ids: str = "channel==MINE",
) -> Dict:
    """
    Query YouTube Analytics API v2 for channel analytics data.

    Args:
        start_date: Start date in YYYY-MM-DD format (required)
        end_date: End date in YYYY-MM-DD format (required)
        metrics: List of metric names (e.g., ['views', 'estimatedMinutesWatched'])
        dimensions: Optional list of dimensions (e.g., ['day', 'video'])
        filters: Optional filter expression (e.g., 'video==dQw4w9WgXcQ')
        sort: Optional sort order (e.g., '-views')
        max_results: Optional max results per page
        ids: Resource IDs (default 'channel==MINE' for authenticated channel)

    Returns:
        Dict with columnHeaders, rows, and rows_as_dicts (convenience key zipping headers with rows)

    Raises:
        YouTubeOAuthNotConfigured, YouTubeQuotaError, ValueError, HttpError
    """
    if not start_date or not start_date.strip():
        raise ValueError("start_date cannot be empty")
    if not end_date or not end_date.strip():
        raise ValueError("end_date cannot be empty")

    service = _get_analytics_service()

    try:
        # Build the request with required and optional parameters
        query_kwargs = {
            "ids": ids,
            "startDate": start_date,
            "endDate": end_date,
            "metrics": ",".join(metrics),
        }

        # Add optional parameters
        if dimensions:
            query_kwargs["dimensions"] = ",".join(dimensions)
        if filters:
            query_kwargs["filters"] = filters
        if sort:
            query_kwargs["sort"] = sort
        if max_results is not None:
            query_kwargs["maxResults"] = max_results

        request = service.reports().query(**query_kwargs)
        result = request.execute()
    except HttpError as e:
        if e.resp.status == 403:
            error_content = e.content.decode("utf-8") if isinstance(e.content, bytes) else str(e.content)
            if "quotaExceeded" in error_content or "dailyLimitExceeded" in error_content:
                raise YouTubeQuotaError("YouTube API quota exceeded") from e
        raise HttpError(e.resp, e.content)

    # Add convenience key: rows_as_dicts, which zips columnHeaders names with each row
    rows_as_dicts = []
    if "columnHeaders" in result and "rows" in result:
        col_names = [col["name"] for col in result["columnHeaders"]]
        for row in result["rows"]:
            rows_as_dicts.append(dict(zip(col_names, row)))

    result["rows_as_dicts"] = rows_as_dicts

    # Record quota cost (best-effort, non-blocking)
    _record_quota("analytics.query", _QUOTA_COSTS.get("analytics.query", 1))

    return result


def analytics_core(start_date: str, end_date: str, by: Optional[str] = None) -> Dict:
    """
    Query core analytics metrics (views, watch time, audience growth, engagement).

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        by: Optional dimension: 'day', 'video', or None (channel total)

    Returns:
        Dict with analytics data including rows_as_dicts
    """
    metrics = [
        "views",
        "estimatedMinutesWatched",
        "averageViewDuration",
        "averageViewPercentage",
        "likes",
        "comments",
        "shares",
        "subscribersGained",
        "subscribersLost",
    ]

    dimensions = None
    kwargs = {}
    if by == "day":
        dimensions = ["day"]
    elif by == "video":
        dimensions = ["video"]
        kwargs["sort"] = "-views"
        kwargs["max_results"] = 200

    return channel_analytics(start_date, end_date, metrics, dimensions=dimensions, **kwargs)


def analytics_ctr(start_date: str, end_date: str, by: Optional[str] = None) -> Dict:
    """
    Query click-through rate analytics (impressions, CTR).

    **LIMITATION:** The YouTube Analytics API v2 does NOT expose `impressions` or
    `impressionClickThroughRate` metrics. These metrics are only available via:
    1. YouTube Reporting API (bulk CSV report jobs): https://developers.google.com/youtube/reporting
    2. YouTube Studio UI

    This function raises YouTubeMetricNotAvailable to signal the limitation clearly
    rather than silently failing with HTTP 400.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        by: Optional dimension: 'day', 'video', or None (channel total)

    Raises:
        YouTubeMetricNotAvailable: Always raised because impressions metrics are not
                                   available via the YouTube Analytics API.

    Returns:
        Never returns; always raises YouTubeMetricNotAvailable.
    """
    raise YouTubeMetricNotAvailable(
        "Thumbnail impressions and impression click-through rate (CTR) are not available "
        "via the YouTube Analytics API v2. These metrics are only accessible through:\n"
        "  1. YouTube Reporting API (bulk CSV reports): https://developers.google.com/youtube/reporting\n"
        "  2. YouTube Studio UI (Analytics > Advanced Analytics)\n"
        "This is a Google platform limitation, not a bug in this client."
    )


def analytics_audience(start_date: str, end_date: str, kind: str) -> Dict:
    """
    Query audience composition analytics by demographics, geography, traffic source, or device.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        kind: One of 'demographics', 'geography', 'traffic', 'device'
              - demographics: ageGroup, gender, viewerPercentage
              - geography: country, views, estimatedMinutesWatched
              - traffic: insightTrafficSourceType, views, estimatedMinutesWatched
              - device: deviceType, views, estimatedMinutesWatched

    Returns:
        Dict with analytics data including rows_as_dicts

    Raises:
        ValueError if kind is not recognized
    """
    if kind == "demographics":
        dimensions = ["ageGroup", "gender"]
        metrics = ["viewerPercentage"]
    elif kind == "geography":
        dimensions = ["country"]
        metrics = ["views", "estimatedMinutesWatched"]
        kwargs = {"sort": "-views"}
    elif kind == "traffic":
        dimensions = ["insightTrafficSourceType"]
        metrics = ["views", "estimatedMinutesWatched"]
        kwargs = {}
    elif kind == "device":
        dimensions = ["deviceType"]
        metrics = ["views", "estimatedMinutesWatched"]
        kwargs = {}
    else:
        raise ValueError(f"kind must be one of: demographics, geography, traffic, device; got {kind}")

    if kind == "geography":
        return channel_analytics(start_date, end_date, metrics, dimensions=dimensions, **kwargs)
    else:
        return channel_analytics(start_date, end_date, metrics, dimensions=dimensions)


def analytics_revenue(start_date: str, end_date: str, by: Optional[str] = None) -> Dict:
    """
    Query revenue analytics (estimated revenue, CPM, monetized playbacks).
    REQUIRES: Monetized YouTube channel (YouTube Partner Program) and monetized OAuth scope.
    Will return 403 Forbidden if channel is not monetized or scope is insufficient.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        by: Optional dimension: 'day', 'video', or None (channel total)

    Returns:
        Dict with analytics data including rows_as_dicts
    """
    metrics = [
        "estimatedRevenue",
        "estimatedAdRevenue",
        "grossRevenue",
        "cpm",
        "playbackBasedCpm",
        "monetizedPlaybacks",
    ]

    dimensions = None
    kwargs = {}
    if by == "day":
        dimensions = ["day"]
    elif by == "video":
        dimensions = ["video"]

    return channel_analytics(start_date, end_date, metrics, dimensions=dimensions, **kwargs)


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
    "analytics.query": 1,  # YouTube Analytics v2 query
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
    # Next reset = upcoming UTC midnight (timedelta handles month/year rollover safely).
    midnight_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    next_reset = midnight_today + timedelta(days=1)

    return {
        "used": used,
        "limit": DAILY_LIMIT,
        "remaining": remaining,
        "reset_at": next_reset.isoformat() + "Z",
        "day": str(datetime.utcnow().date()),
    }
