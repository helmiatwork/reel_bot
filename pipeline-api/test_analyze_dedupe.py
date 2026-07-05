"""
Regression test for analyze_claude dedupe logic.
Tests that:
- When a cached row exists and force=False, the Claude bridge is NOT called
  and the response includes 'cached': true
- When no cached row exists (or force=True), the Claude path runs
  and the response includes 'cached': false
"""

import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


def test_analyze_dedupe_cached_row():
    """Test that a cached row skips Claude call and returns cached: true."""
    from main import analyze_claude, AnalyzeClaudeRequest

    # Columns: youtube_url(0), intent(1), hook(2), structure(3), retention(4), tags(5), model(6), cost_usd(7), created_at(8)
    fake_row = (
        "https://www.youtube.com/watch?v=test123",  # 0: youtube_url
        "test intent",  # 1: intent
        "amazing hook",  # 2: hook
        "story arc",  # 3: structure
        "high retention",  # 4: retention
        json.dumps(["tag1", "tag2"]),  # 5: tags (JSON string)
        "claude-sonnet-4-6",  # 6: model
        0.25,  # 7: cost_usd
        datetime.now(),  # 8: created_at
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fake_row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    req = AnalyzeClaudeRequest(youtube_url="https://www.youtube.com/watch?v=test123")

    with patch("main._db_conn", return_value=mock_conn):
        with patch("httpx.post") as mock_post:
            # If we reach the Claude call, the test should fail
            response = analyze_claude(req)

            # Claude bridge should NOT have been called
            mock_post.assert_not_called()

            # Response should have cached: true and all fields from the cached row
            result = response.body
            if isinstance(result, bytes):
                result = result.decode('utf-8')
            data = json.loads(result) if isinstance(result, str) else result
            assert data.get("cached") is True, f"Expected cached=true, got {data}"
            assert data.get("hook") == "amazing hook"
            assert data.get("structure") == "story arc"
            assert data.get("retention") == "high retention"
            assert data.get("tags") == ["tag1", "tag2"]
            assert data.get("model") == "claude-sonnet-4-6"
            assert data.get("cost_usd") == 0.25

    print("✓ test_analyze_dedupe_cached_row PASSED")


def test_analyze_dedupe_force_refresh():
    """Test that force=True bypasses cache and runs Claude."""
    from main import analyze_claude, AnalyzeClaudeRequest

    # Columns: youtube_url(0), intent(1), hook(2), structure(3), retention(4), tags(5), model(6), cost_usd(7), created_at(8)
    fake_row = (
        "https://www.youtube.com/watch?v=test456",  # 0: youtube_url
        None,  # 1: intent
        "old hook",  # 2: hook
        "old structure",  # 3: structure
        "old retention",  # 4: retention
        json.dumps([]),  # 5: tags
        "claude-sonnet-4-6",  # 6: model
        0.10,  # 7: cost_usd
        datetime.now(),  # 8: created_at
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fake_row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    req = AnalyzeClaudeRequest(
        youtube_url="https://www.youtube.com/watch?v=test456", force=True
    )

    with patch("main._db_conn", return_value=mock_conn):
        with patch("main._extract_keyframes", return_value=["/tmp/frame1.jpg"]):
            with patch("httpx.post") as mock_post:
                # Mock successful Claude response
                mock_post.return_value.json.return_value = {
                    "ok": True,
                    "result": json.dumps({
                        "hook": "new hook",
                        "structure": "new structure",
                        "retention": "new retention",
                        "tags": ["new_tag"],
                    }),
                    "cost_usd": 0.30,
                }

                response = analyze_claude(req)

                # Claude bridge SHOULD have been called
                mock_post.assert_called_once()

                # Response should have cached: false and new values
                result = response.body
                if isinstance(result, bytes):
                    result = result.decode('utf-8')
                data = json.loads(result) if isinstance(result, str) else result
                assert data.get("cached") is False, f"Expected cached=false, got {data}"
                assert data.get("hook") == "new hook"
                assert data.get("cost_usd") == 0.30

    print("✓ test_analyze_dedupe_force_refresh PASSED")


def test_analyze_dedupe_no_cache():
    """Test that when no cached row exists, Claude is called and cached: false."""
    from main import analyze_claude, AnalyzeClaudeRequest

    # Mock _db_conn to return None (no cached row)
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # No cached row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    req = AnalyzeClaudeRequest(youtube_url="https://www.youtube.com/watch?v=test789")

    with patch("main._db_conn", return_value=mock_conn):
        with patch("main._extract_keyframes", return_value=["/tmp/frame1.jpg"]):
            with patch("httpx.post") as mock_post:
                # Mock successful Claude response
                mock_post.return_value.json.return_value = {
                    "ok": True,
                    "result": json.dumps({
                        "hook": "fresh hook",
                        "structure": "fresh structure",
                        "retention": "fresh retention",
                        "tags": ["fresh"],
                    }),
                    "cost_usd": 0.25,
                }

                response = analyze_claude(req)

                # Claude bridge SHOULD have been called (no cache)
                mock_post.assert_called_once()

                # Response should have cached: false
                result = response.body
                if isinstance(result, bytes):
                    result = result.decode('utf-8')
                data = json.loads(result) if isinstance(result, str) else result
                assert data.get("cached") is False, f"Expected cached=false, got {data}"

    print("✓ test_analyze_dedupe_no_cache PASSED")


if __name__ == "__main__":
    test_analyze_dedupe_cached_row()
    test_analyze_dedupe_force_refresh()
    test_analyze_dedupe_no_cache()
    print("\n✓ All dedupe regression tests PASSED")
