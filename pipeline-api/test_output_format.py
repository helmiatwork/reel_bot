# pipeline-api/test_output_format.py
# Unit tests for output_format parameter in /analyze/claude and /sources/upload.

import json
import pytest
import httpx
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from io import BytesIO


def _make_bridge_response(result_payload: dict, ok: bool = True, cost_usd: float = 0.01):
    """Build a mock httpx.Response for the bridge POST /run call."""
    mock_resp = MagicMock()
    if ok:
        mock_resp.json.return_value = {
            "ok": True,
            "result": json.dumps(result_payload),
            "raw_usage": {"input_tokens": 100, "output_tokens": 50},
            "cost_usd": cost_usd,
            "model": "claude-sonnet-4-6",
        }
    else:
        mock_resp.json.return_value = {"ok": False, "error": "test error"}
    return mock_resp


_SAMPLE_RESULT = {
    "summary": "A motivational short about overcoming obstacles",
    "detail": "The video uses pattern interrupts",
    "hook": "Opens with a shocking statistic",
    "structure": "Problem → Solution → Inspiration",
    "retention": "Pattern interrupts every 12 seconds",
    "retention_score": 8,
    "tags": ["motivation", "shorts"],
}

_SAMPLE_FRAMES = [
    "/app/analyze-frames/run1/frame_000.jpg",
    "/app/analyze-frames/run1/frame_001.jpg",
]

def _make_valid_mp4_content():
    """Create fake MP4 with valid ftyp magic bytes."""
    return b"xxxx" + b"ftyp" + b"x" * 92


@pytest.fixture
def client_analyze():
    """TestClient for /analyze/claude with frame extraction and DB mocked."""
    import main as m
    with patch.object(m, "_extract_keyframes", return_value=_SAMPLE_FRAMES), \
         patch.object(m, "_db_conn", return_value=None), \
         patch.object(m, "_save_creator"), \
         patch.object(m, "_save_source"), \
         patch.object(m, "_build_analyze_steps", return_value=[]):
        yield TestClient(m.app)


@pytest.fixture
def client_upload():
    """TestClient for /sources/upload with frame extraction and DB mocked."""
    import main as m
    with patch.object(m, "_extract_frames_from_file", return_value=_SAMPLE_FRAMES), \
         patch.object(m, "_db_conn", return_value=None):
        yield TestClient(m.app)


