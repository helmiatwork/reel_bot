"""
subtitles/subtitles.py - Speech transcription and subtitle burn-in.

Provides:
- generate_srt: Transcribes audio/video to SRT using faster-whisper singleton
- burn_subtitles: Burns SRT subtitles into video using libass-capable FFmpeg
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

__all__ = ["generate_srt", "burn_subtitles", "get_whisper_model"]

# Module-level singleton for WhisperModel
_whisper_model = None

# FFmpeg resolution logic: prefer keg-only ffmpeg-full with libass/subtitles, fallback system ffmpeg
_ffmpeg_full_bin = sorted(
    Path("/opt/homebrew/Cellar/ffmpeg-full").glob("*/bin/ffmpeg")
) if Path("/opt/homebrew/Cellar/ffmpeg-full").exists() else []
_FFMPEG_SUBTITLES_BIN = str(_ffmpeg_full_bin[-1]) if _ffmpeg_full_bin else "ffmpeg"


def get_whisper_model():
    """
    Module-level singleton for WhisperModel: loads 'tiny' model once and caches it.
    Traps model loading errors at the callsite.
    """
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _whisper_model


def _fmt_ts(secs: float) -> str:
    """Format seconds into standard SRT timestamp hh:mm:ss,ms."""
    total_ms = int(round(secs * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _cleanup_file(path: Union[str, Path]) -> None:
    """Safely remove a file if it exists."""
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.warning(f"[subtitles] failed to cleanup {path}: {e}")


def generate_srt(
    audio_or_video_path: Union[str, Path],
    srt_path: Optional[Union[str, Path]] = None
) -> Optional[str]:
    """
    Transcribe speech from audio or video using faster-whisper and write to SRT format.

    - Uses cached WhisperModel singleton.
    - If no speech / silent video: generates an empty/blank SRT file and succeeds.
    - Traps ALL exceptions, logs error, and returns None on failure — never raises.

    Returns:
        str: Absolute or given path to generated SRT file on success, None on failure.
    """
    try:
        source_path = Path(audio_or_video_path)
        if not source_path.exists():
            logger.error(f"[generate_srt] source file does not exist: {audio_or_video_path}")
            return None

        if srt_path is None:
            srt_target = source_path.with_suffix(".srt")
        else:
            srt_target = Path(srt_path)

        model = get_whisper_model()
        segments_iter, _info = model.transcribe(str(source_path), word_timestamps=False)

        lines: list[str] = []
        idx = 1
        for seg in segments_iter:
            text = getattr(seg, "text", "").strip()
            if not text:
                continue
            lines += [str(idx), f"{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}", text, ""]
            idx += 1

        srt_target.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(lines)
        if content and not content.endswith("\n"):
            content += "\n"

        srt_target.write_text(content, encoding="utf-8")
        return str(srt_target)

    except Exception as e:
        logger.error(f"[generate_srt] transcription failed: {e}")
        return None


def burn_subtitles(
    video_path: Union[str, Path],
    srt_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None
) -> Optional[str]:
    """
    Burn subtitles into video using libass-capable FFmpeg with styled lower-third text.
    Maintains audio quality by stream-copying audio (-c:a copy).

    - Resolves libass-capable FFmpeg (prefers ffmpeg-full, fallbacks system ffmpeg).
    - Escapes special characters (single quotes, colons) in SRT path for filter syntax.
    - Cleans up partial/corrupt output file on any mid-process error.
    - Traps errors and returns None on failure — never raises.

    Returns:
        str: Path to subtitled video on success, None on failure.
    """
    input_video = Path(video_path)
    srt_file = Path(srt_path)

    if output_path is None:
        target_output = input_video.parent / f"{input_video.stem}_subtitled{input_video.suffix}"
    else:
        target_output = Path(output_path)

    try:
        if not input_video.exists():
            logger.error(f"[burn_subtitles] video not found: {video_path}")
            return None

        if not srt_file.exists():
            logger.error(f"[burn_subtitles] srt file not found: {srt_path}")
            return None

        # Path escaping for FFmpeg filter syntax
        escaped_srt = str(srt_file.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        style_str = (
            "Bold=1,FontSize=16,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=2,BorderStyle=1,"
            "Alignment=2,MarginV=20"
        )

        ffmpeg_bin = _FFMPEG_SUBTITLES_BIN
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(input_video),
            "-vf", f"subtitles='{escaped_srt}':force_style='{style_str}'",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "copy",  # CRITICAL: no audio re-encode
            str(target_output)
        ]

        target_output.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            logger.error(f"[burn_subtitles] ffmpeg failed (exit {proc.returncode}): {proc.stderr}")
            _cleanup_file(target_output)
            return None

        if not target_output.exists():
            logger.error(f"[burn_subtitles] ffmpeg reported success but output missing: {target_output}")
            return None

        return str(target_output)

    except Exception as e:
        logger.error(f"[burn_subtitles] error: {e}")
        _cleanup_file(target_output)
        return None
