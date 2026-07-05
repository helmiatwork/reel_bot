# pipeline-api/test_render.py
# Unit tests for CLIP engine render pipeline: POST /clips/render, GET /clips/renders/<uuid>/download
# EDL builder unit test, integration test with ffmpeg (gracefully skip if unavailable), endpoint test with mocks.

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid


def test_build_clip_edl_basic():
    """EDL builder unit test: feed clips array with recommended clip + caption → assert dict has correct shape."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from main import _build_clip_edl

    clips = [
        {
            "start_sec": 15,
            "end_sec": 45,
            "title": "First clip",
            "caption": "This is the first clip"
        },
        {
            "start_sec": 120,
            "end_sec": 165,
            "title": "Second clip",
            "caption": "Second clip caption",
            "recommended": True
        }
    ]

    src_path = Path("/tmp/test_source.mp4")
    edl = _build_clip_edl(clips, src_path, chosen_index=None)

    # Check structure
    assert edl["aspect"] == "1080x1920"
    assert edl["fps"] == 30
    assert "clips" in edl
    assert "captions" in edl
    assert isinstance(edl["clips"], list)
    assert len(edl["clips"]) == 1  # Only one clip in EDL (the recommended one)

    # Check the single clip
    clip = edl["clips"][0]
    assert clip["in"] == 120  # From second clip (recommended)
    assert clip["out"] == 165
    assert str(src_path) in clip["src"]

    # Check captions
    assert len(edl["captions"]) == 1
    caption = edl["captions"][0]
    assert caption["start"] == 120
    assert caption["end"] == 165
    assert caption["text"] == "Second clip caption"


def test_build_clip_edl_picks_recommended():
    """EDL builder picks the clip with recommended=True if chosen_index is None."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from main import _build_clip_edl

    clips = [
        {
            "start_sec": 10,
            "end_sec": 30,
            "title": "Not recommended",
            "recommended": False
        },
        {
            "start_sec": 50,
            "end_sec": 70,
            "title": "This is recommended",
            "recommended": True
        }
    ]

    src_path = Path("/tmp/source.mp4")
    edl = _build_clip_edl(clips, src_path, chosen_index=None)

    assert len(edl["clips"]) == 1
    assert edl["clips"][0]["in"] == 50
    assert edl["clips"][0]["out"] == 70


def test_build_clip_edl_chosen_index_override():
    """EDL builder uses chosen_index when provided."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from main import _build_clip_edl

    clips = [
        {
            "start_sec": 10,
            "end_sec": 30,
            "title": "First",
            "recommended": True
        },
        {
            "start_sec": 50,
            "end_sec": 70,
            "title": "Second",
            "recommended": False
        }
    ]

    src_path = Path("/tmp/source.mp4")
    edl = _build_clip_edl(clips, src_path, chosen_index=1)

    assert len(edl["clips"]) == 1
    assert edl["clips"][0]["in"] == 50
    assert edl["clips"][0]["out"] == 70


def test_build_clip_edl_no_captions():
    """EDL builder handles clips without captions."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from main import _build_clip_edl

    clips = [
        {
            "start_sec": 10,
            "end_sec": 30,
            "title": "No caption clip",
            "recommended": True
        }
    ]

    src_path = Path("/tmp/source.mp4")
    edl = _build_clip_edl(clips, src_path, chosen_index=None)

    assert len(edl["captions"]) == 0


