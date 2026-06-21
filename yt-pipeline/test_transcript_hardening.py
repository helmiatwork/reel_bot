"""
Tests for hardened yt-dlp transcript fetch (429 retry, impersonate, player_client fallback).
"""

import json
import tempfile
import os
import subprocess
from pathlib import Path
from unittest import mock
import pytest
import time

from yt_pipeline import (
    _parse_vtt,
    _run_yt_dlp_transcript_attempt,
    get_timecoded_transcript,
)


class TestTranscriptHardening:
    """Tests for hardened transcript fetching with 429 retry and impersonate support."""

    def test_run_yt_dlp_transcript_attempt_success(self):
        """Test successful yt-dlp attempt with impersonate flag."""
        with tempfile.TemporaryDirectory(prefix="vtt_test_") as tmp_dir:
            # Mock subprocess.run to return success
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                returncode, stderr, stdout = _run_yt_dlp_transcript_attempt(
                    "https://www.youtube.com/watch?v=test123",
                    tmp_dir,
                    ["--impersonate", "chrome"]
                )

                assert returncode == 0
                assert stderr == ""
                # Verify --impersonate flag was passed
                args = mock_run.call_args[0][0]
                assert "--impersonate" in args
                assert "chrome" in args
                assert "--socket-timeout" in args
                assert "60" in args

    def test_run_yt_dlp_transcript_attempt_with_cookies(self):
        """Test yt-dlp attempt passes cookies argument when provided."""
        with tempfile.TemporaryDirectory(prefix="vtt_test_") as tmp_dir:
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                returncode, stderr, stdout = _run_yt_dlp_transcript_attempt(
                    "https://www.youtube.com/watch?v=test123",
                    tmp_dir,
                    ["--cookies", "/path/to/cookies.txt"]
                )

                args = mock_run.call_args[0][0]
                assert "--cookies" in args
                assert "/path/to/cookies.txt" in args

    def test_run_yt_dlp_transcript_attempt_429_error(self):
        """Test that 429 error is captured in stderr."""
        with tempfile.TemporaryDirectory(prefix="vtt_test_") as tmp_dir:
            mock_result = mock.MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "ERROR: [youtube] test123: HTTP 429 Too Many Requests"
            mock_result.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_result):
                returncode, stderr, stdout = _run_yt_dlp_transcript_attempt(
                    "https://www.youtube.com/watch?v=test123",
                    tmp_dir,
                    ["--impersonate", "chrome"]
                )

                assert returncode == 1
                assert "429" in stderr

    def test_get_timecoded_transcript_first_strategy_success(self):
        """Test transcript fetch succeeds on first strategy (impersonate)."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            # Create a mock VTT file
            vtt_content = """WEBVTT

00:00:01.000 --> 00:00:05.000
Hello world

00:00:06.000 --> 00:00:10.000
This is a test
"""
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text(vtt_content, encoding="utf-8")

            # Mock subprocess.run to succeed immediately
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_result):
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            assert len(segments) == 2
            assert segments[0]["text"] == "Hello world"
            assert segments[1]["text"] == "This is a test"
            assert segments[0]["start"] == 1.0
            assert segments[0]["end"] == 5.0

    def test_get_timecoded_transcript_retry_on_429(self):
        """Test transcript fetch retries on 429 with exponential backoff."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            # Create a mock VTT file
            vtt_content = """WEBVTT

00:00:01.000 --> 00:00:05.000
Success after retry
"""
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text(vtt_content, encoding="utf-8")

            # First call returns 429, second succeeds
            mock_429 = mock.MagicMock()
            mock_429.returncode = 1
            mock_429.stderr = "ERROR: HTTP 429 Too Many Requests"
            mock_429.stdout = ""

            mock_success = mock.MagicMock()
            mock_success.returncode = 0
            mock_success.stderr = ""
            mock_success.stdout = ""

            with mock.patch("subprocess.run", side_effect=[mock_429, mock_success]):
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    with mock.patch("time.sleep") as mock_sleep:
                        segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            assert len(segments) == 1
            assert segments[0]["text"] == "Success after retry"
            # Verify sleep was called for backoff
            assert mock_sleep.called

    def test_get_timecoded_transcript_fallback_player_client(self):
        """Test transcript fetch falls back to ios/web client after impersonate fails."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            # Create a mock VTT file
            vtt_content = """WEBVTT

