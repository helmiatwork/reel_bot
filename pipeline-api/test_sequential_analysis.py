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
                frames=_SAMPLE_FRAMES,
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
                frames=_SAMPLE_FRAMES,
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
                frames=_SAMPLE_FRAMES,
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
                frames=_SAMPLE_FRAMES,
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
                frames=_SAMPLE_FRAMES,
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
                    frames=_SAMPLE_FRAMES,
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
                frames=_SAMPLE_FRAMES,
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
                frames=_SAMPLE_FRAMES,
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
                frames=[],
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

    def test_gen_prompt_receives_string_context_not_list(self):
        """Verify _generate_gen_prompt correctly handles string context (not list)."""
        import main as m

        # Mock httpx.post to capture the call and verify frames=[]
        with patch("httpx.post") as mock_post:
            video_prompt_result = {
                "gen_prompt": "A compelling video prompt for text-to-video generation"
            }
            mock_post.return_value = _make_bridge_response(video_prompt_result)

            # Call with text description (the correct way)
            frame_context = "Frame 1: scene opens. Frame 2: action occurs. Frame 3: conclusion."
            gen_prompt, gen_prompt_format = m._generate_gen_prompt(
                frame_descriptions=frame_context,
                subdir="test",
                output_format="prompt_video",
                model="claude-sonnet-4-6"
            )

            # Verify the call was made and frames=[] (no images)
            assert mock_post.called
            call_args = mock_post.call_args
            assert call_args[1]["json"]["frames"] == []
            assert frame_context in call_args[1]["json"]["prompt"]
            assert gen_prompt is not None


# ── Tests for Veo3 Storyboard (Timestamps + Transcript + Audio) ──────────────

