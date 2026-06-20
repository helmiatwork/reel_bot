# pipeline-api/test_dash_chat_sessions.py
# Hermetic tests for the /dash/chat/sessions, /dash/chat/session/{sid},
# and /dash/chat (session_key mode) endpoints.
# Uses a tmp directory for OPENCLAW_SESSIONS_DIR — no network, no real OpenClaw.

import json
import os
import time
import pytest
import httpx
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_UUID_1 = "aaaaaaaa-1111-4111-a111-aaaaaaaaaaaa"
FAKE_UUID_2 = "bbbbbbbb-2222-4222-b222-bbbbbbbbbbbb"


def write_session(path: Path, uuid: str, messages: list, model: str = "deepseek-v4-pro",
                  user_msg: str = None):
    """Write a minimal valid <uuid>.jsonl session file."""
    lines = [
        {"type": "session", "version": 3, "id": uuid, "timestamp": "2026-01-01T00:00:00.000Z",
         "cwd": "/root/.openclaw/workspace"},
        {"type": "model_change", "id": "aabbccdd", "parentId": None,
         "timestamp": "2026-01-01T00:00:01.000Z", "provider": "cliproxy", "modelId": model},
    ]
    # Add message turns
    parent = "aabbccdd"
    for i, m in enumerate(messages):
        mid = f"msg{i:04d}"
        role = m["role"]
        content = m["content"]
        # Content stored as list of {type,text} blocks (OpenClaw format)
        if isinstance(content, str):
            content_block = [{"type": "text", "text": content}]
        else:
            content_block = content
        turn = {
            "type": "message",
            "id": mid,
            "parentId": parent,
            "timestamp": f"2026-01-01T00:{i:02d}:00.000Z",
            "message": {
                "role": role,
                "content": content_block,
                "timestamp": 1000000 + i,
            },
        }
        if role == "assistant":
            turn["message"]["api"] = "openai-completions"
            turn["message"]["model"] = model
        lines.append(turn)
        parent = mid

    (path / f"{uuid}.jsonl").write_text(
        "\n".join(json.dumps(l) for l in lines) + "\n",
        encoding="utf-8"
    )


@pytest.fixture
def sessions_dir(tmp_path):
    """Temporary sessions directory with two session files."""
    d = tmp_path / "sessions"
    d.mkdir()

    # Session 1 — older (set mtime explicitly)
    write_session(d, FAKE_UUID_1, [
        {"role": "user", "content": "hello world this is a longer message for title"},
        {"role": "assistant", "content": "Hi there!"},
    ], model="deepseek-v4-pro")
    os.utime(str(d / f"{FAKE_UUID_1}.jsonl"), (1000000, 1000000))  # old

    # Session 2 — newer
    write_session(d, FAKE_UUID_2, [
        {"role": "user", "content": "short msg"},
        {"role": "assistant", "content": "Reply here."},
    ], model="gpt-5-nano")
    os.utime(str(d / f"{FAKE_UUID_2}.jsonl"), (2000000, 2000000))  # newer

    # Trajectory file (should be ignored)
    (d / f"{FAKE_UUID_1}.trajectory.jsonl").write_text(
        '{"type":"trajectory","id":"' + FAKE_UUID_1 + '"}\n', encoding="utf-8"
    )

    return d


@pytest.fixture
def client(sessions_dir):
    """TestClient with OPENCLAW_SESSIONS_DIR monkeypatched."""
    import main as m
    original = m.OPENCLAW_SESSIONS_DIR
    m.OPENCLAW_SESSIONS_DIR = str(sessions_dir)
    from fastapi.testclient import TestClient
    tc = TestClient(m.app)
    yield tc
    m.OPENCLAW_SESSIONS_DIR = original


# ── /dash/chat/sessions ───────────────────────────────────────────────────────