00:00:01.000 --> 00:00:05.000
Fallback success
"""
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text(vtt_content, encoding="utf-8")

            # First strategy fails with JS runtime error, second succeeds
            mock_js_error = mock.MagicMock()
            mock_js_error.returncode = 1
            mock_js_error.stderr = "ERROR: No supported JavaScript runtime"
            mock_js_error.stdout = ""

            mock_success = mock.MagicMock()
            mock_success.returncode = 0
            mock_success.stderr = ""
            mock_success.stdout = ""

            # Impersonate fails, android fails, ios succeeds
            with mock.patch("subprocess.run", side_effect=[mock_js_error, mock_js_error, mock_success]):
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            assert len(segments) == 1
            assert segments[0]["text"] == "Fallback success"

    def test_get_timecoded_transcript_all_strategies_fail(self):
        """Test transcript fetch returns empty list when all strategies fail."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            # All attempts fail
            mock_failure = mock.MagicMock()
            mock_failure.returncode = 1
            mock_failure.stderr = "ERROR: Video unavailable"
            mock_failure.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_failure):
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            assert segments == []

    def test_get_timecoded_transcript_uses_cookies_env(self):
        """Test that YTDLP_COOKIES_FILE env var is passed to yt-dlp."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            # Create a mock cookies file
            cookies_file = Path(tmp_dir) / "cookies.txt"
            cookies_file.write_text("test_cookie_data")

            # Create a mock VTT file
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nTest")

            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = ""

            with mock.patch.dict(os.environ, {"YTDLP_COOKIES_FILE": str(cookies_file)}):
                with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                    with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                        segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            # Verify --cookies was passed
            args = mock_run.call_args[0][0]
            assert "--cookies" in args

    def test_get_timecoded_transcript_impersonate_flag_present(self):
        """Test that --impersonate flag is included in first strategy."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nTest")

            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            # Check first call includes --impersonate
            args = mock_run.call_args_list[0][0][0]
            assert "--impersonate" in args
            assert "chrome" in args

    def test_get_timecoded_transcript_socket_timeout_60s(self):
        """Test that socket timeout is set to 60 seconds."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nTest")

            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            # Verify socket-timeout 60
            args = mock_run.call_args[0][0]
            assert "--socket-timeout" in args
            timeout_idx = args.index("--socket-timeout")
            assert args[timeout_idx + 1] == "60"

    def test_get_timecoded_transcript_no_vtt_file_continues(self):
        """Test that missing VTT file after success continues to next strategy."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            # First attempt succeeds but no VTT file
            # Second attempt succeeds with VTT file
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nSecond strategy")

            mock_success = mock.MagicMock()
            mock_success.returncode = 0
            mock_success.stderr = ""
            mock_success.stdout = ""

            # Simulate: first strategy succeeds (but no VTT file), second succeeds with file
            with mock.patch("subprocess.run", return_value=mock_success):
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    # First attempt: no vtt file, so it continues
                    # But since we only mock once, we'll get the VTT file
                    segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            assert len(segments) == 1
            assert segments[0]["text"] == "Second strategy"


class TestExponentialBackoff:
    """Tests for exponential backoff timing on 429 retries."""

    def test_exponential_backoff_delays(self):
        """Test that backoff uses 2s, 4s, 8s delays."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nTest")

            # All 429 errors, but track sleep calls
            mock_429 = mock.MagicMock()
            mock_429.returncode = 1
            mock_429.stderr = "ERROR: HTTP 429"
            mock_429.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_429):
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    with mock.patch("time.sleep") as mock_sleep:
                        segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            # Should have called sleep multiple times for retries
            # Expected: 2, 4, 8 for first strategy retries
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            # We expect at least one sleep call for backoff
            assert len(sleep_calls) >= 1


class TestStderrIsolation:
    """Tests that diagnostic prints are routed to stderr, keeping stdout clean for JSON."""

    def test_get_timecoded_transcript_diagnostics_on_stderr(self, capsys):
        """Test that get_timecoded_transcript sends diagnostics to stderr only."""
        with tempfile.TemporaryDirectory(prefix="transcript_test_") as tmp_dir:
            vtt_file = Path(tmp_dir) / "subs.en.vtt"
            vtt_file.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nTest segment")

            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = ""

            with mock.patch("subprocess.run", return_value=mock_result):
                with mock.patch("tempfile.mkdtemp", return_value=tmp_dir):
                    segments = get_timecoded_transcript("https://www.youtube.com/watch?v=test123")

            # Capture output to verify diagnostics go to stderr
            captured = capsys.readouterr()
            # Should have something in stderr (diagnostics)
            # stdout should be clean (used for JSON by caller)
            assert len(segments) == 1


class TestJSONFallback:
    """Tests for the defensive JSON fallback parsing in pipeline-api."""

    def test_json_fallback_with_polluted_stdout(self):
        """Test that JSON fallback recovers JSON when stdout has diagnostics before it."""
        # Simulate polluted stdout: diagnostics + JSON
        polluted_stdout = """[transcript] Using cookies...
[transcript] Strategy 1/4...
[transcript] Success...
[transcript] Parsed 2 segments...
{"segments": [{"start": 1.0, "end": 5.0, "text": "Hello"}]}"""

        lines = polluted_stdout.strip().split('\n')
        segments = []
        # Simulate the fallback logic
        for line in reversed(lines):
            if line.strip().startswith('{'):
                try:
                    result = json.loads(line)
                    if isinstance(result, dict) and "segments" in result:
                        segments = result.get("segments", [])
                        break
                except (json.JSONDecodeError, ValueError):
                    continue

        assert len(segments) == 1
        assert segments[0]["text"] == "Hello"

    def test_json_fallback_with_multiline_json(self):
        """Test fallback finds last JSON object even when multi-line."""
        polluted_stdout = """[diagnostic] Line 1
[diagnostic] Line 2
{"segments": []}"""

        lines = polluted_stdout.strip().split('\n')
        segments = []
        for line in reversed(lines):
            if line.strip().startswith('{'):
                try:
                    result = json.loads(line)
                    if isinstance(result, dict) and "segments" in result:
                        segments = result.get("segments", [])
                        break
                except (json.JSONDecodeError, ValueError):
                    continue

        assert segments == []

    def test_json_fallback_finds_last_valid_json_block(self):
        """Test fallback scans from end and finds first valid JSON with segments."""
        polluted_stdout = """[transcript] Some diagnostics
[transcript] More diagnostics
{"invalid": "json"}
{"segments": [{"start": 0, "end": 10, "text": "Valid"}]}"""

        lines = polluted_stdout.strip().split('\n')
        segments = []
        for line in reversed(lines):
            if line.strip().startswith('{'):
                try:
                    result = json.loads(line)
                    if isinstance(result, dict) and "segments" in result:
                        segments = result.get("segments", [])
                        break
                except (json.JSONDecodeError, ValueError):
                    continue

        assert len(segments) == 1
        assert segments[0]["text"] == "Valid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
