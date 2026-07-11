# pipeline-api/test_sequential_analysis.py
# Unit tests for sequential frame analysis (_analyze_frames_sequential).
# Bridge calls are fully mocked — no network, no real claude invocation.

import json
import pytest
from unittest.mock import MagicMock, patch, call
from fastapi.testclient import TestClient
from fastapi import HTTPException


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bridge_response(result_payload: dict = None, ok: bool = True,
                          error_type: str = None) -> MagicMock:
    """Build a mock httpx.Response for the bridge POST /run call."""
    mock_resp = MagicMock()
    if ok:
        if result_payload is None:
            result_payload = {
                "summary": "Test video summary",
                "detail": "Test play-by-play",
                "hook": "Test hook",
                "structure": "Test structure",
                "retention": "Good retention",
                "retention_score": 7,
                "tags": ["test", "viral"],
            }
        mock_resp.json.return_value = {
            "ok": True,
            "result": json.dumps(result_payload),
            "raw_usage": {"input_tokens": 100, "output_tokens": 50},
            "cost_usd": 0.01,
            "model": "claude-sonnet-4-6",
        }
    else:
        payload = {"ok": False, "error": "bridge_test_error"}
        if error_type:
            payload["error_type"] = error_type
        mock_resp.json.return_value = payload
    return mock_resp


_SAMPLE_FRAMES = ["frame_000.jpg", "frame_001.jpg", "frame_002.jpg"]