class TestListChatSessions:
    def test_returns_session_list(self, client):
        r = client.get("/dash/chat/sessions")
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 2

    def test_sorted_newest_first(self, client):
        data = client.get("/dash/chat/sessions").json()
        assert data["sessions"][0]["key"] == FAKE_UUID_2
        assert data["sessions"][1]["key"] == FAKE_UUID_1

    def test_title_from_first_user_message(self, client):
        data = client.get("/dash/chat/sessions").json()
        titles = {s["key"]: s["title"] for s in data["sessions"]}
        # FAKE_UUID_1 has a longer message — should be truncated to 48 chars
        assert titles[FAKE_UUID_1] == "hello world this is a longer message for title"[:48]
        assert titles[FAKE_UUID_2] == "short msg"

    def test_model_present(self, client):
        data = client.get("/dash/chat/sessions").json()
        by_key = {s["key"]: s for s in data["sessions"]}
        assert by_key[FAKE_UUID_1]["model"] == "deepseek-v4-pro"
        assert by_key[FAKE_UUID_2]["model"] == "gpt-5-nano"

    def test_trajectory_files_excluded(self, client):
        data = client.get("/dash/chat/sessions").json()
        keys = [s["key"] for s in data["sessions"]]
        # Should be exactly 2 sessions (trajectory file excluded)
        assert len(keys) == 2

    def test_empty_dir_returns_empty_list(self, tmp_path):
        import main as m
        empty = tmp_path / "empty"
        empty.mkdir()
        original = m.OPENCLAW_SESSIONS_DIR
        m.OPENCLAW_SESSIONS_DIR = str(empty)
        from fastapi.testclient import TestClient
        tc = TestClient(m.app)
        r = tc.get("/dash/chat/sessions")
        m.OPENCLAW_SESSIONS_DIR = original
        assert r.status_code == 200
        assert r.json() == {"sessions": []}

    def test_missing_dir_returns_empty_list(self, tmp_path):
        import main as m
        original = m.OPENCLAW_SESSIONS_DIR
        m.OPENCLAW_SESSIONS_DIR = str(tmp_path / "nonexistent")
        from fastapi.testclient import TestClient
        tc = TestClient(m.app)
        r = tc.get("/dash/chat/sessions")
        m.OPENCLAW_SESSIONS_DIR = original
        assert r.status_code == 200
        assert r.json() == {"sessions": []}

    def test_bad_jsonl_file_skipped(self, sessions_dir, client):
        """Corrupt session file should not crash the endpoint."""
        (sessions_dir / "badfile.jsonl").write_text(
            "{not valid json\n", encoding="utf-8"
        )
        r = client.get("/dash/chat/sessions")
        assert r.status_code == 200
        # Corrupt file produces no valid session_id so it's skipped
        assert len(r.json()["sessions"]) == 2


# ── /dash/chat/session/{sid} ──────────────────────────────────────────────────

class TestGetChatSession:
    def test_returns_ordered_messages(self, client):
        r = client.get(f"/dash/chat/session/{FAKE_UUID_1}")
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello world this is a longer message for title"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Hi there!"

    def test_path_traversal_rejected(self, client):
        # FastAPI normalizes /segment/../other to /other before routing,
        # so the router sees "foo" as the sid. "foo" fails the safe-sid
        # regex (too short / invalid chars) → 400. If the router collapses
        # it differently and misses the route entirely → 404. Both mean the
        # traversal payload never reached the filesystem.
        r = client.get("/dash/chat/session/../foo")
        assert r.status_code in (400, 404, 422)

    def test_path_traversal_with_double_dot_rejected(self, client):
        r = client.get("/dash/chat/session/..%2Ffoo")
        assert r.status_code in (400, 404, 422)

    def test_invalid_sid_rejected(self, client):
        r = client.get("/dash/chat/session/not-a-uuid!!!!")
        assert r.status_code == 400

    def test_unknown_sid_returns_404(self, client):
        r = client.get("/dash/chat/session/cccccccc-3333-4333-c333-cccccccccccc")
        assert r.status_code == 404

    def test_trajectory_sid_rejected(self, client, sessions_dir):
        """A sid that maps to a trajectory file should return 404."""
        # The trajectory file is {FAKE_UUID_1}.trajectory.jsonl — its "name"
        # would require the caller to pass sid={FAKE_UUID_1}.trajectory which
        # contains a dot and fails the safe-sid regex anyway.
        r = client.get(f"/dash/chat/session/{FAKE_UUID_1}.trajectory")
        assert r.status_code == 400

    def test_content_as_string_vs_list(self, tmp_path):
        """Session files where content is a plain string (not a block list)."""
        import main as m
        d = tmp_path / "sessions"
        d.mkdir()
        uuid = "cccccccc-4444-4444-c444-cccccccccccc"
        # Write file with string content (non-standard but tolerated)
        lines = [
            {"type": "session", "version": 3, "id": uuid,
             "timestamp": "2026-01-01T00:00:00.000Z", "cwd": "/"},
            {"type": "message", "id": "m0", "parentId": None,
             "timestamp": "2026-01-01T00:00:01.000Z",
             "message": {"role": "user", "content": "plain string content"}},
        ]
        (d / f"{uuid}.jsonl").write_text(
            "\n".join(json.dumps(l) for l in lines), encoding="utf-8"
        )
        original = m.OPENCLAW_SESSIONS_DIR
        m.OPENCLAW_SESSIONS_DIR = str(d)
        from fastapi.testclient import TestClient
        tc = TestClient(m.app)
        r = tc.get(f"/dash/chat/session/{uuid}")
        m.OPENCLAW_SESSIONS_DIR = original
        assert r.status_code == 200
        assert r.json()["messages"][0]["content"] == "plain string content"


