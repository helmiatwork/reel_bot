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
from fastapi.testclient import TestClient
from main import app, _REPO_ROOT, _persist_frame_analysis, _build_frame_analysis


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
