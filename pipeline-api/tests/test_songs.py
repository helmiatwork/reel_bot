"""
Unit tests for music-import helpers in pipeline-api/main.py.

Covers:
- _analyze_audio: returns numeric bpm/key/energy/duration on a synth wav
- _analyze_audio: is non-fatal (returns Nones on a bad path)
- _suggest_music_tags: returns a list (seam stub)
- tags JSON round-trip (serialize/deserialize as used by import + PATCH)

Run:
    cd pipeline-api && pytest tests/test_songs.py -v
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import _analyze_audio, _suggest_music_tags  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_beat_wav(path: Path, bpm: float = 120.0, duration_s: float = 4.0,
                    sample_rate: int = 22050) -> None:
    """
    Write a 16-bit PCM WAV with periodic noise bursts at the given BPM.
    Noise bursts give librosa's beat tracker actual onset events to latch onto.
    """
    import numpy as np
    import wave

    n = int(sample_rate * duration_s)
    y = np.zeros(n, dtype=np.float32)

    hop = int(sample_rate * 60.0 / bpm)       # samples between beats
    burst_len = int(sample_rate * 0.04)        # 40ms burst per beat

    rng = np.random.default_rng(42)            # deterministic
    for start in range(0, n, hop):
        end = min(start + burst_len, n)
        noise = rng.normal(0, 0.5, end - start).astype(np.float32)
        decay = np.linspace(1.0, 0.0, end - start)
        y[start:end] += noise * decay

    # Normalize
    mx = float(np.abs(y).max())
    if mx > 0:
        y /= mx

    samples = (y * 32767).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_analyze_audio_objective_fields():
    """_analyze_audio returns numeric bpm, key, energy, duration on a rhythmic WAV."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = Path(f.name)
    try:
        _write_beat_wav(wav_path, bpm=120.0, duration_s=4.0)
        result = _analyze_audio(str(wav_path))

        assert isinstance(result["bpm"], float), f"expected float bpm, got {result['bpm']!r}"
        assert result["bpm"] > 0, "bpm must be positive for a rhythmic signal"

        assert isinstance(result["music_key"], str), f"expected str key, got {result['music_key']!r}"
        assert result["music_key"] in [
            "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"
        ], f"key not a standard note: {result['music_key']!r}"

        assert isinstance(result["energy"], float), f"expected float energy, got {result['energy']!r}"
        assert result["energy"] > 0, "energy must be positive for a non-silent signal"

        assert isinstance(result["duration_sec"], float), f"expected float duration, got {result['duration_sec']!r}"
        assert 3.5 <= result["duration_sec"] <= 4.5, f"duration out of range: {result['duration_sec']}"
    finally:
        wav_path.unlink(missing_ok=True)


def test_analyze_audio_no_raise_on_bad_path():
    """_analyze_audio returns a dict with Nones and does NOT raise on a missing file."""
    result = _analyze_audio("/nonexistent/path/audio.wav")

    assert isinstance(result, dict), "must return a dict"
    # All four fields must be present (may be None on error)
    for key in ("bpm", "music_key", "energy", "duration_sec"):
        assert key in result, f"missing key {key!r} in result"


def test_analyze_audio_no_raise_on_empty_file():
    """_analyze_audio returns dict with Nones on a zero-byte file (no crash)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        bad_path = Path(f.name)
    try:
        bad_path.write_bytes(b"")
        result = _analyze_audio(str(bad_path))
        assert isinstance(result, dict)
    finally:
        bad_path.unlink(missing_ok=True)


def test_suggest_music_tags_returns_list_when_key_unset(monkeypatch):
    """_suggest_music_tags returns [] and does not raise when CLIPROXY_KEY is unset."""
    monkeypatch.delenv("CLIPROXY_KEY", raising=False)
    result = _suggest_music_tags("/any/path.mp3")
    assert isinstance(result, list), f"expected list, got {type(result)}"
    assert result == [], "should be empty list when key unset"


def test_suggest_music_tags_returns_list_when_unreachable(monkeypatch):
    """_suggest_music_tags returns [] when the cliproxy endpoint is unreachable."""
    monkeypatch.setenv("CLIPROXY_KEY", "test-key-does-not-matter")
    monkeypatch.setenv("CLIPROXY_URL", "http://127.0.0.1:1")  # port 1 = unreachable
    # Needs a real (but short) audio file to get past ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = Path(f.name)
    try:
        _write_beat_wav(wav_path, duration_s=1.0)
        result = _suggest_music_tags(str(wav_path))
        assert isinstance(result, list)
        assert result == []
    finally:
        wav_path.unlink(missing_ok=True)


# ── Tags JSON round-trip ──────────────────────────────────────────────────────

def test_tags_json_roundtrip():
    """Tags serialize to TEXT and deserialize back to list identically."""
    tags = ["jazz", "piano", "chill"]
    serialized = json.dumps(tags, ensure_ascii=False)
    assert json.loads(serialized) == tags


def test_tags_comma_separated_parse():
    """Import endpoint accepts comma-separated tags and converts to list."""
    raw = "jazz, piano, saxophone"
    parsed = [t.strip() for t in raw.split(",") if t.strip()]
    assert parsed == ["jazz", "piano", "saxophone"]


def test_tags_json_array_parse():
    """Import endpoint accepts JSON array string for tags."""
    raw = '["jazz","piano"]'
    parsed = json.loads(raw) if raw.strip().startswith("[") else []
    assert parsed == ["jazz", "piano"]


def test_tags_dedup_merge():
    """User tags and auto-suggested tags are merged without duplicates."""
    user_tags = ["jazz", "piano"]
    auto_tags = ["piano", "ambient"]  # 'piano' is duplicate
    merged = list({*user_tags, *auto_tags})
    assert len(merged) == 3
    assert set(merged) == {"jazz", "piano", "ambient"}
