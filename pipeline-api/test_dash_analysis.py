# pipeline-api/test_dash_analysis.py
# Unit tests for GET /dash/analysis.
# DB connection is fully mocked — no real database access.

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from fastapi.testclient import TestClient


def _make_analysis_rows():
    """Build mock rows as psycopg would return them (already-parsed JSONB)."""
    return [
        (
            101,
            "https://www.youtube.com/watch?v=abc123",
            "viral motivational",
            "Opens with a shocking fact",
            "Hook → problem → solution → CTA",
            "Pattern interrupts every 15s",
            ["viral", "motivation", "shorts"],  # JSONB parsed by psycopg
            "claude-sonnet-4-6",
            0.01234,
            datetime(2025, 6, 20, 10, 30, 0, tzinfo=timezone.utc),
        ),
        (
            102,
            "https://youtu.be/xyz789",
            "educational",
            "Did you know...",
            "Curiosity gap → reveal → deeper dive",
            "Pacing with beat drops",
            ["education", "tutorial"],
            "claude-haiku-4-5",
            0.00567,
            datetime(2025, 6, 20, 11, 45, 30, tzinfo=timezone.utc),
        ),
    ]


@pytest.fixture
def client_with_db():
    """TestClient with DB connection mocked to return analysis rows."""
    import main as m

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    # Mock cursor.description (column names) — each must have a .name attribute
    col_names = ["id", "youtube_url", "intent", "hook", "structure", "retention", "tags", "model", "cost_usd", "created_at"]
    mock_cursor.description = []
    for n in col_names:
        col = MagicMock()
        col.name = n
        mock_cursor.description.append(col)

    with patch.object(m, "_db_conn", return_value=mock_conn):
        from fastapi.testclient import TestClient

        yield TestClient(m.app), mock_conn, mock_cursor


class TestDashAnalysis:
    def test_200_returns_rows_in_correct_shape(self, client_with_db):
        """GET /dash/analysis returns rows with correct JSON schema."""
        tc, mock_conn, mock_cursor = client_with_db
        mock_cursor.fetchall.return_value = _make_analysis_rows()

        r = tc.get("/dash/analysis")

        assert r.status_code == 200
        data = r.json()
        assert "rows" in data
        assert len(data["rows"]) == 2

        # Check first row shape
        row0 = data["rows"][0]
        assert row0["id"] == 101
        assert row0["youtube_url"] == "https://www.youtube.com/watch?v=abc123"
        assert row0["intent"] == "viral motivational"
        assert row0["hook"] == "Opens with a shocking fact"
        assert row0["structure"] == "Hook → problem → solution → CTA"
        assert row0["retention"] == "Pattern interrupts every 15s"
        assert isinstance(row0["tags"], list)
        assert row0["tags"] == ["viral", "motivation", "shorts"]
        assert row0["model"] == "claude-sonnet-4-6"
        assert row0["cost_usd"] == 0.01234
        assert row0["created_at"] == "2025-06-20T10:30:00+00:00"

        # Check second row
        row1 = data["rows"][1]
        assert row1["id"] == 102
        assert row1["cost_usd"] == 0.00567
        assert len(row1["tags"]) == 2

    def test_default_limit_50(self, client_with_db):
        """Default limit parameter is 50."""
        tc, mock_conn, mock_cursor = client_with_db
        mock_cursor.fetchall.return_value = _make_analysis_rows()

        tc.get("/dash/analysis")

        # Verify the execute call passed limit=50
        call_args = mock_cursor.execute.call_args
        assert call_args is not None
        # The second arg is a tuple with the parameters
        assert call_args[0][1] == (50,)

    def test_custom_limit(self, client_with_db):
        """Custom limit parameter is clamped to 1..200."""
        tc, mock_conn, mock_cursor = client_with_db
        mock_cursor.fetchall.return_value = []

        # Test within range
        tc.get("/dash/analysis?limit=75")
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == (75,)

        # Test below minimum (clamped to 1)
        tc.get("/dash/analysis?limit=0")
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == (1,)

        # Test above maximum (clamped to 200)
        tc.get("/dash/analysis?limit=500")
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == (200,)

    def test_empty_rows_no_db(self, client_with_db):
        """Returns empty rows when DB is unavailable."""
        import main as m

        with patch.object(m, "_db_conn", return_value=None):
            from fastapi.testclient import TestClient

            tc = TestClient(m.app)
            r = tc.get("/dash/analysis")

            assert r.status_code == 200
            data = r.json()
            assert data["rows"] == []

    def test_handles_null_tags(self, client_with_db):
        """NULL tags are converted to empty array."""
        tc, mock_conn, mock_cursor = client_with_db
        rows = _make_analysis_rows()
        rows[0] = rows[0][:6] + (None,) + rows[0][7:]  # Set tags to None
        mock_cursor.fetchall.return_value = rows

        r = tc.get("/dash/analysis")
        data = r.json()
        assert data["rows"][0]["tags"] == []

    def test_handles_tags_as_string_json(self, client_with_db):
        """JSONB tags returned as string are parsed."""
        tc, mock_conn, mock_cursor = client_with_db
        rows = _make_analysis_rows()
        rows[0] = rows[0][:6] + ('["tag1", "tag2"]',) + rows[0][7:]  # String JSON
        mock_cursor.fetchall.return_value = rows

        r = tc.get("/dash/analysis")
        data = r.json()
        assert data["rows"][0]["tags"] == ["tag1", "tag2"]

    def test_handles_invalid_tags_json(self, client_with_db):
        """Unparseable tags default to empty array."""
        tc, mock_conn, mock_cursor = client_with_db
        rows = _make_analysis_rows()
        rows[0] = rows[0][:6] + ("invalid json",) + rows[0][7:]
        mock_cursor.fetchall.return_value = rows

        r = tc.get("/dash/analysis")
        data = r.json()
        assert data["rows"][0]["tags"] == []

    def test_ordered_by_id_desc(self, client_with_db):
        """Rows are ordered by id DESC."""
        tc, mock_conn, mock_cursor = client_with_db
        mock_cursor.fetchall.return_value = _make_analysis_rows()

        tc.get("/dash/analysis")

        # Verify the SQL includes ORDER BY id DESC
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        assert "ORDER BY id DESC" in sql