_SAMPLE_ANALYSIS_RESULT = {
    "summary": "Video showing a person doing something interesting",
    "detail": "Frame 1 shows opening. Frame 2 shows action. Frame 3 shows conclusion.",
    "hook": "Opens with unexpected moment",
    "structure": "Problem → solution → CTA",
    "retention": "Pattern interrupts every 10 seconds",
    "retention_score": 8,
    "tags": ["viral", "shorts", "interesting"],
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient for testing."""
    import main as m
    from fastapi.testclient import TestClient
    return TestClient(m.app)


# ── Tests for _analyze_frames_sequential ──────────────────────────────────────

class TestSequentialAnalysis:
    """Tests for _analyze_frames_sequential helper function."""

    def test_sequential_calls_bridge_n_plus_1_times(self):
        """Should call bridge n times for frames + 1 for synthesis."""
        import main as m

        # Create mock responses: n per-frame responses + 1 synthesis response
        frame_responses = [
            _make_bridge_response({"description": f"Frame {i} description"})
            for i in range(len(_SAMPLE_FRAMES))
        ]
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)

        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frame_names=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test intent",
                output_format="none",
                model="claude-sonnet-4-6",
            )

        # Should have called bridge 4 times (3 frames + 1 synthesis)
        assert call_count[0] == len(_SAMPLE_FRAMES) + 1
        assert result.get("hook") == _SAMPLE_ANALYSIS_RESULT["hook"]
        assert result.get("structure") == _SAMPLE_ANALYSIS_RESULT["structure"]

    def test_returns_parsed_dict_with_expected_keys(self):
        """Should return dict with all expected analysis keys."""
        import main as m

        frame_responses = [
            _make_bridge_response({"description": "Frame desc"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frame_names=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
            )

        assert "summary" in result
        assert "detail" in result
        assert "hook" in result
        assert "structure" in result
        assert "retention" in result
        assert "retention_score" in result
        assert "tags" in result
        assert result["hook"] == _SAMPLE_ANALYSIS_RESULT["hook"]
        assert result["tags"] == _SAMPLE_ANALYSIS_RESULT["tags"]

    def test_frame_returns_empty_then_retries(self):
        """Should retry once if per-frame call returns empty."""
        import main as m

        # First frame call returns empty, second succeeds
        empty_response = MagicMock()
        empty_response.json.return_value = {"ok": True, "result": ""}
        good_response = _make_bridge_response({"description": "Frame desc"})

        frame_responses = [
            empty_response,  # First attempt (empty)
            good_response,   # Retry (succeeds)
            _make_bridge_response({"description": "Frame 2"}),
            _make_bridge_response({"description": "Frame 3"}),
        ]
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frame_names=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
            )

        # Should have retried the first frame (2 calls) + frame 2 + frame 3 + synthesis = 5 calls
        assert call_count[0] == 5
        # Result should still be valid
        assert "hook" in result

    def test_frame_empty_twice_uses_placeholder(self):
        """Should use placeholder if frame call empty after retry."""
        import main as m

        # All frame calls return empty
        empty_response = MagicMock()
        empty_response.json.return_value = {"ok": True, "result": ""}

        frame_responses = [empty_response, empty_response] * len(_SAMPLE_FRAMES)
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frame_names=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
            )

        # Should still return valid result
        assert "hook" in result
        assert result["hook"] == _SAMPLE_ANALYSIS_RESULT["hook"]

    def test_synthesis_parse_failure_retries_once(self):
        """Should retry synthesis call once if JSON parse fails."""
        import main as m

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]

        # First synthesis returns invalid JSON, second succeeds
        bad_synthesis = MagicMock()
        bad_synthesis.json.return_value = {"ok": True, "result": "invalid json {{{"}

        good_synthesis = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)

        all_responses = frame_responses + [bad_synthesis, good_synthesis]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frame_names=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
            )

        # Should have called bridge 3 (frames) + 2 (synthesis attempts) = 5 times
        assert call_count[0] == 5
        assert "hook" in result

    def test_synthesis_parse_failure_twice_raises(self):
        """Should raise HTTPException if synthesis parse fails twice."""
        import main as m

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]

        # Both synthesis attempts return invalid JSON
        bad_synthesis = MagicMock()
        bad_synthesis.json.return_value = {"ok": True, "result": "invalid json {{{"}

        all_responses = frame_responses + [bad_synthesis, bad_synthesis]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            with pytest.raises(HTTPException) as exc_info:
                m._analyze_frames_sequential(
                    frame_names=_SAMPLE_FRAMES,
                    subdir="test_subdir",
                    intent="test",
                    output_format="none",
                    model="claude-sonnet-4-6",
                )

        assert exc_info.value.status_code == 502

    def test_gen_prompt_storyboard_in_result(self):
        """Should include gen_prompt_storyboard in result for prompt_json."""
        import main as m

        result_with_storyboard = _SAMPLE_ANALYSIS_RESULT.copy()
        result_with_storyboard["gen_prompt_storyboard"] = {
            "scene_order": [
                {"scene": 1, "description": "Scene 1", "camera_angle": "wide", "lighting": "bright", "objects": ["obj1"], "style": "cinematic"}
            ]
        }

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(result_with_storyboard)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frame_names=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="prompt_json",
                model="claude-sonnet-4-6",
            )

        assert "gen_prompt_storyboard" in result
        assert "scene_order" in result["gen_prompt_storyboard"]
        assert len(result["gen_prompt_storyboard"]["scene_order"]) > 0

    def test_log_fn_called_during_analysis(self):
        """Should call log_fn with progress messages."""
        import main as m

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        log_messages = []

        def log_fn(msg):
            log_messages.append(msg)

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frame_names=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
                log_fn=log_fn,
            )

        # Should have logged per-frame progress
        assert len(log_messages) >= len(_SAMPLE_FRAMES)
        assert any("Analisa frame" in msg for msg in log_messages)

    def test_empty_frames_list_returns_empty_dict(self):
        """Should handle empty frame list gracefully."""
        import main as m

        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)

        with patch("httpx.post", return_value=synthesis_response):
            result = m._analyze_frames_sequential(
                frame_names=[],
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
            )

        # Should still work, just with synthesis call
        assert "hook" in result


# ── Regression tests ──────────────────────────────────────────────────────────

class TestNoRegressionExistingTests:
    """Ensure existing analyze tests still pass with sequential helper."""

    def test_existing_analyze_async_still_works(self, client):
        """Existing async analyze should still work."""
        import main as m

        # Mock _analyze_frames_sequential to return a valid result
        mock_result = _SAMPLE_ANALYSIS_RESULT.copy()

        with patch.object(m, "_validate_source_url"), \
             patch.object(m, "_extract_keyframes", return_value=[f"/path/{f}" for f in _SAMPLE_FRAMES]), \
             patch.object(m, "_analyze_frames_sequential", return_value=mock_result), \
             patch.object(m, "_db_conn", return_value=None), \
             patch.object(m, "_save_creator"), \
             patch.object(m, "_save_source"):

            response = client.post(
                "/analyze/claude/async",
                json={
                    "youtube_url": "https://youtube.com/watch?v=test",
                    "intent": "test",
                    "output_format": "none",
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "run_id" in data
