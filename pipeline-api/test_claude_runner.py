# pipeline-api/test_claude_runner.py
# Offline unit tests for claude_runner.py.
# Mocks subprocess.run - no real claude calls are made.

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))
import claude_runner

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
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames(["../secret.txt"])
            self.assertEqual(result, [], "Path with .. must be rejected")
        finally:
            claude_runner.FRAME_DIR = orig

    def test_double_dot_rejected(self):
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames(["../../etc/passwd"])
            self.assertEqual(result, [], "Path with / must be rejected")
        finally:
            claude_runner.FRAME_DIR = orig

    def test_valid_basename_resolved(self):
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames([self.frame_name])
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0].endswith(self.frame_name))
        finally:
            claude_runner.FRAME_DIR = orig

    def test_nonexistent_file_skipped(self):
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames(["ghost_frame.jpg"])
            self.assertEqual(result, [])
        finally:
            claude_runner.FRAME_DIR = orig

    def test_empty_list_returns_empty(self):
        result = claude_runner._resolve_frames([])
        self.assertEqual(result, [])

    def test_none_returns_empty(self):
        result = claude_runner._resolve_frames(None)
        self.assertEqual(result, [])


# ── subprocess argv (never shell=True) ────────────────────────────────────────

class TestSubprocessArgv(unittest.TestCase):
    def test_argv_list_not_shell(self):
        """subprocess.run must be called with a list argv, not a shell string."""
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("test prompt", [], "claude-sonnet-5-5", 10)
        args, kwargs = mock_run.call_args
        argv = args[0]
        self.assertIsInstance(argv, list, "argv must be a list")
        self.assertNotIn("shell", kwargs, "shell kwarg must not be set to True")
        # Or if shell is explicitly set, must be False
        if "shell" in kwargs:
            self.assertFalse(kwargs["shell"])

    def test_env_drops_anthropic_vars(self):
        env = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "k", "ANTHROPIC_BASE_URL": "u", "DATABASE_URL": "d"}
        with patch.dict("os.environ", env, clear=True), \
             patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("test", [], "claude-sonnet-5-5", 10)
        self.assertEqual(mock_run.call_args.kwargs["env"], {"PATH": "/usr/bin", "DATABASE_URL": "d"})

    def test_model_in_argv(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("test", [], "claude-opus-5-5", 10)
        argv = mock_run.call_args[0][0]
        self.assertIn("claude-opus-5-5", argv)

    def test_output_format_json_in_argv(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("test", [], "claude-sonnet-5-5", 10)
        argv = mock_run.call_args[0][0]
        self.assertIn("--output-format", argv)
        idx = argv.index("--output-format")
        self.assertEqual(argv[idx + 1], "json")

    def test_prompt_in_argv(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("my test prompt", [], "claude-sonnet-5-5", 10)
        argv = mock_run.call_args[0][0]
        self.assertIn("-p", argv)
        idx = argv.index("-p")
        self.assertIn("my test prompt", argv[idx + 1])

    def test_text_only_job_gets_no_tools(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("test", [], "claude-sonnet-5-5", 10)
        argv = mock_run.call_args[0][0]
        idx = argv.index("--tools")
        self.assertEqual(argv[idx + 1], "")
        self.assertNotIn("--allowedTools", argv)
        self.assertIn("--strict-mcp-config", argv)

    def test_frame_job_read_scoped_to_frame_dir(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("test", ["/x/frame_000.jpg"], "claude-sonnet-5-5", 10)
        argv = mock_run.call_args[0][0]
        self.assertEqual(argv[argv.index("--tools") + 1], "Read")
        self.assertEqual(argv[argv.index("--allowedTools") + 1],
                         f"Read(/{claude_runner.FRAME_DIR}/**)")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "")

    def test_effort_flag_only_when_given(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("t", [], "claude-haiku-5-5", 10, "high")
        argv = mock_run.call_args[0][0]
        self.assertEqual(argv[argv.index("--effort") + 1], "high")
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("t", [], "claude-haiku-5-5", 10)
        self.assertNotIn("--effort", mock_run.call_args[0][0])


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
            result = claude_runner._run_claude("test", [], "claude-sonnet-5-5", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "rate_limit")

    def test_rate_limit_in_stderr(self):
        with patch("subprocess.run", return_value=_completed(
            stdout="", stderr="Error: rate limit exceeded, try again", returncode=1
        )):
            result = claude_runner._run_claude("test", [], "claude-sonnet-5-5", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "rate_limit")

    def test_overloaded_phrase_detected(self):
        with patch("subprocess.run", return_value=_completed(
            stdout="", stderr="Claude is overloaded right now", returncode=1
        )):
            result = claude_runner._run_claude("test", [], "claude-sonnet-5-5", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "rate_limit")

    def test_too_many_requests_detected(self):
        with patch("subprocess.run", return_value=_completed(
            stdout="", stderr="too many requests", returncode=1
        )):
            result = claude_runner._run_claude("test", [], "claude-sonnet-5-5", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "rate_limit")

    def test_normal_error_not_rate_limit(self):
        with patch("subprocess.run", return_value=_completed(
            stdout="", stderr="Error: some other problem", returncode=1
        )):
            result = claude_runner._run_claude("test", [], "claude-sonnet-5-5", 30)
        self.assertFalse(result["ok"])
        self.assertNotEqual(result.get("error_type"), "rate_limit")


# ── Successful claude run parsing ─────────────────────────────────────────────

class TestClaudeRunSuccess(unittest.TestCase):
    def test_ok_true_on_success(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)):
            result = claude_runner._run_claude("hi", [], "claude-sonnet-5-5", 30)
        self.assertTrue(result["ok"])

    def test_result_extracted(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)):
            result = claude_runner._run_claude("hi", [], "claude-sonnet-5-5", 30)
        self.assertIn("hook", result["result"])

    def test_cost_usd_extracted(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)):
            result = claude_runner._run_claude("hi", [], "claude-sonnet-5-5", 30)
        self.assertAlmostEqual(result["cost_usd"], 0.012)

    def test_model_in_response(self):
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)):
            result = claude_runner._run_claude("hi", [], "claude-sonnet-5-5", 30)
        self.assertEqual(result["model"], "claude-sonnet-5-5")

    def test_is_error_true_returns_failure(self):
        payload = json.dumps({
            "result": "something went wrong",
            "is_error": True,
            "total_cost_usd": 0.0,
            "usage": {},
        })
        with patch("subprocess.run", return_value=_completed(payload)):
            result = claude_runner._run_claude("hi", [], "claude-sonnet-5-5", 30)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "claude_error")

    def test_timeout_returns_failure(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            result = claude_runner._run_claude("hi", [], "claude-sonnet-5-5", 5)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "timeout")

    def test_missing_claude_binary_returns_json_error(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("claude")):
            result = claude_runner._run_claude("hi", [], "claude-sonnet-5-5", 5)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error_type"), "claude_error")

    def test_frames_appended_to_prompt(self):
        """Frame paths must be appended to the final prompt sent to claude."""
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("base prompt", ["/tmp/f1.jpg", "/tmp/f2.jpg"],
                                      "claude-sonnet-5-5", 30)
        argv = mock_run.call_args[0][0]
        idx = argv.index("-p")
        final_prompt = argv[idx + 1]
        self.assertIn("/tmp/f1.jpg", final_prompt)
        self.assertIn("/tmp/f2.jpg", final_prompt)
        self.assertIn("Gambar untuk dianalisa", final_prompt)

    def test_no_frames_no_appended_section(self):
        """When no frames provided, the prompt should NOT have the frame section."""
        with patch("subprocess.run", return_value=_completed(_GOOD_CLAUDE_JSON)) as mock_run:
            claude_runner._run_claude("clean prompt", [], "claude-sonnet-5-5", 30)
        argv = mock_run.call_args[0][0]
        idx = argv.index("-p")
        final_prompt = argv[idx + 1]
        self.assertNotIn("Gambar untuk dianalisa", final_prompt)


