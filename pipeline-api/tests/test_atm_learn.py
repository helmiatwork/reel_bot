import json
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from atm import learn  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


def _eval_conn():
    return FakeConn([("FROM content_evaluations e JOIN", (["a"] * 7, [("Kucing", "pets", "draft", "ringkas",
                                                                       [{"issue": "x"}], [{"instruction": "y"}], [])])),
                     ("INSERT INTO learnings", (["id"], [(1,)]))])


def _distill(model_out, conn=None):
    conn = conn or _eval_conn()
    with patch("main._db_conn", return_value=conn), patch("atm.learn.run_claude", return_value=model_out) as rc:
        return learn.distill_learnings(7, 41), conn, rc


def test_distill_upserts_max_five():
    items = [{"kind": "insight", "content": f"pelajaran {i}"} for i in range(7)]
    n, conn, rc = _distill(json.dumps({"learnings": items}))
    inserts = conn.sqls("INSERT INTO learnings")
    assert n == 5 and len(inserts) == 5
    assert "ON CONFLICT (niche, kind, md5(content))" in inserts[0][0]
    assert inserts[0][1] == ("pets", "insight", "pelajaran 0", [7])  # source_ids carries the item id
    assert rc.call_args.kwargs["model"] == learn.ATM_LIGHT_MODEL and conn.commits == 1


def test_distill_bad_json_returns_zero():
    for out in ("bukan json", None, '{"learnings": "x"}', "[]"):
        n, conn, _ = _distill(out)
        assert n == 0 and not conn.sqls("INSERT INTO learnings")


def test_distill_drops_invalid_kind_empty_and_unsafe():
    items = [{"kind": "rant", "content": "a"}, {"kind": "hook", "content": "  "},
             {"kind": "hook", "content": "lihat /Users/ichigo/Documents/x"}, {"kind": "fix", "content": "api_key=abc"},
             {"kind": "hook", "content": 5}, "str", {"kind": "fix", "content": "potong intro 1 detik"}]
    n, conn, _ = _distill(json.dumps({"learnings": items}))
    assert n == 1 and conn.sqls("INSERT INTO learnings")[0][1][1:3] == ("fix", "potong intro 1 detik")


def test_distill_prompt_has_no_paths():
    _, _, rc = _distill('{"learnings": []}')
    assert "/Users/" not in rc.call_args.args[0] and "data/drafts" not in rc.call_args.args[0]


def test_distill_unknown_evaluation_returns_zero():
    conn = FakeConn([])
    with patch("main._db_conn", return_value=conn), patch("atm.learn.run_claude") as rc:
        assert learn.distill_learnings(7, 999) == 0
    rc.assert_not_called()


def test_distill_never_raises_on_db_error():
    conn = _eval_conn()
    orig = conn.cursor

    def cur():
        c = orig()
        o = c.execute

        def ex(sql, params=()):
            if "INSERT INTO learnings" in sql:
                raise RuntimeError("db down")
            return o(sql, params)
        c.execute = ex
        return c
    conn.cursor = cur
    n, _, _ = _distill('{"learnings": [{"kind": "hook", "content": "ok"}]}', conn)
    assert n == 0


GOOD_POST = {"scores": {"title_thumbnail": 4, "reach": 3, "engagement": 5},
             "findings": [{"aspect": "reach", "issue": "views 24 jam di bawah median"}],
             "fixes": [{"no": 1, "instruction": "ganti thumbnail"}], "summary": "Reach rendah."}


def _post_conn(claimed=True):
    return FakeConn([("SET post_eval_done = true", (["id"], [(7,)] if claimed else [])),
                     ("SELECT title, blueprint", (["t", "b"], [("Kucing", {"hook": {}})])),
                     ("SELECT checkpoint_h, views", (["a"] * 4, [(24, 90, 5, 1)])),
                     ("SELECT round, summary", (["r", "s"], [(1, "draft bagus")])),
                     ("SELECT COALESCE(MAX(round)", (["m"], [(2,)])),
                     ("INSERT INTO content_evaluations", (["id"], [(55,)]))])


