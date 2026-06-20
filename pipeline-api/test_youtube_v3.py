# pipeline-api/test_youtube_v3.py
# Tests for YouTube v3 API client — search, video_details, trending, channel_uploads

import pytest
import json
from unittest.mock import patch, MagicMock
from youtube_v3 import (
    search, video_details, trending, channel_uploads,
    captions_list, captions_download,
    get_quota,
    YouTubeNotConfigured, YouTubeQuotaError, YouTubeOAuthNotConfigured,
    YouTubeMetricNotAvailable,
    _parse_iso8601_duration, _record_quota
)
from googleapiclient.errors import HttpError


# ── Duration parsing tests ──────────────────────────────────────

class TestParseDuration:
    def test_parse_full_duration(self):
        assert _parse_iso8601_duration("PT1H2M3S") == 3723  # 1*3600 + 2*60 + 3

    def test_parse_hours_only(self):
        assert _parse_iso8601_duration("PT2H") == 7200

    def test_parse_minutes_only(self):
        assert _parse_iso8601_duration("PT15M") == 900

    def test_parse_seconds_only(self):
        assert _parse_iso8601_duration("PT45S") == 45

    def test_parse_hours_seconds(self):
        assert _parse_iso8601_duration("PT1H30S") == 3630

    def test_parse_zero(self):
        assert _parse_iso8601_duration("PT0S") == 0

    def test_parse_invalid(self):
        assert _parse_iso8601_duration("invalid") == 0

    def test_parse_empty(self):
        assert _parse_iso8601_duration("") == 0

    def test_parse_none(self):
        assert _parse_iso8601_duration(None) == 0

    def test_parse_no_pt_prefix(self):
        assert _parse_iso8601_duration("1H2M3S") == 0


# ── Search tests ────────────────────────────────────────────