# ── /dash/chat (session_key mode) ────────────────────────────────────────────

class TestDashChatSessionKey:
    """Verify that when session_key is set, the x-openclaw-session-key header
    is forwarded and ONLY the new message is sent (history is not resent)."""

    def test_session_key_header_forwarded(self, sessions_dir):
        """When session_key is in the request, x-openclaw-session-key must appear
        in the outgoing OpenClaw request, and full history must NOT be sent."""
        import main as m

        captured_headers = {}
        captured_payload = {}

        # We patch the httpx.AsyncClient.stream context manager to capture the
        # outgoing request without actually calling OpenClaw.
        class FakeResponse:
            status_code = 200
            async def aread(self):
                return b""
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"hi"}}]}'
                yield "data: [DONE]"
            async def __aenter__(self):
                return self
            async def __aexit__(self, *_):
                pass

        class FakeClient:
            def stream(self, method, url, headers=None, json=None, **kw):
                captured_headers.update(headers or {})
                captured_payload.update(json or {})
                return FakeResponse()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *_):
                pass

        original_sessions = m.OPENCLAW_SESSIONS_DIR
        original_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
        m.OPENCLAW_SESSIONS_DIR = str(sessions_dir)
        os.environ["OPENCLAW_GATEWAY_TOKEN"] = "test-token"

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            from fastapi.testclient import TestClient
            tc = TestClient(m.app)
            r = tc.post("/dash/chat", json={
                "message": "new question",
                "session_key": FAKE_UUID_1,
                "history": [
                    {"role": "user", "content": "old msg 1"},
                    {"role": "assistant", "content": "old reply 1"},
                ],
            })

        m.OPENCLAW_SESSIONS_DIR = original_sessions
        if original_token:
            os.environ["OPENCLAW_GATEWAY_TOKEN"] = original_token
        else:
            os.environ.pop("OPENCLAW_GATEWAY_TOKEN", None)

        # Header must be present
        assert "x-openclaw-session-key" in captured_headers, (
            "Expected x-openclaw-session-key header in outgoing request"
        )
        assert captured_headers["x-openclaw-session-key"] == FAKE_UUID_1

        # Only the new user message should be in messages — history NOT resent
        msgs = captured_payload.get("messages", [])
        assert len(msgs) == 1, f"Expected 1 message (no history), got {len(msgs)}: {msgs}"
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "new question"

    def test_no_session_key_sends_history(self, sessions_dir):
        """When session_key is absent, full history is forwarded (back-compat)."""
        import main as m

        captured_payload = {}

        class FakeResponse:
            status_code = 200
            async def aread(self): return b""
            async def aiter_lines(self):
                yield "data: [DONE]"
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass

        class FakeClient:
            def stream(self, method, url, headers=None, json=None, **kw):
                captured_payload.update(json or {})
                return FakeResponse()
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass

        original_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
        os.environ["OPENCLAW_GATEWAY_TOKEN"] = "test-token"

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            from fastapi.testclient import TestClient
            tc = TestClient(m.app)
            tc.post("/dash/chat", json={
                "message": "new msg",
                "history": [
                    {"role": "user", "content": "prior"},
                    {"role": "assistant", "content": "prior reply"},
                ],
            })

        if original_token:
            os.environ["OPENCLAW_GATEWAY_TOKEN"] = original_token
        else:
            os.environ.pop("OPENCLAW_GATEWAY_TOKEN", None)

        msgs = captured_payload.get("messages", [])
        # 2 history messages + 1 new message = 3 total
        assert len(msgs) == 3
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "new msg"