# ── is_rate_limit helper ──────────────────────────────────────────────────────

class TestIsRateLimit(unittest.TestCase):
    def test_usage_limit_phrase(self):
        self.assertTrue(claude_runner._is_rate_limit("Error: usage limit reached"))

    def test_rate_limit_phrase(self):
        self.assertTrue(claude_runner._is_rate_limit("rate limit exceeded"))

    def test_ratelimit_combined(self):
        self.assertTrue(claude_runner._is_rate_limit("ratelimitError"))

    def test_overloaded(self):
        self.assertTrue(claude_runner._is_rate_limit("Claude is overloaded"))

    def test_normal_error_not_rate_limit(self):
        self.assertFalse(claude_runner._is_rate_limit("file not found"))

    def test_empty_string(self):
        self.assertFalse(claude_runner._is_rate_limit(""))

    def test_case_insensitive(self):
        self.assertTrue(claude_runner._is_rate_limit("RATE LIMIT"))


# ── Subdir validation and resolution ─────────────────────────────────────────

class TestSubdirValidation(unittest.TestCase):
    def test_valid_subdir_accepted(self):
        self.assertTrue(claude_runner._validate_subdir("abc123"))
        self.assertTrue(claude_runner._validate_subdir("run-001"))
        self.assertTrue(claude_runner._validate_subdir("A_B_C"))
        self.assertTrue(claude_runner._validate_subdir("a1b2c3d4"))

    def test_slash_subdir_rejected(self):
        self.assertFalse(claude_runner._validate_subdir("run/evil"))

    def test_backslash_subdir_rejected(self):
        self.assertFalse(claude_runner._validate_subdir("run\\evil"))

    def test_dotdot_subdir_rejected(self):
        self.assertFalse(claude_runner._validate_subdir("../secret"))

    def test_dotfile_subdir_rejected(self):
        self.assertFalse(claude_runner._validate_subdir(".hidden"))

    def test_empty_string_rejected(self):
        self.assertFalse(claude_runner._validate_subdir(""))

    def test_none_rejected(self):
        # _validate_subdir(None) should return False — None is not a valid subdir
        self.assertFalse(claude_runner._validate_subdir(None))

    def test_space_rejected(self):
        self.assertFalse(claude_runner._validate_subdir("run 001"))

    def test_dots_only_rejected(self):
        self.assertFalse(claude_runner._validate_subdir("..."))


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
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames([self.frame_name], subdir=self.subdir_name)
            self.assertEqual(len(result), 1)
            expected = str(Path(self.tmp) / self.subdir_name / self.frame_name)
            self.assertEqual(result[0], expected)
        finally:
            claude_runner.FRAME_DIR = orig

    def test_subdir_does_not_find_root_frames(self):
        """A frame in the root dir must NOT be returned when subdir is given."""
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames(["root_frame.jpg"], subdir=self.subdir_name)
            self.assertEqual(result, [], "Root frame must not be found via subdir lookup")
        finally:
            claude_runner.FRAME_DIR = orig

    def test_no_subdir_resolves_root_frame(self):
        """Without subdir, frames are resolved under the root FRAME_DIR."""
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames(["root_frame.jpg"])
            self.assertEqual(len(result), 1)
        finally:
            claude_runner.FRAME_DIR = orig

    def test_dotdot_subdir_returns_empty(self):
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames([self.frame_name], subdir="../etc")
            self.assertEqual(result, [], "../ subdir must be rejected")
        finally:
            claude_runner.FRAME_DIR = orig

    def test_slash_subdir_returns_empty(self):
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames([self.frame_name], subdir="/absolute/path")
            self.assertEqual(result, [], "Absolute path subdir must be rejected")
        finally:
            claude_runner.FRAME_DIR = orig

    def test_dotfile_subdir_returns_empty(self):
        orig = claude_runner.FRAME_DIR
        claude_runner.FRAME_DIR = Path(self.tmp)
        try:
            result = claude_runner._resolve_frames([self.frame_name], subdir=".hidden")
            self.assertEqual(result, [], "Dotfile subdir must be rejected")
        finally:
            claude_runner.FRAME_DIR = orig