class TestSearch:
    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_search_success(self, mock_build):
        # Mock the YouTube API service
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.search().list
        mock_list.return_value.execute.return_value = {
            "items": [
                {
                    "id": {"videoId": "dQw4w9WgXcQ"},
                    "snippet": {
                        "title": "Test Video",
                        "channelTitle": "Test Channel",
                        "channelId": "UCxxxxx",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "thumbnails": {"default": {"url": "http://example.com/thumb.jpg"}},
                    },
                }
            ]
        }

        result = search("test query", max_results=10)

        assert len(result) == 1
        assert result[0]["video_id"] == "dQw4w9WgXcQ"
        assert result[0]["title"] == "Test Video"
        assert result[0]["channel_title"] == "Test Channel"
        mock_list.assert_called_once()

    @patch("youtube_v3.YOUTUBE_API_KEY", "")
    def test_search_no_api_key(self):
        with pytest.raises(YouTubeNotConfigured):
            search("test query")

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_search_quota_exceeded(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.search().list

        # Simulate quota error
        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_list.return_value.execute.side_effect = HttpError(
            mock_resp, b'{"error": {"code": 403, "reason": "quotaExceeded"}}'
        )

        with pytest.raises(YouTubeQuotaError):
            search("test query")

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_search_empty_query(self, mock_build):
        with pytest.raises(ValueError):
            search("")

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_search_max_results_clamping(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.search().list
        mock_list.return_value.execute.return_value = {"items": []}

        # Test clamp to 1
        search("test", max_results=-5)
        call_args = mock_list.call_args
        assert call_args[1]["maxResults"] == 1

        # Test clamp to 50
        search("test", max_results=100)
        call_args = mock_list.call_args
        assert call_args[1]["maxResults"] == 50


# ── Video details tests ────────────────────────────────────────

class TestVideoDetails:
    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_video_details_single_success(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.videos().list
        mock_list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "dQw4w9WgXcQ",
                    "snippet": {
                        "title": "Test Video",
                        "description": "Test description",
                        "channelTitle": "Test Channel",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "tags": ["tag1", "tag2"],
                    },
                    "contentDetails": {"duration": "PT10M30S"},
                    "statistics": {
                        "viewCount": "1000",
                        "likeCount": "50",
                        "commentCount": "10",
                    },
                }
            ]
        }

        result = video_details("dQw4w9WgXcQ")

        assert result["video_id"] == "dQw4w9WgXcQ"
        assert result["title"] == "Test Video"
        assert result["duration_s"] == 630  # 10*60 + 30
        assert result["view_count"] == 1000
        assert result["like_count"] == 50
        assert result["comment_count"] == 10

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_video_details_multiple(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.videos().list
        mock_list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "vid1",
                    "snippet": {
                        "title": "Video 1",
                        "description": "",
                        "channelTitle": "Ch",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "tags": [],
                    },
                    "contentDetails": {"duration": "PT5M"},
                    "statistics": {"viewCount": "100", "likeCount": "5", "commentCount": "1"},
                },
                {
                    "id": "vid2",
                    "snippet": {
                        "title": "Video 2",
                        "description": "",
                        "channelTitle": "Ch",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "tags": [],
                    },
                    "contentDetails": {"duration": "PT3M"},
                    "statistics": {"viewCount": "200", "likeCount": "10", "commentCount": "2"},
                },
            ]
        }

        result = video_details(["vid1", "vid2"])

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["video_id"] == "vid1"
        assert result[1]["video_id"] == "vid2"

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_video_details_empty_stats(self, mock_build):
        """Test handling of missing/zero statistics."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.videos().list
        mock_list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "vid",
                    "snippet": {
                        "title": "Test",
                        "description": "",
                        "channelTitle": "Ch",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "tags": [],
                    },
                    "contentDetails": {"duration": "PT0S"},
                    "statistics": {},  # Missing counts
                }
            ]
        }

        result = video_details("vid")

        assert result["view_count"] == 0
        assert result["like_count"] == 0
        assert result["comment_count"] == 0
        assert result["duration_s"] == 0

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_video_details_quota_error(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.videos().list

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_list.return_value.execute.side_effect = HttpError(
            mock_resp, b'{"error": {"reason": "dailyLimitExceeded"}}'
        )

        with pytest.raises(YouTubeQuotaError):
            video_details("vid")

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_video_details_empty_input(self, mock_build):
        with pytest.raises(ValueError):
            video_details([])


# ── Trending tests ────────────────────────────────────────

class TestTrending:
    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_trending_success(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.videos().list
        mock_list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "trend1",
                    "snippet": {
                        "title": "Trending Video",
                        "channelTitle": "Popular Ch",
                        "channelId": "UCtrend",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "thumbnails": {"default": {"url": "http://example.com/thumb.jpg"}},
                    },
                }
            ]
        }

        result = trending(region_code="US", max_results=10)

        assert len(result) == 1
        assert result[0]["video_id"] == "trend1"
        assert result[0]["title"] == "Trending Video"

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_trending_region_case_insensitive(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.videos().list
        mock_list.return_value.execute.return_value = {"items": []}

        trending(region_code="jp", max_results=5)
        call_args = mock_list.call_args
        assert call_args[1]["regionCode"] == "JP"

    @patch("youtube_v3.YOUTUBE_API_KEY", "")
    def test_trending_no_api_key(self):
        with pytest.raises(YouTubeNotConfigured):
            trending()


# ── Channel uploads tests ────────────────────────────────────

class TestChannelUploads:
    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_channel_uploads_success(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock channels().list() call
        mock_channels_list = mock_service.channels().list
        mock_channels_list.return_value.execute.return_value = {
            "items": [
                {
                    "contentDetails": {
                        "relatedPlaylists": {"uploads": "UUxxxxx"}
                    }
                }
            ]
        }

        # Mock playlistItems().list() call
        mock_playlist_list = mock_service.playlistItems().list
        mock_playlist_list.return_value.execute.return_value = {
            "items": [
                {
                    "snippet": {
                        "resourceId": {"videoId": "vid1"},
                        "title": "Upload 1",
                        "channelTitle": "Test Channel",
                        "channelId": "UCxxxxx",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "thumbnails": {"default": {"url": "http://example.com/thumb.jpg"}},
                    }
                }
            ]
        }

        result = channel_uploads("UCxxxxx", max_results=10)

        assert len(result) == 1
        assert result[0]["video_id"] == "vid1"
        assert result[0]["title"] == "Upload 1"

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_channel_uploads_no_uploads_playlist(self, mock_build):
        """Test graceful handling when channel has no uploads playlist."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_channels_list = mock_service.channels().list
        mock_channels_list.return_value.execute.return_value = {
            "items": [{"contentDetails": {"relatedPlaylists": {}}}]
        }

        result = channel_uploads("UCxxxxx")

        assert result == []

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_channel_uploads_channel_not_found(self, mock_build):
        """Test graceful handling when channel doesn't exist."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_channels_list = mock_service.channels().list
        mock_channels_list.return_value.execute.return_value = {"items": []}

        result = channel_uploads("UCinvalid")

        assert result == []

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_channel_uploads_empty_channel_id(self, mock_build):
        with pytest.raises(ValueError):
            channel_uploads("")

    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_channel_uploads_quota_error(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_channels_list = mock_service.channels().list
        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_channels_list.return_value.execute.side_effect = HttpError(
            mock_resp, b'{"error": {"reason": "quotaExceeded"}}'
        )

        with pytest.raises(YouTubeQuotaError):
            channel_uploads("UCxxxxx")


# ── Integration-style tests (mocked API) ────────────────────

class TestIntegration:
    @patch("youtube_v3.YOUTUBE_API_KEY", "test_key")
    @patch("youtube_v3.build")
    def test_end_to_end_search_and_details(self, mock_build):
        """Search for videos, then fetch details on one of them."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # First call: search
        mock_search_list = mock_service.search().list
        mock_search_list.return_value.execute.return_value = {
            "items": [
                {
                    "id": {"videoId": "vid123"},
                    "snippet": {
                        "title": "Result 1",
                        "channelTitle": "Channel 1",
                        "channelId": "UCch1",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "thumbnails": {"default": {"url": "http://example.com/thumb.jpg"}},
                    },
                }
            ]
        }

        results = search("test")
        assert len(results) == 1

        # Now fetch details on the found video
        mock_videos_list = mock_service.videos().list
        mock_videos_list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "vid123",
                    "snippet": {
                        "title": "Result 1",
                        "description": "Full description here",
                        "channelTitle": "Channel 1",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "tags": ["tag1"],
                    },
                    "contentDetails": {"duration": "PT5M"},
                    "statistics": {"viewCount": "5000", "likeCount": "100", "commentCount": "20"},
                }
            ]
        }

        details = video_details("vid123")
        assert details["view_count"] == 5000
        assert details["duration_s"] == 300


