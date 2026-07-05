"""
Tests for the clip render pipeline (_build_clip_edl + assemble.sh integration).

Runnable two ways:
  - pytest test_render.py
  - python3 test_render.py        (assert-based fallback, no pytest needed)

Unit tests exercise the pure EDL builder against the real implementation.
The integration test runs the actual scripts/assemble.sh with an ffmpeg-generated
sample video and asserts a real 1080x1920 mp4 is produced; it skips (does not fail)
if ffmpeg/ffprobe are unavailable.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from main import _build_clip_edl

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ASSEMBLE = _REPO_ROOT / "scripts" / "assemble.sh"

_SAMPLE_CLIPS = [
    {"start_sec": 5, "end_sec": 20, "title": "first", "caption": "hook one", "rank": 2},
    {"start_sec": 120, "end_sec": 165, "title": "best", "caption": "hook two",
     "rank": 1, "recommended": True},
]


def test_edl_basic_shape():
    edl = _build_clip_edl(_SAMPLE_CLIPS, Path("/tmp/src.mp4"))
    assert edl["aspect"] == "1080x1920"
    assert edl["fps"] == 30
    assert isinstance(edl["clips"], list) and len(edl["clips"]) == 1
    clip = edl["clips"][0]
    # src is a string absolute path; in/out are ints
    assert isinstance(clip["src"], str)
    assert clip["src"].endswith("src.mp4")
    assert isinstance(clip["in"], int) and isinstance(clip["out"], int)


def test_edl_picks_recommended():
    edl = _build_clip_edl(_SAMPLE_CLIPS, Path("/tmp/src.mp4"))
    # recommended clip is the second one (120..165)
    assert edl["clips"][0]["in"] == 120
    assert edl["clips"][0]["out"] == 165
    assert edl["title"] == "best"


def test_edl_chosen_index_override():
    edl = _build_clip_edl(_SAMPLE_CLIPS, Path("/tmp/src.mp4"), chosen_index=0)
    assert edl["clips"][0]["in"] == 5
    assert edl["clips"][0]["out"] == 20
    assert edl["title"] == "first"


def test_edl_fallback_to_first_when_none_recommended():
    clips = [{"start_sec": 1, "end_sec": 9, "title": "only"}]
    edl = _build_clip_edl(clips, Path("/tmp/src.mp4"))
    assert edl["clips"][0]["in"] == 1
    assert edl["title"] == "only"


def test_edl_caption_present_and_absent():
    with_cap = _build_clip_edl(_SAMPLE_CLIPS, Path("/tmp/src.mp4"))
    assert len(with_cap["captions"]) == 1
    assert with_cap["captions"][0]["text"] == "hook two"
    no_cap = _build_clip_edl(
        [{"start_sec": 0, "end_sec": 5, "title": "x", "recommended": True}],
        Path("/tmp/src.mp4"),
    )
    assert no_cap["captions"] == []


def test_assemble_renders_portrait_mp4():
    """Integration: real assemble.sh render. Skips if ffmpeg/ffprobe missing."""
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("SKIP test_assemble_renders_portrait_mp4 (ffmpeg/ffprobe not available)")
        return
    if not _ASSEMBLE.exists():
        print(f"SKIP test_assemble_renders_portrait_mp4 (missing {_ASSEMBLE})")
        return

    tmp = Path(tempfile.mkdtemp())
    try:
        sample = tmp / "sample.mp4"
        gen = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=640x480:rate=30",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
             "-shortest", "-pix_fmt", "yuv420p", str(sample)],
            capture_output=True, timeout=60,
        )
        assert gen.returncode == 0, gen.stderr[-300:]

        edl = _build_clip_edl(
            [{"start_sec": 0, "end_sec": 4, "title": "t", "caption": "c", "recommended": True}],
            sample,
        )
        edl_path = tmp / "edl.json"
        edl_path.write_text(json.dumps(edl))
        out = tmp / "final.mp4"

        render = subprocess.run(
            ["bash", str(_ASSEMBLE), str(edl_path), str(out)],
            capture_output=True, text=True, timeout=120,
        )
        assert render.returncode == 0, render.stderr[-400:]
        assert out.exists() and out.stat().st_size > 0

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True, timeout=30,
        )
        w, h = probe.stdout.strip().split(",")
        assert int(w) == 1080 and int(h) == 1920, f"got {w}x{h}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
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
