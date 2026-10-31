import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from atm.common import STATUSES, item_row, parse_json, run_claude  # noqa: E402
from atm.db import init_atm_db  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402


def test_parse_json_fenced():
    assert parse_json('x ```json\n{"a": 1}\n``` y') == {"a": 1}


def test_parse_json_invalid_returns_none():
    assert parse_json("no json") is None
    assert parse_json(None) is None
    assert parse_json('{"a": ') is None


def test_parse_json_bare_object_with_prose():
    assert parse_json('Ini hasilnya: {"a": {"b": 2}} selesai') == {"a": {"b": 2}}


def test_run_claude_bridge_down_returns_none():
    with patch("httpx.post", side_effect=httpx.ConnectError("down")):
        assert run_claude("p", agent="t") is None


def test_run_claude_not_ok_returns_none():
    resp = MagicMock()
    resp.json.return_value = {"ok": False, "error": "x"}
    with patch("httpx.post", return_value=resp):
        assert run_claude("p", agent="t") is None


def test_run_claude_ok_returns_text_and_logs_usage():
    resp = MagicMock()
    resp.json.return_value = {"ok": True, "result": "hi", "raw_usage": {"output_tokens": 3}, "cost_usd": 0.1, "model": "m"}
    with patch("httpx.post", return_value=resp) as post, patch("main._log_api_usage") as log:
        assert run_claude("p", agent="t", subdir="d") == "hi"
    assert post.call_args.kwargs["json"]["subdir"] == "d"
    log.assert_called_once_with("t", "m", {"output_tokens": 3}, 0.1)


def test_statuses_order():
    assert STATUSES == ("idea", "blueprint", "shoot", "edit", "review", "ready", "scheduled", "posted", "monitored")


def test_item_row_serializes_datetimes_and_status():
    import datetime as dt
    from types import SimpleNamespace
    d = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    out = item_row([SimpleNamespace(name="id"), SimpleNamespace(name="stage"), SimpleNamespace(name="created_at")], (1, "idea", d))
    assert out == {"id": 1, "stage": "idea", "created_at": d.isoformat(), "status": "idea"}


def test_init_maps_legacy_stages_and_is_additive():
    conn = FakeConn()
    with patch("main._db_conn", return_value=conn):
        init_atm_db()
    updates = conn.sqls("UPDATE content_items SET stage")
    assert [p for _, p in updates] == [("blueprint", "script"), ("shoot", "prep")]
    assert all("IF NOT EXISTS" in s or s.startswith(("UPDATE", "INSERT")) for s, _ in conn.log)
    assert conn.commits == 1 and conn.closed


def test_init_without_db_is_noop():
    with patch("main._db_conn", return_value=None):
        init_atm_db()
