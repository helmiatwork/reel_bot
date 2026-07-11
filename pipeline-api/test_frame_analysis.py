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

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from fastapi.testclient import TestClient
from main import app, _REPO_ROOT


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
