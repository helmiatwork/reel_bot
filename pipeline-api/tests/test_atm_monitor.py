import datetime as dt
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from atm import monitor  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


class StateConn(FakeConn):
    """Remembers inserted snapshots: the unique (item, checkpoint) insert returns a row only the first time."""

    def __init__(self, items, baseline_rows=()):
        super().__init__([("SELECT alert_ratio", (["r"], [(0.5,)])),
                          ("SELECT id, title, published_url", (["a"] * 4, items)),
                          ("SELECT views FROM monitor_snapshots", (["v"], [(v,) for v in baseline_rows]))])
        self.snaps = set()

    def cursor(self):
        cur, conn = super().cursor(), self
        orig = cur.execute

        def ex(sql, params=()):
            orig(sql, params)
            if "SELECT checkpoint_h FROM monitor_snapshots" in sql:
                cur._rows = [(c,) for i, c in conn.snaps if i == params[0]]
            elif "INSERT INTO monitor_snapshots" in sql:
                key = (params[0], params[2])
                cur._rows = [] if key in conn.snaps else [(1,)]
                conn.snaps.add(key)
        cur.execute = ex
        return cur


def _item(i=1, hours_old=2):
    return (i, f"Video {i}", f"https://youtu.be/abc{i}", NOW - dt.timedelta(hours=hours_old))


STATS = {"views": 10, "likes": 1, "comments": 0}


def _run(conn, stats=STATS, diagnosis="Judul kurang menarik."):
    with patch("main._db_conn", return_value=conn), patch("atm.monitor.fetch_public_stats", return_value=stats) as f, \
            patch("atm.monitor._sleep") as sl, patch("main._telegram_notify", return_value=True) as tg, \
            patch("atm.monitor.run_claude", return_value=diagnosis) as rc:
        out = monitor.run_monitor(NOW)
    return out, f, sl, tg, rc


def test_due_checkpoint_skips_missed():
    pub = NOW - dt.timedelta(hours=30)
    assert monitor.due_checkpoint(pub, NOW, {1}) == 24
    assert monitor.due_checkpoint(pub, NOW, {24}) is None
    assert monitor.due_checkpoint(NOW - dt.timedelta(minutes=30), NOW, set()) is None
    assert monitor.due_checkpoint(NOW - dt.timedelta(hours=200), NOW, set()) == 168


def test_baseline_none_under_three():
    for rows, expected in (([(10,), (20,)], None), ([(10,), (20,), (30,)], 20.0), ([(0,), (0,), (0,)], None)):
        conn = FakeConn([("FROM monitor_snapshots", (["v"], rows))])
        with patch("main._db_conn", return_value=conn):
            assert monitor.baseline_views(24, 1) == expected


def test_is_underperforming():
    assert monitor.is_underperforming(49, 100, 0.5) and not monitor.is_underperforming(50, 100, 0.5)


def test_fallback_used_without_baseline():
    out, _, _, tg, _ = _run(StateConn([_item()], baseline_rows=[100, 200]))  # only 2 rows -> fallback 2% of 5000
    assert out == {"checked": 1, "snapshots": 1, "alerts": 1}
    text = tg.call_args.args[0]
    assert "di bawah target (100)" in text and "Video 1" in text and "https://youtu.be/abc1" in text


def test_baseline_used_when_enough_rows():
    out, _, _, tg, _ = _run(StateConn([_item()], baseline_rows=[100, 200, 300]))
    assert out["alerts"] == 1 and "median channel (200)" in tg.call_args.args[0]


def test_no_alert_when_above_threshold():
    out, _, _, tg, rc = _run(StateConn([_item()]), stats={"views": 90, "likes": 0, "comments": 0})
    assert out == {"checked": 1, "snapshots": 1, "alerts": 0}
    tg.assert_not_called()
    rc.assert_not_called()


def test_alert_sent_once():
    conn = StateConn([_item()])
    _, _, _, tg1, _ = _run(conn)
    out, f, _, tg2, _ = _run(conn)  # same checkpoint again: already recorded, nothing is fetched or sent
    assert tg1.call_count == 1 and tg2.call_count == 0 and f.call_count == 0 and out["checked"] == 0


def test_concurrent_tick_does_not_double_alert():
    conn = StateConn([_item()])
    conn.snaps.add((1, 1))  # the other tick inserted between our due-check and our insert
    orig = StateConn.cursor

    def stale(self):
        cur = orig(self)
        o = cur.execute

        def ex(sql, params=()):
            o(sql, params)
            if "SELECT checkpoint_h FROM monitor_snapshots" in sql:
                cur._rows = []  # stale view: looks undone
        cur.execute = ex
        return cur
    with patch.object(StateConn, "cursor", stale):
        out, _, _, tg, _ = _run(conn)
    assert out["snapshots"] == 0 and tg.call_count == 0