# ── run() validation and wiring ───────────────────────────────────────────────

_OK = {"ok": True, "result": "{}", "cost_usd": 0.0, "model": "x"}


class TestRunPayload(unittest.TestCase):
    def test_missing_prompt_rejected(self):
        result = claude_runner.run({"frames": []})
        self.assertFalse(result["ok"])
        self.assertIn("prompt", result["error"])

    def test_blank_prompt_rejected(self):
        self.assertFalse(claude_runner.run({"prompt": "   "})["ok"])

    def test_old_model_rejected(self):
        with patch.object(claude_runner, "_run_claude") as run:
            result = claude_runner.run({"prompt": "analyze", "frames": [], "model": "claude-sonnet-4-6"})
        self.assertFalse(result["ok"])
        self.assertIn("model", result["error"])
        run.assert_not_called()

    def test_bad_effort_rejected(self):
        with patch.object(claude_runner, "_run_claude") as run:
            result = claude_runner.run({"prompt": "analyze", "effort": "turbo"})
        self.assertFalse(result["ok"])
        run.assert_not_called()

    def test_bad_timeout_rejected_without_raising(self):
        result = claude_runner.run({"prompt": "analyze", "timeout_s": "soon"})
        self.assertFalse(result["ok"])

    def test_default_effort_per_model(self):
        for model, want in (("claude-haiku-5-5", "high"), ("claude-sonnet-5-5", "low"), ("claude-opus-5-5", None)):
            with patch.object(claude_runner, "_run_claude", return_value=_OK) as run:
                claude_runner.run({"prompt": "analyze", "model": model})
            self.assertEqual(run.call_args[0][4], want, model)

    def test_effort_passed_to_run_claude(self):
        with patch.object(claude_runner, "_run_claude", return_value=_OK) as run:
            claude_runner.run({"prompt": "analyze", "model": "claude-haiku-5-5", "effort": "xhigh"})
        self.assertEqual(run.call_args[0][4], "xhigh")

    def test_valid_subdir_passed_to_resolve_frames(self):
        with patch.object(claude_runner, "_resolve_frames", return_value=[]) as resolve, \
             patch.object(claude_runner, "_run_claude", return_value=_OK):
            result = claude_runner.run({"prompt": "analyze", "frames": [], "subdir": "run-abc123"})
        resolve.assert_called_once_with([], subdir="run-abc123")
        self.assertTrue(result["ok"])

    def test_absent_subdir_resolves_with_none(self):
        with patch.object(claude_runner, "_resolve_frames", return_value=[]) as resolve, \
             patch.object(claude_runner, "_run_claude", return_value=_OK):
            claude_runner.run({"prompt": "analyze", "frames": []})
        resolve.assert_called_once_with([], subdir=None)

    def test_dotdot_subdir_rejected(self):
        with patch.object(claude_runner, "_run_claude") as run:
            result = claude_runner.run({"prompt": "analyze", "subdir": "../etc/passwd"})
        self.assertFalse(result["ok"])
        self.assertIn("subdir", result["error"])
        run.assert_not_called()

    def test_slash_subdir_rejected(self):
        self.assertFalse(claude_runner.run({"prompt": "analyze", "subdir": "run/evil"})["ok"])

    def test_non_string_subdir_rejected(self):
        self.assertFalse(claude_runner.run({"prompt": "analyze", "subdir": ["a"]})["ok"])

    def test_frames_requested_none_resolved_is_frames_missing(self):
        with patch.object(claude_runner, "_resolve_frames", return_value=[]), \
             patch.object(claude_runner, "_run_claude") as run:
            result = claude_runner.run({"prompt": "p", "frames": ["a.jpg"]})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "frames_missing")
        run.assert_not_called()

    def test_frames_resolved_runs_claude(self):
        with patch.object(claude_runner, "_resolve_frames", return_value=["/x/a.jpg"]), \
             patch.object(claude_runner, "_run_claude", return_value=_OK) as run:
            result = claude_runner.run({"prompt": "p", "frames": ["a.jpg"]})
        self.assertTrue(result["ok"])
        self.assertEqual(run.call_args[0][1], ["/x/a.jpg"])

    def test_rate_limit_result_passed_through(self):
        rl = {"ok": False, "error": "rate limit", "error_type": "rate_limit"}
        with patch.object(claude_runner, "_run_claude", return_value=rl):
            self.assertEqual(claude_runner.run({"prompt": "test"}), rl)


