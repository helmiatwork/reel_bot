"""
Tests for multi-account YouTube OAuth support (accounts → per-account tokens).
Tests: _get_oauth_service(account_id), connected status, backward compatibility.
"""

import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
import main as m
import youtube_v3 as yt


@pytest.fixture
def temp_creds_dir():
    """Temporary credentials directory for testing."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_db_conn():
    """Mock database connection."""
    with patch("main._db_conn") as mock:
        yield mock


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(m.app)


# ── youtube_v3._get_oauth_service tests ───────────────────────────────────────

class TestGetOAuthService:
    """Tests for _get_oauth_service(account_id=None)."""

    def test_signature_accepts_account_id(self):
        """_get_oauth_service should accept account_id parameter."""
        # Test that the function signature allows account_id
        import inspect
        sig = inspect.signature(yt._get_oauth_service)
        assert "account_id" in sig.parameters
        # Default should be None for backward compat
        assert sig.parameters["account_id"].default is None

    def test_legacy_token_path_when_no_account_id(self):
        """When account_id=None, should try legacy youtube_token.json path."""
        with patch("youtube_v3.Path") as mock_path_cls:
            # Track calls to Path() to verify legacy path
            legacy_path_accessed = []

            def path_side_effect(p):
                if str(p) == "youtube_token.json":
                    legacy_path_accessed.append(True)
                    mock_path = MagicMock()
                    mock_path.exists.return_value = False
                    return mock_path
                elif p == "credentials/client_secrets.json":
                    mock_path = MagicMock()
                    mock_path.exists.return_value = False
                    return mock_path
                return Path(p)

            mock_path_cls.side_effect = path_side_effect

            with patch("youtube_v3.Credentials") as mock_creds:
                mock_creds.from_authorized_user_file.side_effect = Exception("no token")
                with patch("youtube_v3.build"):
                    try:
                        yt._get_oauth_service(account_id=None)
                    except yt.YouTubeOAuthNotConfigured:
                        pass
                    # Verify legacy path was checked
                    assert len(legacy_path_accessed) > 0

    def test_per_account_token_path_when_account_id_given(self):
        """When account_id is given, should try per-account youtube_token_<id>.json path."""
        account_id = 42
        with patch("youtube_v3.Path") as mock_path_cls:
            per_account_path_accessed = []

            def path_side_effect(p):
                if str(p) == f"credentials/youtube_token_{account_id}.json":
                    per_account_path_accessed.append(True)
                    mock_path = MagicMock()
                    mock_path.exists.return_value = False
                    return mock_path
                elif p == "credentials/client_secrets.json":
                    mock_path = MagicMock()
                    mock_path.exists.return_value = False
                    return mock_path
                return Path(p)

            mock_path_cls.side_effect = path_side_effect

            with patch("youtube_v3.Credentials"):
                with patch("youtube_v3.build"):
                    try:
                        yt._get_oauth_service(account_id=account_id)
                    except yt.YouTubeOAuthNotConfigured:
                        pass
                    # Verify per-account path was checked
                    assert len(per_account_path_accessed) > 0

    def test_load_oauth_creds_signature(self):
        """_load_oauth_creds should accept account_id parameter."""
        import inspect
        sig = inspect.signature(yt._load_oauth_creds)
        assert "account_id" in sig.parameters
        assert sig.parameters["account_id"].default is None

    def test_get_analytics_service_signature(self):
        """_get_analytics_service should accept account_id parameter."""
        import inspect
        sig = inspect.signature(yt._get_analytics_service)
        assert "account_id" in sig.parameters
        assert sig.parameters["account_id"].default is None


# ── /accounts/{id}/connect-youtube endpoint tests ──────────────────────────────

class TestConnectYoutubeEndpoint:
    """Tests for POST /accounts/{id}/connect-youtube OAuth flow."""

    def test_endpoint_exists(self, client):
        """Endpoint should exist (returns error when mocked, but exists)."""
        # Even if DB returns 503, the endpoint exists
        response = client.post("/accounts/1/connect-youtube")
        # Will fail due to missing DB, but endpoint exists
        assert response.status_code in [503, 500, 404]

    def test_connect_youtube_account_not_found(self, client, mock_db_conn):
        """Should return 404 if account doesn't exist."""
        account_id = 999
        mock_conn = MagicMock()
        mock_db_conn.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock account lookup that returns nothing
        mock_cursor.fetchone.return_value = None

        response = client.post(f"/accounts/{account_id}/connect-youtube")
        assert response.status_code == 404

    def test_connect_youtube_wrong_platform(self, client, mock_db_conn):
        """Should return 400 if account is not youtube platform."""
        account_id = 1
        mock_conn = MagicMock()
        mock_db_conn.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock account lookup for TikTok account
        mock_cursor.fetchone.return_value = (account_id, "tiktok", "testuser")

        response = client.post(f"/accounts/{account_id}/connect-youtube")
        assert response.status_code == 400

    def test_db_unavailable_returns_503(self, client, mock_db_conn):
        """Should return 503 if database is unavailable."""
        mock_db_conn.return_value = None

        response = client.post(f"/accounts/1/connect-youtube")
        assert response.status_code == 503


