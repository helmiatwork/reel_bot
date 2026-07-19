"""
Tests for idea generator endpoints (2-stage flow)
"""

import pytest
from unittest.mock import patch, MagicMock
import socket
import json
from fastapi.testclient import TestClient
import main as m


@pytest.fixture
def client():
    """FastAPI TestClient for the app."""
    return TestClient(m.app)


class TestGeminiIdeasEndpoint:
    """Tests for /analyze/gemini-ideas endpoint (reworked for stage 1)."""

    def test_valid_youtube_url_returns_instruction_with_save_ideas(self, client):
        """Should return instruction mentioning save_ideas and get_clips."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_conn:
                mock_conn.return_value = None

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=test123")

                assert response.status_code == 200
                data = response.json()
                assert "instruction" in data
                assert data["youtube_url"] == "https://www.youtube.com/watch?v=test123"
                assert "save_ideas" in data["instruction"]
                assert "get_clips" in data["instruction"]
                assert "EXACTLY 5" in data["instruction"] or "5 candidates" in data["instruction"].lower()

    def test_instruction_emphasizes_must_call_save_ideas(self, client):
        """Should emphasize MUST call save_ideas."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_conn:
                mock_conn.return_value = None

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=abc")

                assert response.status_code == 200
                instruction = response.json()["instruction"]
                assert "MUST call save_ideas" in instruction
                assert "STEP 4" in instruction

    def test_invalid_youtube_url_returns_400(self, client):
        """Should return 400 for DNS failure."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = socket.gaierror(socket.EAI_NONAME, "Name or service not known")

            response = client.get("/analyze/gemini-ideas?youtube_url=https://this-domain-does-not-exist-xyz.example/watch?v=abc")

            assert response.status_code == 400

    def test_with_db_source_niche_embedded(self, client):
        """Should embed niche from DB if source exists."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = ("frugal-living",)

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=test")

                assert response.status_code == 200
                data = response.json()
                assert data["niche"] == "frugal-living"
                assert "frugal-living" in data["instruction"]


class TestIdeasStatusEndpoint:
    """Tests for /analyze/ideas-status endpoint."""

    def test_no_row_returns_empty_status(self, client):
        """Should return has_candidates=False when no row exists."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = None

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/ideas-status?youtube_url=https://www.youtube.com/watch?v=test")

                assert response.status_code == 200
                data = response.json()
                assert data["has_candidates"] is False
                assert data["count"] == 0
                assert data["candidates"] is None
                assert data["selected_index"] is None
                assert data["has_detail"] is False
                assert data["detail"] is None

    def test_with_5_candidates_returns_count(self, client):
        """Should return candidates and count when present."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                candidates = [
                    {"title": "Idea 1", "description": "desc1"},
                    {"title": "Idea 2", "description": "desc2"},
                    {"title": "Idea 3", "description": "desc3"},
                    {"title": "Idea 4", "description": "desc4"},
                    {"title": "Idea 5", "description": "desc5"},
                ]

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (candidates, None, None)

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/ideas-status?youtube_url=https://www.youtube.com/watch?v=test")

                assert response.status_code == 200
                data = response.json()
                assert data["has_candidates"] is True
                assert data["count"] == 5
                assert data["candidates"] == candidates
                assert data["selected_index"] is None

    def test_with_detail_returns_detail(self, client):
        """Should return detail when present."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                candidates = [{"title": "Idea 1"}]
                detail = {"naskah": "story", "edit_cues": []}

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (candidates, 0, detail)

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/ideas-status?youtube_url=https://www.youtube.com/watch?v=test")

                assert response.status_code == 200
                data = response.json()
                assert data["has_detail"] is True
                assert data["detail"] == detail
                assert data["selected_index"] == 0

    def test_invalid_url_returns_400(self, client):
        """Should return 400 for invalid URL."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = socket.gaierror(socket.EAI_NONAME, "Name or service not known")

            response = client.get("/analyze/ideas-status?youtube_url=https://this-domain-does-not-exist-xyz.example/watch?v=abc")

            assert response.status_code == 400


class TestIdeasSelectEndpoint:
    """Tests for /analyze/ideas/select endpoint."""

    def test_valid_index_updates_selection(self, client):
        """Should update selected_index for valid index."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                candidates = [
                    {"title": "Idea 1"},
                    {"title": "Idea 2"},
                    {"title": "Idea 3"},
                ]

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (candidates,)

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.post("/analyze/ideas/select?youtube_url=https://www.youtube.com/watch?v=test&index=1")

                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert data["selected_index"] == 1

    def test_out_of_range_index_returns_400(self, client):
        """Should return 400 for out-of-range index."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                candidates = [{"title": "Idea 1"}, {"title": "Idea 2"}]

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (candidates,)

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.post("/analyze/ideas/select?youtube_url=https://www.youtube.com/watch?v=test&index=10")

                assert response.status_code == 400

    def test_no_candidates_returns_400(self, client):
        """Should return 400 when no candidates exist."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = None

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.post("/analyze/ideas/select?youtube_url=https://www.youtube.com/watch?v=test&index=0")

                assert response.status_code == 400

    def test_invalid_url_returns_400(self, client):
        """Should return 400 for invalid URL."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = socket.gaierror(socket.EAI_NONAME, "Name or service not known")

            response = client.post("/analyze/ideas/select?youtube_url=https://this-domain-does-not-exist-xyz.example/watch?v=abc&index=0")

            assert response.status_code == 400


class TestGeminiIdeaDetailEndpoint:
    """Tests for /analyze/gemini-idea-detail endpoint (stage 2)."""

    def test_valid_index_returns_instruction(self, client):
        """Should return instruction for valid candidate index."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                candidates = [
                    {"title": "Viral Hook", "premise": "open with surprise"},
                    {"title": "Idea 2", "premise": "premise 2"},
                ]

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (candidates,)

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/gemini-idea-detail?youtube_url=https://www.youtube.com/watch?v=test&index=0")

                assert response.status_code == 200
                data = response.json()
                assert "instruction" in data
                assert data["youtube_url"] == "https://www.youtube.com/watch?v=test"
                assert data["index"] == 0
                assert data["candidate"] == candidates[0]

    def test_instruction_mentions_save_idea_detail(self, client):
        """Should mention save_idea_detail in instruction."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                candidates = [{"title": "Idea 1", "premise": "test premise"}]

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (candidates,)

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/gemini-idea-detail?youtube_url=https://www.youtube.com/watch?v=test&index=0")

                assert response.status_code == 200
                instruction = response.json()["instruction"]
                assert "save_idea_detail" in instruction
                assert "MUST call save_idea_detail" in instruction

    def test_out_of_range_index_returns_400(self, client):
        """Should return 400 for out-of-range index."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                candidates = [{"title": "Idea 1"}]

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (candidates,)

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/gemini-idea-detail?youtube_url=https://www.youtube.com/watch?v=test&index=5")

                assert response.status_code == 400

    def test_no_candidates_returns_400(self, client):
        """Should return 400 when no candidates exist."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = None

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/gemini-idea-detail?youtube_url=https://www.youtube.com/watch?v=test&index=0")

                assert response.status_code == 400

    def test_invalid_url_returns_400(self, client):
        """Should return 400 for invalid URL."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = socket.gaierror(socket.EAI_NONAME, "Name or service not known")

            response = client.get("/analyze/gemini-idea-detail?youtube_url=https://this-domain-does-not-exist-xyz.example/watch?v=abc&index=0")

            assert response.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
