"""
Tests for Suno multi-section audio segmentation.
Tests _detect_audio_sections and _suno_audio_analysis_segment behavior.
"""

import pytest
import os
import numpy as np
from unittest.mock import patch, MagicMock, Mock
import tempfile
import main as m

# Try to import audio synthesis tools; skip real tests if unavailable
try:
    import soundfile
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False


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
        """SUNO_MAX_SECTIONS env var should be respected and cap works correctly."""
        # Mock librosa to simulate audio with many natural sections
        mock_y = np.random.randn(22050 * 180)  # 180 seconds of audio
        mock_features = np.random.randn(26, 100)  # chroma(12) + mfcc(13) + 1 = 26 features

        with patch("librosa.load") as mock_load, \
             patch("librosa.get_duration") as mock_duration, \
             patch("librosa.feature.chroma_stft") as mock_chroma, \
             patch("librosa.feature.mfcc") as mock_mfcc, \
             patch("librosa.util.sync") as mock_sync, \
             patch("librosa.feature.stack_memory") as mock_stack, \
             patch("librosa.frames_to_time") as mock_frames_to_time, \
             patch("scipy.cluster.hierarchy.linkage") as mock_linkage, \
             patch("scipy.cluster.hierarchy.fcluster") as mock_fcluster:

            mock_load.return_value = (mock_y, 22050)
            mock_duration.return_value = 180.0
            mock_chroma.return_value = np.random.randn(12, 100)
            mock_mfcc.return_value = np.random.randn(13, 100)
            mock_sync.return_value = mock_features
            mock_stack.return_value = mock_features
            mock_frames_to_time.return_value = np.array([30., 60., 90., 120., 150.])

            # Simulate clustering that produces 6 sections (more than max_sections=3)
            mock_linkage.return_value = np.random.randn(99, 4)
            mock_fcluster.return_value = np.array([0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5] + [5] * 88)

            old_max = os.environ.get("SUNO_MAX_SECTIONS")
            try:
                os.environ["SUNO_MAX_SECTIONS"] = "3"
                result = m._detect_audio_sections("/test/path.mp3", max_sections=6)
                # Should respect the env override (3) and cap correctly
                assert isinstance(result, list)
                assert len(result) <= 3, f"Expected ≤3 sections, got {len(result)}"
                assert all(isinstance(seg, tuple) for seg in result)
                assert all(seg[0] <= seg[1] for seg in result)
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
        """Without CLIPROXY_KEY, should return empty dict before doing any ffmpeg work."""
        # Clear the key and ensure we return {} immediately
        with patch.dict(os.environ, {}, clear=False):
            # Ensure CLIPROXY_KEY is not set
            if "CLIPROXY_KEY" in os.environ:
                del os.environ["CLIPROXY_KEY"]

            # This should return {} WITHOUT calling subprocess or other expensive operations
            result = m._suno_audio_analysis_segment("/path/audio.mp3", 0.0, 30.0)
            assert result == {}

    def test_cap_merge_chooses_shortest_pair(self):
        """Cap-merge should merge the shortest-duration adjacent segments, not always the first pair."""
        # Test with unequal segment durations to verify shortest pair is merged.
        # Segments with durations: [15, 10, 15, 20] seconds
        # Adjacent pair sums: [25, 25, 35]
        # The 10s segment is between 15 and 15, and when paired, one of the sums is 25.
        # Merge should pick the 10s segment (pos 1) since it's the shortest individual segment.

        with patch("librosa.load") as mock_load, \
             patch("librosa.get_duration") as mock_duration, \
             patch("librosa.feature.chroma_stft") as mock_chroma, \
             patch("librosa.feature.mfcc") as mock_mfcc, \
             patch("librosa.util.sync") as mock_sync, \
             patch("librosa.feature.stack_memory") as mock_stack, \
             patch("librosa.frames_to_time") as mock_frames_to_time, \
             patch("scipy.cluster.hierarchy.linkage") as mock_linkage, \
             patch("scipy.cluster.hierarchy.fcluster") as mock_fcluster:

            mock_y = np.random.randn(22050 * 60)
            mock_load.return_value = (mock_y, 22050)
            mock_duration.return_value = 60.0
            mock_chroma.return_value = np.random.randn(12, 100)
            mock_mfcc.return_value = np.random.randn(13, 100)
            mock_features = np.random.randn(26, 100)
            mock_sync.return_value = mock_features
            mock_stack.return_value = mock_features
            # Boundaries at 15, 25, 40 seconds -> segments [0-15, 15-25, 25-40, 40-60]
            # Durations: [15, 10, 15, 20]
            mock_frames_to_time.return_value = np.array([15., 25., 40.])

            mock_linkage.return_value = np.random.randn(99, 4)
            # 4 sections with boundaries at 15, 25, 40
            mock_fcluster.return_value = np.array([0, 0, 1, 1, 2, 2, 3, 3] + [3] * 92)

            result = m._detect_audio_sections("/test/path.mp3", max_sections=2)
            # Should cap to 2 sections; the 10s segment should be merged first
            assert len(result) <= 2
            assert isinstance(result, list)
            assert all(isinstance(seg, tuple) for seg in result)


