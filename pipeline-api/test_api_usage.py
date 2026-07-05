"""
Tests for the api_usage feature (logging all LLM calls for cost dashboard).

Runnable two ways:
  - pytest test_api_usage.py
  - python3 test_api_usage.py        (assert-based fallback, no pytest needed)

Tests exercise:
1. _log_api_usage token mapping: raw_usage dict → prompt/completion/total_tokens computed correctly
2. Non-fatal on DB unavailable: _db_conn returns None → no exception raised
3. dash_token_usage by_agent: mock DB rows → response includes by_agent array with agent/calls/total_tokens/cost_usd
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import _log_api_usage, app


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_log_api_usage_token_mapping():
    """_log_api_usage should compute prompt/completion/total_tokens correctly."""
    raw_usage = {
        "input_tokens": 10,
        "cache_creation_input_tokens": 5,
        "cache_read_input_tokens": 3,
        "output_tokens": 20,
    }
    cost_usd = 0.0042

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("main._db_conn", return_value=mock_conn):
        _log_api_usage(agent="test_agent", model="test-model", raw_usage=raw_usage, cost_usd=cost_usd)

        # Assert execute was called with correct values
        # prompt_tokens = 10 + 5 + 3 = 18
        # completion_tokens = 20
        # total_tokens = 38
        mock_cur.execute.assert_called_once()
        call_args = mock_cur.execute.call_args
        assert call_args[0][1] == ("test_agent", "test-model", 18, 20, 38, 0.0042)


def test_log_api_usage_token_mapping_with_none_values():
    """_log_api_usage should treat None/missing values as 0."""
    raw_usage = {
        "input_tokens": 100,
        "cache_creation_input_tokens": None,
        "output_tokens": 50,
    }
    cost_usd = None

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("main._db_conn", return_value=mock_conn):
        _log_api_usage(agent="analyze", model="claude-sonnet", raw_usage=raw_usage, cost_usd=cost_usd)

        # prompt_tokens = 100 + 0 + 0 = 100
        # completion_tokens = 50
        # total_tokens = 150
        mock_cur.execute.assert_called_once()
        call_args = mock_cur.execute.call_args
        assert call_args[0][1] == ("analyze", "claude-sonnet", 100, 50, 150, 0.0)


def test_log_api_usage_non_fatal_on_db_unavailable():
    """_log_api_usage should not raise if _db_conn returns None."""
    raw_usage = {"input_tokens": 10, "output_tokens": 5}

    with patch("main._db_conn", return_value=None):
        # Should not raise
        _log_api_usage(agent="clipper", model="claude-haiku", raw_usage=raw_usage, cost_usd=0.001)


def test_log_api_usage_non_fatal_on_db_error():
    """_log_api_usage should not raise if DB insert fails."""
    raw_usage = {"input_tokens": 10, "output_tokens": 5}

    mock_conn = MagicMock()
    mock_conn.cursor.side_effect = Exception("DB connection error")

    with patch("main._db_conn", return_value=mock_conn):
        # Should not raise
        _log_api_usage(agent="gender", model="claude-haiku", raw_usage=raw_usage, cost_usd=0.0001)


def test_log_api_usage_empty_raw_usage():
    """_log_api_usage should handle empty raw_usage dict."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("main._db_conn", return_value=mock_conn):
        _log_api_usage(agent="test", model="test-model", raw_usage={}, cost_usd=0.0)

        # All tokens should be 0
        mock_cur.execute.assert_called_once()
        call_args = mock_cur.execute.call_args
        assert call_args[0][1] == ("test", "test-model", 0, 0, 0, 0.0)


def test_dash_token_usage_by_agent(client):
    """dash_token_usage should return by_agent breakdown."""
    mock_rows_by_model = [
        ("claude-sonnet-4-6", 1000, 500, 1500, 10),
        ("claude-haiku-4", 100, 50, 150, 5),
    ]
    mock_rows_by_date = [
        ("07-04", 1650),
    ]
    mock_rows_by_agent = [
        ("analyze", 8, 1200, 0.0360),
        ("clipper", 5, 400, 0.0120),
        ("gender", 2, 50, 0.0003),
    ]

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Set up execute to return different results based on the query
    call_count = [0]
    def mock_execute(query, *args):
        call_count[0] += 1
        if "GROUP BY model" in query:
            mock_cur.fetchall.return_value = mock_rows_by_model
        elif "GROUP BY d" in query:
            mock_cur.fetchall.return_value = mock_rows_by_date
        elif "GROUP BY agent" in query:
            mock_cur.fetchall.return_value = mock_rows_by_agent

    mock_cur.execute.side_effect = mock_execute

    with patch("main._db_conn", return_value=mock_conn):
        response = client.get("/dash/token-usage")
        assert response.status_code == 200
        data = response.json()

        # Check that by_agent is present
        assert "by_agent" in data
        assert len(data["by_agent"]) == 3

        # Check structure
        assert data["by_agent"][0]["agent"] == "analyze"
        assert data["by_agent"][0]["calls"] == 8
        assert data["by_agent"][0]["total_tokens"] == 1200
        assert data["by_agent"][0]["cost_usd"] == 0.036

        # Check that existing fields are still present
        assert "rows" in data
        assert "series" in data
        assert "totals" in data


def test_dash_token_usage_db_unavailable(client):
    """dash_token_usage should return graceful error if DB unavailable."""
    with patch("main._db_conn", return_value=None):
        response = client.get("/dash/token-usage")
        assert response.status_code == 200
        data = response.json()
        assert data.get("error") == "db unavailable"
        assert data["by_agent"] == []


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
