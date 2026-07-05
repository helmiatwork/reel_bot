"""
Tests for the creators feature (POST /analyze/claude + GET /creators).

Runnable two ways:
  - pytest test_creators.py
  - python3 test_creators.py        (assert-based fallback, no pytest needed)

Tests exercise:
1. Check-and-skip logic: existing creator → no gender inference, no insert
2. New creator → gender inference called, insert executed
3. _infer_gender parsing: bridge responses → male/female/unknown
4. GET /creators endpoint: returns list, DB error → graceful []
"""

import json
import pytest
from unittest.mock import MagicMock, patch, call
from fastapi.testclient import TestClient

from main import _fetch_channel_meta, _infer_gender, _save_creator, app


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_fetch_channel_meta_success():
    """_fetch_channel_meta should parse yt-dlp output correctly."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({
        "channel_id": "UCabc123",
        "channel": "Test Channel",
        "uploader": "Test Creator",
        "channel_follower_count": 50000,
    })

    with patch("subprocess.run", return_value=mock_proc):
        result = _fetch_channel_meta("https://youtube.com/watch?v=test")
        assert result["channel_id"] == "UCabc123"
        assert result["channel"] == "Test Channel"
        assert result["creator_name"] == "Test Creator"
        assert result["total_followers"] == 50000


def test_fetch_channel_meta_fallback_fields():
    """_fetch_channel_meta should fallback to uploader_id and uploader."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({
        "uploader_id": "UCfallback",
        "uploader": "Fallback Creator",
    })

    with patch("subprocess.run", return_value=mock_proc):
        result = _fetch_channel_meta("https://youtube.com/watch?v=test")
        assert result["channel_id"] == "UCfallback"
        assert result["creator_name"] == "Fallback Creator"


def test_fetch_channel_meta_error_returns_empty():
    """_fetch_channel_meta returns {} on yt-dlp error (non-fatal)."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Download failed"

    with patch("subprocess.run", return_value=mock_proc):
        result = _fetch_channel_meta("https://youtube.com/watch?v=test")
        assert result == {}


def test_infer_gender_male():
    """_infer_gender should parse 'male' from bridge response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": "male",
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _infer_gender("John Smith", "John's Channel")
        assert result == "male"


def test_infer_gender_female():
    """_infer_gender should parse 'female' from bridge response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": "female",
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _infer_gender("Jane Doe", "Jane's Channel")
        assert result == "female"


def test_infer_gender_unknown():
    """_infer_gender should default to 'unknown' for unrecognized responses."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": "not_a_gender",
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _infer_gender("Someone", "Some Channel")
        assert result == "unknown"


def test_infer_gender_bridge_error():
    """_infer_gender should return 'unknown' on bridge error (non-fatal)."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": False,
        "error": "bridge_error",
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _infer_gender("Test", "Test")
        assert result == "unknown"


def test_save_creator_new_creator_calls_gender_inference():
    """
    _save_creator with a new creator should:
    1. Fetch channel meta
    2. Check if exists in DB (does not)
    3. Call _infer_gender
    4. Insert the creator
    """
    mock_meta = {
        "channel_id": "UCnew123",
        "channel": "New Channel",
        "creator_name": "New Creator",
        "total_followers": 1000,
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None  # Creator does not exist

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._db_conn", return_value=mock_conn), \
         patch("main._infer_gender", return_value="male") as mock_infer:
        _save_creator("https://youtube.com/watch?v=test")

        # Assert gender inference was called
        mock_infer.assert_called_once_with("New Creator", "New Channel")

        # Assert insert was called
        mock_conn.cursor.return_value.__enter__.return_value.execute.assert_any_call(
            """INSERT INTO creators
                    (channel_id, channel, creator_name, total_followers, gender)
                    VALUES (%s, %s, %s, %s, %s)""",
            ("UCnew123", "New Channel", "New Creator", 1000, "male"),
        )


def test_save_creator_existing_creator_skips_gender_inference():
    """
    _save_creator with an existing creator should:
    1. Fetch channel meta
    2. Check if exists in DB (does exist)
    3. Return without calling _infer_gender or inserting
    """
    mock_meta = {
        "channel_id": "UCexist123",
        "channel": "Existing Channel",
        "creator_name": "Existing Creator",
        "total_followers": 5000,
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = (1,)  # Creator exists

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._db_conn", return_value=mock_conn), \
         patch("main._infer_gender") as mock_infer:
        _save_creator("https://youtube.com/watch?v=test")

        # Assert gender inference was NOT called
        mock_infer.assert_not_called()

        # Assert insert was NOT called
        calls = mock_conn.cursor.return_value.__enter__.return_value.execute.call_args_list
        insert_calls = [c for c in calls if "INSERT" in str(c)]
        assert len(insert_calls) == 0


def test_save_creator_no_channel_id_skips():
    """_save_creator should skip silently if channel_id is missing."""
    mock_meta = {}  # No channel_id

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._db_conn") as mock_db:
        _save_creator("https://youtube.com/watch?v=test")

        # Assert DB was never opened
        mock_db.assert_not_called()


def test_get_creators_returns_list(client):
    """GET /creators should return a list of creators."""
    mock_rows = [
        ("UCabc123", "Test Channel", "Test Creator", 1000, "male", "2025-01-01T00:00:00", "2025-01-02T00:00:00"),
        ("UCxyz789", "Other Channel", "Other Creator", 2000, "female", "2025-01-01T00:00:00", "2025-01-02T00:00:00"),
    ]

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.return_value = mock_rows

    with patch("main._db_conn", return_value=mock_conn):
        response = client.get("/creators")
        assert response.status_code == 200
        data = response.json()
        assert len(data["creators"]) == 2
        assert data["creators"][0]["channel_id"] == "UCabc123"
        assert data["creators"][0]["gender"] == "male"
        assert data["creators"][1]["creator_name"] == "Other Creator"


def test_get_creators_db_error_returns_empty_list(client):
    """GET /creators should return [] gracefully on DB error."""
    with patch("main._db_conn", return_value=None):
        response = client.get("/creators")
        assert response.status_code == 200
        data = response.json()
        assert data["creators"] == []


def test_get_creators_exception_returns_empty_list(client):
    """GET /creators should return [] on query exception (non-fatal)."""
    mock_conn = MagicMock()
    mock_conn.cursor.side_effect = Exception("DB connection error")

    with patch("main._db_conn", return_value=mock_conn):
        response = client.get("/creators")
        assert response.status_code == 200
        data = response.json()
        assert data["creators"] == []


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