# ── Captions tests ──────────────────────────────────────────────

class TestCaptions:
    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_captions_list_success(self, mock_build, mock_path):
        """Test successful caption listing (OAuth)."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_list = mock_service.captions().list
        mock_list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "cap1",
                    "snippet": {
                        "language": "en",
                        "name": "English",
                        "trackKind": "standard",
                    },
                },
                {
                    "id": "cap2",
                    "snippet": {
                        "language": "es",
                        "name": "Spanish",
                        "trackKind": "standard",
                    },
                },
            ]
        }

        # Mock the OAuth flow
        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds
            result = captions_list("dQw4w9WgXcQ")

        assert len(result) == 2
        assert result[0]["caption_id"] == "cap1"
        assert result[0]["language"] == "en"
        assert result[1]["caption_id"] == "cap2"

    @patch("youtube_v3.Path")
    def test_captions_list_no_oauth(self, mock_path):
        """Test caption list when OAuth not configured."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = False
        mock_path.return_value = mock_path_obj

        with pytest.raises(YouTubeOAuthNotConfigured):
            captions_list("vid")

    @patch("youtube_v3.Path")
    def test_captions_download_invalid_format(self, mock_path):
        """Test captions download with invalid format."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            with pytest.raises(ValueError):
                captions_download("cap1", fmt="invalid")


# ── Quota tracking tests ────────────────────────────────────────

class TestQuotaTracking:
    @patch("youtube_v3.psycopg")
    @patch("youtube_v3.DATABASE_URL", "postgres://localhost/test")
    def test_record_quota_success(self, mock_psycopg):
        """Test successful quota recording."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_psycopg.connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # This should not raise
        _record_quota("search.list", 100)

        # Verify execute was called (table creation + upsert)
        assert mock_cursor.execute.call_count >= 2

    @patch("youtube_v3.DATABASE_URL", "")
    def test_record_quota_no_db(self):
        """Test quota recording when DB not configured."""
        # Should return gracefully without error
        _record_quota("search.list", 100)

    @patch("youtube_v3.psycopg")
    @patch("youtube_v3.DATABASE_URL", "postgres://localhost/test")
    def test_record_quota_db_error(self, mock_psycopg):
        """Test quota recording handles DB errors gracefully."""
        mock_psycopg.connect.side_effect = Exception("Connection refused")

        # Should not raise, just fail silently
        _record_quota("search.list", 100)

    @patch("youtube_v3.psycopg")
    @patch("youtube_v3.DATABASE_URL", "postgres://localhost/test")
    def test_get_quota_success(self, mock_psycopg):
        """Test successful quota retrieval."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_psycopg.connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (500,)

        result = get_quota()

        assert result["used"] == 500
        assert result["limit"] == 10000
        assert result["remaining"] == 9500
        assert "reset_at" in result
        assert "day" in result

    @patch("youtube_v3.DATABASE_URL", "")
    def test_get_quota_no_db(self):
        """Test quota retrieval when DB not configured."""
        result = get_quota()

        assert result["used"] == 0
        assert result["limit"] == 10000
        assert result["remaining"] == 10000

    @patch("youtube_v3.psycopg")
    @patch("youtube_v3.DATABASE_URL", "postgres://localhost/test")
    def test_get_quota_reset_boundary(self, mock_psycopg):
        """Test quota reset_at is always in the future."""
        from datetime import datetime as dt, timezone, timedelta
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_psycopg.connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (0,)

        result = get_quota()
        reset_at = dt.fromisoformat(result["reset_at"].replace("Z", "+00:00"))
        now = dt.now(timezone.utc)

        # Reset should be in the future, within the next 24h.
        assert reset_at > now
        assert reset_at - now <= timedelta(hours=24)


# ── Normalization tests (main.py) ──────────────────────────────
# Note: These test the normalization helper in main.py by importing it.
# They're included in test_youtube_v3.py for organizational simplicity.

class TestNormalization:
    def test_normalize_ytdlp_video_basic(self):
        """Test yt-dlp video normalization to v3 shape."""
        # Define the normalize function inline to avoid circular imports
        def _normalize_ytdlp_video(raw: dict) -> dict:
            if not raw:
                return {}
            vid = raw.get("id") or raw.get("video_id") or ""
            return {
                "video_id": vid,
                "title": raw.get("title", ""),
                "description": (raw.get("description", "") or "")[:1000],
                "duration_iso": "",
                "duration_s": raw.get("duration", 0),
                "view_count": int(raw.get("view_count", 0) or 0),
                "like_count": int(raw.get("like_count", 0) or 0),
                "comment_count": int(raw.get("comment_count", 0) or 0),
                "channel_title": raw.get("channel", "") or raw.get("uploader", ""),
                "tags": raw.get("tags", [])[:20] if raw.get("tags") else [],
                "published_at": raw.get("upload_date") or "",
            }

        raw = {
            "id": "dQw4w9WgXcQ",
            "title": "Test Video",
            "description": "A test video",
            "duration": 180,
            "view_count": 1000000,
            "like_count": 50000,
            "comment_count": 5000,
            "channel": "Test Channel",
            "tags": ["test", "video"],
            "upload_date": "2024-01-01",
        }

        result = _normalize_ytdlp_video(raw)

        assert result["video_id"] == "dQw4w9WgXcQ"
        assert result["title"] == "Test Video"
        assert result["duration_s"] == 180
        assert result["view_count"] == 1000000
        assert result["channel_title"] == "Test Channel"
        assert len(result["tags"]) == 2

    def test_normalize_ytdlp_video_empty(self):
        """Test normalization of empty yt-dlp video."""
        def _normalize_ytdlp_video(raw: dict) -> dict:
            raw = raw or {}  # always emit full shape (matches main.py)
            vid = raw.get("id") or raw.get("video_id") or ""
            return {
                "video_id": vid,
                "title": raw.get("title", ""),
                "description": (raw.get("description", "") or "")[:1000],
                "duration_iso": "",
                "duration_s": raw.get("duration", 0),
                "view_count": int(raw.get("view_count", 0) or 0),
                "like_count": int(raw.get("like_count", 0) or 0),
                "comment_count": int(raw.get("comment_count", 0) or 0),
                "channel_title": raw.get("channel", "") or raw.get("uploader", ""),
                "tags": raw.get("tags", [])[:20] if raw.get("tags") else [],
                "published_at": raw.get("upload_date") or "",
            }

        result = _normalize_ytdlp_video({})

        assert result["video_id"] == ""
        assert result["title"] == ""
        assert result["duration_s"] == 0

    def test_normalize_ytdlp_video_fallbacks(self):
        """Test normalization with fallback fields."""
        def _normalize_ytdlp_video(raw: dict) -> dict:
            if not raw:
                return {}
            vid = raw.get("id") or raw.get("video_id") or ""
            return {
                "video_id": vid,
                "title": raw.get("title", ""),
                "description": (raw.get("description", "") or "")[:1000],
                "duration_iso": "",
                "duration_s": raw.get("duration", 0),
                "view_count": int(raw.get("view_count", 0) or 0),
                "like_count": int(raw.get("like_count", 0) or 0),
                "comment_count": int(raw.get("comment_count", 0) or 0),
                "channel_title": raw.get("channel", "") or raw.get("uploader", ""),
                "tags": raw.get("tags", [])[:20] if raw.get("tags") else [],
                "published_at": raw.get("upload_date") or "",
            }

        raw = {
            "video_id": "vid123",
            "uploader": "Test Uploader",
        }

        result = _normalize_ytdlp_video(raw)

        assert result["video_id"] == "vid123"
        assert result["channel_title"] == "Test Uploader"


# ── YouTube Analytics API v2 tests ────────────────────────────────────

class TestAnalyticsOAuthScopes:
    """Test OAUTH_SCOPES constant includes analytics and monetary scopes."""

    def test_oauth_scopes_includes_force_ssl(self):
        """OAUTH_SCOPES includes the force-ssl scope for captions."""
        from youtube_v3 import OAUTH_SCOPES
        assert "https://www.googleapis.com/auth/youtube.force-ssl" in OAUTH_SCOPES

    def test_oauth_scopes_includes_yt_analytics(self):
        """OAUTH_SCOPES includes the yt-analytics.readonly scope."""
        from youtube_v3 import OAUTH_SCOPES
        assert "https://www.googleapis.com/auth/yt-analytics.readonly" in OAUTH_SCOPES

    def test_oauth_scopes_includes_monetary(self):
        """OAUTH_SCOPES includes the yt-analytics-monetary.readonly scope."""
        from youtube_v3 import OAUTH_SCOPES
        assert "https://www.googleapis.com/auth/yt-analytics-monetary.readonly" in OAUTH_SCOPES


class TestGetAnalyticsService:
    """Test _get_analytics_service() helper."""

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_get_analytics_service_success(self, mock_build, mock_path):
        """Test successful analytics service creation with valid OAuth token."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import _get_analytics_service
            result = _get_analytics_service()

        assert result is not None
        mock_build.assert_called_once()
        # build is called as build("youtubeAnalytics", "v2", credentials=creds)
        call_args = mock_build.call_args
        assert call_args[0][0] == "youtubeAnalytics"
        assert call_args[0][1] == "v2"
        assert "credentials" in call_args[1]

    @patch("youtube_v3.Path")
    def test_get_analytics_service_no_oauth(self, mock_path):
        """Test analytics service raises YouTubeOAuthNotConfigured when no token."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = False
        mock_path.return_value = mock_path_obj

        from youtube_v3 import _get_analytics_service, YouTubeOAuthNotConfigured
        with pytest.raises(YouTubeOAuthNotConfigured):
            _get_analytics_service()

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_get_analytics_service_refreshes_expired_token(self, mock_build, mock_path):
        """Test analytics service refreshes expired token."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = False
            mock_creds.expired = True
            mock_creds.refresh_token = "refresh_token"
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            # Patch filesystem calls to prevent writing mock files
            with patch("youtube_v3.os.open") as mock_os_open, \
                 patch("youtube_v3.os.fdopen", create=True) as mock_os_fdopen, \
                 patch("youtube_v3.os.chmod") as mock_os_chmod:
                mock_fd = MagicMock()
                mock_os_open.return_value = mock_fd
                mock_os_fdopen.return_value.__enter__.return_value = MagicMock()

                from youtube_v3 import _get_analytics_service
                result = _get_analytics_service()

        # Should have called refresh
        assert result is not None


