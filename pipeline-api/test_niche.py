"""
Tests for the niche feature (_infer_niche + _save_source with niche).

Runnable two ways:
  - pytest test_niche.py
  - python3 test_niche.py        (assert-based fallback, no pytest needed)

Tests exercise:
1. _infer_niche parses a bridge response to a short string (mock bridge)
2. _save_source on a new row includes niche in the INSERT
3. _save_source on existing row with NULL niche does an UPDATE
4. _save_source on existing row WITH niche → no update
5. _infer_niche non-fatal: bridge error → returns ""
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import _infer_niche, _save_source, app


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_infer_niche_parses_bridge_response():
    """_infer_niche should parse bridge response and return cleaned string."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": "couples prank",
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _infer_niche("Husband Pranks Wife", "", "Comedy Channel")
        assert result == "couples prank"


def test_infer_niche_truncates_to_40_chars():
    """_infer_niche should truncate result to max 40 chars."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": "this is a very long niche label that exceeds forty characters total",
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _infer_niche("Long Title", "", "Channel")
        assert len(result) <= 40


def test_infer_niche_lowercases():
    """_infer_niche should lowercase the result."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": "COUPLES PRANK",
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _infer_niche("Title", "", "Channel")
        assert result == "couples prank"


def test_infer_niche_bridge_error_returns_empty():
    """_infer_niche should return '' on bridge error (non-fatal)."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": False,
    }

    with patch("httpx.post", return_value=mock_resp):
        result = _infer_niche("Title", "", "Channel")
        assert result == ""


def test_infer_niche_exception_returns_empty():
    """_infer_niche should return '' on exception (non-fatal)."""
    with patch("httpx.post", side_effect=Exception("Connection error")):
        result = _infer_niche("Title", "", "Channel")
        assert result == ""


def test_save_source_new_inserts_with_niche():
    """
    _save_source with a new source should infer niche and include it in INSERT.
    """
    mock_meta = {
        "channel_id": "UCnew123",
        "channel": "New Channel",
        "creator_name": "New Creator",
        "total_followers": 1000,
        "title": "New Video Title",
        "view_count": 50000,
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None  # Source does not exist

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._infer_niche", return_value="test niche"), \
         patch("main._db_conn", return_value=mock_conn):
        _save_source("https://youtube.com/watch?v=test")

        # Assert insert was called with niche in the column list
        calls = mock_conn.cursor.return_value.__enter__.return_value.execute.call_args_list
        insert_calls = [c for c in calls if c and "INSERT" in str(c[0][0])]
        assert len(insert_calls) > 0
        insert_call = insert_calls[0]
        assert "niche" in insert_call[0][0]
        assert "test niche" in insert_call[0][1]


def test_save_source_existing_null_niche_updates():
    """
    _save_source with existing source having NULL niche should UPDATE the niche.
    """
    mock_meta = {
        "channel_id": "UCexist123",
        "channel": "Existing Channel",
        "creator_name": "Existing Creator",
        "total_followers": 5000,
        "title": "Existing Video",
        "view_count": 100000,
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    # First call (SELECT niche) returns None (NULL)
    mock_cur.fetchone.return_value = (None,)

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._infer_niche", return_value="updated niche"), \
         patch("main._db_conn", return_value=mock_conn):
        _save_source("https://youtube.com/watch?v=test")

        # Assert UPDATE was called
        calls = mock_conn.cursor.return_value.__enter__.return_value.execute.call_args_list
        update_calls = [c for c in calls if c and "UPDATE" in str(c[0][0])]
        assert len(update_calls) > 0
        update_call = update_calls[0]
        assert "updated niche" in update_call[0][1]


def test_save_source_existing_with_niche_no_update():
    """
    _save_source with existing source having non-NULL niche should not UPDATE.
    """
    mock_meta = {
        "channel_id": "UCexist123",
        "channel": "Existing Channel",
        "creator_name": "Existing Creator",
        "total_followers": 5000,
        "title": "Existing Video",
        "view_count": 100000,
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    # First call (SELECT niche) returns existing niche
    mock_cur.fetchone.return_value = ("existing niche",)

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._infer_niche", return_value="new niche"), \
         patch("main._db_conn", return_value=mock_conn):
        _save_source("https://youtube.com/watch?v=test")

        # Assert UPDATE was NOT called (only SELECT)
        calls = mock_conn.cursor.return_value.__enter__.return_value.execute.call_args_list
        update_calls = [c for c in calls if c and "UPDATE" in str(c[0][0])]
        assert len(update_calls) == 0


def test_save_source_niche_non_fatal_on_infer_error():
    """
    _save_source should gracefully handle _infer_niche errors (non-fatal).
    """
    mock_meta = {
        "channel_id": "UCnew123",
        "channel": "New Channel",
        "creator_name": "New Creator",
        "total_followers": 1000,
        "title": "New Video Title",
        "view_count": 50000,
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._infer_niche", side_effect=Exception("Bridge timeout")), \
         patch("main._db_conn", return_value=mock_conn):
        # Should not raise
        _save_source("https://youtube.com/watch?v=test")


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
