import datetime as dt
import sys
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from atm import schedule  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
WIB = ZoneInfo("Asia/Jakarta")


def test_next_slots_mon_wed_fri_jakarta():
    after = dt.datetime(2026, 10, 30, 20, 0, tzinfo=WIB)  # Friday evening, past the 19:00 slot
    got = schedule.next_slots([0, 2, 4], "19:00", "Asia/Jakarta", after, 3, set())
    assert [g.isoformat() for g in got] == ["2026-11-02T19:00:00+07:00", "2026-11-04T19:00:00+07:00",
                                            "2026-11-06T19:00:00+07:00"]


def test_next_slots_skips_taken():
    after = dt.datetime(2026, 10, 30, 20, 0, tzinfo=WIB)
    taken = {dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.timezone.utc)}  # = Mon 19:00 WIB
    got = schedule.next_slots([0, 2, 4], "19:00", "Asia/Jakarta", after, 2, taken)
    assert [g.day for g in got] == [4, 6]


def _it(i, status, sched=None):
    return {"id": i, "title": f"t{i}", "status": status, "scheduled_at": sched}


def test_today_tasks_rules():
    now = dt.datetime(2026, 11, 2, 9, 0, tzinfo=WIB)
    soon = (now + dt.timedelta(days=2)).isoformat()
    far = (now + dt.timedelta(days=9)).isoformat()
    tonight = dt.datetime(2026, 11, 2, 19, 0, tzinfo=WIB).isoformat()
    items = [_it(1, "blueprint", soon), _it(2, "blueprint", far), _it(3, "edit"), _it(4, "review"),
             _it(5, "ready", tonight), _it(6, "scheduled", soon), _it(7, "posted", tonight)]
    got = {t["item_id"]: t["action"] for t in schedule.today_tasks(items, now)}
    assert got == {1: "shoot", 3: "edit", 4: "evaluate", 5: "upload"}


class _ClaimConn(FakeConn):
    """Stateful: SELECT returns only unclaimed rows; UPDATE ... IS NULL RETURNING claims once."""

    def __init__(self, sched):
        super().__init__()
        self.sched, self.claimed = sched, set()

    def cursor(self):
        conn = self

        class Cur:
            description = []
            _rows = []

            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def execute(s, sql, params=()):
                s._rows = []
                if "FROM routine_settings" in sql:
                    s._rows = [([0], "19:00", "Asia/Jakarta")]
                elif sql.startswith("SELECT id, title"):
                    col = "d1" if "reminded_d1_at" in sql else "d0"
                    if col == "d1":  # fixture item is only "today", never inside the H-1 window
                        return
                    s._rows = [(1, "Kucing", conn.sched)] if (1, col) not in conn.claimed else []
                elif "IS NULL RETURNING" in sql:
                    key = (params[0], "d0" if "reminded_d0_at" in sql else "d1")
                    if key not in conn.claimed:
                        conn.claimed.add(key)
                        s._rows = [(params[0],)]
                elif "= NULL WHERE" in sql:
                    conn.claimed.discard((params[0], "d0" if "reminded_d0_at" in sql else "d1"))

            def fetchone(s):
                return s._rows[0] if s._rows else None

            def fetchall(s):
                return s._rows
        return Cur()


def test_reminders_not_sent_twice():
    now = dt.datetime(2026, 11, 2, 9, 0, tzinfo=WIB)
    conn = _ClaimConn(dt.datetime(2026, 11, 2, 19, 0, tzinfo=WIB))
    with patch("main._db_conn", return_value=conn), patch("main._telegram_notify", return_value=True) as tg:
        assert schedule.send_reminders(now) == 1
        assert schedule.send_reminders(now) == 0
    assert tg.call_count == 1


def test_failed_telegram_releases_claim():
    now = dt.datetime(2026, 11, 2, 9, 0, tzinfo=WIB)
    conn = _ClaimConn(dt.datetime(2026, 11, 2, 19, 0, tzinfo=WIB))
    with patch("main._db_conn", return_value=conn), patch("main._telegram_notify", return_value=False):
        assert schedule.send_reminders(now) == 0
    assert conn.claimed == set()


def test_tick_survives_job_exception():
    with patch("atm.schedule.send_reminders", side_effect=RuntimeError("boom")):
        r = client.post("/atm/cron/tick")
    assert r.status_code == 200
    assert r.json() == {"reminders": 0, "monitor": {}, "post_evals": 0, "errors": ["reminders"]}


def test_tick_returns_reminder_count():
    with patch("atm.schedule.send_reminders", return_value=2):
        assert client.post("/atm/cron/tick").json()["reminders"] == 2


def test_tick_requires_admin_key_when_set(monkeypatch):
    monkeypatch.setenv("PIPELINE_API_KEY", "s3cret")
    with patch("atm.schedule.send_reminders", return_value=0):
        assert client.post("/atm/cron/tick").status_code == 401
        assert client.post("/atm/cron/tick", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_autofill_assigns_free_slots_and_ready_becomes_scheduled():
    conn = FakeConn([
        ("FROM routine_settings", (["weekdays", "post_time", "tz"], [([0, 1, 2, 3, 4, 5, 6], "19:00", "Asia/Jakarta")])),
        ("SELECT scheduled_at FROM", (["s"], [])),
        ("SELECT id FROM content_items", (["id"], [(4,), (9,)])),
        ("UPDATE content_items", (["id"], [(1,)])),
    ])
    with patch("main._db_conn", return_value=conn):
        r = client.post("/atm/schedule/autofill")
    assert r.status_code == 200
    assert [a["item_id"] for a in r.json()["assigned"]] == [4, 9]
    ups = conn.sqls("UPDATE content_items")
    assert len(ups) == 2 and "WHEN stage = 'ready' THEN 'scheduled'" in ups[0][0]
    assert conn.commits == 1


def test_today_endpoint_shape():
    conn = FakeConn([
        ("FROM routine_settings", (["weekdays", "post_time", "tz"], [([0], "19:00", "Asia/Jakarta")])),
        ("FROM content_items WHERE stage", (["id", "title", "stage", "scheduled_at"], [(1, "A", "edit", None)])),
        ("FROM monitor_snapshots", (["content_item_id", "title"], [(2, "B")])),
    ])
    with patch("main._db_conn", return_value=conn):
        r = client.get("/atm/today")
    body = r.json()
    assert r.status_code == 200
    assert body["tasks"][0]["action"] == "edit" and body["alerts"][0]["title"] == "B" and body["upcoming"] == []
