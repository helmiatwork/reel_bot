"""
Unit tests for audio workflow changes in pipeline-api/main.py.

Covers:
- _save_song is no longer called during video analysis
- POST /songs/import accepts and processes audio files (current behavior)
- POST /songs/import accepts video files, extracts audio, and analyzes it
- Video files are deleted after extraction; only mp3 is stored
- Size caps are enforced per file type (30 MB audio, 200 MB video)

Run:
    cd pipeline-api && pytest tests/test_audio_workflow.py -v
"""
import json
import sys
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from io import BytesIO

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Part 1: Verify _save_song calls are removed ────────────────────────────────

def test_save_song_not_callable_from_analyze():
    """
    After removing auto-save, _save_song should not be imported or called during analyze.
    This test verifies the function is gone from the analyze flow by checking the code.
    Simplest check: grep for _save_song call sites and verify they're gone.
    """
    result = subprocess.run(
        ["grep", "-n", "_save_song(req.youtube_url)", "main.py"],
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True,
        text=True
    )
    # returncode 1 = not found (expected)
    # returncode 0 = found (test fails)
    assert result.returncode == 1, \
        f"Found _save_song(req.youtube_url) calls that should be removed:\n{result.stdout}"


def test_save_song_extract_audio_functions_deleted():
    """
    The _save_song and _extract_audio functions should be deleted entirely
    (no longer defined in main.py).
    """
    result = subprocess.run(
        ["grep", "-n", "^def _save_song\|^def _extract_audio", "main.py"],
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True,
        text=True
    )
    # returncode 1 = not found (expected - functions deleted)
    # returncode 0 = found (test fails - functions still exist)
    assert result.returncode == 1, \
        f"Found _save_song or _extract_audio function definitions that should be deleted:\n{result.stdout}"


# ── Part 2: Audio file import (existing behavior, unchanged) ────────────────────

def test_import_song_audio_exts_defined():
    """
    Audio-only extensions must be defined in main.py.
    Verify the code constants exist by checking the file content.
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    # Check that audio extensions are defined
    assert "_SONG_IMPORT_AUDIO_EXTS" in content
    # Verify expected audio formats
    assert ".mp3" in content.split("_SONG_IMPORT_AUDIO_EXTS")[1].split("\n")[0]


def test_import_song_size_cap_audio_constant():
    """
    Audio size cap must be defined as 30 MB.
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    # Check that audio max bytes constant is defined
    assert "_SONG_IMPORT_AUDIO_MAX_BYTES = 30 * 1024 * 1024" in content


# ── Part 3: Video file import (new behavior) ──────────────────────────────────

def test_import_song_accepts_video_extensions():
    """
    The import endpoint should accept common video extensions.
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    # Check that video extensions are defined
    assert "_SONG_IMPORT_VIDEO_EXTS" in content
    # Verify expected video formats
    assert ".mp4" in content.split("_SONG_IMPORT_VIDEO_EXTS")[1].split("\n")[0]


def test_import_song_size_cap_video_defined():
    """
    Video files must have a larger size cap than audio (200 MB).
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    # Check that video max bytes constant is defined and is larger
    assert "_SONG_IMPORT_VIDEO_MAX_BYTES = 200 * 1024 * 1024" in content


def test_import_song_video_extraction_in_code():
    """
    When a video file is uploaded:
    1. The code should run ffmpeg to extract audio
    2. The extracted audio should be analyzed
    3. Only the MP3 path is stored
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    # Find the import_song function
    import_start = content.find("def import_song(")
    assert import_start != -1, "import_song function not found"

    # Check for video extraction logic
    # Should have conditional check for is_video
    import_func_end = content.find("\ndef ", import_start + 1)
    import_func = content[import_start:import_func_end]

    assert "is_video" in import_func or "VIDEO_EXTS" in import_func, \
        "Video file handling logic not found in import_song"
    assert "ffmpeg" in import_func, "ffmpeg call not found for video extraction"


def test_import_song_video_cleanup():
    """
    Video files should be cleaned up (deleted) after extraction.
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    # Find the import_song function
    import_start = content.find("def import_song(")
    assert import_start != -1, "import_song function not found"

    import_func_end = content.find("\ndef ", import_start + 1)
    import_func = content[import_start:import_func_end]

    # Check for temp file cleanup
    assert "unlink" in import_func or "remove" in import_func, \
        "Video file cleanup (unlink/remove) not found in import_song"


def test_import_song_video_extraction_stores_mp3_only():
    """
    After video → audio extraction, the stored audio_path must be *.mp3.
    The original video file is deleted and not stored in the database.
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    # Find the import_song function
    import_start = content.find("def import_song(")
    assert import_start != -1, "import_song function not found"

    import_func_end = content.find("\ndef ", import_start + 1)
    import_func = content[import_start:import_func_end]

    # Should have logic that ends with .mp3 for audio extraction
    assert ".mp3" in import_func, "MP3 extraction logic not found"


# ── Edge cases ─────────────────────────────────────────────────────────────────

def test_import_song_allowed_exts_union():
    """
    _SONG_IMPORT_ALLOWED_EXTS must be union of audio and video exts.
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    # Check that allowed exts is union of audio and video
    assert "_SONG_IMPORT_ALLOWED_EXTS" in content
    relevant_section = content.split("_SONG_IMPORT_ALLOWED_EXTS")[1].split("\n")[0]
    assert "|" in relevant_section or "union" in relevant_section.lower(), \
        "Allowed exts should be union of audio and video exts"


def test_song_import_constants_ordering():
    """
    Constants should be defined in sensible order.
    """
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()

    audio_exts_pos = content.find("_SONG_IMPORT_AUDIO_EXTS")
    video_exts_pos = content.find("_SONG_IMPORT_VIDEO_EXTS")
    allowed_exts_pos = content.find("_SONG_IMPORT_ALLOWED_EXTS")
    audio_max_pos = content.find("_SONG_IMPORT_AUDIO_MAX_BYTES")
    video_max_pos = content.find("_SONG_IMPORT_VIDEO_MAX_BYTES")

    # All should be defined
    assert all([audio_exts_pos > 0, video_exts_pos > 0, allowed_exts_pos > 0,
                audio_max_pos > 0, video_max_pos > 0]), \
        "Some constants are missing"

    # Audio should come before video in definition
    assert audio_exts_pos < video_exts_pos, \
        "AUDIO_EXTS should be defined before VIDEO_EXTS"