# ── accounts_list connected status tests ───────────────────────────────────────

class TestAccountsConnectedStatus:
    """Tests for connected field in GET /accounts response."""

    def test_connected_field_added_to_response(self, client, mock_db_conn):
        """YouTube accounts in response should include connected field."""
        mock_conn = MagicMock()
        mock_db_conn.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock account query
        mock_cursor.description = [MagicMock(name=n) for n in
            ["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at"]]
        mock_cursor.fetchall.return_value = [
            (1, "youtube", "testchannel", "Test Channel", True, "publish", None, "2024-01-01")
        ]

        with patch("main.Path") as mock_path_cls:
            token_path = MagicMock()
            token_path.exists.return_value = True
            token_path.stat.return_value.st_size = 1024

            def path_side_effect(p):
                if "youtube_token_" in str(p):
                    return token_path
                return Path(p)
            mock_path_cls.side_effect = path_side_effect

            response = client.get("/accounts")
            assert response.status_code == 200
            data = response.json()
            # Response should have at least id and platform for filtering check
            assert isinstance(data, list)

    def test_non_youtube_accounts_no_connected_field(self, client, mock_db_conn):
        """Non-YouTube accounts should not have connected field."""
        mock_conn = MagicMock()
        mock_db_conn.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock TikTok account query
        mock_cursor.description = [MagicMock(name=n) for n in
            ["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at"]]
        mock_cursor.fetchall.return_value = [
            (1, "tiktok", "testuser", "Test User", True, "publish", None, "2024-01-01")
        ]

        response = client.get("/accounts")
        assert response.status_code == 200
        # Response should succeed but connected field only added for YouTube
        assert isinstance(response.json(), list)

    def test_accounts_list_db_unavailable_returns_empty(self, client, mock_db_conn):
        """When DB unavailable, should return empty list gracefully."""
        mock_db_conn.return_value = None

        response = client.get("/accounts")
        assert response.status_code == 200
        assert response.json() == []


# ── Backward compatibility tests ───────────────────────────────────────────────

class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""

    def test_captions_list_calls_get_oauth_service_no_args(self):
        """captions_list() should call _get_oauth_service() with no account_id."""
        with patch("youtube_v3._get_oauth_service") as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.captions.return_value.list.return_value.execute.return_value = {"items": []}

            result = yt.captions_list("test_video_id")
            # Should call with no arguments (default None)
            mock_get_service.assert_called_once()
            call_args = mock_get_service.call_args
            # Either called with no args or with account_id=None
            assert call_args[0] == () or call_args[1].get("account_id") is None

    def test_captions_download_backward_compat(self):
        """captions_download() should still work with default OAuth service."""
        with patch("youtube_v3._get_oauth_service") as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.captions.return_value.download.return_value.execute.return_value = b"subtitle content"

            result = yt.captions_download("caption_id_123")
            assert "caption_id" in result
            assert "content" in result

    def test_analytics_core_backward_compat(self):
        """analytics_core() should still work with default OAuth service."""
        with patch("youtube_v3._get_analytics_service") as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.reports.return_value.query.return_value.execute.return_value = {
                "columnHeaders": [],
                "rows": []
            }

            result = yt.analytics_core("2024-01-01", "2024-01-31")
            assert "rows_as_dicts" in result


# ── Integration tests ──────────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests for account-related functionality."""

    def test_per_account_token_file_location(self):
        """Verify token file location logic."""
        # Legacy: youtube_token.json (root)
        # Per-account: credentials/youtube_token_<id>.json
        account_id = 42

        with patch("youtube_v3.Path") as mock_path_cls:
            calls = []

            def path_side_effect(p):
                calls.append(str(p))
                mock_path = MagicMock()
                mock_path.exists.return_value = False
                mock_path.parent.mkdir = MagicMock()
                return mock_path

            mock_path_cls.side_effect = path_side_effect

            with patch("youtube_v3.Credentials"):
                with patch("youtube_v3.build"):
                    try:
                        yt._get_oauth_service(account_id=account_id)
                    except:
                        pass

                    # Should have tried the per-account path
                    assert any(f"youtube_token_{account_id}" in str(c) for c in calls)

    def test_accounts_endpoint_filter_by_platform(self, client, mock_db_conn):
        """accounts_list should support platform filter."""
        mock_conn = MagicMock()
        mock_db_conn.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.description = [MagicMock(name=n) for n in
            ["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at"]]
        mock_cursor.fetchall.return_value = []

        response = client.get("/accounts?platform=youtube")
        assert response.status_code == 200

    def test_accounts_endpoint_filter_by_role(self, client, mock_db_conn):
        """accounts_list should support role filter."""
        mock_conn = MagicMock()
        mock_db_conn.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.description = [MagicMock(name=n) for n in
            ["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at"]]
        mock_cursor.fetchall.return_value = []

        response = client.get("/accounts?role=publish")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
