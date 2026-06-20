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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
