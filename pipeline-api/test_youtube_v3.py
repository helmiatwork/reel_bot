# pipeline-api/test_youtube_v3.py
# Tests for YouTube v3 API client — search, video_details, trending, channel_uploads

import pytest
import json
from unittest.mock import patch, MagicMock
from youtube_v3 import (
    search, video_details, trending, channel_uploads,
    YouTubeNotConfigured, YouTubeQuotaError,
    _parse_iso8601_duration
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