# ── Concurrency cap (MAX_CONCURRENT semaphore) ────────────────────────────────

class TestHostSlot(unittest.TestCase):
    def test_waits_for_slot_held_by_another_open_file(self):
        """A slot flock'd through another fd (as another process would) blocks until released."""
        import fcntl
        with tempfile.TemporaryDirectory() as d, \
             patch.object(claude_runner, "SLOT_DIR", Path(d)), \
             patch.object(claude_runner, "MAX_CONCURRENT", 1):
            holder = open(Path(d) / "slot-0.lock", "w")
            fcntl.flock(holder, fcntl.LOCK_EX)
            entered = threading.Event()

            def _go():
                with claude_runner._host_slot():
                    entered.set()

            t = threading.Thread(target=_go, daemon=True)
            t.start()
            self.assertFalse(entered.wait(0.5), "must wait while the slot is held")
            holder.close()
            self.assertTrue(entered.wait(2), "must enter once the slot is released")
            t.join(2)


def _run_concurrently(payloads, join_timeout=5):
    """Call run() for each payload in its own thread; return (errors, still_alive, results)."""
    errors, results = [], []

    def _go(payload):
        try:
            results.append(claude_runner.run(payload))
        except BaseException as exc:  # surface thread failures in the test
            errors.append(exc)

    threads = [threading.Thread(target=_go, args=(p,), daemon=True) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join(join_timeout)
    return errors, [t for t in threads if t.is_alive()], results


class TestConcurrencyCap(unittest.TestCase):
    def test_cap_1_never_runs_two_claude_calls_at_once(self):
        # Barrier(2) passes only when two calls are inside _run_claude together.
        # At cap 1 no second party ever arrives, so every wait must break on timeout.
        barrier = threading.Barrier(2, timeout=0.5)
        lock = threading.Lock()
        active = {"now": 0, "max": 0}
        outcomes = []

        def _fake_run(prompt, frame_paths, model, timeout_s, effort=None):
            with lock:
                active["now"] += 1
                active["max"] = max(active["max"], active["now"])
            try:
                barrier.wait()
                outcome = "passed"
            except threading.BrokenBarrierError:
                outcome = "broken"
            finally:
                with lock:
                    active["now"] -= 1
            with lock:
                outcomes.append(outcome)
            return _OK

        with patch.object(claude_runner, "_RUN_SLOTS", threading.BoundedSemaphore(1)), \
             patch.object(claude_runner, "_run_claude", side_effect=_fake_run):
            errors, alive, _ = _run_concurrently([{"prompt": f"p{i}"} for i in range(2)])
        self.assertEqual(errors, [])
        self.assertEqual(alive, [])
        self.assertEqual(outcomes, ["broken", "broken"], "no barrier may pass at cap 1")
        self.assertEqual(active["max"], 1)

    def test_cap_2_allows_two_claude_calls_at_once(self):
        # Barrier(2) only passes when both calls are inside _run_claude together.
        barrier = threading.Barrier(2, timeout=5)
        lock = threading.Lock()
        active = {"now": 0, "max": 0}

        def _fake_run(prompt, frame_paths, model, timeout_s, effort=None):
            with lock:
                active["now"] += 1
                active["max"] = max(active["max"], active["now"])
            try:
                barrier.wait()
            finally:
                with lock:
                    active["now"] -= 1
            return _OK

        with patch.object(claude_runner, "_RUN_SLOTS", threading.BoundedSemaphore(2)), \
             patch.object(claude_runner, "_run_claude", side_effect=_fake_run):
            errors, alive, _ = _run_concurrently([{"prompt": f"p{i}"} for i in range(2)])
        self.assertEqual(errors, [])
        self.assertEqual(alive, [])
        self.assertEqual(active["max"], 2)

    def test_invalid_request_returns_error_while_slots_are_held(self):
        slots = threading.BoundedSemaphore(1)
        slots.acquire()  # cap fully held by another caller
        try:
            with patch.object(claude_runner, "_RUN_SLOTS", slots), \
                 patch.object(claude_runner, "_run_claude") as run:
                errors, alive, results = _run_concurrently([{"prompt": "   "}])
        finally:
            slots.release()
        self.assertEqual(errors, [])
        self.assertEqual(alive, [], "validation must not wait for a slot")
        self.assertFalse(results[0]["ok"])
        run.assert_not_called()

    def test_valid_request_waits_for_a_free_slot(self):
        slots = threading.BoundedSemaphore(1)
        entered = threading.Event()
        calls = []

        def _fake_run(prompt, frame_paths, model, timeout_s, effort=None):
            calls.append(prompt)
            entered.set()
            return _OK

        results = []
        slots.acquire()
        with patch.object(claude_runner, "_RUN_SLOTS", slots), \
             patch.object(claude_runner, "_run_claude", side_effect=_fake_run):
            t = threading.Thread(target=lambda: results.append(claude_runner.run({"prompt": "analyze"})), daemon=True)
            t.start()
            self.assertFalse(entered.wait(0.3), "request must wait while cap is full")
            slots.release()
            self.assertTrue(entered.wait(5), "request must run once a slot frees")
            t.join(5)
            self.assertFalse(t.is_alive())
        self.assertEqual(len(calls), 1)
        self.assertTrue(results[0]["ok"])

    def _cap_in_fresh_interpreter(self, env):
        out = subprocess.run(
            [sys.executable, "-c", "import claude_runner as b; print(b.MAX_CONCURRENT)"],
            cwd=str(Path(__file__).parent), env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def test_env_clamps_cap_to_at_least_one(self):
        self.assertEqual(self._cap_in_fresh_interpreter(dict(os.environ, CLAUDE_MAX_CONCURRENT="0")), "1")

    def test_default_cap_is_two(self):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_MAX_CONCURRENT"}
        self.assertEqual(self._cap_in_fresh_interpreter(env), "2")


if __name__ == "__main__":
    unittest.main()
