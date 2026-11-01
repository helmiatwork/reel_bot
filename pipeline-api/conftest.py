import httpx
import pytest

import claude_runner


@pytest.fixture(autouse=True)
def _claude_runner_through_httpx_post(request, monkeypatch):
    """Route claude_runner.run through httpx.post so tests that mock the old HTTP bridge call
    keep working and never spawn a real `claude`. A test with no mock fails like "bridge down".

    shortcut: test seam only; new tests should patch claude_runner.run directly.
    """
    if request.module.__name__ == "test_claude_runner":
        return  # that file tests the real run()
    monkeypatch.setattr(claude_runner, "run", lambda payload: httpx.post("claude-runner://run", json=payload).json())
