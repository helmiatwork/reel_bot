"""
Tests for _ytdlp_source_args helper.

Runnable two ways:
  - pytest test_ytdlp_source_args.py
  - python3 test_ytdlp_source_args.py        (assert-based fallback, no pytest needed)

Unit tests exercise the helper against env vars and temp files.
"""

import os
import tempfile
from pathlib import Path
import shutil

from main import _ytdlp_source_args


def test_ytdlp_source_args_basic():
    """Test that helper returns extractor-args for player_client."""
    # Save original env
    original_env = os.environ.copy()

    try:
        # Clear cookies env var
        if "YTDLP_COOKIES_FILE" in os.environ:
            del os.environ["YTDLP_COOKIES_FILE"]

        args = _ytdlp_source_args()

        # Should be a list
        assert isinstance(args, list), f"Expected list, got {type(args)}"

        # Should contain extractor-args
        assert "--extractor-args" in args, f"Missing --extractor-args in {args}"

        # Get index of --extractor-args and check the next element
        idx = args.index("--extractor-args")
        assert idx + 1 < len(args), "No value after --extractor-args"
        player_client_arg = args[idx + 1]

        # Should have player_client with fallback chain
        assert "youtube:player_client=android" in player_client_arg, \
            f"Expected android in {player_client_arg}"
        assert "web_safari" in player_client_arg, \
            f"Expected web_safari in {player_client_arg}"
        assert "ios" in player_client_arg, \
            f"Expected ios in {player_client_arg}"

        # Should NOT have cookies args if env var unset
        assert "--cookies" not in args, f"Should not have --cookies when env unset, got {args}"

    finally:
        # Restore original env
        os.environ.clear()
        os.environ.update(original_env)


def test_ytdlp_source_args_with_cookies():
    """Test that helper includes cookies when YTDLP_COOKIES_FILE is set."""
    # Save original env
    original_env = os.environ.copy()

    tmp_dir = tempfile.mkdtemp()
    try:
        # Create a fake cookies file
        cookies_file = Path(tmp_dir) / "cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\ttest\tvalue\n")

        # Set env var
        os.environ["YTDLP_COOKIES_FILE"] = str(cookies_file)

        args = _ytdlp_source_args()

        # Should have --cookies
        assert "--cookies" in args, f"Expected --cookies in {args}"

        # Get the path after --cookies
        idx = args.index("--cookies")
        assert idx + 1 < len(args), "No path after --cookies"
        cookies_path = args[idx + 1]

        # Should be a valid path
        assert Path(cookies_path).exists(), f"Cookies file not found at {cookies_path}"

        # Should still have extractor-args
        assert "--extractor-args" in args, f"Missing --extractor-args in {args}"

    finally:
        # Restore original env
        os.environ.clear()
        os.environ.update(original_env)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_ytdlp_source_args_nonexistent_cookies():
    """Test that helper skips cookies if file doesn't exist."""
    # Save original env
    original_env = os.environ.copy()

    try:
        # Set env var to nonexistent file
        os.environ["YTDLP_COOKIES_FILE"] = "/nonexistent/cookies.txt"

        args = _ytdlp_source_args()

        # Should NOT have --cookies if file doesn't exist
        assert "--cookies" not in args, f"Should not have --cookies for nonexistent file, got {args}"

        # But should still have extractor-args
        assert "--extractor-args" in args, f"Missing --extractor-args in {args}"

    finally:
        # Restore original env
        os.environ.clear()
        os.environ.update(original_env)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
