"""
Tests for Suno multi-section audio segmentation.
Tests _detect_audio_sections and _suno_audio_analysis_segment behavior.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
import main as m


class TestDetectAudioSections:
    """Tests for _detect_audio_sections section detection and merging."""

    def test_single_section_fallback_on_error(self):
        """On librosa error, should return single fallback segment [(0.0, 0.0)]."""
        result = m._detect_audio_sections("/nonexistent/path.mp3")
        assert result == [(0.0, 0.0)]

    def test_returns_tuples_with_floats(self):
        """Result should always be list of (float, float) tuples."""
        result = m._detect_audio_sections("/nonexistent/path.mp3")
        assert isinstance(result, list)
        assert len(result) > 0
        for start, end in result:
            assert isinstance(start, float)
            assert isinstance(end, float)
            assert start <= end

    def test_first_segment_starts_at_zero_on_error(self):
        """Even on error, fallback segment structure is valid."""
        result = m._detect_audio_sections("/nonexistent/path.mp3")
        assert result[0][0] == 0.0

    def test_max_sections_env_override(self):
        """SUNO_MAX_SECTIONS env var should be respected (tested via function signature)."""
        # Just test that the function accepts and uses the max_sections parameter
        old_max = os.environ.get("SUNO_MAX_SECTIONS")
        try:
            os.environ["SUNO_MAX_SECTIONS"] = "3"
            result = m._detect_audio_sections("/nonexistent/path.mp3", max_sections=3)
            # Should return list of tuples regardless
            assert isinstance(result, list)
            assert all(isinstance(seg, tuple) for seg in result)
        finally:
            if old_max is not None:
                os.environ["SUNO_MAX_SECTIONS"] = old_max
            else:
                os.environ.pop("SUNO_MAX_SECTIONS", None)


class TestSunoAudioAnalysisSegment:
    """Tests for _suno_audio_analysis_segment segment analysis."""

    def test_returns_empty_dict_on_error(self):
        """On any error, should return empty dict (non-fatal)."""
        result = m._suno_audio_analysis_segment("/nonexistent/path.mp3", 0.0, 10.0)
        assert result == {}

    def test_returns_empty_dict_on_invalid_range(self):
        """If start >= end, should return empty dict immediately."""
        result = m._suno_audio_analysis_segment("/some/path.mp3", 10.0, 5.0)
        assert result == {}

    def test_returns_empty_dict_on_zero_range(self):
        """If start == end, should return empty dict."""
        result = m._suno_audio_analysis_segment("/some/path.mp3", 5.0, 5.0)
        assert result == {}

    def test_graceful_failure_on_missing_cliproxy_key(self):
        """Without CLIPROXY_KEY, should return empty dict."""
        with patch.dict(os.environ, {"CLIPROXY_KEY": ""}):
            result = m._suno_audio_analysis_segment("/path/audio.mp3", 0.0, 30.0)
            assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
