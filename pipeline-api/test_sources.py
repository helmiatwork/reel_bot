"""
Tests for the sources feature (_save_source + _sources_init_db).

Runnable two ways:
  - pytest test_sources.py
  - python3 test_sources.py        (assert-based fallback, no pytest needed)

Tests exercise:
1. Check-and-skip logic: existing source → no insert
2. New source → insert executed with correct values
3. _fetch_channel_meta extension: returns title + view_count
4. _save_source skip conditions: no title AND no channel → skip
5. _save_source non-fatal: db_conn None → no raise
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import _fetch_channel_meta, _save_source, app


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_fetch_channel_meta_returns_title_and_view_count():
    """_fetch_channel_meta should return title and view_count in addition to existing fields."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({
        "channel_id": "UCabc123",
        "channel": "Test Channel",
        "uploader": "Test Creator",
        "channel_follower_count": 50000,
        "title": "Test Video Title",
        "view_count": 100000,
    })

    with patch("subprocess.run", return_value=mock_proc):
        result = _fetch_channel_meta("https://youtube.com/watch?v=test")
        assert result["channel_id"] == "UCabc123"
        assert result["title"] == "Test Video Title"
        assert result["view_count"] == 100000
        assert result["channel"] == "Test Channel"
        assert result["creator_name"] == "Test Creator"
        assert result["total_followers"] == 50000


def test_fetch_channel_meta_title_and_view_count_missing():
    """_fetch_channel_meta should handle missing title and view_count (None values)."""
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
        assert result["title"] is None
        assert result["view_count"] is None
        assert result["channel_id"] == "UCabc123"


def test_save_source_new_source_inserts():
    """
    _save_source with a new source should:
    1. Fetch channel meta
    2. Check if exists in DB (does not)
    3. Insert the source with title, channel, view_count
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
         patch("main._db_conn", return_value=mock_conn):
        _save_source("https://youtube.com/watch?v=test")

        # Assert insert was called with the right values
        mock_conn.cursor.return_value.__enter__.return_value.execute.assert_any_call(
            """INSERT INTO sources
                    (youtube_url, title, platform, channel, views_at_analysis, status)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
            ("https://youtube.com/watch?v=test", "New Video Title", "youtube", "New Channel", 50000, "analyzed"),
        )


def test_save_source_existing_source_skips_insert():
    """
    _save_source with an existing source should:
    1. Fetch channel meta
    2. Check if exists in DB (does exist)
    3. Return without inserting
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
    mock_cur.fetchone.return_value = (1,)  # Source exists

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._db_conn", return_value=mock_conn):
        _save_source("https://youtube.com/watch?v=test")

        # Assert insert was NOT called
        calls = mock_conn.cursor.return_value.__enter__.return_value.execute.call_args_list
        insert_calls = [c for c in calls if "INSERT" in str(c)]
        assert len(insert_calls) == 0


def test_save_source_no_title_and_no_channel_skips():
    """_save_source should skip silently if both title and channel are missing."""
    mock_meta = {
        "channel_id": "UCtest123",
        "creator_name": "Test Creator",
        "total_followers": 1000,
        "title": None,  # No title
        "view_count": 50000,
        "channel": None,  # No channel
    }

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._db_conn") as mock_db:
        _save_source("https://youtube.com/watch?v=test")

        # Assert DB was never opened
        mock_db.assert_not_called()


def test_save_source_with_title_only_inserts():
    """_save_source should insert if title is present (even if channel is missing)."""
    mock_meta = {
        "channel_id": "UCtest123",
        "channel": None,
        "creator_name": "Test Creator",
        "total_followers": 1000,
        "title": "Video With Title Only",
        "view_count": 50000,
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None  # Source does not exist

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._db_conn", return_value=mock_conn):
        _save_source("https://youtube.com/watch?v=test")

        # Assert insert was called
        mock_conn.cursor.return_value.__enter__.return_value.execute.assert_any_call(
            """INSERT INTO sources
                    (youtube_url, title, platform, channel, views_at_analysis, status)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
            ("https://youtube.com/watch?v=test", "Video With Title Only", "youtube", None, 50000, "analyzed"),
        )


def test_save_source_with_channel_only_inserts():
    """_save_source should insert if channel is present (even if title is missing)."""
    mock_meta = {
        "channel_id": "UCtest123",
        "channel": "Channel Only",
        "creator_name": "Test Creator",
        "total_followers": 1000,
        "title": None,
        "view_count": 50000,
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None  # Source does not exist

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._db_conn", return_value=mock_conn):
        _save_source("https://youtube.com/watch?v=test")

        # Assert insert was called
        mock_conn.cursor.return_value.__enter__.return_value.execute.assert_any_call(
            """INSERT INTO sources
                    (youtube_url, title, platform, channel, views_at_analysis, status)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
            ("https://youtube.com/watch?v=test", None, "youtube", "Channel Only", 50000, "analyzed"),
        )


def test_save_source_db_none_non_fatal():
    """_save_source should not raise if _db_conn returns None."""
    mock_meta = {
        "channel_id": "UCtest123",
        "channel": "Test Channel",
        "creator_name": "Test Creator",
        "total_followers": 1000,
        "title": "Test Video",
        "view_count": 50000,
    }

    with patch("main._fetch_channel_meta", return_value=mock_meta), \
         patch("main._db_conn", return_value=None):
        # Should not raise
        _save_source("https://youtube.com/watch?v=test")


def test_save_source_exception_non_fatal():
    """_save_source should catch and log exceptions without raising."""
    with patch("main._fetch_channel_meta", side_effect=Exception("Test error")), \
         patch("main._db_conn") as mock_db:
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