def _post(conn, out):
    with patch("main._db_conn", return_value=conn), patch("atm.learn.run_claude", return_value=out) as rc:
        return learn.run_post_evaluation(7), rc


def test_post_eval_sets_done():
    conn = _post_conn()
    eid, rc = _post(conn, json.dumps(GOOD_POST))
    assert eid == 55
    assert conn.sqls("SET post_eval_done = true")  # claimed before the model call
    ins = conn.sqls("INSERT INTO content_evaluations")[0]
    assert "'post'" in ins[0] and ins[1][1] == 2  # round = max + 1
    assert "frames" not in rc.call_args.kwargs or not rc.call_args.kwargs["frames"]
    assert "draft bagus" in rc.call_args.args[0] and "90" in rc.call_args.args[0]


def test_post_eval_runs_only_once_per_item():
    eid, rc = _post(_post_conn(claimed=False), json.dumps(GOOD_POST))
    assert eid is None
    rc.assert_not_called()


def test_post_eval_bridge_down_releases_claim():
    conn = _post_conn()
    eid, _ = _post(conn, None)
    assert eid is None and conn.sqls("SET post_eval_done = false")


def test_post_eval_bad_answer_stores_error_and_keeps_claim():
    conn = _post_conn()
    bad = dict(GOOD_POST, scores={"title_thumbnail": 99, "reach": 3, "engagement": 5})
    eid, _ = _post(conn, json.dumps(bad))
    assert eid is None and not conn.sqls("SET post_eval_done = false")
    assert "'error'" in conn.sqls("INSERT INTO content_evaluations")[0][0]


def test_post_eval_validation_rejects_bool_and_missing_summary():
    assert learn._valid_post_eval(GOOD_POST)
    assert not learn._valid_post_eval(dict(GOOD_POST, scores={"title_thumbnail": True, "reach": 3, "engagement": 5}))
    assert not learn._valid_post_eval(dict(GOOD_POST, summary=" "))
    assert not learn._valid_post_eval(dict(GOOD_POST, fixes="x"))


def test_cron_post_eval_runs_once():
    conn = FakeConn([("stage = 'monitored'", (["id"], [(7,), (8,)]))])
    calls = {}

    def fake_post(item_id):
        calls[item_id] = calls.get(item_id, 0) + 1
        return 55 if item_id == 7 else None  # item 8: already done / bridge down

    with patch("main._db_conn", return_value=conn), patch("atm.learn.run_post_evaluation", side_effect=fake_post), \
            patch("atm.learn.distill_learnings", return_value=3) as dl:
        assert learn.run_post_evals() == 1
    dl.assert_called_once_with(7, 55)
    assert calls == {7: 1, 8: 1}
    assert "post_eval_done = false" in conn.sqls("stage = 'monitored'")[0][0]


def test_learn_feed_and_delete():
    feed = FakeConn([("FROM learnings", (["a"] * 6, [(1, "pets", "hook", "buka dengan close-up", 3, None)])),
                     ("FROM content_evaluations e", (["a"] * 8, [(9, 7, "Kucing", "post", 1, "ok", "ready", None)]))])
    with patch("main._db_conn", return_value=feed):
        r = client.get("/atm/learn?niche=pets")
    body = r.json()
    assert r.status_code == 200 and body["learnings"][0]["hits"] == 3 and body["evaluations"][0]["title"] == "Kucing"
    assert feed.sqls("FROM learnings")[0][1] == ("pets",)
    with patch("main._db_conn", return_value=FakeConn([("DELETE FROM learnings", (["id"], [(1,)]))])):
        assert client.delete("/atm/learnings/1").status_code == 200
    with patch("main._db_conn", return_value=FakeConn([])):
        assert client.delete("/atm/learnings/1").status_code == 404
