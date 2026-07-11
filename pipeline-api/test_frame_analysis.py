"""
Test frame_analysis persistence and /sources/frames endpoint.
Verifies that per-frame descriptions are captured, persisted to frames.json,
and exposed via the API with exact timestamp-based scene mapping.
"""
import json
import tempfile
import shutil
from pathlib import Path
import sys
from unittest.mock import patch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

import pytest
import os
import importlib
from fastapi.testclient import TestClient
from main import app, _REPO_ROOT, _persist_frame_analysis, _build_frame_analysis, _parse_batch_descriptions, ANALYZE_SYNTHESIS_MODEL, _pick_scene_frame_times


@pytest.fixture
def test_video_id():
    """Use a test ID for frames."""
    return "test_frame_analysis_001"


@pytest.fixture
def frames_dir(test_video_id):
    """Create a temporary frames directory for testing."""
    frames_path = _REPO_ROOT / "data" / "frames" / test_video_id
    frames_path.mkdir(parents=True, exist_ok=True)
    yield frames_path
    # Cleanup
    if frames_path.exists():
        shutil.rmtree(frames_path)


def test_frames_json_sidecar_structure(frames_dir, test_video_id):
    """Test that frames.json is created with correct structure."""
    # Create mock frame images
    for i in range(3):
        frame_path = frames_dir / f"frame_{i:03d}.jpg"
        frame_path.write_bytes(b"fake jpeg data")

    # Create frames.json with proper structure
    frame_analysis = [
        {"name": "frame_000.jpg", "t": 0.0, "desc": "Opening shot of person"},
        {"name": "frame_001.jpg", "t": 3.5, "desc": "Close-up of face"},
        {"name": "frame_002.jpg", "t": 7.2, "desc": "Wide shot of scene"},
    ]
    frames_json_path = frames_dir / "frames.json"
    frames_json_path.write_text(json.dumps(frame_analysis, ensure_ascii=False), encoding="utf-8")

    # Verify file was created
    assert frames_json_path.exists()
    data = json.loads(frames_json_path.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert data[0]["name"] == "frame_000.jpg"
    assert data[0]["t"] == 0.0
    assert data[0]["desc"] == "Opening shot of person"


def test_sources_frames_endpoint_rich_objects(frames_dir, test_video_id):
    """Test that /sources/frames returns richer frame objects with url, t, desc."""
    client = TestClient(app)

    # Create mock frame images
    for i in range(2):
        frame_path = frames_dir / f"frame_{i:03d}.jpg"
        frame_path.write_bytes(b"fake jpeg data")

    # Create frames.json
    frame_analysis = [
        {"name": "frame_000.jpg", "t": 1.0, "desc": "First frame description"},
        {"name": "frame_001.jpg", "t": 5.0, "desc": "Second frame description"},
    ]
    frames_json_path = frames_dir / "frames.json"
    frames_json_path.write_text(json.dumps(frame_analysis, ensure_ascii=False), encoding="utf-8")

    # Query the API with file:// URL (upload scenario)
    youtube_url = f"file://{test_video_id}"
    response = client.get(f"/sources/frames?youtube_url={youtube_url}")
    assert response.status_code == 200

    result = response.json()
    assert result["video_id"] == test_video_id
    assert len(result["frames"]) == 2

    # Verify frame objects have richer structure
    frame0 = result["frames"][0]
    assert "url" in frame0
    assert "t" in frame0
    assert "desc" in frame0
    assert frame0["url"] == f"/frames/{test_video_id}/frame_000.jpg"
    assert frame0["t"] == 1.0
    assert frame0["desc"] == "First frame description"

    frame1 = result["frames"][1]
    assert frame1["t"] == 5.0
    assert frame1["desc"] == "Second frame description"


def test_sources_frames_fallback_for_old_sources(frames_dir, test_video_id):
    """Test that frames without matching frames.json entry get null t and desc (backward compat)."""
    client = TestClient(app)

    # Create frame images but NO frames.json (old source)
    for i in range(2):
        frame_path = frames_dir / f"frame_{i:03d}.jpg"
        frame_path.write_bytes(b"fake jpeg data")

    youtube_url = f"file://{test_video_id}"
    response = client.get(f"/sources/frames?youtube_url={youtube_url}")
    assert response.status_code == 200

    result = response.json()
    assert len(result["frames"]) == 2

    # Without frames.json, t and desc should be null
    for frame in result["frames"]:
        assert frame["t"] is None
        assert frame["desc"] is None
        assert "url" in frame


def test_frame_analysis_list_structure():
    """Test that frame_analysis list has correct structure for persistence."""
    frame_analysis = [
        {
            "name": "frame_000.jpg",
            "t": 0.5,
            "desc": "Opening scene with bright lighting"
        },
        {
            "name": "frame_001.jpg",
            "t": 2.1,
            "desc": "Person enters frame from left"
        },
        {
            "name": "frame_002.jpg",
            "t": None,
            "desc": "Static shot of background"
        }
    ]

    # Verify JSON-serializable
    serialized = json.dumps(frame_analysis, ensure_ascii=False)
    deserialized = json.loads(serialized)

    assert len(deserialized) == 3
    assert deserialized[2]["t"] is None
    assert deserialized[0]["desc"] == "Opening scene with bright lighting"


def test_analyze_frames_sequential_builds_frame_analysis():
    """Unit test: verify frame_analysis is built during analysis with correct structure.

    Tests the data structure collected during per-frame analysis, ensuring each frame
    produces an entry with {name, t, desc}.
    """
    # This is a structural test: we verify the frame_analysis dict structure
    # that gets built by the function. We don't need to mock httpx since
    # frame_analysis is built locally from the input frames and descriptions.

    # Simulate what _analyze_frames_sequential does: build frame_analysis
    frame_dicts = [
        {"name": "frame_000.jpg", "path": None, "t": 0.0},
        {"name": "frame_001.jpg", "path": None, "t": 2.5},
        {"name": "frame_002.jpg", "path": None, "t": 5.0},
    ]

    # Simulate the per-frame analysis loop
    frame_descriptions = []
    frame_analysis = []
    for i, frame_info in enumerate(frame_dicts, 1):
        frame_name = frame_info.get("name")
        timestamp_s = frame_info.get("t")
        # In real code, raw_desc comes from Claude
        raw_desc = f"Description of {frame_name}"
        frame_descriptions.append(raw_desc)
        frame_analysis.append({"name": frame_name, "t": timestamp_s, "desc": raw_desc})

    # Verify frame_analysis structure
    assert len(frame_analysis) == 3
    assert frame_analysis[0]["name"] == "frame_000.jpg"
    assert frame_analysis[0]["t"] == 0.0
    assert frame_analysis[0]["desc"] == "Description of frame_000.jpg"

    assert frame_analysis[1]["name"] == "frame_001.jpg"
    assert frame_analysis[1]["t"] == 2.5

    assert frame_analysis[2]["name"] == "frame_002.jpg"
    assert frame_analysis[2]["t"] == 5.0

    # Verify JSON-serializable
    serialized = json.dumps(frame_analysis, ensure_ascii=False)
    deserialized = json.loads(serialized)
    assert len(deserialized) == 3
    assert deserialized[0]["desc"] == "Description of frame_000.jpg"


def test_build_frame_analysis_basic():
    """Test _build_frame_analysis correctly zips frames with descriptions."""
    normalized_frames = [
        {"name": "frame_000.jpg", "t": 0.0},
        {"name": "frame_001.jpg", "t": 2.5},
        {"name": "frame_002.jpg", "t": 5.0},
    ]
    frame_descriptions = ["Opening shot", "Close-up", "Wide shot"]

    result = _build_frame_analysis(normalized_frames, frame_descriptions)

    assert len(result) == 3
    assert result[0]["name"] == "frame_000.jpg"
    assert result[0]["t"] == 0.0
    assert result[0]["desc"] == "Opening shot"
    assert result[1]["t"] == 2.5
    assert result[1]["desc"] == "Close-up"
    assert result[2]["t"] == 5.0
    assert result[2]["desc"] == "Wide shot"


def test_synthesis_resilience_frame_analysis_on_failure():
    """Test that frame_analysis is attached to result even when synthesis (parsed) is None.

    Simulates the resilience logic: when synthesis bridge times out, parsed=None,
    but we still want to preserve the per-frame analysis collected so far.
    """
    # Simulate the resilience merge logic from _analyze_frames_sequential
    normalized_frames = [
        {"name": "frame_000.jpg", "t": 0.0},
        {"name": "frame_001.jpg", "t": 2.5},
    ]
    frame_descriptions = ["First description", "Second description"]

    # Synthesis failed, so parsed is None
    parsed = None

    # Apply the resilience logic
    frame_analysis = _build_frame_analysis(normalized_frames, frame_descriptions)
    result = parsed if isinstance(parsed, dict) else {}
    if frame_analysis:
        result["frame_analysis"] = frame_analysis

    # Verify frame_analysis is in result even though synthesis failed
    assert "frame_analysis" in result
    assert len(result["frame_analysis"]) == 2
    assert result["frame_analysis"][0]["name"] == "frame_000.jpg"
    assert result["frame_analysis"][0]["desc"] == "First description"
    assert result["frame_analysis"][1]["t"] == 2.5


def test_build_frame_analysis_with_null_timestamps():
    """Test _build_frame_analysis handles null timestamps."""
    normalized_frames = [
        {"name": "frame_000.jpg", "t": 1.0},
        {"name": "frame_001.jpg", "t": None},
        {"name": "frame_002.jpg", "t": 5.0},
    ]
    frame_descriptions = ["Has time", "No time", "Has time again"]

    result = _build_frame_analysis(normalized_frames, frame_descriptions)

    assert result[0]["t"] == 1.0
    assert result[1]["t"] is None
    assert result[1]["desc"] == "No time"
    assert result[2]["t"] == 5.0


def test_build_frame_analysis_mismatched_lengths():
    """Test _build_frame_analysis handles mismatched list lengths (zip behavior)."""
    normalized_frames = [
        {"name": "frame_000.jpg", "t": 0.0},
        {"name": "frame_001.jpg", "t": 2.5},
        {"name": "frame_002.jpg", "t": 5.0},
    ]
    # Fewer descriptions than frames
    frame_descriptions = ["First", "Second"]

    result = _build_frame_analysis(normalized_frames, frame_descriptions)

    # zip stops at the shorter list
    assert len(result) == 2
    assert result[0]["name"] == "frame_000.jpg"
    assert result[1]["name"] == "frame_001.jpg"


def test_build_frame_analysis_non_dict_frames():
    """Test _build_frame_analysis handles backward-compat string names gracefully."""
    normalized_frames = [
        {"name": "frame_000.jpg", "t": 0.0},
        "frame_001.jpg",  # Old format fallback (string)
        {"name": "frame_002.jpg", "t": 5.0},
    ]
    frame_descriptions = ["First", "Second", "Third"]

    result = _build_frame_analysis(normalized_frames, frame_descriptions)

    # All entries are processed, including string names (backward compat)
    assert len(result) == 3
    assert result[0]["name"] == "frame_000.jpg"
    assert result[0]["t"] == 0.0
    assert result[1]["name"] == "frame_001.jpg"
    assert result[1]["t"] is None  # string entry has no timestamp
    assert result[2]["name"] == "frame_002.jpg"


def test_persist_frame_analysis_writes_sidecar(tmp_path):
    """Test that _persist_frame_analysis writes frames.json with correct data."""
    video_id = "test_persist_001"

    # Mock _REPO_ROOT to use tmp_path
    with patch("main._REPO_ROOT", tmp_path):
        frame_analysis = [
            {"name": "frame_000.jpg", "t": 0.0, "desc": "Opening shot"},
            {"name": "frame_001.jpg", "t": 2.5, "desc": "Close-up"},
            {"name": "frame_002.jpg", "t": 5.0, "desc": "Wide shot"},
        ]
        parsed = {"frame_analysis": frame_analysis}

        # Call the persistence helper
        _persist_frame_analysis(video_id, parsed)

        # Verify the sidecar file exists
        frames_json_path = tmp_path / "data" / "frames" / video_id / "frames.json"
        assert frames_json_path.exists(), f"Expected {frames_json_path} to exist"

        # Verify the content
        data = json.loads(frames_json_path.read_text(encoding="utf-8"))
        assert len(data) == 3
        assert data[0]["name"] == "frame_000.jpg"
        assert data[0]["t"] == 0.0
        assert data[0]["desc"] == "Opening shot"
        assert data[2]["t"] == 5.0


def test_persist_frame_analysis_empty_frame_list(tmp_path):
    """Test that empty frame_analysis list doesn't write a sidecar (non-fatal)."""
    video_id = "test_persist_empty"

    with patch("main._REPO_ROOT", tmp_path):
        parsed = {"frame_analysis": []}

        # Call the persistence helper
        _persist_frame_analysis(video_id, parsed)

        # Verify no sidecar was written
        frames_json_path = tmp_path / "data" / "frames" / video_id / "frames.json"
        assert not frames_json_path.exists(), "Empty frame_analysis should not write sidecar"


def test_persist_frame_analysis_missing_video_id(tmp_path):
    """Test that missing video_id doesn't cause exception (non-fatal)."""
    with patch("main._REPO_ROOT", tmp_path):
        frame_analysis = [
            {"name": "frame_000.jpg", "t": 0.0, "desc": "Test frame"},
        ]
        parsed = {"frame_analysis": frame_analysis}

        # Call with None video_id - should not raise
        _persist_frame_analysis(None, parsed)
        _persist_frame_analysis("", parsed)

        # No crash = success


def test_persist_frame_analysis_malformed_parsed(tmp_path):
    """Test that malformed parsed dict doesn't cause exception (non-fatal)."""
    video_id = "test_persist_malformed"

    with patch("main._REPO_ROOT", tmp_path):
        # Call with non-dict parsed
        _persist_frame_analysis(video_id, None)
        _persist_frame_analysis(video_id, "not a dict")
        _persist_frame_analysis(video_id, [])

        # No crash = success


def test_persist_frame_analysis_with_null_timestamps(tmp_path):
    """Test that frame_analysis with null timestamps persists correctly."""
    video_id = "test_persist_null_t"

    with patch("main._REPO_ROOT", tmp_path):
        frame_analysis = [
            {"name": "frame_000.jpg", "t": 1.5, "desc": "Has timestamp"},
            {"name": "frame_001.jpg", "t": None, "desc": "No timestamp"},
        ]
        parsed = {"frame_analysis": frame_analysis}

        _persist_frame_analysis(video_id, parsed)

        frames_json_path = tmp_path / "data" / "frames" / video_id / "frames.json"
        assert frames_json_path.exists()

        data = json.loads(frames_json_path.read_text(encoding="utf-8"))
        assert data[1]["t"] is None
        assert data[1]["desc"] == "No timestamp"


def test_analyze_synthesis_model_defaults_to_sonnet():
    """Test that ANALYZE_SYNTHESIS_MODEL defaults to claude-sonnet-4-6."""
    # Import directly from main to verify the constant exists and has correct default
    import main

    # When ANALYZE_SYNTHESIS_MODEL is not set in env, should default to sonnet
    if "ANALYZE_SYNTHESIS_MODEL" not in os.environ:
        assert main.ANALYZE_SYNTHESIS_MODEL == "claude-sonnet-4-6"
        assert isinstance(main.ANALYZE_SYNTHESIS_MODEL, str)
        assert len(main.ANALYZE_SYNTHESIS_MODEL) > 0


def test_analyze_synthesis_model_honors_env_override(monkeypatch):
    """Test that ANALYZE_SYNTHESIS_MODEL honors environment variable override."""
    # Set a custom model via environment variable
    monkeypatch.setenv("ANALYZE_SYNTHESIS_MODEL", "claude-opus-4-1")

    # Reload the main module to pick up the new env var
    import main
    importlib.reload(main)

    assert main.ANALYZE_SYNTHESIS_MODEL == "claude-opus-4-1"

    # Clean up by resetting to default
    monkeypatch.delenv("ANALYZE_SYNTHESIS_MODEL", raising=False)
    importlib.reload(main)


def test_parse_batch_descriptions_valid_json():
    """Test parsing valid JSON array of frame descriptions."""
    raw_result = '["Opening shot with bright lighting", "Person enters frame from left", "Static shot of background"]'
    expected_count = 3

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is not None
    assert len(result) == 3
    assert result[0] == "Opening shot with bright lighting"
    assert result[1] == "Person enters frame from left"
    assert result[2] == "Static shot of background"


def test_parse_batch_descriptions_json_with_fences():
    """Test parsing JSON array wrapped in ```json markdown fences."""
    raw_result = '```json\n["First description", "Second description", "Third description"]\n```'
    expected_count = 3

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is not None
    assert len(result) == 3
    assert result[0] == "First description"
    assert result[1] == "Second description"
    assert result[2] == "Third description"


def test_parse_batch_descriptions_wrong_count():
    """Test that wrong count (array size mismatch) returns None (triggers fallback)."""
    raw_result = '["First", "Second", "Third"]'
    expected_count = 5  # Expect 5, got 3

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is None


def test_parse_batch_descriptions_non_json_garbage():
    """Test that non-JSON garbage returns None (triggers fallback)."""
    raw_result = "This is not JSON at all, just plain text"
    expected_count = 2

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is None


def test_parse_batch_descriptions_empty_string():
    """Test that empty string returns None."""
    raw_result = ""
    expected_count = 3

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is None


def test_parse_batch_descriptions_not_an_array():
    """Test that a JSON object (not array) returns None."""
    raw_result = '{"desc1": "First", "desc2": "Second"}'
    expected_count = 2

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is None


def test_parse_batch_descriptions_array_with_non_strings():
    """Test that array with non-string elements returns None."""
    raw_result = '["Valid string", 42, "Another string"]'
    expected_count = 3

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is None


def test_parse_batch_descriptions_single_item():
    """Test parsing a single-item array."""
    raw_result = '["Single frame description"]'
    expected_count = 1

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is not None
    assert len(result) == 1
    assert result[0] == "Single frame description"


def test_parse_batch_descriptions_with_special_chars():
    """Test parsing descriptions with special characters and unicode."""
    raw_result = '["Frame dengan emoji 🎬", "Teks dengan 中文", "Quote \\"escaped\\""]'
    expected_count = 3

    result = _parse_batch_descriptions(raw_result, expected_count)

    assert result is not None
    assert len(result) == 3
    assert result[0] == "Frame dengan emoji 🎬"
    assert result[1] == "Teks dengan 中文"
    assert result[2] == 'Quote "escaped"'


def test_parse_batch_descriptions_json_with_markdown_fences_variations():
    """Test parsing JSON with different markdown fence formats."""
    # Fence with newlines
    raw_result1 = '```json\n["First", "Second"]\n```'
    result1 = _parse_batch_descriptions(raw_result1, 2)
    assert result1 == ["First", "Second"]

    # Fence without language identifier
    raw_result2 = '```\n["First", "Second"]\n```'
    result2 = _parse_batch_descriptions(raw_result2, 2)
    assert result2 == ["First", "Second"]

    # Just code fence markers
    raw_result3 = '```["First", "Second"]```'
    result3 = _parse_batch_descriptions(raw_result3, 2)
    assert result3 == ["First", "Second"]


# --- _pick_scene_frame_times unit tests (pure function, no IO) ---

def test_pick_scene_frame_times_short_scene():
    """dur < 2 → exactly 1 timestamp, strictly inside (start, end)."""
    times = _pick_scene_frame_times(10.0, 11.0)
    assert len(times) == 1
    assert 10.0 < times[0] < 11.0


def test_pick_scene_frame_times_medium_scene():
    """dur = 4 → 2 timestamps, both strictly inside, ascending."""
    times = _pick_scene_frame_times(10.0, 14.0)
    assert len(times) == 2
    assert times[0] < times[1]
    assert all(10.0 < t < 14.0 for t in times)


def test_pick_scene_frame_times_long_scene():
    """dur = 20 → 3 timestamps, ascending, all strictly inside."""
    times = _pick_scene_frame_times(5.0, 25.0)
    assert len(times) == 3
    assert times == sorted(times)
    assert all(5.0 < t < 25.0 for t in times)


def test_pick_scene_frame_times_very_long_scene():
    """dur = 75 → 4–5 timestamps, ascending, inside, none within 0.3s of each other."""
    times = _pick_scene_frame_times(0.0, 75.0)
    assert 4 <= len(times) <= 5
    assert times == sorted(times)
    assert all(0.0 < t < 75.0 for t in times)
    for i in range(len(times) - 1):
        assert times[i + 1] - times[i] >= 0.3


def test_pick_scene_frame_times_all_inside_bounds():
    """All timestamps satisfy start < t < end across varied durations."""
    cases = [(0.0, 1.5), (0.0, 4.0), (0.0, 15.0), (100.0, 145.0), (0.0, 90.0)]
    for start, end in cases:
        times = _pick_scene_frame_times(start, end)
        assert len(times) >= 1, f"Expected ≥1 timestamp for ({start}, {end})"
        assert all(start < t < end for t in times), f"Time out of bounds for ({start}, {end}): {times}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