def test_alert_includes_diagnosis():
    _, _, _, tg, rc = _run(StateConn([_item()]))
    assert "Judul kurang menarik." in tg.call_args.args[0]
    assert rc.call_args.kwargs["model"] == monitor.ATM_LIGHT_MODEL


def test_alert_without_diagnosis_when_bridge_down():
    out, _, _, tg, _ = _run(StateConn([_item()]), diagnosis=None)
    assert out["alerts"] == 1 and "Dugaan" not in tg.call_args.args[0]


def test_alert_text_has_no_paths_or_secrets():
    _, _, _, tg, _ = _run(StateConn([_item()]))
    text = tg.call_args.args[0]
    assert "/Users/" not in text and "data/" not in text.replace("https://", "")


def test_checkpoint_168_marks_monitored():
    conn = StateConn([_item(hours_old=200)])
    _run(conn, stats={"views": 9999, "likes": 0, "comments": 0})
    assert conn.sqls("SET stage = 'monitored'")


def test_other_checkpoints_do_not_mark_monitored():
    conn = StateConn([_item()])
    _run(conn)
    assert not conn.sqls("SET stage = 'monitored'")


def test_failed_fetch_records_nothing_and_retries_next_tick():
    conn = StateConn([_item()])
    out, _, _, tg, _ = _run(conn, stats=None)
    assert out == {"checked": 1, "snapshots": 0, "alerts": 0} and not conn.snaps
    tg.assert_not_called()


def test_max_20_fetches_per_tick_with_sleeps():
    conn = StateConn([_item(i) for i in range(1, 26)])
    out, f, sl, _, _ = _run(conn, stats={"views": 9999, "likes": 0, "comments": 0})
    assert f.call_count == 20 and out["checked"] == 20 and sl.call_count == 19


def test_sleep_is_2_to_5_seconds():
    with patch("atm.monitor.time.sleep") as s, patch("atm.monitor.random.uniform", return_value=3.3) as u:
        monitor._sleep()
    u.assert_called_once_with(2, 5)
    s.assert_called_once_with(3.3)


def test_fetch_public_stats_uses_no_cookies():
    proc = MagicMock(returncode=0, stdout=json.dumps({"view_count": 12, "like_count": 3, "comment_count": 1}))
    with patch("atm.monitor.subprocess.run", return_value=proc) as run:
        assert monitor.fetch_public_stats("https://youtu.be/abc") == {"views": 12, "likes": 3, "comments": 1}
    argv = run.call_args.args[0]
    assert "--no-cookies" in argv and not any(a.startswith("--cookies") for a in argv)
    assert run.call_args.kwargs["timeout"] == 60 and argv[-2:] == ["--", "https://youtu.be/abc"]


def test_fetch_public_stats_failures_return_none():
    bad = MagicMock(returncode=1, stdout="")
    junk = MagicMock(returncode=0, stdout="not json")
    with patch("atm.monitor.subprocess.run", return_value=bad):
        assert monitor.fetch_public_stats("https://youtu.be/abc") is None
    with patch("atm.monitor.subprocess.run", return_value=junk):
        assert monitor.fetch_public_stats("https://youtu.be/abc") is None
    with patch("atm.monitor.subprocess.run", side_effect=OSError("no yt-dlp")):
        assert monitor.fetch_public_stats("https://youtu.be/abc") is None


def test_fetch_public_stats_refuses_non_http_without_running():
    with patch("atm.monitor.subprocess.run") as run:
        assert monitor.fetch_public_stats("--exec=evil") is None
        assert monitor.fetch_public_stats("file:///etc/passwd") is None
    run.assert_not_called()


def test_run_monitor_without_db_returns_empty():
    with patch("main._db_conn", return_value=None):
        assert monitor.run_monitor(NOW) == {}


def test_tick_runs_monitor_job():
    with patch("atm.schedule.send_reminders", return_value=0), patch("atm.monitor.run_monitor", return_value={"checked": 2}), \
            patch("atm.learn.run_post_evals", return_value=1):
        r = client.post("/atm/cron/tick").json()
    assert r["monitor"] == {"checked": 2} and r["post_evals"] == 1 and r["errors"] == []


def test_item_monitor_endpoint():
    conn = FakeConn([("FROM monitor_snapshots", (["a"] * 6, [(1, 10, 1, 0, True, NOW), (24, 90, 5, 1, False, None)]))])
    with patch("main._db_conn", return_value=conn):
        r = client.get("/atm/items/1/monitor")
    snaps = r.json()["snapshots"]
    assert r.status_code == 200 and [s["checkpoint_h"] for s in snaps] == [1, 24] and snaps[0]["alerted"] is True