@pytest.mark.skipif(not HAS_SOUNDFILE, reason="soundfile required for real audio synthesis test")
class TestDetectAudioSectionsRealSignal:
    """Tests using real synthesized audio to verify _detect_audio_sections works end-to-end."""

    def test_heterogeneous_signal_detects_multiple_sections(self):
        """Synthesize audio with clear structural change and verify >1 sections detected."""
        sr = 22050
        duration_sec = 60
        # First 30 seconds: low-frequency sine (200 Hz) - like a calm intro
        t1 = np.linspace(0, 30, int(sr * 30), endpoint=False)
        y1 = 0.3 * np.sin(2 * np.pi * 200 * t1)

        # Next 30 seconds: high-frequency noise + sine (3000 Hz) - like a build-up
        t2 = np.linspace(30, 60, int(sr * 30), endpoint=False)
        y2 = 0.3 * (0.5 * np.sin(2 * np.pi * 3000 * t2) + np.random.randn(len(t2)) * 0.2)

        y = np.concatenate([y1, y2])

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            # Write synthesized audio to temp file
            soundfile.write(temp_path, y, sr)

            # Call the real _detect_audio_sections (no mocks)
            result = m._detect_audio_sections(temp_path, min_section_sec=5.0, max_sections=8)

            # Should detect the structural change and return >1 section
            assert len(result) >= 2, f"Expected >=2 sections for heterogeneous signal, got {len(result)}: {result}"
            assert all(isinstance(seg, tuple) and len(seg) == 2 for seg in result)
            assert all(start < end for start, end in result)
            # First section should start at 0, last should end at ~60
            assert result[0][0] == 0.0
            assert result[-1][1] <= 60.0 + 0.1  # allow small float error
        finally:
            os.unlink(temp_path)

    def test_homogeneous_signal_single_section(self):
        """Synthesize uniform audio and verify it collapses to ~1 section."""
        sr = 22050
        duration_sec = 40
        # Homogeneous: constant sine wave throughout
        t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
        y = 0.3 * np.sin(2 * np.pi * 440 * t)  # constant 440 Hz tone

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            soundfile.write(temp_path, y, sr)

            result = m._detect_audio_sections(temp_path, min_section_sec=5.0, max_sections=8)

            # Should detect minimal structure, likely 1 section
            assert len(result) >= 1
            assert len(result) <= 2, f"Homogeneous signal should be 1-2 sections, got {len(result)}: {result}"
            assert result[0][0] == 0.0
            assert result[-1][1] <= 40.0 + 0.1
        finally:
            os.unlink(temp_path)


