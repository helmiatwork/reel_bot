# scripts/test_claude_bridge.py
# Offline stdlib-only unit tests for claude_bridge.py.
# Mocks subprocess.run — no real claude calls are made.

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make the scripts/ directory importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))
import claude_bridge


# ── Helper: completed process ──────────────────────────────────────────────────

def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Build a mock CompletedProcess-like object."""
    m = MagicMock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


_GOOD_CLAUDE_JSON = json.dumps({
    "result": '{"hook":"great hook","tags":["a","b"]}',
    "is_error": False,
    "total_cost_usd": 0.012,
    "usage": {"input_tokens": 200, "output_tokens": 80},
})


# ── Path-traversal frame guard ─────────────────────────────────────────────────

class TestFramePathTraversal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Write a real frame file
        self.frame_name = "frame_001.jpg"
        (Path(self.tmp) / self.frame_name).write_bytes(b"\xff\xd8\xff")  # minimal JPEG magic

    def test_slash_in_name_rejected(self):
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames(["../secret.txt"])
            self.assertEqual(result, [], "Path with .. must be rejected")
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_double_dot_rejected(self):
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames(["../../etc/passwd"])
            self.assertEqual(result, [], "Path with / must be rejected")
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_valid_basename_resolved(self):
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames([self.frame_name])
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0].endswith(self.frame_name))
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_nonexistent_file_skipped(self):
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames(["ghost_frame.jpg"])
            self.assertEqual(result, [])
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_empty_list_returns_empty(self):
        result = claude_bridge._resolve_frames([])
        self.assertEqual(result, [])

    def test_none_returns_empty(self):
        result = claude_bridge._resolve_frames(None)
        self.assertEqual(result, [])


# ── subprocess argv (never shell=True) ────────────────────────────────────────

class TestSubprocessArgv(unittest.TestCase):
    def test_argv_list_not_shell(self):
        """subprocess.run must be called with a list argv, not a shell string."""
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_bridge._run_claude("test prompt", [], "claude-sonnet-4-6", 10)
        args, kwargs = mock_run.call_args
        argv = args[0]
        self.assertIsInstance(argv, list, "argv must be a list")
        self.assertNotIn("shell", kwargs, "shell kwarg must not be set to True")
        # Or if shell is explicitly set, must be False
        if "shell" in kwargs:
            self.assertFalse(kwargs["shell"])

    def test_model_in_argv(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_bridge._run_claude("test", [], "claude-opus-4-5", 10)
        argv = mock_run.call_args[0][0]
        self.assertIn("claude-opus-4-5", argv)

    def test_output_format_json_in_argv(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_bridge._run_claude("test", [], "claude-sonnet-4-6", 10)
        argv = mock_run.call_args[0][0]
        self.assertIn("--output-format", argv)
        idx = argv.index("--output-format")
        self.assertEqual(argv[idx + 1], "json")

    def test_prompt_in_argv(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_bridge._run_claude("my test prompt", [], "claude-sonnet-4-6", 10)
        argv = mock_run.call_args[0][0]
        self.assertIn("-p", argv)
        idx = argv.index("-p")
        self.assertIn("my test prompt", argv[idx + 1])


# ── Rate-limit detection ───────────────────────────────────────────────────────

class TestRateLimitDetection(unittest.TestCase):
    def test_rate_limit_in_stdout(self):
        payload = json.dumps({
            "result": "usage limit reached please wait",
            "is_error": True,
            "total_cost_usd": 0.0,
            "usage": {},
        })
        with patch("subprocess.run", return_value=_completed(stdout=payload)):
            result = claude_bridge._run_claude("test", [], "claude-sonnet-4-6", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "rate_limit")

    def test_rate_limit_in_stderr(self):
        with patch("subprocess.run", return_value=_completed(
            stdout="", stderr="Error: rate limit exceeded, try again", returncode=1
        )):
            result = claude_bridge._run_claude("test", [], "claude-sonnet-4-6", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "rate_limit")

    def test_overloaded_phrase_detected(self):
        with patch("subprocess.run", return_value=_completed(
            stdout="", stderr="Claude is overloaded right now", returncode=1
        )):
            result = claude_bridge._run_claude("test", [], "claude-sonnet-4-6", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "rate_limit")

    def test_too_many_requests_detected(self):
        with patch("subprocess.run", return_value=_completed(
            stdout="", stderr="too many requests", returncode=1
        )):
            result = claude_bridge._run_claude("test", [], "claude-sonnet-4-6", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "rate_limit")

    def test_normal_error_not_rate_limit(self):
        with patch("subprocess.run", return_value=_completed(
            stdout="", stderr="Error: some other problem", returncode=1
        )):
            result = claude_bridge._run_claude("test", [], "claude-sonnet-4-6", 30)
        self.assertFalse(result["ok"])
        self.assertNotEqual(result.get("error_type"), "rate_limit")


# ── Successful claude run parsing ─────────────────────────────────────────────

class TestClaudeRunSuccess(unittest.TestCase):
    def test_ok_true_on_success(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)):
            result = claude_bridge._run_claude("hi", [], "claude-sonnet-4-6", 30)
        self.assertTrue(result["ok"])

    def test_result_extracted(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)):
            result = claude_bridge._run_claude("hi", [], "claude-sonnet-4-6", 30)
        self.assertIn("hook", result["result"])

    def test_cost_usd_extracted(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)):
            result = claude_bridge._run_claude("hi", [], "claude-sonnet-4-6", 30)
        self.assertAlmostEqual(result["cost_usd"], 0.012)

    def test_model_in_response(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)):
            result = claude_bridge._run_claude("hi", [], "claude-sonnet-4-6", 30)
        self.assertEqual(result["model"], "claude-sonnet-4-6")

    def test_is_error_true_returns_failure(self):
        payload = json.dumps({
            "result": "something went wrong",
            "is_error": True,
            "total_cost_usd": 0.0,
            "usage": {},
        })
        with patch("subprocess.run", return_value=_completed(payload)):
            result = claude_bridge._run_claude("hi", [], "claude-sonnet-4-6", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "claude_error")

    def test_timeout_returns_failure(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            result = claude_bridge._run_claude("hi", [], "claude-sonnet-4-6", 5)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "timeout")

    def test_frames_appended_to_prompt(self):
        """Frame paths must be appended to the final prompt sent to claude."""
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_bridge._run_claude("base prompt", ["/tmp/f1.jpg", "/tmp/f2.jpg"],
                                      "claude-sonnet-4-6", 30)
        argv = mock_run.call_args[0][0]
        idx = argv.index("-p")
        final_prompt = argv[idx + 1]
        self.assertIn("/tmp/f1.jpg", final_prompt)
        self.assertIn("/tmp/f2.jpg", final_prompt)
        self.assertIn("Gambar untuk dianalisa", final_prompt)

    def test_no_frames_no_appended_section(self):
        """When no frames provided, the prompt should NOT have the frame section."""
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_bridge._run_claude("clean prompt", [], "claude-sonnet-4-6", 30)
        argv = mock_run.call_args[0][0]
        idx = argv.index("-p")
        final_prompt = argv[idx + 1]
        self.assertNotIn("Gambar untuk dianalisa", final_prompt)


# ── HTTP handler ───────────────────────────────────────────────────────────────

class TestHealthEndpoint(unittest.TestCase):
    def _make_request(self, method, path, body=None):
        """Simulate an HTTP request against BridgeHandler using mock sockets."""
        handler = claude_bridge.BridgeHandler.__new__(claude_bridge.BridgeHandler)
        handler.path = path
        # Build response capture
        response_bytes = io.BytesIO()
        handler.wfile = response_bytes
        handler.headers = {}
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        def _capture_write(b):
            response_bytes.write(b)

        handler.wfile.write = _capture_write
        return handler

    def test_get_health_returns_ok(self):
        with patch("subprocess.run"):  # not called for GET /health
            handler = self._make_request("GET", "/health")
            captured = []
            handler._send_json = lambda status, payload: captured.append((status, payload))
            handler.do_GET()
        self.assertEqual(len(captured), 1)
        status, payload = captured[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_get_unknown_returns_404(self):
        handler = self._make_request("GET", "/unknown")
        captured = []
        handler._send_json = lambda status, payload: captured.append((status, payload))
        handler.do_GET()
        status, _ = captured[0]
        self.assertEqual(status, 404)

    def test_post_unknown_path_returns_404(self):
        handler = self._make_request("POST", "/badpath")
        handler.headers = {"Content-Length": "0"}
        handler.rfile = io.BytesIO(b"")
        captured = []
        handler._send_json = lambda status, payload: captured.append((status, payload))
        handler.do_POST()
        status, _ = captured[0]
        self.assertEqual(status, 404)

    def test_post_run_missing_prompt_returns_400(self):
        body = json.dumps({"frames": []}).encode()
        handler = self._make_request("POST", "/run")
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        captured = []
        handler._send_json = lambda status, payload: captured.append((status, payload))
        handler.do_POST()
        status, payload = captured[0]
        self.assertEqual(status, 400)
        self.assertIn("prompt", payload["error"])

    def test_post_run_invalid_json_returns_400(self):
        body = b"not json at all"
        handler = self._make_request("POST", "/run")
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        captured = []
        handler._send_json = lambda status, payload: captured.append((status, payload))
        handler.do_POST()
        status, payload = captured[0]
        self.assertEqual(status, 400)

    def test_post_run_rate_limit_returns_429(self):
        body = json.dumps({"prompt": "test", "frames": []}).encode()
        handler = self._make_request("POST", "/run")
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        captured = []
        handler._send_json = lambda status, payload: captured.append((status, payload))
        with patch.object(claude_bridge, "_resolve_frames", return_value=[]), \
             patch.object(claude_bridge, "_run_claude",
                          return_value={"ok": False, "error": "rate limit", "error_type": "rate_limit"}):
            handler.do_POST()
        status, payload = captured[0]
        self.assertEqual(status, 429)

    def test_post_run_success_returns_200(self):
        body = json.dumps({"prompt": "analyze", "frames": []}).encode()
        handler = self._make_request("POST", "/run")
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        captured = []
        handler._send_json = lambda status, payload: captured.append((status, payload))
        with patch.object(claude_bridge, "_resolve_frames", return_value=[]), \
             patch.object(claude_bridge, "_run_claude",
                          return_value={"ok": True, "result": '{}', "cost_usd": 0.01, "model": "x"}):
            handler.do_POST()
        status, payload = captured[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])


# ── is_rate_limit helper ──────────────────────────────────────────────────────

class TestIsRateLimit(unittest.TestCase):
    def test_usage_limit_phrase(self):
        self.assertTrue(claude_bridge._is_rate_limit("Error: usage limit reached"))

    def test_rate_limit_phrase(self):
        self.assertTrue(claude_bridge._is_rate_limit("rate limit exceeded"))

    def test_ratelimit_combined(self):
        self.assertTrue(claude_bridge._is_rate_limit("ratelimitError"))

    def test_overloaded(self):
        self.assertTrue(claude_bridge._is_rate_limit("Claude is overloaded"))

    def test_normal_error_not_rate_limit(self):
        self.assertFalse(claude_bridge._is_rate_limit("file not found"))

    def test_empty_string(self):
        self.assertFalse(claude_bridge._is_rate_limit(""))

    def test_case_insensitive(self):
        self.assertTrue(claude_bridge._is_rate_limit("RATE LIMIT"))


# ── Subdir validation and resolution ─────────────────────────────────────────

class TestSubdirValidation(unittest.TestCase):
    def test_valid_subdir_accepted(self):
        self.assertTrue(claude_bridge._validate_subdir("abc123"))
        self.assertTrue(claude_bridge._validate_subdir("run-001"))
        self.assertTrue(claude_bridge._validate_subdir("A_B_C"))
        self.assertTrue(claude_bridge._validate_subdir("a1b2c3d4"))

    def test_slash_subdir_rejected(self):
        self.assertFalse(claude_bridge._validate_subdir("run/evil"))

    def test_backslash_subdir_rejected(self):
        self.assertFalse(claude_bridge._validate_subdir("run\\evil"))

    def test_dotdot_subdir_rejected(self):
        self.assertFalse(claude_bridge._validate_subdir("../secret"))

    def test_dotfile_subdir_rejected(self):
        self.assertFalse(claude_bridge._validate_subdir(".hidden"))

    def test_empty_string_rejected(self):
        self.assertFalse(claude_bridge._validate_subdir(""))

    def test_none_rejected(self):
        # _validate_subdir(None) should return False — None is not a valid subdir
        self.assertFalse(claude_bridge._validate_subdir(None))

    def test_space_rejected(self):
        self.assertFalse(claude_bridge._validate_subdir("run 001"))

    def test_dots_only_rejected(self):
        self.assertFalse(claude_bridge._validate_subdir("..."))


class TestSubdirFrameResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Create a subdirectory with a frame
        self.subdir_name = "run-abc123"
        subdir_path = Path(self.tmp) / self.subdir_name
        subdir_path.mkdir()
        self.frame_name = "frame_000.jpg"
        (subdir_path / self.frame_name).write_bytes(b"\xff\xd8\xff")
        # Also write a frame at root (should NOT be found when subdir is given)
        (Path(self.tmp) / "root_frame.jpg").write_bytes(b"\xff\xd8\xff")

    def test_valid_subdir_resolves_frame_under_subfolder(self):
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames([self.frame_name], subdir=self.subdir_name)
            self.assertEqual(len(result), 1)
            expected = str(Path(self.tmp) / self.subdir_name / self.frame_name)
            self.assertEqual(result[0], expected)
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_subdir_does_not_find_root_frames(self):
        """A frame in the root dir must NOT be returned when subdir is given."""
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames(["root_frame.jpg"], subdir=self.subdir_name)
            self.assertEqual(result, [], "Root frame must not be found via subdir lookup")
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_no_subdir_resolves_root_frame(self):
        """Without subdir, frames are resolved under the root FRAME_DIR."""
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames(["root_frame.jpg"])
            self.assertEqual(len(result), 1)
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_dotdot_subdir_returns_empty(self):
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames([self.frame_name], subdir="../etc")
            self.assertEqual(result, [], "../ subdir must be rejected")
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_slash_subdir_returns_empty(self):
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames([self.frame_name], subdir="/absolute/path")
            self.assertEqual(result, [], "Absolute path subdir must be rejected")
        finally:
            claude_bridge.FRAME_DIR = orig

    def test_dotfile_subdir_returns_empty(self):
        orig = claude_bridge.FRAME_DIR
        claude_bridge.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_bridge._resolve_frames([self.frame_name], subdir=".hidden")
            self.assertEqual(result, [], "Dotfile subdir must be rejected")
        finally:
            claude_bridge.FRAME_DIR = orig


class TestSubdirHTTPHandler(unittest.TestCase):
    """Tests that do_POST correctly validates subdir and routes to _resolve_frames."""

    def _make_post_handler(self, body_dict):
        body = json.dumps(body_dict).encode()
        handler = claude_bridge.BridgeHandler.__new__(claude_bridge.BridgeHandler)
        handler.path = "/run"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        captured = []
        handler._send_json = lambda status, payload: captured.append((status, payload))
        return handler, captured

    def test_valid_subdir_accepted_passes_to_resolve_frames(self):
        handler, captured = self._make_post_handler(
            {"prompt": "analyze", "frames": [], "subdir": "run-abc123"}
        )
        with patch.object(claude_bridge, "_resolve_frames", return_value=[]) as mock_resolve, \
             patch.object(claude_bridge, "_run_claude",
                          return_value={"ok": True, "result": "{}", "cost_usd": 0.0, "model": "x"}):
            handler.do_POST()
        mock_resolve.assert_called_once_with([], subdir="run-abc123")
        status, _ = captured[0]
        self.assertEqual(status, 200)

    def test_dotdot_subdir_returns_400(self):
        handler, captured = self._make_post_handler(
            {"prompt": "analyze", "frames": [], "subdir": "../etc/passwd"}
        )
        handler.do_POST()
        status, payload = captured[0]
        self.assertEqual(status, 400)
        self.assertIn("subdir", payload["error"])

    def test_slash_subdir_returns_400(self):
        handler, captured = self._make_post_handler(
            {"prompt": "analyze", "frames": [], "subdir": "run/evil"}
        )
        handler.do_POST()
        status, payload = captured[0]
        self.assertEqual(status, 400)

    def test_absent_subdir_calls_resolve_with_none(self):
        handler, captured = self._make_post_handler(
            {"prompt": "analyze", "frames": []}
        )
        with patch.object(claude_bridge, "_resolve_frames", return_value=[]) as mock_resolve, \
             patch.object(claude_bridge, "_run_claude",
                          return_value={"ok": True, "result": "{}", "cost_usd": 0.0, "model": "x"}):
            handler.do_POST()
        mock_resolve.assert_called_once_with([], subdir=None)


if __name__ == "__main__":
    unittest.main()