class TestVeo3Storyboard:
    """Tests for Veo3 storyboard enrichment with timestamps, transcript, and audio."""

    def test_timed_frames_include_timestamp_in_per_frame_prompt(self):
        """Should include timestamp in per-frame prompt when timed frames are provided."""
        import main as m

        # Provide timed frames (dicts with t field)
        timed_frames = [
            {"name": "frame_000.jpg", "path": "/tmp/frame_000.jpg", "t": 1.5},
            {"name": "frame_001.jpg", "path": "/tmp/frame_001.jpg", "t": 3.2},
            {"name": "frame_002.jpg", "path": "/tmp/frame_002.jpg", "t": 5.0},
        ]

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in timed_frames
        ]
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]
        captured_prompts = []

        def mock_post(*args, **kwargs):
            captured_prompts.append(kwargs["json"]["prompt"])
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frames=timed_frames,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
            )

        # Verify per-frame prompts include timestamps
        assert len(captured_prompts) >= 3
        for i, prompt in enumerate(captured_prompts[:3]):
            # Should include "detik X.X" (second X.X in Indonesian)
            assert "detik" in prompt.lower() or "ke-" in prompt

    def test_transcript_included_in_synthesis_prompt(self):
        """Should include transcript text in synthesis prompt when provided."""
        import main as m

        transcript_text = "[0:00] Pembukaan\n[0:05] Konten utama\n[0:10] Penutup"

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]
        captured_synthesis_prompt = [None]

        def mock_post(*args, **kwargs):
            # Capture the synthesis prompt (last call, no frames)
            if "frames" in kwargs["json"] and kwargs["json"]["frames"] == []:
                captured_synthesis_prompt[0] = kwargs["json"]["prompt"]
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frames=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
                transcript_text=transcript_text,
            )

        # Verify transcript is in synthesis prompt
        assert captured_synthesis_prompt[0] is not None
        assert "Transkrip:" in captured_synthesis_prompt[0]
        assert "[0:00] Pembukaan" in captured_synthesis_prompt[0]

    def test_audio_tags_included_in_synthesis_prompt(self):
        """Should include audio tags in synthesis prompt when provided."""
        import main as m

        audio_tags = {
            "bpm": 120.5,
            "music_key": "A",
            "energy": 0.75,
            "duration_sec": 30.0,
        }

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]
        captured_synthesis_prompt = [None]

        def mock_post(*args, **kwargs):
            if "frames" in kwargs["json"] and kwargs["json"]["frames"] == []:
                captured_synthesis_prompt[0] = kwargs["json"]["prompt"]
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frames=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
                audio_tags=audio_tags,
            )

        # Verify audio tags are in synthesis prompt
        assert captured_synthesis_prompt[0] is not None
        assert "Audio/Musik:" in captured_synthesis_prompt[0] or "BPM:" in captured_synthesis_prompt[0]

    def test_rich_veo3_storyboard_schema(self):
        """Should return rich Veo3 storyboard with new fields for prompt_json."""
        import main as m

        rich_storyboard = {
            "scene_order": [
                {
                    "scene": 1,
                    "start": "0:00",
                    "end": "0:05",
                    "duration_sec": 5.0,
                    "shot": "wide",
                    "camera_movement": "static",
                    "subject": "Person on beach",
                    "action": "Walking toward camera",
                    "lighting": "bright",
                    "color_palette": "blues and golds",
                    "on_screen_text": "",
                    "audio": "Ocean waves sound",
                    "transition": "cut",
                }
            ]
        }

        result_with_rich_storyboard = _SAMPLE_ANALYSIS_RESULT.copy()
        result_with_rich_storyboard["gen_prompt_storyboard"] = {
            "aspect_ratio": "9:16",
            "overall_style": "cinematic",
            "music_mood": "uplifting",
            "scene_order": rich_storyboard["scene_order"],
        }

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(result_with_rich_storyboard)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frames=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="prompt_json",
                model="claude-sonnet-4-6",
            )

        # Verify rich storyboard fields are present
        assert "gen_prompt_storyboard" in result
        storyboard = result["gen_prompt_storyboard"]
        assert "aspect_ratio" in storyboard
        assert "overall_style" in storyboard
        assert "music_mood" in storyboard
        assert "scene_order" in storyboard

        scene = storyboard["scene_order"][0]
        assert "start" in scene
        assert "end" in scene
        assert "duration_sec" in scene
        assert "shot" in scene
        assert "camera_movement" in scene
        assert "subject" in scene
        assert "action" in scene
        assert "lighting" in scene
        assert "color_palette" in scene
        assert "on_screen_text" in scene
        assert "audio" in scene
        assert "transition" in scene

    def test_backward_compat_with_frame_names_strings(self):
        """Should still accept plain string frame names for backward compatibility."""
        import main as m

        # Pass old-style plain strings instead of dicts
        plain_frames = ["frame_000.jpg", "frame_001.jpg", "frame_002.jpg"]

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in plain_frames
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
                frames=plain_frames,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
            )

        # Should still work and return valid result
        assert "hook" in result
        assert result["hook"] == _SAMPLE_ANALYSIS_RESULT["hook"]

    def test_transcript_and_audio_combined(self):
        """Should handle both transcript and audio in the same call."""
        import main as m

        transcript_text = "[0:00] Intro\n[0:05] Main content"
        audio_tags = {"bpm": 128, "music_key": "C", "energy": 0.8}

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(_SAMPLE_ANALYSIS_RESULT)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]
        captured_synthesis_prompt = [None]

        def mock_post(*args, **kwargs):
            if "frames" in kwargs["json"] and kwargs["json"]["frames"] == []:
                captured_synthesis_prompt[0] = kwargs["json"]["prompt"]
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frames=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="none",
                model="claude-sonnet-4-6",
                transcript_text=transcript_text,
                audio_tags=audio_tags,
            )

        # Verify both are in synthesis prompt
        assert captured_synthesis_prompt[0] is not None
        assert "Transkrip:" in captured_synthesis_prompt[0]
        assert "Audio/Musik:" in captured_synthesis_prompt[0]
        assert "[0:00] Intro" in captured_synthesis_prompt[0]
        assert "128" in captured_synthesis_prompt[0] or "BPM" in captured_synthesis_prompt[0]

    def test_scene_duration_cap_enforcement(self):
        """Should enforce 8-second max duration per scene for Veo3."""
        import main as m

        # Create a storyboard with one scene that exceeds 8 seconds
        long_scene_storyboard = {
            "aspect_ratio": "9:16",
            "overall_style": "cinematic",
            "music_mood": "uplifting",
            "scene_order": [
                {
                    "scene": 1,
                    "start": "0:00",
                    "end": "0:15",  # 15 seconds — exceeds 8s cap
                    "duration_sec": 15.0,
                    "shot": "wide",
                    "camera_movement": "pan",
                    "subject": "Landscape",
                    "action": "Camera pans across",
                    "lighting": "bright",
                    "color_palette": "greens and blues",
                    "on_screen_text": "",
                    "audio": "Wind sound",
                    "transition": "cut",
                }
            ]
        }

        result_with_long_scene = _SAMPLE_ANALYSIS_RESULT.copy()
        result_with_long_scene["gen_prompt_storyboard"] = long_scene_storyboard

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(result_with_long_scene)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frames=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="prompt_json",
                model="claude-sonnet-4-6",
            )

        # Verify scene duration cap is enforced
        assert "gen_prompt_storyboard" in result
        storyboard = result["gen_prompt_storyboard"]
        scenes = storyboard.get("scene_order", [])

        # Original had 1 scene of 15s, should be split into 2 scenes of ~7.5s each
        assert len(scenes) == 2, f"Expected 2 split scenes, got {len(scenes)}"

        # Verify each scene is ≤ 8 seconds
        for scene in scenes:
            duration = scene.get("duration_sec", 0)
            assert duration <= 8.0, f"Scene {scene.get('scene')} has duration {duration} > 8.0s"

        # Verify scenes are renumbered correctly
        assert scenes[0].get("scene") == 1
        assert scenes[1].get("scene") == 2

        # Verify visual content is preserved in both splits
        assert scenes[0].get("subject") == "Landscape"
        assert scenes[1].get("subject") == "Landscape"
        assert scenes[0].get("action") == "Camera pans across"
        assert scenes[1].get("action") == "Camera pans across"

    def test_no_scene_split_when_under_cap(self):
        """Should not split scenes that are already under 8 seconds."""
        import main as m

        short_scene_storyboard = {
            "aspect_ratio": "9:16",
            "overall_style": "cinematic",
            "music_mood": "uplifting",
            "scene_order": [
                {
                    "scene": 1,
                    "start": "0:00",
                    "end": "0:05",  # 5 seconds — under 8s cap
                    "duration_sec": 5.0,
                    "shot": "close-up",
                    "camera_movement": "static",
                    "subject": "Person",
                    "action": "Speaking",
                    "lighting": "soft",
                    "color_palette": "warm tones",
                    "on_screen_text": "Hello",
                    "audio": "Voice speaking",
                    "transition": "cut",
                }
            ]
        }

        result_with_short_scene = _SAMPLE_ANALYSIS_RESULT.copy()
        result_with_short_scene["gen_prompt_storyboard"] = short_scene_storyboard

        frame_responses = [
            _make_bridge_response({"description": "Frame"})
            for _ in _SAMPLE_FRAMES
        ]
        synthesis_response = _make_bridge_response(result_with_short_scene)
        all_responses = frame_responses + [synthesis_response]
        call_count = [0]

        def mock_post(*args, **kwargs):
            resp = all_responses[call_count[0]]
            call_count[0] += 1
            return resp

        with patch("httpx.post", side_effect=mock_post):
            result = m._analyze_frames_sequential(
                frames=_SAMPLE_FRAMES,
                subdir="test_subdir",
                intent="test",
                output_format="prompt_json",
                model="claude-sonnet-4-6",
            )

        # Verify scene is NOT split
        storyboard = result.get("gen_prompt_storyboard", {})
        scenes = storyboard.get("scene_order", [])
        assert len(scenes) == 1
        assert scenes[0].get("duration_sec") == 5.0
        assert scenes[0].get("scene") == 1
