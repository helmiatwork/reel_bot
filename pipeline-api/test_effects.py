"""
Tests for effects breakdown endpoints
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


class TestGeminiEffectsEndpoint:
    """Tests for /analyze/gemini-effects endpoint."""

    def test_valid_youtube_url_returns_instruction_with_save_effects(self, client):
        """Should return instruction mentioning save_effects and get_clips."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_conn:
                mock_conn.return_value = None

                response = client.get("/analyze/gemini-effects?youtube_url=https://www.youtube.com/watch?v=test123")

                assert response.status_code == 200
                data = response.json()
                assert "instruction" in data
                assert data["youtube_url"] == "https://www.youtube.com/watch?v=test123"
                assert "save_effects" in data["instruction"]
                assert "get_clips" in data["instruction"]
                assert "zoom" in data["instruction"].lower() or "effect" in data["instruction"].lower()

    def test_instruction_emphasizes_must_call_save_effects(self, client):
        """Should emphasize MUST call save_effects."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_conn:
                mock_conn.return_value = None

                response = client.get("/analyze/gemini-effects?youtube_url=https://www.youtube.com/watch?v=abc")

                assert response.status_code == 200
                instruction = response.json()["instruction"]
                assert "MUST call save_effects" in instruction
                assert "STEP 3" in instruction

    def test_invalid_youtube_url_returns_400(self, client):
        """Should return 400 for DNS failure."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = socket.gaierror(socket.EAI_NONAME, "Name or service not known")

            response = client.get("/analyze/gemini-effects?youtube_url=https://this-domain-does-not-exist-xyz.example/watch?v=abc")

            assert response.status_code == 400

    def test_url_with_quote_is_sanitized(self, client):
        """Should sanitize quotes in the URL."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_conn:
                mock_conn.return_value = None

                response = client.get('/analyze/gemini-effects?youtube_url=https://www.youtube.com/watch?v=test"malicious')

                assert response.status_code == 200
                data = response.json()
                # Check that quotes are stripped from the instruction
                assert '"malicious' not in data["instruction"]


class TestEffectsStatusEndpoint:
    """Tests for /analyze/effects-status endpoint."""

    def test_no_row_returns_empty_status(self, client):
        """Should return has_effects=False when no row exists."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = None

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/effects-status?youtube_url=https://www.youtube.com/watch?v=test")

                assert response.status_code == 200
                data = response.json()
                assert data["has_effects"] is False
                assert data["count"] == 0
                assert data["effects"] is None
                assert data["effects_at"] is None

    def test_with_effects_returns_count_and_effects(self, client):
        """Should return effects and count when present."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                effects = [
                    {"ts_start": "0:03", "ts_end": "0:05", "effect": "zoom in", "capcut_tool": "Keyframe > Scale", "how_to": "Add keyframes", "intensity": "medium"},
                    {"ts_start": "0:05", "ts_end": "0:08", "effect": "slow motion", "capcut_tool": "Speed > Curve", "how_to": "Adjust speed curve", "intensity": "strong"},
                ]

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (effects, "2026-07-24T12:00:00")

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/effects-status?youtube_url=https://www.youtube.com/watch?v=test")

                assert response.status_code == 200
                data = response.json()
                assert data["has_effects"] is True
                assert data["count"] == 2
                assert data["effects"] == effects
                assert data["effects_at"] is not None

    def test_with_single_effect_returns_count_one(self, client):
        """Should return count=1 for a single detected effect."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                effects = [
                    {"ts_start": "0:01", "ts_end": "0:03", "effect": "pan left", "capcut_tool": "Keyframe > Position", "how_to": "Move position", "intensity": "subtle"},
                ]

                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (effects, "2026-07-24T11:30:00")

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/effects-status?youtube_url=https://www.youtube.com/watch?v=test")

                assert response.status_code == 200
                data = response.json()
                assert data["has_effects"] is True
                assert data["count"] == 1
                assert len(data["effects"]) == 1

    def test_invalid_url_returns_400(self, client):
        """Should return 400 for invalid URL."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.side_effect = socket.gaierror(socket.EAI_NONAME, "Name or service not known")

            response = client.get("/analyze/effects-status?youtube_url=https://this-domain-does-not-exist-xyz.example/watch?v=abc")

            assert response.status_code == 400

    def test_with_empty_effects_list_returns_zero(self, client):
        """Should return has_effects=False and count=0 for empty effects list."""
        with patch("socket.getaddrinfo") as mock_ga:
            mock_ga.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]

            with patch("main._db_conn") as mock_db_conn:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = ([], "2026-07-24T12:00:00")

                mock_conn = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_db_conn.return_value = mock_conn

                response = client.get("/analyze/effects-status?youtube_url=https://www.youtube.com/watch?v=test")

                assert response.status_code == 200
                data = response.json()
                assert data["has_effects"] is False
                assert data["count"] == 0
                assert data["effects"] == []
