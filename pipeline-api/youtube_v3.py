# pipeline-api/youtube_v3.py
# YouTube Data API v3 client — read-only search, metadata, trending, uploads
# Falls back gracefully when API key is missing or quota is exceeded.

import os
import json
from typing import List, Optional, Dict
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")


class YouTubeNotConfigured(Exception):
    """Raised when YOUTUBE_API_KEY is not set."""
    pass


class YouTubeQuotaError(Exception):
    """Raised when YouTube API quota is exceeded (403 with quotaExceeded/dailyLimitExceeded)."""
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