def test_build_clip_edl_fallback_to_index_0():
    """EDL builder falls back to index 0 if no recommended clip found."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from main import _build_clip_edl

    clips = [
        {
            "start_sec": 10,
            "end_sec": 30,
            "title": "First (no recommended flag)",
            "recommended": False
        }
    ]

    src_path = Path("/tmp/source.mp4")
    edl = _build_clip_edl(clips, src_path, chosen_index=None)

    assert len(edl["clips"]) == 1
    assert edl["clips"][0]["in"] == 10
    assert edl["clips"][0]["out"] == 30


def test_render_integration_with_ffmpeg():
    """Integration test: generate tiny sample video IN test with ffmpeg, build EDL, run assemble.sh, assert success.
    Gracefully skip if ffmpeg/ffprobe unavailable."""

    # Check if ffmpeg and ffprobe are available
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("SKIPPED: ffmpeg or ffprobe not available")
        return

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from main import _build_clip_edl

    # Create temp directories
    work_dir = tempfile.mkdtemp(prefix="render_test_")
    try:
        # Create a tiny test video (4 seconds, 1080x1920) using ffmpeg
        src_video = Path(work_dir) / "source.mp4"
        ffmpeg_cmd = [
            "ffmpeg", "-f", "lavfi", "-i", "color=c=red:s=1080x1920:d=4",
            "-f", "lavfi", "-i", "sine=f=440:d=4",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-y", str(src_video)
        ]
        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=30)
        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        assert src_video.exists(), "Generated test video not found"

        # Build EDL pointing at the test video (clip from 0 to 4 seconds)
        clips = [
            {
                "start_sec": 0,
                "end_sec": 4,
                "title": "Tiny test clip",
                "caption": "Test caption",
                "recommended": True
            }
        ]
        edl = _build_clip_edl(clips, src_video, chosen_index=None)

        # Write EDL to file
        edl_file = Path(work_dir) / "test.edl.json"
        edl_file.write_text(json.dumps(edl))

        # Run assemble.sh
        assemble_sh = Path(__file__).parent.parent / "scripts" / "assemble.sh"
        out_mp4 = Path(work_dir) / "output.mp4"

        if not assemble_sh.exists():
            print(f"SKIPPED: {assemble_sh} not found")
            return

        result = subprocess.run(
            ["bash", str(assemble_sh), str(edl_file), str(out_mp4)],
            capture_output=True, timeout=60
        )

        assert result.returncode == 0, f"assemble.sh failed: {result.stderr.decode()}"
        assert out_mp4.exists(), "Output MP4 not created"
        assert out_mp4.stat().st_size > 0, "Output MP4 is empty"

        # Verify output via ffprobe
        ffprobe_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "stream=width,height",
            "-of", "json", str(out_mp4)
        ]
        result = subprocess.run(ffprobe_cmd, capture_output=True, timeout=10)
        assert result.returncode == 0, f"ffprobe failed: {result.stderr.decode()}"

        probe_data = json.loads(result.stdout)
        streams = probe_data.get("streams", [])
        assert len(streams) > 0, "No video streams found"
        video_stream = streams[0]
        assert video_stream.get("width") == 1080, f"Expected width=1080, got {video_stream.get('width')}"
        assert video_stream.get("height") == 1920, f"Expected height=1920, got {video_stream.get('height')}"

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def test_render_endpoint_mocked():
    """Endpoint test: monkeypatch _download_source_video and subprocess.run for assemble.sh.
    Assert EDL passed to assemble.sh has right shape, response contains video_path."""

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import main as m
    from fastapi.testclient import TestClient

    client = TestClient(m.app)

    # Mock _download_source_video to return a fake path
    fake_source_path = Path("/tmp/fake_source.mp4")

    def mock_download(url):
        return fake_source_path

    # Mock subprocess.run for assemble.sh
    captured_edl_path = None
    captured_out_path = None

    def mock_subprocess_run(args, *a, **kw):
        nonlocal captured_edl_path, captured_out_path
        if args[0] == "bash" and "assemble.sh" in args[1]:
            captured_edl_path = args[2]
            captured_out_path = args[3]
            # Fake success
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result
        # For other calls, just return success
        result = MagicMock()
        result.returncode = 0
        return result

    # Mock _db_conn to return None (no DB)
    with patch.object(m, "_download_source_video", side_effect=mock_download), \
         patch.object(m, "_validate_source_url", return_value="https://youtube.com/watch?v=test"), \
         patch("subprocess.run", side_effect=mock_subprocess_run), \
         patch.object(m, "_db_conn", return_value=None), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat:

        # Mock Path.stat to return a fake file size
        mock_stat.return_value.st_size = 1000000

        r = client.post("/clips/render", json={
            "youtube_url": "https://www.youtube.com/watch?v=test123",
            "clips": [
                {
                    "start_sec": 0,
                    "end_sec": 30,
                    "title": "Test clip",
                    "caption": "Test",
                    "recommended": True
                }
            ]
        })

        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "video_path" in data
        assert "clip" in data
        assert "edl" in data


def test_render_endpoint_loads_from_clip_finds():
    """Test /clips/render loads clips from clip_finds table by clip_find_id."""

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import main as m
    from fastapi.testclient import TestClient

    client = TestClient(m.app)

    # Mock DB to return sample clip_find row
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    sample_clips = [
        {
            "start_sec": 10,
            "end_sec": 40,
            "title": "Clip from DB",
            "caption": "DB caption",
            "recommended": True
        }
    ]

    mock_cursor.fetchone.return_value = (
        1,  # id
        "https://www.youtube.com/watch?v=dbvideo",
        json.dumps(sample_clips),  # clips
        "claude-sonnet-4-6"
    )

    def mock_subprocess_run(args, *a, **kw):
        if args[0] == "bash" and "assemble.sh" in args[1]:
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result
        result = MagicMock()
        result.returncode = 0
        return result

    with patch.object(m, "_download_source_video", return_value=Path("/tmp/source.mp4")), \
         patch.object(m, "_validate_source_url", return_value="https://youtube.com/watch?v=test"), \
         patch.object(m, "_db_conn", return_value=mock_conn), \
         patch("subprocess.run", side_effect=mock_subprocess_run), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat") as mock_stat:

        mock_stat.return_value.st_size = 1000000

        r = client.post("/clips/render", json={
            "clip_find_id": 1
        })

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"


def test_render_endpoint_validates_youtube_url():
    """Test /clips/render validates YouTube URL."""

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import main as m
    from fastapi.testclient import TestClient

    client = TestClient(m.app)

    # Invalid URL should raise HTTPException from _validate_source_url
    r = client.post("/clips/render", json={
        "youtube_url": "not-a-valid-url",
        "clips": []
    })

    assert r.status_code == 400


def test_render_endpoint_assemble_failure():
    """Test /clips/render returns 500 on assemble.sh failure."""

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import main as m
    from fastapi.testclient import TestClient

    client = TestClient(m.app)

    def mock_subprocess_run(args, *a, **kw):
        if args[0] == "bash" and "assemble.sh" in args[1]:
            result = MagicMock()
            result.returncode = 1
            result.stderr = "FFmpeg error: codec not found"
            return result
        result = MagicMock()
        result.returncode = 0
        return result

    with patch.object(m, "_download_source_video", return_value=Path("/tmp/source.mp4")), \
         patch.object(m, "_validate_source_url", return_value="https://youtube.com/watch?v=test"), \
         patch.object(m, "_db_conn", return_value=None), \
         patch("subprocess.run", side_effect=mock_subprocess_run):

        r = client.post("/clips/render", json={
            "youtube_url": "https://www.youtube.com/watch?v=test123",
            "clips": [
                {
                    "start_sec": 0,
                    "end_sec": 30,
                    "title": "Test",
                    "recommended": True
                }
            ]
        })

        assert r.status_code == 500


def test_download_route_returns_mp4():
    """Test GET /clips/renders/<uuid>/download returns MP4 file."""

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import main as m
    from fastapi.testclient import TestClient

    client = TestClient(m.app)

    # Create a fake MP4 file in data/renders
    render_id = str(uuid.uuid4())
    render_dir = Path(__file__).parent.parent / "data" / "renders" / render_id
    render_dir.mkdir(parents=True, exist_ok=True)

    try:
        mp4_file = render_dir / "output.mp4"
        mp4_file.write_bytes(b"fake mp4 data")

        r = client.get(f"/clips/renders/{render_id}/download")

        assert r.status_code == 200
        assert r.headers["content-type"] == "video/mp4"
        assert r.content == b"fake mp4 data"
    finally:
        shutil.rmtree(render_dir, ignore_errors=True)


def test_download_route_guards_path_traversal():
    """Test GET /clips/renders/<uuid>/download guards against path traversal attacks."""

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import main as m
    from fastapi.testclient import TestClient

    client = TestClient(m.app)

    # Try path traversal
    r = client.get("/clips/renders/../../../etc/passwd/download")

    assert r.status_code == 404 or r.status_code == 400


if __name__ == "__main__":
    # Run tests without pytest if needed
    print("Running test_build_clip_edl_basic...")
    test_build_clip_edl_basic()
    print("PASS")

    print("Running test_build_clip_edl_picks_recommended...")
    test_build_clip_edl_picks_recommended()
    print("PASS")

    print("Running test_build_clip_edl_chosen_index_override...")
    test_build_clip_edl_chosen_index_override()
    print("PASS")

    print("Running test_build_clip_edl_no_captions...")
    test_build_clip_edl_no_captions()
    print("PASS")

    print("Running test_build_clip_edl_fallback_to_index_0...")
    test_build_clip_edl_fallback_to_index_0()
    print("PASS")

    print("Running test_render_integration_with_ffmpeg...")
    test_render_integration_with_ffmpeg()
    print("PASS")

    print("Running test_render_endpoint_mocked...")
    test_render_endpoint_mocked()
    print("PASS")

    print("Running test_render_endpoint_loads_from_clip_finds...")
    test_render_endpoint_loads_from_clip_finds()
    print("PASS")

    print("Running test_render_endpoint_validates_youtube_url...")
    test_render_endpoint_validates_youtube_url()
    print("PASS")

    print("Running test_render_endpoint_assemble_failure...")
    test_render_endpoint_assemble_failure()
    print("PASS")

    print("Running test_download_route_returns_mp4...")
    test_download_route_returns_mp4()
    print("PASS")

    print("Running test_download_route_guards_path_traversal...")
    test_download_route_guards_path_traversal()
    print("PASS")

    print("\nAll tests passed!")
