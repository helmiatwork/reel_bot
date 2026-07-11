"""
Tests for file:// URL extraction in _extract_video_id_from_youtube_url.

Tests that uploaded sources with file:// URLs properly extract the file_id
for use in data/frames/<file_id> directory resolution.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from main import _extract_video_id_from_youtube_url, app


# ── Unit tests ─────────────────────────────────────────────────────────────────

def test_extract_file_url_simple():
    """Test extraction from file://simple_id."""
    result = _extract_video_id_from_youtube_url("file://abc123")
    assert result == "abc123"


def test_extract_file_url_with_hyphens_underscores():
    """Test extraction from file:// with hyphens and underscores preserved."""
    result = _extract_video_id_from_youtube_url("file://abc-def_123")
    assert result == "abc-def_123"


def test_extract_file_url_sanitizes_special_chars():
    """Test that special characters are stripped from file_id."""
    result = _extract_video_id_from_youtube_url("file://abc@def#ghi")
    assert result == "abcdefghi"


def test_extract_file_url_sanitizes_slashes():
    """Test that file_ids with directory separators are sanitized."""
    result = _extract_video_id_from_youtube_url("file://abc/def/ghi")
    assert result == "abcdefghi"


def test_extract_file_url_mixed_sanitization():
    """Test extraction with mixed special characters and valid chars."""
    result = _extract_video_id_from_youtube_url("file://upload-id_@2024#test")
    assert result == "upload-id_2024test"


def test_extract_file_url_naked_raises():
    """Bare file:// (no id) must raise, not silently yield ''."""
    with pytest.raises(ValueError):
        _extract_video_id_from_youtube_url("file://")


def test_extract_file_url_all_special_chars_raises():
    """file:// whose id is entirely special chars sanitizes to '' -> raise."""
    with pytest.raises(ValueError):
        _extract_video_id_from_youtube_url("file://!@#$%^")


def test_extract_youtube_url_still_works():
    """Verify YouTube URL extraction still works after file:// addition."""
    result = _extract_video_id_from_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result == "dQw4w9WgXcQ"


def test_extract_tiktok_url_still_works():
    """Verify TikTok URL extraction still works after file:// addition."""
    result = _extract_video_id_from_youtube_url("https://www.tiktok.com/@user/video/1234567890")
    assert result == "tt_1234567890"


# ── Integration test with /sources/frames endpoint ──────────────────────────────

def test_sources_frames_endpoint_with_file_url():
    """Integration: /sources/frames endpoint resolves file:// URLs."""
    client = TestClient(app)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        file_id = "upload-123-test"
        frames_dir = tmpdir_path / "data" / "frames" / file_id
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Create a sample frame
        frame_file = frames_dir / "frame_000.jpg"
        frame_file.write_bytes(b"fake jpeg data")

        with patch("main._REPO_ROOT", tmpdir_path):
            resp = client.get(f"/sources/frames?youtube_url=file://{file_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert "frames" in data
            assert len(data["frames"]) == 1
            # The frame URL should reference the file_id
            assert file_id in data["frames"][0]


# ── Runnable as script ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            if "client" in t.__code__.co_varnames:
                # Skip fixture-based tests when running as script
                if t.__name__.startswith("test_sources_frames"):
                    t()
                    print(f"PASS {t.__name__}")
                else:
                    print(f"SKIP {t.__name__} (requires fixture setup)")
                continue
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
