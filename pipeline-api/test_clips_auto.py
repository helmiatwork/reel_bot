"""
Tests for POST /clips/auto endpoint — unified clip-find + render in a single call.

Runnable two ways:
  - pytest test_clips_auto.py
  - python3 test_clips_auto.py        (assert-based fallback, no pytest needed)

Tests exercise the auto endpoint with monkeypatched deps (no real network/LLM calls).
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from main import app, _build_clip_edl, _download_source_video
from fastapi.testclient import TestClient

client = TestClient(app)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE_YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Mock clips that would be returned by find-claude
_MOCK_CLIPS = [
    {
        "start_sec": 10,
        "end_sec": 25,
        "title": "Hook moment",
        "caption": "This is the viral hook",
        "why": "High energy transition",
        "rank": 1,
        "recommended": True,
    },
    {
        "start_sec": 60,
        "end_sec": 75,
        "title": "Punchline",
        "caption": "The payoff",
        "why": "Strong conclusion",
        "rank": 2,
        "recommended": False,
    },
]


def test_clips_auto_success_with_find_and_render():
    """Full path: find clips via claude, then render the recommended one."""

    def mock_find_clips(youtube_url):
        """Mock the find-clips logic: return clips + clip_find_id."""
        return {
            "clips": _MOCK_CLIPS,
            "clip_find_id": 123,  # Simulate DB insert
            "cached_find": False,
        }

    def mock_download(youtube_url):
        """Mock video download: return a temp path."""
        tmp = Path(tempfile.gettempdir())
        fake_video = tmp / "fake_source.mp4"
        fake_video.write_text("FAKE_VIDEO_DATA")
        return fake_video

    def mock_assemble(cmd, *args, **kwargs):
        """Mock assemble.sh: create fake output MP4."""
        # cmd is a list like ["bash", "/path/to/assemble.sh", "/path/to/edl.json", "/path/to/output.mp4"]
        if len(cmd) >= 4:
            out_mp4_path = cmd[3]
            Path(out_mp4_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_mp4_path).write_text("FAKE_MP4_OUTPUT")
        # Return a mock result that indicates success
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        return mock_result

    # Mock DB connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (123,)  # Simulate DB returning the inserted ID
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value.__exit__.return_value = None

    # Patch all the I/O-heavy functions
    with patch("main._fetch_transcript") as mock_transcript, \
         patch("httpx.post") as mock_claude, \
         patch("main._download_source_video", side_effect=mock_download), \
         patch("subprocess.run", side_effect=mock_assemble), \
         patch("main._db_conn", return_value=mock_conn):

        # Mock transcript fetch
        mock_transcript.return_value = [
            {"start": 10, "text": "Hook text"},
            {"start": 60, "text": "Punchline text"},
        ]

        # Mock claude bridge response
        mock_claude_resp = MagicMock()
        mock_claude_resp.json.return_value = {
            "ok": True,
            "result": json.dumps({"clips": _MOCK_CLIPS}),
            "cost_usd": 0.05,
        }
        mock_claude.return_value = mock_claude_resp

        # Make the POST /clips/auto request
        response = client.post(
            "/clips/auto",
            json={"youtube_url": _SAMPLE_YOUTUBE_URL},
        )

        # Assert success
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        body = response.json()

        assert body["status"] == "ok", f"Expected status ok, got {body}"
        assert "clip_find_id" in body, f"Missing clip_find_id in {body}"
        assert body["clip_find_id"] == 123, f"Expected clip_find_id 123, got {body['clip_find_id']}"
        assert "render_id" in body, f"Missing render_id in {body}"
        assert "video_path" in body, f"Missing video_path in {body}"
        assert "clip" in body, f"Missing clip in {body}"
        assert body["clip"]["recommended"] is True, f"clip.recommended not True: {body['clip']}"
        assert body["clip"]["title"] == "Hook moment", f"Expected title 'Hook moment', got {body['clip']['title']}"
        assert "cached_find" in body, f"Missing cached_find in {body}"
        assert body["cached_find"] is False


def test_clips_auto_no_clips_found():
    """When find-claude returns no clips, auto should return 422."""

    def mock_transcript(*args, **kwargs):
        return [{"start": 0, "text": "Some text"}]

    mock_claude_resp = MagicMock()
    mock_claude_resp.json.return_value = {
        "ok": True,
        "result": json.dumps({"clips": []}),  # Empty clips
        "cost_usd": 0.01,
    }

    with patch("main._fetch_transcript", return_value=mock_transcript()), \
         patch("httpx.post", return_value=mock_claude_resp):

        response = client.post(
            "/clips/auto",
            json={"youtube_url": _SAMPLE_YOUTUBE_URL},
        )

        assert response.status_code == 422
        body = response.json()
        assert body["detail"] == "no_clips"


def test_clips_auto_with_explicit_clip_index():
    """When clip_index is provided, render that specific clip instead of recommended."""

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

    with patch("main._fetch_transcript") as mock_transcript, \
         patch("httpx.post") as mock_claude, \
         patch("main._download_source_video", side_effect=mock_download), \
         patch("subprocess.run", side_effect=mock_assemble):

        mock_transcript.return_value = [
            {"start": 10, "text": "Hook"},
            {"start": 60, "text": "Punchline"},
        ]

        mock_claude_resp = MagicMock()
        mock_claude_resp.json.return_value = {
            "ok": True,
            "result": json.dumps({"clips": _MOCK_CLIPS}),
            "cost_usd": 0.05,
        }
        mock_claude.return_value = mock_claude_resp

        # Request with explicit clip_index=1 (the second clip)
        response = client.post(
            "/clips/auto",
            json={
                "youtube_url": _SAMPLE_YOUTUBE_URL,
                "clip_index": 1,
            },
        )

        assert response.status_code == 200
        body = response.json()
        # Verify the rendered clip is the one at index 1 (Punchline)
        assert body["clip"]["title"] == "Punchline"
        assert body["clip"]["rank"] == 2


def test_clips_auto_bridge_error():
    """When claude bridge returns error, auto should bubble it."""

    with patch("main._fetch_transcript") as mock_transcript, \
         patch("httpx.post") as mock_claude:

        mock_transcript.return_value = [{"start": 0, "text": "text"}]

        mock_claude_resp = MagicMock()
        mock_claude_resp.json.return_value = {
            "ok": False,
            "error": "rate_limit",
        }
        mock_claude.return_value = mock_claude_resp

        response = client.post(
            "/clips/auto",
            json={"youtube_url": _SAMPLE_YOUTUBE_URL},
        )

        assert response.status_code == 502


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
