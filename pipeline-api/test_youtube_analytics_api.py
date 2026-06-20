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


# ── /dash/overview channel block tests ──────────────────────────────────────


def _make_fake_cursor(sources=3, produced=5, total_views=1000, formulas=2, clips=8,
                      top_sources=None, series_rows=None, movers=None):
    """Return a fake psycopg cursor mock that returns canned DB values."""
    cur = MagicMock()

    if top_sources is None:
        top_sources = []
    if series_rows is None:
        series_rows = []
    if movers is None:
        movers = [("Video A", 500), ("Video B", 300)]

    # _scalar is called 5 times in order: sources, produced, total_views, formulas, clips
    cur.fetchone.side_effect = [
        (sources,),
        (produced,),
        (total_views,),
        (formulas,),
        (clips,),
    ]
    # cur.execute is called for top_sources query, then series queries, then movers
    # cur.fetchall is called for each of those
    cur.fetchall.side_effect = [
        top_sources,   # top_sources SELECT
        *[series_rows for _ in top_sources],  # one series SELECT per source
        movers,        # movers SELECT
    ]
    return cur


def _make_fake_conn(cur):
    """Wrap a fake cursor in a fake connection context manager."""
    conn = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = ctx
    return conn


def _analytics_core_side_effect(total_rows, day_rows, video_rows):
    """Build a side_effect callable that returns different results per call order."""
    calls = [0]

    def _side_effect(start_date, end_date, by=None):
        if by is None:
            # total
            return {"rows_as_dicts": total_rows}
        elif by == "day":
            return {"rows_as_dicts": day_rows}
        elif by == "video":
            return {"rows_as_dicts": video_rows}
        return {"rows_as_dicts": []}

    return _side_effect