# ── DELETE /dash/chat/session/{sid} ──────────────────────────────────────────

class TestDeleteChatSession:
    def test_delete_removes_all_three_siblings(self, sessions_dir, client):
        """DELETE removes .jsonl, .trajectory.jsonl, .trajectory-path.json and returns deleted count."""
        # Add the trajectory-path.json sibling for FAKE_UUID_1
        (sessions_dir / f"{FAKE_UUID_1}.trajectory-path.json").write_text(
            '{"steps": []}', encoding="utf-8"
        )
        r = client.delete(f"/dash/chat/session/{FAKE_UUID_1}")
        assert r.status_code == 200
        data = r.json()
        assert data["sid"] == FAKE_UUID_1
        # Should have deleted .jsonl + .trajectory.jsonl + .trajectory-path.json = 3
        assert data["deleted"] == 3
        # Primary file must be gone
        assert not (sessions_dir / f"{FAKE_UUID_1}.jsonl").exists()
        # Trajectory siblings also gone
        assert not (sessions_dir / f"{FAKE_UUID_1}.trajectory.jsonl").exists()
        assert not (sessions_dir / f"{FAKE_UUID_1}.trajectory-path.json").exists()

    def test_deleted_session_absent_from_list(self, sessions_dir, client):
        """After DELETE the session no longer appears in GET /dash/chat/sessions."""
        client.delete(f"/dash/chat/session/{FAKE_UUID_1}")
        r = client.get("/dash/chat/sessions")
        keys = [s["key"] for s in r.json()["sessions"]]
        assert FAKE_UUID_1 not in keys
        # Other session still present
        assert FAKE_UUID_2 in keys

    def test_delete_nonexistent_sid_returns_404(self, client):
        """DELETE of an unknown (but valid-format) sid → 404."""
        unknown = "dddddddd-4444-4444-d444-dddddddddddd"
        r = client.delete(f"/dash/chat/session/{unknown}")
        assert r.status_code == 404

    def test_delete_path_traversal_dot_dot_slash(self, client):
        """DELETE with ../etc in sid → 400, nothing outside dir touched."""
        r = client.delete("/dash/chat/session/../../etc")
        assert r.status_code in (400, 404, 422)

    def test_delete_path_traversal_url_encoded(self, client):
        """DELETE with URL-encoded traversal → 400."""
        r = client.delete("/dash/chat/session/..%2Fetc%2Fpasswd")
        assert r.status_code in (400, 404, 422)

    def test_delete_slash_in_sid(self, client):
        """DELETE with a/b sid (contains slash) → 400 or routing miss."""
        r = client.delete("/dash/chat/session/a/b")
        assert r.status_code in (400, 404, 422)

    def test_delete_invalid_sid_characters(self, client):
        """DELETE with non-alnum/dash chars in sid → 400."""
        r = client.delete("/dash/chat/session/not-a-uuid!!!!")
        assert r.status_code == 400

    def test_delete_only_jsonl_exists_no_500(self, tmp_path):
        """DELETE when only .jsonl exists (no trajectory siblings) → success, deleted>=1."""
        import main as m
        d = tmp_path / "sessions"
        d.mkdir()
        uuid = "eeeeeeee-5555-4555-e555-eeeeeeeeeeee"
        write_session(d, uuid, [{"role": "user", "content": "solo"}])
        # Ensure no siblings exist
        assert not (d / f"{uuid}.trajectory.jsonl").exists()
        assert not (d / f"{uuid}.trajectory-path.json").exists()

        original = m.OPENCLAW_SESSIONS_DIR
        m.OPENCLAW_SESSIONS_DIR = str(d)
        from fastapi.testclient import TestClient
        tc = TestClient(m.app)
        r = tc.delete(f"/dash/chat/session/{uuid}")
        m.OPENCLAW_SESSIONS_DIR = original

        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] >= 1
        assert not (d / f"{uuid}.jsonl").exists()
