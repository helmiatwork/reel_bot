"""
Tests for /analyze/gemini-ideas endpoint
"""

import pytest
from unittest.mock import patch, MagicMock
import socket
from fastapi.testclient import TestClient
import main as m


@pytest.fixture
def client():
    """FastAPI TestClient for the app."""
    return TestClient(m.app)


class TestGeminiIdeasEndpoint:
    """Tests for /analyze/gemini-ideas endpoint."""

    def test_valid_youtube_url_no_db_source(self, client):
        """Should return instruction with default niche when URL is valid but not in DB."""
        with patch("socket.getaddrinfo") as mock_ga:
            # Mock public IP resolution
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_conn:
                # Mock DB connection to return None (no source found)
                mock_conn.return_value = None

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ")

                assert response.status_code == 200
                data = response.json()
                assert "instruction" in data
                assert data["youtube_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                assert data["niche"] == "general"
                assert "get_clips" in data["instruction"]
                assert "3-5" in data["instruction"].lower() or "3–5" in data["instruction"]
                assert "JSON" in data["instruction"]

    def test_valid_youtube_url_with_db_source(self, client):
        """Should return instruction with source's niche when found in DB."""
        with patch("socket.getaddrinfo") as mock_ga:
            # Mock public IP resolution
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                # Mock DB connection and cursor
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = ("frugal-living", "river bath tutorial")

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=abc123")

                assert response.status_code == 200
                data = response.json()
                assert data["niche"] == "frugal-living"
                assert "frugal-living" in data["instruction"]
                assert "get_clips" in data["instruction"]

    def test_invalid_youtube_url(self, client):
        """Should return 400 error for DNS failure (mocked getaddrinfo)."""
        with patch("socket.getaddrinfo") as mock_ga:
            # Mock DNS failure for a non-localhost hostname
            mock_ga.side_effect = socket.gaierror(socket.EAI_NONAME, "Name or service not known")

            response = client.get("/analyze/gemini-ideas?youtube_url=https://this-domain-does-not-exist-xyz.example/watch?v=abc")

            assert response.status_code == 400
            assert "invalid youtube_url" in response.json()["detail"]

    def test_empty_youtube_url(self, client):
        """Should return 400 error for empty URL."""
        response = client.get("/analyze/gemini-ideas?youtube_url=")

        assert response.status_code == 400

    def test_instruction_contains_required_elements(self, client):
        """Should include all key elements in the instruction."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_db_conn.return_value = None

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=test123")

                assert response.status_code == 200
                instruction = response.json()["instruction"]

                # Check key required elements
                assert "get_clips" in instruction
                assert "STEP 1" in instruction
                assert "STEP 2" in instruction
                assert "STEP 3" in instruction
                assert "JSON" in instruction
                assert "hook" in instruction
                assert "cover_caption" in instruction
                assert "hashtags" in instruction
                assert "angle" in instruction

    def test_instruction_warns_against_fabrication(self, client):
        """Should warn against inventing ideas without actually watching clips."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_db_conn.return_value = None

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=test123")

                assert response.status_code == 200
                instruction = response.json()["instruction"]

                # Check for safety guardrails
                assert "WATCH" in instruction
                assert "never invent" in instruction.lower()
                assert "fabricate" in instruction.lower()

    def test_db_query_with_null_niche(self, client):
        """Should default to 'general' when DB returns NULL niche."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_cursor = MagicMock()
                # DB returns (None, "title") — niche is null
                mock_cursor.fetchone.return_value = (None, "some title")

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=xyz")

                assert response.status_code == 200
                data = response.json()
                assert data["niche"] == "general"

    def test_db_connection_failure_non_fatal(self, client):
        """Should proceed with default niche even if DB connection fails."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                # DB connection raises an exception
                mock_db_conn.side_effect = Exception("DB connection failed")

                response = client.get("/analyze/gemini-ideas?youtube_url=https://www.youtube.com/watch?v=abc")

                # Should still succeed with default niche
                assert response.status_code == 200
                data = response.json()
                assert data["niche"] == "general"
                assert "instruction" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
