"""
test_subtitles.py - Test suite for Subtitle Burn-in feature.

Covers:
- Acceptance Criteria 1: generate_srt and burn_subtitles exported functions
- Acceptance Criteria 2 & singleton: WhisperModel("tiny", device="cpu", compute_type="int8") cached
- Acceptance Criteria 3: generate_srt traps ALL exceptions, returns None
- Acceptance Criteria 4: pipeline.py falls back to final_with_audio.mp4 on subtitle failure
- Acceptance Criteria 5: burn_subtitles resolves libass-capable ffmpeg
- Acceptance Criteria 6: burn_subtitles cleans up partial file on failure
- Edge case 1: Silent video / no speech -> blank SRT -> burn_subtitles succeeds
- Edge case 2: Model load OOM/failure -> generate_srt returns None -> pipeline falls back
- Edge case 3: libass FFmpeg missing -> burn_subtitles catches error -> pipeline falls back
- Edge case 4: Special chars in path (colons, single quotes) properly escaped
- Edge case 5: burn_subtitles=False -> zero model loading, zero SRT gen, zero FFmpeg calls
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import module under test
import subtitles.subtitles as sub_mod
from subtitles.subtitles import burn_subtitles, generate_srt


# ============================================================================
# 1. Happy Path Tests
# ============================================================================

def test_generate_srt_happy_path(tmp_path):
    """Test standard SRT generation with timestamps and segment numbering."""
    audio_file = tmp_path / "speech.mp3"
    audio_file.write_text("dummy audio")
    srt_file = tmp_path / "captions.srt"

    mock_segments = [
        SimpleNamespace(start=0.0, end=2.5, text="  Welcome to Reelbot!  "),
        SimpleNamespace(start=2.5, end=5.85, text="Subtitle burn-in automated."),
    ]

    mock_model = MagicMock()
    mock_model.transcribe.return_value = (mock_segments, {})

    with patch.object(sub_mod, "get_whisper_model", return_value=mock_model):
        res = generate_srt(str(audio_file), srt_path=str(srt_file))

    assert res == str(srt_file)
    assert srt_file.exists()

    content = srt_file.read_text(encoding="utf-8")
    expected = (
        "1\n"
        "00:00:00,000 --> 00:00:02,500\n"
        "Welcome to Reelbot!\n\n"
        "2\n"
        "00:00:02,500 --> 00:00:05,850\n"
        "Subtitle burn-in automated.\n"
    )
    assert content == expected


def test_whisper_model_singleton(tmp_path):
    """Verify WhisperModel is loaded once and cached as a module-level singleton."""
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_text("dummy")

    with patch.object(sub_mod, "_whisper_model", None), \
         patch("faster_whisper.WhisperModel") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.transcribe.return_value = ([], {})
        mock_cls.return_value = mock_instance

        # First call: instantiates model
        res1 = generate_srt(str(audio_file))
        assert res1 is not None
        assert mock_cls.call_count == 1
        mock_cls.assert_called_once_with("tiny", device="cpu", compute_type="int8")

        # Second call: reuses cached singleton
        res2 = generate_srt(str(audio_file))
        assert res2 is not None
        assert mock_cls.call_count == 1  # Not called again


def test_burn_subtitles_happy_path(tmp_path):
    """Test burn_subtitles executes correct FFmpeg command without audio re-encoding."""
    video_file = tmp_path / "input.mp4"
    video_file.write_text("dummy video")
    srt_file = tmp_path / "captions.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    out_file = tmp_path / "output.mp4"

    def fake_subprocess_run(cmd, **kwargs):
        # Simulate FFmpeg producing output file
        Path(cmd[-1]).write_text("subtitled video content")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_subprocess_run) as mock_run:
        result = burn_subtitles(str(video_file), str(srt_file), str(out_file))

    assert result == str(out_file)
    assert out_file.exists()

    # Verify FFmpeg command flags
    called_cmd = mock_run.call_args[0][0]
    assert "-i" in called_cmd
    assert str(video_file) in called_cmd
    assert "-c:a" in called_cmd
    assert called_cmd[called_cmd.index("-c:a") + 1] == "copy"
    assert "-c:v" in called_cmd
    assert called_cmd[called_cmd.index("-c:v") + 1] == "libx264"
    assert "-preset" in called_cmd
    assert called_cmd[called_cmd.index("-preset") + 1] == "fast"
    assert "-crf" in called_cmd
    assert called_cmd[called_cmd.index("-crf") + 1] == "23"
    assert called_cmd[-1] == str(out_file)

    # Verify style string in -vf
    vf_arg = called_cmd[called_cmd.index("-vf") + 1]
    assert "force_style='Bold=1,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,BorderStyle=1,Alignment=2,MarginV=20'" in vf_arg


# ============================================================================
# 2. Edge Case Tests
# ============================================================================

def test_edge_case_silent_video_no_speech(tmp_path):
    """Edge Case: Silent video / no speech -> blank SRT -> FFmpeg succeeds, no visible text."""
    video_file = tmp_path / "silent.mp4"
    video_file.write_text("dummy silent video")
    srt_file = tmp_path / "captions.srt"
    out_file = tmp_path / "subtitled.mp4"

    mock_model = MagicMock()
    # Empty segments
    mock_model.transcribe.return_value = (iter([]), {})

    with patch.object(sub_mod, "get_whisper_model", return_value=mock_model):
        res = generate_srt(str(video_file), srt_path=str(srt_file))

    assert res == str(srt_file)
    assert srt_file.exists()
    assert srt_file.read_text(encoding="utf-8") == ""

    # Burning blank SRT succeeds
    def fake_subprocess_run(cmd, **kwargs):
        Path(cmd[-1]).write_text("subtitled video with no visible captions")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        burn_res = burn_subtitles(str(video_file), str(srt_file), str(out_file))

    assert burn_res == str(out_file)
    assert out_file.exists()


def test_edge_case_model_load_oom_generate_srt_returns_none(tmp_path):
    """Edge Case: Model load OOM/failure -> generate_srt returns None (never raises)."""
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_text("dummy")

    with patch.object(sub_mod, "get_whisper_model", side_effect=RuntimeError("CUDA out of memory")):
        res = generate_srt(str(audio_file))
        assert res is None

    with patch.object(sub_mod, "get_whisper_model", side_effect=MemoryError("OOM")):
        res = generate_srt(str(audio_file))
        assert res is None

    with patch.object(sub_mod, "get_whisper_model", side_effect=Exception("Unexpected whisper failure")):
        res = generate_srt(str(audio_file))
        assert res is None


def test_edge_case_libass_ffmpeg_missing_catches_error(tmp_path):
    """Edge Case: libass FFmpeg missing or failure -> burn_subtitles catches error, returns None."""
    video_file = tmp_path / "video.mp4"
    video_file.write_text("dummy")
    srt_file = tmp_path / "captions.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n")
    out_file = tmp_path / "out.mp4"

    # 1. FFmpeg returns error (e.g. libass filter missing)
    failed_proc = MagicMock(returncode=1, stderr="No such filter: 'subtitles'")
    with patch("subprocess.run", return_value=failed_proc):
        res = burn_subtitles(str(video_file), str(srt_file), str(out_file))
        assert res is None

    # 2. FFmpeg binary not found / FileNotFoundError
    with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg not found")):
        res = burn_subtitles(str(video_file), str(srt_file), str(out_file))
        assert res is None


def test_edge_case_special_chars_in_path_escaped(tmp_path):
    """Edge Case: Special chars in path (single quotes, colons) -> properly escaped in FFmpeg filter."""
    special_dir = tmp_path / "path'with'quote:and:colon"
    special_dir.mkdir(parents=True)
    video_file = special_dir / "video'1:test.mp4"
    video_file.write_text("dummy")
    srt_file = special_dir / "sub'titles:file.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n")
    out_file = special_dir / "output.mp4"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        burn_subtitles(str(video_file), str(srt_file), str(out_file))

    called_cmd = mock_run.call_args[0][0]
    vf_arg = called_cmd[called_cmd.index("-vf") + 1]

    # Verify single quotes escaped to \' and colons escaped to \:
    expected_path_esc = str(Path(srt_file).absolute()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    assert f"subtitles='{expected_path_esc}'" in vf_arg


def test_edge_case_partial_file_cleaned_up_on_failure(tmp_path):
    """Edge Case: Mid-process failure cleans up corrupt/partial output file."""
    video_file = tmp_path / "video.mp4"
    video_file.write_text("dummy")
    srt_file = tmp_path / "captions.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n")
    out_file = tmp_path / "corrupt_partial.mp4"

    def failing_subprocess(cmd, **kwargs):
        # Create a partial corrupt file before failing
        Path(cmd[-1]).write_text("corrupted partial content")
        return MagicMock(returncode=137, stderr="Killed / OOM")

    with patch("subprocess.run", side_effect=failing_subprocess):
        res = burn_subtitles(str(video_file), str(srt_file), str(out_file))

    assert res is None
    assert not out_file.exists(), "Corrupt partial output file must be deleted on failure"


def test_generate_srt_nonexistent_audio_returns_none(tmp_path):
    """Verify generate_srt gracefully returns None if input file does not exist."""
    res = generate_srt(str(tmp_path / "nonexistent.mp3"))
    assert res is None


def test_generate_srt_skips_empty_text_segments(tmp_path):
    """Verify segments with empty text or whitespace only are skipped."""
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_text("dummy")
    srt_file = tmp_path / "captions.srt"

    mock_segments = [
        SimpleNamespace(start=0.0, end=1.0, text="   "),
        SimpleNamespace(start=1.0, end=2.0, text="Valid caption"),
        SimpleNamespace(start=2.0, end=3.0, text=""),
    ]
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (mock_segments, {})

    with patch.object(sub_mod, "get_whisper_model", return_value=mock_model):
        res = generate_srt(str(audio_file), srt_path=str(srt_file))

    assert res == str(srt_file)
    content = srt_file.read_text(encoding="utf-8")
    assert "Valid caption" in content
    assert "1\n00:00:01,000 --> 00:00:02,000\nValid caption\n" in content
    assert "2\n" not in content


def test_generate_srt_default_srt_path(tmp_path):
    """Verify generate_srt defaults srt_path to source_path.with_suffix('.srt')."""
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_text("dummy")

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], {})

    with patch.object(sub_mod, "get_whisper_model", return_value=mock_model):
        res = generate_srt(str(audio_file))

    expected = str(tmp_path / "audio.srt")
    assert res == expected
    assert Path(expected).exists()


def test_burn_subtitles_missing_input_video(tmp_path):
    """Verify burn_subtitles returns None if video_path does not exist."""
    srt_file = tmp_path / "captions.srt"
    srt_file.write_text("dummy")
    res = burn_subtitles(str(tmp_path / "nonexistent.mp4"), str(srt_file))
    assert res is None


def test_burn_subtitles_missing_srt_file(tmp_path):
    """Verify burn_subtitles returns None if srt_path does not exist."""
    video_file = tmp_path / "video.mp4"
    video_file.write_text("dummy")
    res = burn_subtitles(str(video_file), str(tmp_path / "nonexistent.srt"))
    assert res is None


def test_burn_subtitles_default_output_path(tmp_path):
    """Verify burn_subtitles defaults output_path to {stem}_subtitled{suffix}."""
    video_file = tmp_path / "video.mp4"
    video_file.write_text("dummy")
    srt_file = tmp_path / "captions.srt"
    srt_file.write_text("dummy")

    expected_out = str(tmp_path / "video_subtitled.mp4")

    def fake_subprocess_run(cmd, **kwargs):
        Path(cmd[-1]).write_text("output video")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        res = burn_subtitles(str(video_file), str(srt_file))

    assert res == expected_out
    assert Path(expected_out).exists()


# ============================================================================
# 3. Pipeline Integration Tests
# ============================================================================

def test_pipeline_burn_subtitles_happy_path(tmp_path, monkeypatch):
    """Verify pipeline integrates subtitle step and passes subtitled video to QC."""
    from pipeline import run_complete_pipeline

    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    work_dir = tmp_path / "test_run_sub_ok"
    work_dir.mkdir(parents=True)
    raw_video = str(work_dir / "arcreel_raw.mp4")
    Path(raw_video).write_text("raw video")

    script = {"title": "Test Subtitle Pipeline", "beats": []}

    with patch("pipeline.notify_telegram"), \
         patch("pipeline._download_arcreel_video", return_value=raw_video), \
         patch("pipeline.generate_full_voiceover", return_value=str(work_dir / "vo.mp3")), \
         patch("pipeline.merge_with_video") as mock_merge, \
         patch("pipeline.generate_srt") as mock_gen_srt, \
         patch("pipeline.burn_subtitles") as mock_burn_sub, \
         patch("pipeline.quality_check_video") as mock_qc:

        def fake_merge(r, vo, final_v, bg_music=None):
            Path(final_v).write_text("final with audio")
        mock_merge.side_effect = fake_merge

        subtitled_target = str(work_dir / "final_with_subtitles.mp4")
        Path(subtitled_target).write_text("subtitled video")

        mock_gen_srt.return_value = str(work_dir / "subtitles.srt")
        mock_burn_sub.return_value = subtitled_target
        mock_qc.return_value = {"recommendation": "pass", "overall_score": 90}

        result = run_complete_pipeline(
            run_id="test_run_sub_ok",
            script=script,
            arcreel_project_id="proj_123",
            auto_publish=False,
            burn_subtitles=True
        )

    mock_gen_srt.assert_called_once()
    mock_burn_sub.assert_called_once()
    assert result["steps"]["subtitles"]["status"] == "ok"
    assert result["steps"]["subtitles"]["path"] == subtitled_target

    # QC received the subtitled video
    qc_video_arg = mock_qc.call_args[0][0]
    assert qc_video_arg == subtitled_target


def test_pipeline_burn_subtitles_failure_falls_back_to_unsubtitled(tmp_path, monkeypatch):
    """Verify pipeline falls back to final_with_audio.mp4 when subtitle step fails."""
    from pipeline import run_complete_pipeline

    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    work_dir = tmp_path / "test_run_sub_fail"
    work_dir.mkdir(parents=True)
    raw_video = str(work_dir / "arcreel_raw.mp4")
    Path(raw_video).write_text("raw video")

    script = {"title": "Test Fallback Pipeline", "beats": []}

    with patch("pipeline.notify_telegram"), \
         patch("pipeline._download_arcreel_video", return_value=raw_video), \
         patch("pipeline.generate_full_voiceover", return_value=str(work_dir / "vo.mp3")), \
         patch("pipeline.merge_with_video") as mock_merge, \
         patch("pipeline.generate_srt", return_value=None), \
         patch("pipeline.burn_subtitles") as mock_burn_sub, \
         patch("pipeline.quality_check_video") as mock_qc:

        def fake_merge(r, vo, final_v, bg_music=None):
            Path(final_v).write_text("final with audio")
        mock_merge.side_effect = fake_merge

        mock_qc.return_value = {"recommendation": "pass", "overall_score": 85}

        result = run_complete_pipeline(
            run_id="test_run_sub_fail",
            script=script,
            arcreel_project_id="proj_123",
            auto_publish=False,
            burn_subtitles=True
        )

    # burn_subtitles shouldn't be called if generate_srt returned None
    mock_burn_sub.assert_not_called()

    # Step marked as failed with fallback
    assert result["steps"]["subtitles"]["status"] == "failed"
    expected_fallback = str(work_dir / "final_with_audio.mp4")
    assert result["steps"]["subtitles"]["fallback"] == expected_fallback

    # QC received unsubtitled final_with_audio.mp4
    qc_video_arg = mock_qc.call_args[0][0]
    assert qc_video_arg == expected_fallback


def test_pipeline_burn_subtitles_false_zero_calls(tmp_path, monkeypatch):
    """Edge Case: burn_subtitles=False -> zero model loading, zero SRT gen, zero FFmpeg calls."""
    from pipeline import run_complete_pipeline

    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    work_dir = tmp_path / "test_run_sub_false"
    work_dir.mkdir(parents=True)
    raw_video = str(work_dir / "arcreel_raw.mp4")
    Path(raw_video).write_text("raw video")

    script = {"title": "Test Subtitle False Pipeline", "beats": []}

    with patch("pipeline.notify_telegram"), \
         patch("pipeline._download_arcreel_video", return_value=raw_video), \
         patch("pipeline.generate_full_voiceover", return_value=str(work_dir / "vo.mp3")), \
         patch("pipeline.merge_with_video") as mock_merge, \
         patch("pipeline.generate_srt") as mock_gen_srt, \
         patch("pipeline.burn_subtitles") as mock_burn_sub, \
         patch("subtitles.subtitles.get_whisper_model") as mock_get_model, \
         patch("pipeline.quality_check_video") as mock_qc:

        def fake_merge(r, vo, final_v, bg_music=None):
            Path(final_v).write_text("final with audio")
        mock_merge.side_effect = fake_merge

        mock_qc.return_value = {"recommendation": "pass", "overall_score": 85}

        result = run_complete_pipeline(
            run_id="test_run_sub_false",
            script=script,
            arcreel_project_id="proj_123",
            auto_publish=False,
            burn_subtitles=False  # Disabled!
        )

    # Asserts zero model loading, zero SRT gen, zero FFmpeg calls
    mock_gen_srt.assert_not_called()
    mock_burn_sub.assert_not_called()
    mock_get_model.assert_not_called()

    # QC received unsubtitled final_with_audio.mp4
    expected_video = str(work_dir / "final_with_audio.mp4")
    qc_video_arg = mock_qc.call_args[0][0]
    assert qc_video_arg == expected_video


def test_subtitles_module_does_not_import_pipeline():
    """Architecture Constraint: subtitles.py MUST NOT import pipeline.py."""
    with open(_REPO_ROOT / "subtitles" / "subtitles.py") as f:
        content = f.read()

    assert "import pipeline" not in content
    assert "from pipeline" not in content
