"""
Regression test for clip-find dedupe logic (find-claude + auto endpoints).
Tests that:
- When a cached row exists and force=False, the Claude bridge is NOT called
  and the response includes 'cached_find': true
- When no cached row exists (or force=True), the Claude path runs
  and the response includes 'cached_find': false
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
import sys

sys.path.insert(0, str(Path(__file__).parent))

from main import app

client = TestClient(app)
_SAMPLE_YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

_MOCK_CLIPS = [
    {
        "start_sec": 10,
        "end_sec": 25,
        "title": "Hook moment",
        "caption": "Viral hook",
        "why": "High energy",
        "rank": 1,
        "recommended": True,
    },
    {
        "start_sec": 60,
        "end_sec": 75,
        "title": "Punchline",
        "caption": "Payoff",
        "why": "Strong conclusion",
        "rank": 2,
        "recommended": False,
    },
]


def test_find_claude_with_cached_row():
    """Test that /clips/find-claude with cached row skips Claude and returns cached_find: true."""
    fake_row = (
        123,  # id
        json.dumps(_MOCK_CLIPS),  # clips
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fake_row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("main._db_conn", return_value=mock_conn):
        with patch("httpx.post") as mock_post:
            response = client.post(
                "/clips/find-claude",
                json={"youtube_url": _SAMPLE_YOUTUBE_URL},
            )

            # Claude bridge should NOT have been called
            mock_post.assert_not_called()

            # Response should have cached_find: true
            assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
            body = response.json()
            assert body.get("cached_find") is True, f"Expected cached_find=true, got {body}"
            assert body.get("clips") == _MOCK_CLIPS


def test_find_claude_with_force_true():
    """Test that /clips/find-claude with force=True bypasses cache."""

    fake_cached_row = (
        123,  # id
        json.dumps([{"start_sec": 0, "end_sec": 5, "title": "old"}]),  # clips
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fake_cached_row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value.__exit__.return_value = None

    with patch("main._db_conn", return_value=mock_conn):
        with patch("main._fetch_transcript", return_value=[{"start": 0, "text": "test"}]):
            with patch("httpx.post") as mock_post:
                mock_post.return_value.json.return_value = {
                    "ok": True,
                    "result": json.dumps({"clips": _MOCK_CLIPS}),
                    "cost_usd": 0.05,
                }

                response = client.post(
                    "/clips/find-claude",
                    json={"youtube_url": _SAMPLE_YOUTUBE_URL, "force": True},
                )

                # Claude bridge SHOULD have been called (force bypasses cache)
                mock_post.assert_called_once()

                # Response should have cached_find: false
                assert response.status_code == 200
                body = response.json()
                assert body.get("cached_find") is False, f"Expected cached_find=false, got {body}"


def test_find_claude_no_cache():
    """Test that /clips/find-claude with no cached row calls Claude."""

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # No cached row
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("main._db_conn", return_value=mock_conn):
        with patch("main._fetch_transcript", return_value=[{"start": 0, "text": "test"}]):
            with patch("httpx.post") as mock_post:
                mock_post.return_value.json.return_value = {
                    "ok": True,
                    "result": json.dumps({"clips": _MOCK_CLIPS}),
                    "cost_usd": 0.05,
                }

                response = client.post(
                    "/clips/find-claude",
                    json={"youtube_url": _SAMPLE_YOUTUBE_URL},
                )

                # Claude bridge SHOULD have been called (no cache)
                mock_post.assert_called_once()

                # Response should have cached_find: false
                assert response.status_code == 200
                body = response.json()
                assert body.get("cached_find") is False, f"Expected cached_find=false, got {body}"


def test_auto_clips_with_cached_find():
    """Test that /clips/auto with cached row skips Claude and includes cached_find: true."""

    def mock_download(youtube_url):
        tmp = Path(tempfile.gettempdir())
        fake_video = tmp / "fake_source.mp4"
        fake_video.write_text("FAKE_VIDEO_DATA")
        return fake_video

    def mock_assemble(cmd, *args, **kwargs):
        if len(cmd) >= 4:
            out_mp4_path = cmd[3]
            Path(out_mp4_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_mp4_path).write_text("FAKE_MP4_OUTPUT")
        mock_result = MagicMock()
        mock_result.returncode = 0
        return mock_result

    fake_cached_row = (
        123,  # id
        json.dumps(_MOCK_CLIPS),  # clips
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [fake_cached_row, (123,)]  # cache check, then DB insert
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("main._db_conn", return_value=mock_conn):
        with patch("httpx.post") as mock_post:
            with patch("main._download_source_video", side_effect=mock_download):
                with patch("subprocess.run", side_effect=mock_assemble):

                    response = client.post(
                        "/clips/auto",
                        json={"youtube_url": _SAMPLE_YOUTUBE_URL},
                    )

                    # Claude bridge should NOT have been called
                    mock_post.assert_not_called()

                    # Response should have cached_find: true
                    assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
                    body = response.json()
                    assert body.get("cached_find") is True, f"Expected cached_find=true, got {body}"
                    assert body.get("status") == "ok"
                    assert body.get("clip") is not None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
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