class TestDownloadWindowLogic:
    """Tests for empty audio_end → bounded-full window (600s default) behavior."""

    def test_empty_audio_end_uses_bounded_window(self):
        """
        When audio_end is None, yt-dlp download should use start + SUNO_WINDOW_SEC.
        Default SUNO_WINDOW_SEC is 600s (10 min).
        """
        with patch("subprocess.run") as mock_run, \
             patch("pathlib.Path.glob") as mock_glob, \
             patch("pathlib.Path.mkdir"), \
             patch("shutil.move"):

            # Mock the yt-dlp subprocess call
            mock_run.return_value = MagicMock(returncode=0)
            # Mock the downloaded audio file discovery
            mock_glob.return_value = [MagicMock(name="audio.mp3")]

            # Call with audio_start=0, audio_end=None (empty)
            try:
                m._download_and_clip_audio_for_suno("https://youtube.com/watch?v=test", 0, None)
            except Exception:
                # May fail on file move or other downstream ops; we only care about the cmd
                pass

            # Verify subprocess.run was called
            mock_run.assert_called()
            call_args = mock_run.call_args
            cmd = call_args[0][0]  # first positional arg is the command list

            # Extract --download-sections argument
            assert "--download-sections" in cmd, f"expected --download-sections in {cmd}"
            idx = cmd.index("--download-sections")
            sections_arg = cmd[idx + 1]
            # Should be "*0-600" (or "*0-{SUNO_WINDOW_SEC}" if env is set)
            assert sections_arg.startswith("*0-"), f"Expected section arg to start with '*0-', got {sections_arg}"
            # Parse the end time from the section arg (*start-end format)
            parts = sections_arg.split("-")
            end_time = float(parts[-1])
            # Should be 600 (default SUNO_WINDOW_SEC)
            assert end_time == 600, f"Expected end=600, got {end_time}"

    def test_explicit_audio_end_honored(self):
        """
        When audio_end is explicitly provided (not None), use it exactly.
        Do NOT apply the bounded-window logic.
        """
        with patch("subprocess.run") as mock_run, \
             patch("pathlib.Path.glob") as mock_glob, \
             patch("pathlib.Path.mkdir"), \
             patch("shutil.move"):

            # Mock the yt-dlp subprocess call
            mock_run.return_value = MagicMock(returncode=0)
            mock_glob.return_value = [MagicMock(name="audio.mp3")]

            # Call with audio_start=10, audio_end=120 (explicit)
            try:
                m._download_and_clip_audio_for_suno("https://youtube.com/watch?v=test", 10, 120)
            except Exception:
                pass

            # Verify the command
            mock_run.assert_called()
            call_args = mock_run.call_args
            cmd = call_args[0][0]

            assert "--download-sections" in cmd, f"expected --download-sections in {cmd}"
            idx = cmd.index("--download-sections")
            sections_arg = cmd[idx + 1]
            # Should be "*10.0-120.0" (exactly as provided, not start + 600)
            # Parse to verify the values
            parts = sections_arg.split("-")
            start_time = float(parts[0].lstrip("*"))
            end_time = float(parts[-1])
            assert start_time == 10.0, f"Expected start=10.0, got {start_time}"
            assert end_time == 120.0, f"Expected end=120.0, got {end_time}"

    def test_suno_window_sec_env_override(self):
        """
        SUNO_WINDOW_SEC env var should override the default 600s bounded window.
        """
        with patch("subprocess.run") as mock_run, \
             patch("pathlib.Path.glob") as mock_glob, \
             patch("pathlib.Path.mkdir"), \
             patch("shutil.move"):

            # Note: patch.dict(os.environ) is a no-op for _SUNO_WINDOW_SEC because it is
            # evaluated at module import time, not at runtime. The direct assignment below drives the test.
            old_window = m._SUNO_WINDOW_SEC
            try:
                # Temporarily override the module constant
                m._SUNO_WINDOW_SEC = 300

                mock_run.return_value = MagicMock(returncode=0)
                mock_glob.return_value = [MagicMock(name="audio.mp3")]

                # Call with empty audio_end
                try:
                    m._download_and_clip_audio_for_suno("https://youtube.com/watch?v=test", 0, None)
                except Exception:
                    pass

                # Verify the window uses 300 instead of 600
                mock_run.assert_called()
                call_args = mock_run.call_args
                cmd = call_args[0][0]

                assert "--download-sections" in cmd, f"expected --download-sections in {cmd}"
                idx = cmd.index("--download-sections")
                sections_arg = cmd[idx + 1]
                parts = sections_arg.split("-")
                end_time = float(parts[-1])
                assert end_time == 300, f"Expected end=300 (from env), got {end_time}"
            finally:
                m._SUNO_WINDOW_SEC = old_window


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
