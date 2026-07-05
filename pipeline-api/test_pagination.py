"""
Tests for server-side pagination on list endpoints.

Runnable two ways:
  - pytest test_pagination.py
  - python3 test_pagination.py        (assert-based fallback, no pytest needed)

Tests exercise:
1. GET /dash/table/sources with limit/offset returns total+rows and clamps limit>100 to 100
2. GET /creators includes total/limit/offset in response
3. GET /songs includes total/limit/offset in response
4. GET /dash/clip-finds includes total/limit/offset in response
5. GET /dash/analysis includes total/limit/offset in response
6. limit clamping: limit>100 → clamped to 100
7. offset >= 0: offset<0 → clamped to 0
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)


class ColumnDesc:
    """Simple column descriptor for mocking psycopg cursor.description."""
    def __init__(self, name):
        self.name = name


def mock_db_response(table_name):
    """Create a mock database connection for pagination testing."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value.__exit__.return_value = None
    return mock_conn, mock_cur


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_dash_table_sources_returns_pagination_fields():
    """GET /dash/table/sources should return total, limit, offset."""
    mock_conn, mock_cur = mock_db_response("sources")
    # Mock count query
    call_count = [0]
    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # count(*) query
            mock_cur.fetchone.return_value = (42,)
        else:
            # Main data query - create proper descriptor objects
            col_names = ["id", "title", "niche", "platform", "channel", "views", "status"]
            mock_cur.description = [ColumnDesc(n) for n in col_names]
            mock_cur.fetchall.return_value = [(1, "Test", "test niche", "youtube", "Channel", 1000, "analyzed")]

    mock_cur.execute.side_effect = execute_side_effect

    with patch("main._db_conn", return_value=mock_conn):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/dash/table/sources?limit=10&offset=0")
        data = resp.json()
        assert data["total"] == 42
        assert data["limit"] == 10
        assert data["offset"] == 0


def test_dash_table_sources_clamps_limit_to_100():
    """GET /dash/table/sources with limit>100 should clamp to 100."""
    mock_conn, mock_cur = mock_db_response("sources")
    call_count = [0]
    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            mock_cur.fetchone.return_value = (42,)
        else:
            col_names = ["id", "title", "niche", "platform", "channel", "views", "status"]
            mock_cur.description = [ColumnDesc(n) for n in col_names]
            mock_cur.fetchall.return_value = []

    mock_cur.execute.side_effect = execute_side_effect

    with patch("main._db_conn", return_value=mock_conn):
        client = TestClient(app)
        resp = client.get("/dash/table/sources?limit=200&offset=0")
        data = resp.json()
        assert data["limit"] == 100


def test_dash_table_sources_negative_offset_clamped_to_0():
    """GET /dash/table/sources with offset<0 should clamp to 0."""
    mock_conn, mock_cur = mock_db_response("sources")
    call_count = [0]
    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            mock_cur.fetchone.return_value = (42,)
        else:
            col_names = ["id", "title", "niche", "platform", "channel", "views", "status"]
            mock_cur.description = [ColumnDesc(n) for n in col_names]
            mock_cur.fetchall.return_value = []

    mock_cur.execute.side_effect = execute_side_effect

    with patch("main._db_conn", return_value=mock_conn):
        client = TestClient(app)
        resp = client.get("/dash/table/sources?limit=10&offset=-5")
        data = resp.json()
        assert data["offset"] == 0


def test_creators_returns_pagination_fields():
    """GET /creators should return creators, total, limit, offset."""
    mock_conn, mock_cur = mock_db_response("creators")
    call_count = [0]
    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # count query
            mock_cur.fetchone.return_value = (10,)
        else:
            # data query
            mock_cur.fetchall.return_value = [
                ("UC123", "Test Channel", "Test Creator", 1000, "male", "2024-01-01T00:00:00", "2024-01-01T00:00:00")
            ]

    mock_cur.execute.side_effect = execute_side_effect

    with patch("main._db_conn", return_value=mock_conn):
        client = TestClient(app)
        resp = client.get("/creators?limit=5&offset=0")
        data = resp.json()
        assert "creators" in data
        assert data["total"] == 10
        assert data["limit"] == 5
        assert data["offset"] == 0


def test_songs_returns_pagination_fields():
    """GET /songs should return songs, total, limit, offset."""
    mock_conn, mock_cur = mock_db_response("songs")
    call_count = [0]
    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # count query
            mock_cur.fetchone.return_value = (20,)
        else:
            # data query
            mock_cur.fetchall.return_value = [
                (1, "https://youtube.com/watch?v=test", "Test Song", "/path/song.mp3", 180, "2024-01-01T00:00:00")
            ]

    mock_cur.execute.side_effect = execute_side_effect

    with patch("main._db_conn", return_value=mock_conn):
        client = TestClient(app)
        resp = client.get("/songs?limit=10&offset=0")
        data = resp.json()
        assert "songs" in data
        assert data["total"] == 20
        assert data["limit"] == 10
        assert data["offset"] == 0


def test_clip_finds_returns_pagination_fields():
    """GET /dash/clip-finds should return rows, total, limit, offset."""
    mock_conn, mock_cur = mock_db_response("clip_finds")
    call_count = [0]
    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # count query
            mock_cur.fetchone.return_value = (15,)
        else:
            # data query
            mock_cur.fetchall.return_value = [
                (1, "https://youtube.com/watch?v=test", json.dumps([]), "sonnet", 1.5, "2024-01-01T00:00:00")
            ]

    mock_cur.execute.side_effect = execute_side_effect

    with patch("main._db_conn", return_value=mock_conn):
        client = TestClient(app)
        resp = client.get("/dash/clip-finds?limit=5&offset=0")
        data = resp.json()
        assert "rows" in data
        assert data["total"] == 15
        assert data["limit"] == 5
        assert data["offset"] == 0


def test_analysis_returns_pagination_fields():
    """GET /dash/analysis should return rows, total, limit, offset."""
    mock_conn, mock_cur = mock_db_response("video_analysis")
    call_count = [0]
    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # count query
            mock_cur.fetchone.return_value = (25,)
        else:
            # data query
            mock_cur.fetchall.return_value = [
                (1, "https://youtube.com/watch?v=test", "analyze", "hook", "structure", 75, json.dumps([]), "sonnet", 2.0, "2024-01-01T00:00:00")
            ]

    mock_cur.execute.side_effect = execute_side_effect

    with patch("main._db_conn", return_value=mock_conn):
        client = TestClient(app)
        resp = client.get("/dash/analysis?limit=10&offset=0")
        data = resp.json()
        assert "rows" in data
        assert data["total"] == 25
        assert data["limit"] == 10
        assert data["offset"] == 0


def test_creators_clamps_limit_to_100():
    """GET /creators with limit>100 should clamp to 100."""
    mock_conn, mock_cur = mock_db_response("creators")
    call_count = [0]
    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            mock_cur.fetchone.return_value = (10,)
        else:
            # Verify limit is clamped
            assert args[0][-1] == 100 or args[0][-2] == 100
            mock_cur.fetchall.return_value = []

    mock_cur.execute.side_effect = execute_side_effect

    with patch("main._db_conn", return_value=mock_conn):
        client = TestClient(app)
        resp = client.get("/creators?limit=999&offset=0")
        data = resp.json()
        assert data["limit"] == 100


# ── Runnable as script ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            # Skip fixture-based tests (those with client param)
            if "client" in t.__code__.co_varnames:
                print(f"SKIP {t.__name__} (requires pytest fixture)")
                continue
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
