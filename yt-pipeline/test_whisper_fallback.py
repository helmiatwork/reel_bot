import sys
from unittest import mock
import pytest

from yt_pipeline import transcribe_with_whisper, get_transcript_or_fallback


class TestTranscribeWithWhisper:
    def test_maps_whisper_segments_to_shape(self):
        fake_model = mock.MagicMock()
        fake_model.transcribe.return_value = {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": " Hello there"},
                {"start": 2.5, "end": 5.0, "text": " general"},
            ]
        }
        fake_whisper = mock.MagicMock()
        fake_whisper.load_model.return_value = fake_model
        with mock.patch.dict(sys.modules, {"whisper": fake_whisper}):
            segments = transcribe_with_whisper("/tmp/audio.mp3")
        assert segments == [
            {"start": 0.0, "end": 2.5, "text": "Hello there"},
            {"start": 2.5, "end": 5.0, "text": "general"},
        ]
        fake_whisper.load_model.assert_called_once_with("base")
        fake_model.transcribe.assert_called_once_with("/tmp/audio.mp3")

    def test_returns_empty_on_exception(self):
        fake_whisper = mock.MagicMock()
        fake_whisper.load_model.side_effect = RuntimeError("model load failed")
        with mock.patch.dict(sys.modules, {"whisper": fake_whisper}):
            segments = transcribe_with_whisper("/tmp/audio.mp3")
        assert segments == []


class TestGetTranscriptOrFallback:
    def test_uses_subtitles_when_available_no_whisper(self):
        subs = [{"start": 0.0, "end": 1.0, "text": "hi"}]
        with mock.patch("yt_pipeline.get_timecoded_transcript", return_value=subs) as g, \
             mock.patch("yt_pipeline.download_audio_only") as dl, \
             mock.patch("yt_pipeline.transcribe_with_whisper") as tw:
            out = get_transcript_or_fallback("https://x.com/v")
        assert out == subs
        g.assert_called_once()
        dl.assert_not_called()
        tw.assert_not_called()

    def test_falls_back_to_whisper_on_empty_subs(self):
        whisper_segs = [{"start": 0.0, "end": 2.0, "text": "from audio"}]
        with mock.patch("yt_pipeline.get_timecoded_transcript", return_value=[]), \
             mock.patch("yt_pipeline.download_audio_only", return_value="/tmp/x/source_audio.mp3") as dl, \
             mock.patch("yt_pipeline.transcribe_with_whisper", return_value=whisper_segs) as tw:
            out = get_transcript_or_fallback("https://tiktok.com/v")
        assert out == whisper_segs
        dl.assert_called_once()
        tw.assert_called_once_with("/tmp/x/source_audio.mp3")

    def test_returns_empty_when_audio_download_fails(self):
        with mock.patch("yt_pipeline.get_timecoded_transcript", return_value=[]), \
             mock.patch("yt_pipeline.download_audio_only", side_effect=Exception("dl failed")), \
             mock.patch("yt_pipeline.transcribe_with_whisper") as tw:
            out = get_transcript_or_fallback("https://tiktok.com/v")
        assert out == []
        tw.assert_not_called()


class TestTranscriptCliChokepoint:
    def test_cli_transcript_branch_calls_orchestrator(self):
        """The --transcript CLI branch must route through get_transcript_or_fallback."""
        import yt_pipeline
        import inspect
        src = inspect.getsource(yt_pipeline)
        marker = src.split('"--transcript"')[1].split("elif")[0]
        assert "get_transcript_or_fallback(url)" in marker
        assert "segments = get_timecoded_transcript(url)" not in marker