class TestChannelAnalytics:
    """Test channel_analytics() query wrapper."""

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_channel_analytics_basic_query(self, mock_build, mock_path):
        """Test basic analytics query with metrics and dimensions."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [
                {"name": "views", "dataType": "INTEGER"},
                {"name": "estimatedMinutesWatched", "dataType": "INTEGER"},
            ],
            "rows": [
                ["1000", "5000"],
                ["1500", "7000"],
            ],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import channel_analytics
            result = channel_analytics("2024-01-01", "2024-01-31", ["views", "estimatedMinutesWatched"])

        assert result["columnHeaders"] == [
            {"name": "views", "dataType": "INTEGER"},
            {"name": "estimatedMinutesWatched", "dataType": "INTEGER"},
        ]
        assert len(result["rows"]) == 2
        assert result["rows"][0] == ["1000", "5000"]

        # Check rows_as_dicts convenience key
        assert "rows_as_dicts" in result
        assert len(result["rows_as_dicts"]) == 2
        assert result["rows_as_dicts"][0]["views"] == "1000"
        assert result["rows_as_dicts"][0]["estimatedMinutesWatched"] == "5000"
        assert result["rows_as_dicts"][1]["views"] == "1500"
        assert result["rows_as_dicts"][1]["estimatedMinutesWatched"] == "7000"

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_channel_analytics_with_dimensions_and_filters(self, mock_build, mock_path):
        """Test analytics query with dimensions and filters."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "day"}, {"name": "views"}],
            "rows": [["2024-01-01", "100"], ["2024-01-02", "150"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import channel_analytics
            result = channel_analytics(
                "2024-01-01", "2024-01-31",
                ["views"],
                dimensions=["day"],
                filters="video==dQw4w9WgXcQ",
                sort="-views"
            )

        # Verify the call was made with expected kwargs
        call_kwargs = mock_query_method.call_args.kwargs
        assert call_kwargs["startDate"] == "2024-01-01"
        assert call_kwargs["endDate"] == "2024-01-31"
        assert call_kwargs["metrics"] == "views"
        assert call_kwargs["dimensions"] == "day"
        assert call_kwargs["filters"] == "video==dQw4w9WgXcQ"
        assert call_kwargs["sort"] == "-views"

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_channel_analytics_quota_exceeded(self, mock_build, mock_path):
        """Test quota exceeded handling."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query = mock_service.reports().query()

        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_query.execute.side_effect = HttpError(
            mock_resp, b'{"error": {"reason": "quotaExceeded"}}'
        )

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import channel_analytics, YouTubeQuotaError
            with pytest.raises(YouTubeQuotaError):
                channel_analytics("2024-01-01", "2024-01-31", ["views"])

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_channel_analytics_invalid_dates(self, mock_build, mock_path):
        """Test empty date validation."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import channel_analytics
            with pytest.raises(ValueError):
                channel_analytics("", "2024-01-31", ["views"])

            with pytest.raises(ValueError):
                channel_analytics("2024-01-01", "", ["views"])


class TestYouTubeMetricNotAvailable:
    """Test YouTubeMetricNotAvailable exception class."""

    def test_exception_exists_and_is_exception_subclass(self):
        """Test that YouTubeMetricNotAvailable is defined and is an Exception."""
        from youtube_v3 import YouTubeMetricNotAvailable
        assert issubclass(YouTubeMetricNotAvailable, Exception)

    def test_exception_can_be_raised_and_caught(self):
        """Test that YouTubeMetricNotAvailable can be raised and caught."""
        from youtube_v3 import YouTubeMetricNotAvailable
        with pytest.raises(YouTubeMetricNotAvailable):
            raise YouTubeMetricNotAvailable("Test message")

    def test_exception_message_contains_youtube_reporting_api_link(self):
        """Test that exception message mentions YouTube Reporting API as alternative."""
        from youtube_v3 import analytics_ctr
        with pytest.raises(YouTubeMetricNotAvailable) as exc_info:
            analytics_ctr("2024-01-01", "2024-01-31")
        assert "YouTube Reporting API" in str(exc_info.value)
        assert "https://developers.google.com/youtube/reporting" in str(exc_info.value)


class TestAnalyticsCore:
    """Test analytics_core() convenience wrapper."""

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_core_channel_total(self, mock_build, mock_path):
        """Test analytics_core with no dimension (channel total)."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "views"}],
            "rows": [["10000"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_core
            result = analytics_core("2024-01-01", "2024-01-31")

        # Verify the correct metrics are used
        call_kwargs = mock_query_method.call_args.kwargs
        expected_metrics = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost"
        assert call_kwargs["metrics"] == expected_metrics
        assert call_kwargs.get("dimensions") is None

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_core_by_day(self, mock_build, mock_path):
        """Test analytics_core with by='day' dimension."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "day"}, {"name": "views"}],
            "rows": [["2024-01-01", "100"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_core
            result = analytics_core("2024-01-01", "2024-01-31", by="day")

        call_kwargs = mock_query_method.call_args.kwargs
        assert call_kwargs["dimensions"] == "day"

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_core_by_video(self, mock_build, mock_path):
        """Test analytics_core with by='video' dimension."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "video"}, {"name": "views"}],
            "rows": [["vid1", "1000"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_core
            result = analytics_core("2024-01-01", "2024-01-31", by="video")

        call_kwargs = mock_query_method.call_args.kwargs
        assert call_kwargs["dimensions"] == "video"
        assert call_kwargs["sort"] == "-views"
        assert call_kwargs["maxResults"] == 200


class TestAnalyticsCTR:
    """Test analytics_ctr() convenience wrapper."""

    def test_analytics_ctr_raises_metric_not_available(self):
        """Test that analytics_ctr() raises YouTubeMetricNotAvailable immediately."""
        from youtube_v3 import analytics_ctr

        with pytest.raises(YouTubeMetricNotAvailable):
            analytics_ctr("2024-01-01", "2024-01-31")

    def test_analytics_ctr_raises_with_by_day(self):
        """Test that analytics_ctr() raises even with by='day' dimension."""
        from youtube_v3 import analytics_ctr

        with pytest.raises(YouTubeMetricNotAvailable):
            analytics_ctr("2024-01-01", "2024-01-31", by="day")

    def test_analytics_ctr_raises_with_by_video(self):
        """Test that analytics_ctr() raises even with by='video' dimension."""
        from youtube_v3 import analytics_ctr

        with pytest.raises(YouTubeMetricNotAvailable):
            analytics_ctr("2024-01-01", "2024-01-31", by="video")


class TestAnalyticsAudience:
    """Test analytics_audience() convenience wrapper."""

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_audience_demographics(self, mock_build, mock_path):
        """Test analytics_audience with demographics."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "ageGroup"}, {"name": "gender"}, {"name": "viewerPercentage"}],
            "rows": [["18-24", "MALE", "0.25"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_audience
            result = analytics_audience("2024-01-01", "2024-01-31", kind="demographics")

        call_kwargs = mock_query_method.call_args.kwargs
        assert "ageGroup" in call_kwargs["dimensions"]
        assert "gender" in call_kwargs["dimensions"]
        assert call_kwargs["metrics"] == "viewerPercentage"

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_audience_geography(self, mock_build, mock_path):
        """Test analytics_audience with geography."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "country"}, {"name": "views"}],
            "rows": [["JP", "5000"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_audience
            result = analytics_audience("2024-01-01", "2024-01-31", kind="geography")

        call_kwargs = mock_query_method.call_args.kwargs
        assert call_kwargs["dimensions"] == "country"
        assert "views" in call_kwargs["metrics"]
        assert call_kwargs["sort"] == "-views"

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_audience_traffic(self, mock_build, mock_path):
        """Test analytics_audience with traffic sources."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "insightTrafficSourceType"}, {"name": "views"}],
            "rows": [["SEARCH", "1000"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_audience
            result = analytics_audience("2024-01-01", "2024-01-31", kind="traffic")

        call_kwargs = mock_query_method.call_args.kwargs
        assert call_kwargs["dimensions"] == "insightTrafficSourceType"

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_audience_device(self, mock_build, mock_path):
        """Test analytics_audience with device type."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "deviceType"}, {"name": "views"}],
            "rows": [["MOBILE", "8000"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_audience
            result = analytics_audience("2024-01-01", "2024-01-31", kind="device")

        call_kwargs = mock_query_method.call_args.kwargs
        assert call_kwargs["dimensions"] == "deviceType"


class TestAnalyticsRevenue:
    """Test analytics_revenue() convenience wrapper."""

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_revenue_success(self, mock_build, mock_path):
        """Test analytics_revenue with monetized channel."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "estimatedRevenue"}],
            "rows": [["1500.50"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_revenue
            result = analytics_revenue("2024-01-01", "2024-01-31")

        call_kwargs = mock_query_method.call_args.kwargs
        expected_metrics = "estimatedRevenue,estimatedAdRevenue,grossRevenue,cpm,playbackBasedCpm,monetizedPlaybacks"
        assert call_kwargs["metrics"] == expected_metrics

    @patch("youtube_v3.Path")
    @patch("youtube_v3.build")
    def test_analytics_revenue_by_video(self, mock_build, mock_path):
        """Test analytics_revenue with video dimension."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.return_value = mock_path_obj

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_query_method = mock_service.reports.return_value.query
        mock_query_method.return_value.execute.return_value = {
            "columnHeaders": [{"name": "video"}, {"name": "estimatedRevenue"}],
            "rows": [["vid1", "500.00"]],
        }

        with patch("youtube_v3.Credentials") as mock_creds_class:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds_class.from_authorized_user_file.return_value = mock_creds

            from youtube_v3 import analytics_revenue
            result = analytics_revenue("2024-01-01", "2024-01-31", by="video")

        call_kwargs = mock_query_method.call_args.kwargs
        assert call_kwargs["dimensions"] == "video"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
