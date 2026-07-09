"""
Unit tests for Xiaohongshu/RedNote ingest helpers.

Run:
    cd pipeline-api && pytest tests/test_xhs.py -v
    # or without pytest:
    cd pipeline-api && python tests/test_xhs.py

Integration test (real network + cookies) is marked skip when no cookies file exists.
"""
import os
import sys
import subprocess
from pathlib import Path

import pytest

# Ensure pipeline-api/main.py is importable from the tests/ subdir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import _detect_platform, _extract_video_id_from_youtube_url

PROVEN_NOTE_URL = (
    "https://www.rednote.com/explore/6a2b6cd3000000001700a584"
    "?xsec_token=ABXotqMyuSFwlQlUr7fJ2-h3Wb2Q7WN9T3F2sPyVUjF1M=&xsec_source=pc_search"
)
COOKIES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "cookies" / "xiaohongshu.txt"


# ── Unit tests (pure functions, no network) ───────────────────────────────────

class TestDetectPlatform:
    def test_xiaohongshu_dot_com(self):
        assert _detect_platform("https://www.xiaohongshu.com/explore/abc123") == "xiaohongshu"

    def test_rednote_dot_com(self):
        assert _detect_platform("https://www.rednote.com/explore/6a2b6cd3000000001700a584") == "xiaohongshu"

    def test_xhslink(self):
        assert _detect_platform("https://xhslink.com/a/abc") == "xiaohongshu"

    def test_xhscdn(self):
        assert _detect_platform("https://sns-video-bd.xhscdn.com/stream/110/video.mp4") == "xiaohongshu"

    def test_rednotecdn(self):
        assert _detect_platform("https://rednotecdn.com/stream/video.mp4") == "xiaohongshu"

    def test_youtube(self):
        assert _detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

    def test_tiktok(self):
        assert _detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"

    def test_instagram(self):
        assert _detect_platform("https://www.instagram.com/reel/abc123/") == "instagram"

    def test_unknown(self):
        assert _detect_platform("https://example.com/video") == "unknown"


class TestExtractVideoId:
    def test_rednote_explore(self):
        url = "https://www.rednote.com/explore/6a2b6cd3000000001700a584?xsec_token=ABC&xsec_source=pc_search"
        vid = _extract_video_id_from_youtube_url(url)
        assert vid == "xhs_6a2b6cd3000000001700a584", f"got {vid!r}"

    def test_xiaohongshu_explore(self):
        url = "https://www.xiaohongshu.com/explore/6a2b6cd3000000001700a584"
        vid = _extract_video_id_from_youtube_url(url)
        assert vid == "xhs_6a2b6cd3000000001700a584", f"got {vid!r}"

    def test_xiaohongshu_discovery_item(self):
        url = "https://www.xiaohongshu.com/discovery/item/6a2b6cd3000000001700a584"
        vid = _extract_video_id_from_youtube_url(url)
        assert vid == "xhs_6a2b6cd3000000001700a584", f"got {vid!r}"

    def test_id_is_sanitized(self):
        url = "https://www.rednote.com/explore/6a2b6cd3000000001700a584"
        vid = _extract_video_id_from_youtube_url(url)
        # Only alphanumeric, underscore, hyphen allowed
        import re
        assert re.fullmatch(r"[a-zA-Z0-9_-]+", vid), f"unsanitary chars in {vid!r}"

    def test_youtube_id_unchanged(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert _extract_video_id_from_youtube_url(url) == "dQw4w9WgXcQ"


# ── Integration test (real network, skipped without cookies) ──────────────────

@pytest.mark.skipif(
    not COOKIES_FILE.exists(),
    reason=f"XHS cookies not found at {COOKIES_FILE}"
)
def test_xhs_resolve_and_download(tmp_path):
    """Full scrape + CDN download of the proven XHS note. Verifies video is valid."""
    from main import _xhs_resolve_video, _download_direct

    cdn_url, title = _xhs_resolve_video(PROVEN_NOTE_URL)
    assert cdn_url.startswith("http"), f"expected http URL, got {cdn_url!r}"
    assert "xhscdn" in cdn_url or "xhsvideo" in cdn_url or cdn_url.endswith(".mp4"), \
        f"URL doesn't look like an XHS CDN URL: {cdn_url!r}"

    dest = tmp_path / "xhs_test.mp4"
    _download_direct(cdn_url, dest)
    assert dest.exists(), "file not written"
    assert dest.stat().st_size > 100_000, f"file too small: {dest.stat().st_size} bytes"

    # ffprobe: confirm it's a valid video with width > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width", "-of", "csv=p=0", str(dest)],
        capture_output=True, text=True, timeout=15
    )
    assert probe.returncode == 0, f"ffprobe failed: {probe.stderr}"
    width = int(probe.stdout.strip().split("\n")[0])
    assert width > 0, f"video width is 0 — not a valid video"
    print(f"\n[integration] cdn={cdn_url[:60]}... title={title!r} size={dest.stat().st_size} width={width}")


if __name__ == "__main__":
    # Plain-Python fallback (no pytest needed)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    # Also collect class-based tests
    import inspect
    for name, obj in sorted(globals().items()):
        if inspect.isclass(obj) and name.startswith("Test"):
            for mname, meth in inspect.getmembers(obj, predicate=inspect.isfunction):
                if mname.startswith("test_"):
                    tests.append(meth.__get__(obj(), obj))

    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {getattr(t, '__name__', str(t))}")
        except Exception as e:
            failed += 1
            print(f"FAIL {getattr(t, '__name__', str(t))}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
