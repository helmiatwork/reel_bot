"""Unit tests for creators platform column."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from main import _detect_platform


class TestDetectPlatform:
    """Test _detect_platform function."""

    def test_youtube_url(self):
        """YouTube URLs detect as 'youtube'."""
        assert _detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
        assert _detect_platform("https://youtu.be/dQw4w9WgXcQ") == "youtube"
        assert _detect_platform("http://youtube.com/channel/UC123") == "youtube"

    def test_tiktok_url(self):
        """TikTok URLs detect as 'tiktok'."""
        assert _detect_platform("https://www.tiktok.com/@username/video/123") == "tiktok"
        assert _detect_platform("https://tiktok.com/@user") == "tiktok"

    def test_instagram_url(self):
        """Instagram URLs detect as 'instagram'."""
        assert _detect_platform("https://www.instagram.com/p/ABC123") == "instagram"
        assert _detect_platform("https://instagram.com/username") == "instagram"

    def test_xiaohongshu_url(self):
        """Xiaohongshu URLs detect as 'xiaohongshu'."""
        assert _detect_platform("https://www.xiaohongshu.com/explore/123") == "xiaohongshu"
        assert _detect_platform("https://xhslink.com/abc123") == "xiaohongshu"
        assert _detect_platform("https://rednote.com/notes/123") == "xiaohongshu"

    def test_unknown_url(self):
        """Unknown URLs return 'unknown'."""
        assert _detect_platform("https://example.com") == "unknown"
        assert _detect_platform("https://google.com") == "unknown"

    def test_case_insensitive(self):
        """URL detection is case-insensitive."""
        assert _detect_platform("https://WWW.YOUTUBE.COM/watch?v=123") == "youtube"
        assert _detect_platform("https://TIKTOK.COM/@user") == "tiktok"


class TestCreatorsEndpoint:
    """Test GET /creators endpoint returns platform field."""

    @pytest.fixture
    def client(self):
        """Get test client."""
        from main import app
        return app.test_client()

    def test_get_creators_includes_platform(self, client):
        """GET /creators response includes platform field."""
        response = client.get("/creators")
        assert response.status_code == 200
        data = response.get_json()

        assert "creators" in data
        assert "total" in data

        # Even if empty, each creator row should have platform field
        if data["creators"]:
            for creator in data["creators"]:
                assert "platform" in creator
                # Platform can be None/null for existing rows without backfill
                if creator["platform"]:
                    assert creator["platform"] in ["youtube", "tiktok", "instagram", "xiaohongshu", "unknown"]

    def test_get_creators_pagination(self, client):
        """GET /creators supports pagination."""
        response = client.get("/creators?limit=10&offset=0")
        assert response.status_code == 200
        data = response.get_json()

        assert data["limit"] == 10
        assert data["offset"] == 0
        assert isinstance(data["creators"], list)
        assert isinstance(data["total"], int)
