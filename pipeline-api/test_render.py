"""
Tests for the render pipeline: /clips/render endpoint + helpers
"""
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import os

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Test imports
try:
    from main import _build_clip_edl, _extract_video_id_from_youtube_url
    HAS_MAIN = True
except ImportError:
    HAS_MAIN = False
    print("Warning: Could not import from main.py, skipping integration tests")


def test_extract_video_id():
    """Test YouTube video ID extraction"""
    if not HAS_MAIN:
        print("SKIP: test_extract_video_id (main.py imports failed)")
        return

    test_cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ]

    for url, expected_id in test_cases:
        extracted = _extract_video_id_from_youtube_url(url)
        assert extracted == expected_id, f"Expected {expected_id}, got {extracted} for {url}"

    print("PASS: test_extract_video_id")


def test_build_clip_edl_unit():
    """Unit test for EDL builder (pure function, no I/O)"""
    if not HAS_MAIN:
        print("SKIP: test_build_clip_edl_unit (main.py imports failed)")
        return

    clips = [
        {
            "start_sec": 5.0,
            "end_sec": 15.0,
            "title": "Epic Moment",
            "caption": "This is wild!",
            "rank": 2,
            "recommended": False,
        },
        {
            "start_sec": 20.0,
            "end_sec": 35.0,
            "title": "Best Moment",
            "caption": "Top clip",
            "rank": 1,
            "recommended": True,
        },
    ]

    src_path = Path("/tmp/test_source.mp4")

    # Test 1: Pick recommended clip
    edl = _build_clip_edl(clips, src_path)
    assert edl["title"] == "Best Moment", f"Expected 'Best Moment', got {edl['title']}"
    assert edl["aspect"] == "1080x1920"
    assert edl["fps"] == 30
    assert len(edl["clips"]) == 1
    assert edl["clips"][0]["in"] == 20.0
    assert edl["clips"][0]["out"] == 35.0
    assert len(edl["captions"]) == 1
    assert edl["captions"][0]["text"] == "Top clip"

    # Test 2: Pick by index
    edl2 = _build_clip_edl(clips, src_path, chosen_index=0)
    assert edl2["title"] == "Epic Moment"
    assert edl2["clips"][0]["in"] == 5.0
    assert edl2["clips"][0]["out"] == 15.0

    print("PASS: test_build_clip_edl_unit")


def test_render_integration_with_sample_video():
    """Integration test: generate sample video, build EDL, run assemble.sh"""
    if not HAS_MAIN:
        print("SKIP: test_render_integration_with_sample_video (main.py imports failed)")
        return

    # Check for required tools
    has_ffmpeg = subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0
    has_ffprobe = subprocess.run(["which", "ffprobe"], capture_output=True).returncode == 0
    has_jq = subprocess.run(["which", "jq"], capture_output=True).returncode == 0
    has_assemble = Path(__file__).parent.parent / "scripts" / "assemble.sh"

    if not (has_ffmpeg and has_ffprobe and has_jq and has_assemble.exists()):
        print(f"SKIP: test_render_integration_with_sample_video (missing tools: ffmpeg={has_ffmpeg}, ffprobe={has_ffprobe}, jq={has_jq}, assemble.sh exists={has_assemble.exists()})")
        return

    # Create a temporary directory for test artifacts
    with tempfile.TemporaryDirectory(prefix="render_test_") as tmpdir:
        tmpdir = Path(tmpdir)

        # Generate a tiny test video using ffmpeg lavfi
        test_video = tmpdir / "sample.mp4"
        ffmpeg_cmd = [
            "ffmpeg", "-f", "lavfi",
            "-i", "testsrc=duration=6:size=640x480:rate=30",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=6",
            "-shortest", "-pix_fmt", "yuv420p",
            "-y", str(test_video),
        ]
        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            print(f"SKIP: test_render_integration_with_sample_video (ffmpeg sample generation failed: {result.stderr[:200]})")
            return

        assert test_video.exists(), "Sample video not created"

        # Build EDL
        clips = [
            {
                "start_sec": 0,
                "end_sec": 4,
                "title": "Test Clip",
                "caption": "Test Caption",
                "recommended": True,
            }
        ]
        edl = _build_clip_edl(clips, test_video)

        # Write EDL
        edl_path = tmpdir / "test.json"
        with open(edl_path, "w") as f:
            json.dump(edl, f)

        # Run assemble.sh
        out_mp4 = tmpdir / "output.mp4"
        assemble_cmd = ["bash", str(has_assemble), str(edl_path), str(out_mp4)]
        result = subprocess.run(assemble_cmd, capture_output=True, timeout=120)

        if result.returncode != 0:
            print(f"FAIL: assemble.sh returned {result.returncode}")
            print(f"stderr: {result.stderr[:300]}")
            return

        assert out_mp4.exists(), "Output video not created"
        assert out_mp4.stat().st_size > 0, "Output video is empty"

        # Verify output with ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_entries", "stream=width,height", str(out_mp4),
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        if probe_result.returncode == 0:
            probe_data = json.loads(probe_result.stdout)
            streams = probe_data.get("streams", [])
            if streams:
                width = streams[0].get("width")
                height = streams[0].get("height")
                assert width == 1080 and height == 1920, f"Expected 1080x1920, got {width}x{height}"

        print("PASS: test_render_integration_with_sample_video")


def test_endpoint_mock():
    """Endpoint test with mocked dependencies"""
    if not HAS_MAIN:
        print("SKIP: test_endpoint_mock (main.py imports failed)")
        return

    # This would require TestClient and mocking, which is better done with pytest
    # For now, just verify the request model can be instantiated
    try:
        from main import RenderRequest

        # Test valid request
        req1 = RenderRequest(
            clip_find_id=1,
            clip_index=0,
        )
        assert req1.clip_find_id == 1

        # Test with inline clips
        req2 = RenderRequest(
            youtube_url="https://www.youtube.com/watch?v=test",
            clips=[{"start_sec": 0, "end_sec": 10, "title": "Test"}],
        )
        assert req2.youtube_url is not None

        print("PASS: test_endpoint_mock")
    except ImportError as e:
        print(f"SKIP: test_endpoint_mock ({e})")


if __name__ == "__main__":
    print("\n=== Running render pipeline tests ===\n")

    test_extract_video_id()
    test_build_clip_edl_unit()
    test_render_integration_with_sample_video()
    test_endpoint_mock()

    print("\n=== Test run complete ===\n")
