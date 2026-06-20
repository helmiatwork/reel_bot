# pipeline-api/test_youtube_analytics_api.py
# Tests for YouTube Analytics API endpoints

import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import main
from main import app
import youtube_v3

client = TestClient(app)


class TestYouTubeAnalyticsEndpoints:
    """Test the YouTube Analytics channel endpoints."""

    @patch("main.analytics_core")
    def test_analytics_core_success(self, mock_analytics):
        """Test GET /analytics/channel/core with default dates."""
        mock_analytics.return_value = {
            "columnHeaders": [{"name": "date"}, {"name": "views"}],
            "rows": [["2024-01-01", "100"]],
            "rows_as_dicts": [{"date": "2024-01-01", "views": "100"}],
        }

        response = client.get("/analytics/channel/core")
        assert response.status_code == 200
        data = response.json()
        assert "start" in data
        assert "end" in data
        assert data["by"] is None
        assert len(data["rows"]) == 1
        assert data["rows"][0]["views"] == "100"

    @patch("main.analytics_core")
    def test_analytics_core_with_by_parameter(self, mock_analytics):
        """Test GET /analytics/channel/core?by=day."""
        mock_analytics.return_value = {
            "rows_as_dicts": [
                {"day": "2024-01-01", "views": "100"},
                {"day": "2024-01-02", "views": "200"},
            ],
        }

        response = client.get("/analytics/channel/core?by=day")
        assert response.status_code == 200
        data = response.json()
        assert data["by"] == "day"
        assert len(data["rows"]) == 2

    @patch("main.analytics_core")
    def test_analytics_core_with_custom_dates(self, mock_analytics):
        """Test GET /analytics/channel/core?start=2024-01-01&end=2024-01-31."""
        mock_analytics.return_value = {"rows_as_dicts": []}

        response = client.get("/analytics/channel/core?start=2024-01-01&end=2024-01-31")
        assert response.status_code == 200
        data = response.json()
        assert data["start"] == "2024-01-01"
        assert data["end"] == "2024-01-31"
        mock_analytics.assert_called_once()

    @patch("main.analytics_audience")
    def test_analytics_audience_geography_success(self, mock_audience):
        """Test GET /analytics/channel/audience?kind=geography."""
        mock_audience.return_value = {
            "rows_as_dicts": [
                {"country": "US", "views": "1000"},
                {"country": "GB", "views": "500"},
            ],
        }

        response = client.get("/analytics/channel/audience?kind=geography")
        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "geography"
        assert len(data["rows"]) == 2

    @patch("main.analytics_audience")
    def test_analytics_audience_invalid_kind(self, mock_audience):
        """Test GET /analytics/channel/audience?kind=invalid returns 400."""
        response = client.get("/analytics/channel/audience?kind=invalid")
        assert response.status_code == 400

    @patch("main.analytics_audience")
    def test_analytics_audience_default_kind(self, mock_audience):
        """Test GET /analytics/channel/audience defaults to geography."""
        mock_audience.return_value = {"rows_as_dicts": []}

        response = client.get("/analytics/channel/audience")
        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "geography"
        mock_audience.assert_called_once()
        # Check that kind=geography was passed
        call_args = mock_audience.call_args
        assert call_args[1]["kind"] == "geography"

    @patch("main.analytics_audience")
    def test_analytics_audience_demographics(self, mock_audience):
        """Test GET /analytics/channel/audience?kind=demographics."""
        mock_audience.return_value = {
            "rows_as_dicts": [
                {"ageGroup": "18-24", "gender": "M", "viewerPercentage": "25.5"}
            ],
        }

        response = client.get("/analytics/channel/audience?kind=demographics")
        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "demographics"

    @patch("main.analytics_revenue")
    def test_analytics_revenue_success(self, mock_revenue):
        """Test GET /analytics/channel/revenue."""
        mock_revenue.return_value = {
            "rows_as_dicts": [
                {
                    "estimatedRevenue": "1000.50",
                    "cpm": "12.34",
                }
            ],
        }

        response = client.get("/analytics/channel/revenue")
        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1

    @patch("main.analytics_revenue")
    def test_analytics_revenue_with_by(self, mock_revenue):
        """Test GET /analytics/channel/revenue?by=video."""
        mock_revenue.return_value = {"rows_as_dicts": []}

        response = client.get("/analytics/channel/revenue?by=video")
        assert response.status_code == 200
        data = response.json()
        assert data["by"] == "video"

    @patch("main.analytics_ctr")
    def test_analytics_ctr_raises_metric_not_available(self, mock_ctr):
        """Test GET /analytics/channel/ctr raises YouTubeMetricNotAvailable → 501."""
        mock_ctr.side_effect = youtube_v3.YouTubeMetricNotAvailable(
            "Impressions not available via YouTube Analytics API v2"
        )

        response = client.get("/analytics/channel/ctr")
        assert response.status_code == 501
        data = response.json()
        assert "detail" in data
        assert "not available" in data["detail"].lower()

    @patch("main.analytics_core")
    def test_analytics_core_oauth_not_configured(self, mock_analytics):
        """Test YouTubeOAuthNotConfigured → 503."""
        mock_analytics.side_effect = youtube_v3.YouTubeOAuthNotConfigured(
            "youtube_token.json missing"
        )

        response = client.get("/analytics/channel/core")
        assert response.status_code == 503
        data = response.json()
        assert "youtube_token.json" in data["detail"]

    @patch("main.analytics_core")
    def test_analytics_core_not_configured(self, mock_analytics):
        """Test YouTubeNotConfigured → 503."""
        mock_analytics.side_effect = youtube_v3.YouTubeNotConfigured(
            "YOUTUBE_API_KEY not set"
        )

        response = client.get("/analytics/channel/core")
        assert response.status_code == 503

    @patch("main.analytics_core")
    def test_analytics_core_quota_error(self, mock_analytics):
        """Test YouTubeQuotaError → 429."""
        mock_analytics.side_effect = youtube_v3.YouTubeQuotaError(
            "YouTube API quota exceeded"
        )

        response = client.get("/analytics/channel/core")
        assert response.status_code == 429

    @patch("main.analytics_core")
    def test_analytics_core_value_error(self, mock_analytics):
        """Test ValueError → 400."""
        mock_analytics.side_effect = ValueError("Invalid date format")

        response = client.get("/analytics/channel/core")
        assert response.status_code == 400

    @patch("main.analytics_core")
    def test_analytics_core_http_error(self, mock_analytics):
        """Test HttpError → 502."""
        from googleapiclient.errors import HttpError
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.status = 502
        mock_analytics.side_effect = HttpError(mock_resp, b"Bad Gateway")

        response = client.get("/analytics/channel/core")
        assert response.status_code == 502

    @patch("main.analytics_audience")
    def test_analytics_audience_traffic_kind(self, mock_audience):
        """Test GET /analytics/channel/audience?kind=traffic."""
        mock_audience.return_value = {
            "rows_as_dicts": [
                {
                    "insightTrafficSourceType": "YT_SEARCH",
                    "views": "500",
                }
            ],
        }

        response = client.get("/analytics/channel/audience?kind=traffic")
        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "traffic"

    @patch("main.analytics_audience")
    def test_analytics_audience_device_kind(self, mock_audience):
        """Test GET /analytics/channel/audience?kind=device."""
        mock_audience.return_value = {
            "rows_as_dicts": [
                {"deviceType": "MOBILE", "views": "1000"},
                {"deviceType": "DESKTOP", "views": "500"},
            ],
        }

        response = client.get("/analytics/channel/audience?kind=device")
        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "device"

    def test_analytics_channel_core_response_structure(self):
        """Test that /analytics/channel/core returns the expected response structure."""
        with patch("main.youtube_v3.analytics_core") as mock_analytics:
            mock_analytics.return_value = {
                "columnHeaders": [{"name": "views"}],
                "rows": [["100"]],
                "rows_as_dicts": [{"views": "100"}],
            }

            response = client.get("/analytics/channel/core?start=2024-01-01&end=2024-01-31")
            assert response.status_code == 200
            data = response.json()

            # Check required fields
            assert "start" in data
            assert "end" in data
            assert "by" in data
            assert "rows" in data
            assert isinstance(data["rows"], list)

    def test_analytics_channel_audience_response_structure(self):
        """Test that /analytics/channel/audience returns the expected response structure."""
        with patch("main.youtube_v3.analytics_audience") as mock_audience:
            mock_audience.return_value = {
                "columnHeaders": [{"name": "country"}, {"name": "views"}],
                "rows": [["US", "1000"]],
                "rows_as_dicts": [{"country": "US", "views": "1000"}],
            }

            response = client.get("/analytics/channel/audience?kind=geography")
            assert response.status_code == 200
            data = response.json()

            assert "start" in data
            assert "end" in data
            assert "kind" in data
            assert "rows" in data
            assert isinstance(data["rows"], list)

    def test_analytics_channel_revenue_response_structure(self):
        """Test that /analytics/channel/revenue returns the expected response structure."""
        with patch("main.youtube_v3.analytics_revenue") as mock_revenue:
            mock_revenue.return_value = {
                "columnHeaders": [{"name": "estimatedRevenue"}],
                "rows": [["1000.50"]],
                "rows_as_dicts": [{"estimatedRevenue": "1000.50"}],
            }

            response = client.get("/analytics/channel/revenue")
            assert response.status_code == 200
            data = response.json()

            assert "start" in data
            assert "end" in data
            assert "by" in data
            assert "rows" in data

    @patch("main.analytics_audience")
    def test_analytics_audience_respects_custom_dates(self, mock_audience):
        """Test that /analytics/channel/audience respects custom date parameters."""
        mock_audience.return_value = {"rows_as_dicts": []}

        response = client.get(
            "/analytics/channel/audience?kind=geography&start=2024-06-01&end=2024-06-15"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["start"] == "2024-06-01"
        assert data["end"] == "2024-06-15"