class TestAnalyzeClaudeOutputFormat:
    def test_invalid_output_format_returns_400(self, client_analyze):
        """Invalid output_format should return 400."""
        r = client_analyze.post(
            "/analyze/claude",
            json={"youtube_url": "https://youtube.com/watch?v=test", "output_format": "invalid"}
        )
        assert r.status_code == 400
        assert "Invalid output_format" in r.json()["detail"]

    def test_output_format_none_by_default(self, client_analyze):
        """By default, output_format should be 'none' and gen_prompt not in response."""
        result_payload = {**_SAMPLE_RESULT, "gen_prompt": "This would be ignored"}

        with patch.object(httpx, "post", return_value=_make_bridge_response(result_payload)):
            r = client_analyze.post(
                "/analyze/claude",
                json={"youtube_url": "https://youtube.com/watch?v=test"}
            )

        assert r.status_code == 200
        resp_data = r.json()
        assert "gen_prompt" not in resp_data
        assert "gen_prompt_format" not in resp_data

    def test_output_format_prompt_video_extracts_gen_prompt(self, client_analyze):
        """output_format=prompt_video should extract gen_prompt."""
        gen_prompt_text = "A cinematic video about overcoming with music and cuts"
        result_payload = {**_SAMPLE_RESULT, "gen_prompt": gen_prompt_text}

        with patch.object(httpx, "post", return_value=_make_bridge_response(result_payload)):
            r = client_analyze.post(
                "/analyze/claude",
                json={"youtube_url": "https://youtube.com/watch?v=test", "output_format": "prompt_video"}
            )

        assert r.status_code == 200
        resp_data = r.json()
        assert resp_data.get("gen_prompt") == gen_prompt_text
        assert resp_data.get("gen_prompt_format") == "prompt_video"

    def test_output_format_prompt_json_extracts_storyboard(self, client_analyze):
        """output_format=prompt_json should extract gen_prompt_storyboard."""
        storyboard = {
            "scene_order": [
                {"scene": 1, "description": "Opening", "camera_angle": "wide",
                 "lighting": "bright", "objects": ["person"], "style": "dramatic"}
            ]
        }
        result_payload = {**_SAMPLE_RESULT, "gen_prompt_storyboard": storyboard}

        with patch.object(httpx, "post", return_value=_make_bridge_response(result_payload)):
            r = client_analyze.post(
                "/analyze/claude",
                json={"youtube_url": "https://youtube.com/watch?v=test", "output_format": "prompt_json"}
            )

        assert r.status_code == 200
        resp_data = r.json()
        assert resp_data.get("gen_prompt_format") == "prompt_json"
        gen_prompt_str = resp_data.get("gen_prompt")
        assert gen_prompt_str is not None
        parsed = json.loads(gen_prompt_str)
        assert parsed["scene_order"][0]["scene"] == 1

    def test_analyze_claude_persists_gen_prompt(self, client_analyze):
        """After analyze/claude with output_format=prompt_video, gen_prompt should be persisted to sources."""
        import main as m
        gen_prompt_text = "A cinematic video about overcoming with music and cuts"
        result_payload = {**_SAMPLE_RESULT, "gen_prompt": gen_prompt_text}

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit = MagicMock()
        mock_conn.close = MagicMock()

        with patch.object(m, "_db_conn", return_value=mock_conn), \
             patch.object(m, "_extract_keyframes", return_value=_SAMPLE_FRAMES), \
             patch.object(m, "_save_creator"), \
             patch.object(m, "_save_source"), \
             patch.object(m, "_build_analyze_steps", return_value=[]), \
             patch.object(httpx, "post", return_value=_make_bridge_response(result_payload)):
            tc = TestClient(m.app)
            r = tc.post(
                "/analyze/claude",
                json={"youtube_url": "https://youtube.com/watch?v=test", "output_format": "prompt_video"}
            )

        assert r.status_code == 200
        # Verify that UPDATE was called on sources with gen_prompt
        update_calls = [call for call in mock_cursor.execute.call_args_list
                        if len(call[0]) > 0 and "UPDATE sources SET gen_prompt" in str(call[0][0])]
        assert len(update_calls) > 0, "UPDATE gen_prompt should have been called"
        # Check that the update includes the correct values
        update_call = update_calls[0]
        assert gen_prompt_text in str(update_call[0][1]), "gen_prompt text should be in UPDATE params"
        assert "prompt_video" in str(update_call[0][1]), "gen_prompt_format should be in UPDATE params"


class TestBuildClaudePrompt:
    def test_prompt_json_schema_uses_single_braces(self):
        """prompt_json addition must reach Claude with real JSON braces, not literal {{ }}."""
        import main as m
        p = m._build_claude_prompt("test", "prompt_json")
        assert '"gen_prompt_storyboard": {' in p, "schema must use a single opening brace"
        assert "{{" not in p and "}}" not in p, "no doubled braces should survive .format()"

    def test_prompt_none_has_no_gen_prompt(self):
        import main as m
        p = m._build_claude_prompt("test", "none")
        assert "gen_prompt" not in p


class TestSourcesUploadOutputFormat:
    def test_invalid_output_format_returns_400(self, client_upload):
        """Invalid output_format should return 400."""
        r = client_upload.post(
            "/sources/upload",
            data={"output_format": "invalid"},
            files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")}
        )
        assert r.status_code == 400
        assert "Invalid output_format" in r.json()["detail"]

    def test_output_format_prompt_video_stored(self, client_upload):
        """output_format=prompt_video should include gen_prompt in response."""
        import main as m
        gen_prompt_text = "A cinematic video"
        result_payload = {**_SAMPLE_RESULT, "gen_prompt": gen_prompt_text}

        # Mock DB to return a source_id
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (123,)
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(m, "_db_conn", return_value=mock_conn), \
             patch.object(m, "_extract_frames_from_file", return_value=_SAMPLE_FRAMES), \
             patch.object(m, "_log_api_usage"), \
             patch.object(httpx, "post", return_value=_make_bridge_response(result_payload)):
            tc = TestClient(m.app)
            r = tc.post(
                "/sources/upload",
                data={"output_format": "prompt_video"},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")}
            )

        assert r.status_code == 200
        resp_data = r.json()
        assert resp_data.get("gen_prompt") == gen_prompt_text
        assert resp_data.get("gen_prompt_format") == "prompt_video"
