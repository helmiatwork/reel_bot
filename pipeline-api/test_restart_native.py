"""B1 regression tests: _restart_one must not interpolate repo_root into the command string."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import main as _m


def _call_restart_one(service: str, fake_root: Path):
    """Call _restart_one with _REPO_ROOT monkeypatched to fake_root."""
    captured = {}

    original_popen = subprocess.Popen

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        mock = MagicMock()
        return mock

    with patch.object(_m, "_REPO_ROOT", fake_root):
        with patch("subprocess.Popen", side_effect=fake_popen):
            with patch("subprocess.run"):  # swallow pkill
                result = _m._restart_one(service)

    return result, captured


def test_b1_shell_false():
    """Popen must never be called with shell=True."""
    root = Path("/tmp/reelbot")
    _, cap = _call_restart_one("cliproxy", root)
    assert cap["kwargs"].get("shell") is not True, "shell=True would allow injection"


def test_b1_static_command_no_root_in_argv():
    """The repo root path must NOT appear anywhere inside the bash -c command string."""
    root = Path("/tmp/reelbot")
    _, cap = _call_restart_one("cliproxy", root)
    cmd_str = cap["argv"][2]  # bash -c <this>
    assert str(root) not in cmd_str, (
        f"repo root leaked into command string: {cmd_str!r}"
    )


def test_b1_cwd_carries_root():
    """cwd kwarg must equal _REPO_ROOT so relative paths resolve correctly."""
    root = Path("/tmp/reelbot")
    _, cap = _call_restart_one("cliproxy", root)
    assert cap["kwargs"]["cwd"] == str(root)


def test_b1_path_with_space_does_not_corrupt_command():
    """A repo root with spaces must not word-split into the command string."""
    root = Path("/home/user/my projects/reelbot")
    _, cap = _call_restart_one("cliproxy", root)
    cmd_str = cap["argv"][2]
    # The space-containing path must NOT appear in the command — only in cwd
    assert "my projects" not in cmd_str, (
        f"space in path leaked into command: {cmd_str!r}"
    )
    assert cap["kwargs"]["cwd"] == str(root)


def test_b1_arcreel_static():
    """arcreel command is also static — no repo root in command string."""
    root = Path("/srv/reelbot")
    _, cap = _call_restart_one("arcreel", root)
    cmd_str = cap["argv"][2]
    assert str(root) not in cmd_str
    assert cap["kwargs"]["cwd"] == str(root)


def test_b1_returns_restarted():
    root = Path("/tmp/reelbot")
    result, _ = _call_restart_one("cliproxy", root)
    assert result == {"status": "restarted"}


if __name__ == "__main__":
    import sys
    tests = [
        test_b1_shell_false,
        test_b1_static_command_no_root_in_argv,
        test_b1_cwd_carries_root,
        test_b1_path_with_space_does_not_corrupt_command,
        test_b1_arcreel_static,
        test_b1_returns_restarted,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
    sys.exit(failed)