class TestDashOverviewChannelBlock:
    """Tests for the channel analytics block in /dash/overview."""

    @patch("main._db_conn")
    @patch("main.analytics_core")
    @patch("main.youtube_v3.video_details")
    def test_channel_block_populated(self, mock_video_details, mock_analytics_core, mock_db_conn):
        """channel block is populated with total_views, series, top_videos; kpis still present."""
        cur = _make_fake_cursor(sources=7, produced=12, formulas=4, clips=20)
        mock_db_conn.return_value = _make_fake_conn(cur)

        mock_analytics_core.side_effect = _analytics_core_side_effect(
            total_rows=[{
                "views": "5000",
                "averageViewPercentage": "42.5",
                "averageViewDuration": "65",
            }],
            day_rows=[
                {"day": "2024-01-01", "views": "100"},
                {"day": "2024-01-02", "views": "150"},
            ],
            video_rows=[
                {"video": "abc123", "views": "2000", "averageViewPercentage": "55.0"},
                {"video": "def456", "views": "1000", "averageViewPercentage": "30.0"},
            ],
        )
        mock_video_details.return_value = [
            {"video_id": "abc123", "title": "My Great Video"},
            {"video_id": "def456", "title": "Another Video"},
        ]

        response = client.get("/dash/overview")
        assert response.status_code == 200
        data = response.json()

        # existing kpis keys must still be present
        assert "kpis" in data
        assert data["kpis"]["sources"] == 7
        assert data["kpis"]["produced"] == 12
        assert data["kpis"]["formulas"] == 4
        assert data["kpis"]["clips"] == 20

        # channel block
        assert "channel" in data
        ch = data["channel"]
        assert ch["total_views"] == 5000
        assert ch["avg_view_pct"] == 42.5
        assert ch["avg_duration"] == 65

        # series: one entry labelled "views channel" with two points
        assert len(ch["series"]) == 1
        assert ch["series"][0]["label"] == "views channel"
        points = ch["series"][0]["points"]
        assert len(points) == 2
        assert points[0] == {"d": "01-01", "v": 100}
        assert points[1] == {"d": "01-02", "v": 150}

        # top_videos: resolved titles + retention
        assert len(ch["top_videos"]) == 2
        assert ch["top_videos"][0]["title"] == "My Great Video"
        assert ch["top_videos"][0]["views"] == 2000
        assert ch["top_videos"][0]["retention"] == 55.0
        assert ch["top_videos"][1]["title"] == "Another Video"

        # no error key set
        assert not ch.get("error")

    @patch("main._db_conn")
    @patch("main.analytics_core")
    def test_channel_block_oauth_not_configured(self, mock_analytics_core, mock_db_conn):
        """analytics_core raises YouTubeOAuthNotConfigured → response 200 with channel.error set."""
        cur = _make_fake_cursor()
        mock_db_conn.return_value = _make_fake_conn(cur)

        mock_analytics_core.side_effect = youtube_v3.YouTubeOAuthNotConfigured(
            "youtube_token.json missing"
        )

        response = client.get("/dash/overview")
        assert response.status_code == 200  # must NOT 500
        data = response.json()

        assert "channel" in data
        ch = data["channel"]
        assert ch["total_views"] == 0
        assert ch["error"] != ""
        assert "oauth" in ch["error"].lower()
        # series and top_videos degrade gracefully
        assert ch["series"] == []
        assert ch["top_videos"] == []

    @patch("main._db_conn")
    @patch("main.analytics_core")
    def test_channel_block_not_configured(self, mock_analytics_core, mock_db_conn):
        """analytics_core raises YouTubeNotConfigured → channel.error set, endpoint still 200."""
        cur = _make_fake_cursor()
        mock_db_conn.return_value = _make_fake_conn(cur)

        mock_analytics_core.side_effect = youtube_v3.YouTubeNotConfigured("YOUTUBE_API_KEY not set")

        response = client.get("/dash/overview")
        assert response.status_code == 200
        data = response.json()
        ch = data["channel"]
        assert ch["total_views"] == 0
        assert "api key" in ch["error"].lower()

    @patch("main._db_conn")
    @patch("main.analytics_core")
    def test_channel_block_quota_error(self, mock_analytics_core, mock_db_conn):
        """analytics_core raises YouTubeQuotaError → channel.error set, endpoint still 200."""
        cur = _make_fake_cursor()
        mock_db_conn.return_value = _make_fake_conn(cur)

        mock_analytics_core.side_effect = youtube_v3.YouTubeQuotaError("quota exceeded")

        response = client.get("/dash/overview")
        assert response.status_code == 200
        data = response.json()
        ch = data["channel"]
        assert ch["total_views"] == 0
        assert "quota" in ch["error"].lower()

    @patch("main._db_conn")
    @patch("main.analytics_core")
    def test_channel_block_generic_exception(self, mock_analytics_core, mock_db_conn):
        """Any unexpected exception → channel.error set, endpoint still 200."""
        cur = _make_fake_cursor()
        mock_db_conn.return_value = _make_fake_conn(cur)

        mock_analytics_core.side_effect = RuntimeError("unexpected failure")

        response = client.get("/dash/overview")
        assert response.status_code == 200
        data = response.json()
        ch = data["channel"]
        assert ch["total_views"] == 0
        assert ch["error"] == "RuntimeError"

    @patch("main._db_conn")
    @patch("main.analytics_core")
    @patch("main.youtube_v3.video_details")
    def test_channel_block_title_resolution_failure(
        self, mock_video_details, mock_analytics_core, mock_db_conn
    ):
        """video_details failing → falls back to raw video ID as title, endpoint still 200."""
        cur = _make_fake_cursor()
        mock_db_conn.return_value = _make_fake_conn(cur)

        mock_analytics_core.side_effect = _analytics_core_side_effect(
            total_rows=[{"views": "100", "averageViewPercentage": "30.0", "averageViewDuration": "45"}],
            day_rows=[],
            video_rows=[{"video": "xyz999", "views": "100", "averageViewPercentage": "30.0"}],
        )
        mock_video_details.side_effect = Exception("network error")

        response = client.get("/dash/overview")
        assert response.status_code == 200
        data = response.json()
        ch = data["channel"]
        # title falls back to the raw video id
        assert ch["top_videos"][0]["title"] == "xyz999"
        assert not ch.get("error")  # title failure should NOT poison the whole block
