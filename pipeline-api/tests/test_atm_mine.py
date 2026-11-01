import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from atm import common  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
DATA = {"channel": "Kucing TV", "channel_url": "https://www.youtube.com/channel/UC1", "channel_follower_count": 900,
        "entries": [{"id": "aaaaaaaaaaa", "title": "A", "view_count": 10},
                    {"id": "bbbbbbbbbbb", "title": "B", "view_count": 500},
                    {"id": "ccccccccccc", "title": "C"},
                    {"id": "bad id!", "title": "X", "view_count": 9999}]}


def _proc(data=DATA, code=0):
    return MagicMock(returncode=code, stdout=json.dumps(data))


def test_mine_sorts_by_views_limits_and_never_sends_cookies():
    with patch("atm.mine.subprocess.run", return_value=_proc()) as run:
        r = client.post("/atm/mine", json={"channel_url": "https://www.youtube.com/@kucingtv", "limit": 2})
    assert r.status_code == 200
    body = r.json()
    assert [v["video_id"] for v in body["videos"]] == ["bbbbbbbbbbb", "aaaaaaaaaaa"]
    assert body["videos"][0]["url"] == "https://www.youtube.com/shorts/bbbbbbbbbbb"
    assert body["channel"] == {"name": "Kucing TV", "url": "https://www.youtube.com/channel/UC1", "followers": 900,
                               "median_views": 255}
    argv = run.call_args.args[0]
    assert "--ignore-config" in argv and "--no-cookies" in argv and not any(a.startswith("--cookies") for a in argv)
    assert argv[argv.index("--playlist-end") + 1] == "60" and argv[-2:] == ["--", "https://www.youtube.com/@kucingtv/shorts"]


def test_mine_scan_window_grows_with_limit_and_is_capped():
    for limit, expected in ((10, "60"), (30, "90"), (50, "150")):
        with patch("atm.mine.subprocess.run", return_value=_proc()) as run:
            client.post("/atm/mine", json={"channel_url": "https://www.youtube.com/@kucingtv", "limit": limit})
        argv = run.call_args.args[0]
        assert argv[argv.index("--playlist-end") + 1] == expected


def test_mine_rejects_non_channel_urls_and_bad_limit():
    for u in ("https://evil.com/@x", "ftp://www.youtube.com/@x", "https://www.youtube.com/watch?v=abc",
              "https://www.youtube.com.evil.com/@x", "--flag"):
        with patch("atm.mine.subprocess.run") as run:
            assert client.post("/atm/mine", json={"channel_url": u}).status_code == 400
        run.assert_not_called()
    assert client.post("/atm/mine", json={"channel_url": "https://www.youtube.com/@x", "limit": 51}).status_code == 422


def test_mine_ytdlp_failure_is_502():
    with patch("atm.mine.subprocess.run", return_value=_proc(code=1)):
        assert client.post("/atm/mine", json={"channel_url": "https://www.youtube.com/@x/videos"}).status_code == 502


def test_import_creates_items_and_starts_analysis():
    conn = FakeConn([("INSERT INTO content_items", (["id", "title", "reference_url"], [(9, "A", "https://www.youtube.com/shorts/aaaaaaaaaaa")]))])
    u = "https://www.youtube.com/shorts/aaaaaaaaaaa"
    with patch("main._db_conn", return_value=conn), patch("main._validate_source_url"), \
            patch("main.analyze_claude_async", return_value={"run_id": "r1"}) as an:
        r = client.post("/atm/mine/import", json={"urls": [u], "niche": "kucing", "titles": {u: "Judul A"},
                                                  "auto_blueprint": False})
    assert r.status_code == 200 and r.json()["items"][0]["analysis"] == {"run_id": "r1"}
    ins = conn.sqls("INSERT INTO content_items")[0]
    assert ins[1][:3] == ("Judul A", "kucing", u) and conn.commits == 1
    assert an.call_args.args[0].youtube_url == u


def test_import_validates_before_writing():
    conn = FakeConn()
    with patch("main._db_conn", return_value=conn):
        assert client.post("/atm/mine/import", json={"urls": ["https://www.tiktok.com/@a/video/1"]}).status_code == 400
        assert client.post("/atm/mine/import", json={"urls": []}).status_code == 422
        assert client.post("/atm/mine/import", json={"urls": ["https://youtu.be/abcdefghijk"] * 11}).status_code == 422
    assert not conn.log


def test_ytdlp_bin_prefers_venv_binary(tmp_path):
    (tmp_path / "yt-dlp").write_text("")
    with patch.object(sys, "executable", str(tmp_path / "python")):
        assert common.ytdlp_bin() == str(tmp_path / "yt-dlp")


def test_discover_lists_get_view_counts_batched():
    import main
    items = [{"video_id": "a", "title": "A"}, {"video_id": "b", "title": "B"}]
    with patch("main.v3_video_details", return_value=[{"video_id": "a", "view_count": 7, "like_count": 1, "duration_s": 30}]) as vd:
        out = main._with_stats(items)
    vd.assert_called_once_with(["a", "b"])
    assert out[0]["view_count"] == 7 and out[0]["duration_s"] == 30 and "view_count" not in out[1]


def test_discover_stats_failure_keeps_items():
    import main
    items = [{"video_id": "a"}]
    with patch("main.v3_video_details", side_effect=RuntimeError("quota")):
        assert main._with_stats(items) == [{"video_id": "a"}]


URL = "https://www.youtube.com/shorts/aaaaaaaaaaa"


def _import_conn(analysis_exists=True, start_ok=True, blocked=False):
    rules = [("INSERT INTO content_items", (["id", "title", "reference_url"], [(9, "A", URL)])),
             ("FOR UPDATE", (["reference_url", "blocked"], [(URL, blocked)] if start_ok else [])),
             ("FROM video_analysis", (["x"], [(1,)] if analysis_exists else []))]
    return FakeConn(rules)


def _import(conn, analyze, load_run=None, body=None, sleep=None, job=None):
    """Run POST /atm/mine/import with DB, analysis start, run polling and blueprint job patched."""
    payload = {"urls": [URL], "niche": "kucing", **(body or {})}
    with patch("main._db_conn", return_value=conn), patch("main._validate_source_url"), \
            patch("main.analyze_claude_async", **analyze) as an, \
            patch("main._load_run", **(load_run or {"return_value": None})) as lr, \
            patch("atm.mine.time.sleep", **(sleep or {})) as sl, \
            patch("atm.blueprint._run_blueprint", **(job or {})) as bp:
        r = client.post("/atm/mine/import", json=payload)
    return r, {"analyze": an, "load_run": lr, "sleep": sl, "job": bp}


def test_import_auto_blueprint_starts_after_analysis_done():
    conn = _import_conn()
    r, m = _import(conn, {"return_value": {"run_id": "r1"}}, {"return_value": {"status": "done"}})
    assert r.status_code == 200
    m["job"].assert_called_once_with(9, None)
    m["sleep"].assert_not_called()
    assert conn.sqls("SET blueprint_status = 'building'") and conn.sqls("blueprint_started_at = now()")


def test_import_auto_blueprint_skipped_when_analysis_errors():
    conn = _import_conn()
    r, m = _import(conn, {"return_value": {"run_id": "r1"}}, {"return_value": {"status": "error"}})
    assert r.status_code == 200 and r.json()["items"][0]["analysis"] == {"run_id": "r1"}
    m["job"].assert_not_called()
    assert not conn.sqls("SET blueprint_status = 'building'")


def test_import_auto_blueprint_gives_up_after_20_minutes():
    from atm import mine
    conn = _import_conn()
    r, m = _import(conn, {"return_value": {"run_id": "r1"}}, {"return_value": {"status": "running"}},
                   sleep={"return_value": None})
    assert r.status_code == 200
    assert m["sleep"].call_count == mine._MAX_POLLS and mine._MAX_POLLS * mine._POLL_S == 20 * 60
    m["job"].assert_not_called()
    assert not conn.sqls("SET blueprint_status = 'building'")


def test_import_auto_blueprint_off_does_nothing():
    conn = _import_conn()
    r, m = _import(conn, {"return_value": {"run_id": "r1"}}, {"return_value": {"status": "done"}},
                   body={"auto_blueprint": False})
    assert r.status_code == 200
    m["load_run"].assert_not_called()
    m["job"].assert_not_called()


def test_import_already_analysed_starts_blueprint_directly():
    conn = _import_conn()
    r, m = _import(conn, {"return_value": {"already_exists": True, "source": {}}})
    assert r.status_code == 200
    m["load_run"].assert_not_called()
    m["job"].assert_called_once_with(9, None)


def test_import_already_exists_without_analysis_row_is_not_started():
    conn = _import_conn(analysis_exists=False)
    r, m = _import(conn, {"return_value": {"already_exists": True, "source": {}}})
    assert r.status_code == 200
    m["job"].assert_not_called()
    assert not conn.sqls("SET blueprint_status = 'building'")


def test_auto_blueprint_skips_item_that_already_has_blueprint():
    conn = _import_conn(blocked=True)
    r, m = _import(conn, {"return_value": {"run_id": "r1"}}, {"return_value": {"status": "done"}})
    assert r.status_code == 200
    m["job"].assert_not_called()
    assert not conn.sqls("SET blueprint_status = 'building'")
    assert "blueprint IS NOT NULL" in conn.sqls("FOR UPDATE")[0][0]


def test_auto_blueprint_skips_item_building_within_15_minutes():
    conn = _import_conn(blocked=True)
    r, m = _import(conn, {"return_value": {"already_exists": True, "source": {}}})
    assert r.status_code == 200
    m["job"].assert_not_called()
    assert "blueprint_status = 'building' AND blueprint_started_at > now() - interval '15 minutes'" \
        in conn.sqls("FOR UPDATE")[0][0]


def test_import_auto_blueprint_is_sequential_and_skips_failed_analysis():
    from fastapi import HTTPException
    conn = _import_conn()
    items = [{"id": 9, "title": "A", "reference_url": URL}, {"id": 10, "title": "B", "reference_url": URL},
             {"id": 11, "title": "C", "reference_url": URL}]
    analyses = [{"run_id": "r1"}, {"run_id": "r2"}, HTTPException(status_code=502, detail="boom")]
    polled = []

    def load_run(run_id):
        polled.append(run_id)
        return {"status": "done"}

    with patch("atm.mine.insert_item", side_effect=items):
        r, m = _import(conn, {"side_effect": analyses}, {"side_effect": load_run},
                       body={"urls": [URL, URL, URL]})
    assert r.status_code == 200 and [i["analysis"] for i in r.json()["items"]][2] == {"error": "boom"}
    assert polled == ["r1", "r2"]
    assert m["job"].call_args_list == [call(9, None), call(10, None)]


def test_wait_run_treats_partial_run_file_as_still_running():
    from atm import mine
    with patch("main._load_run", side_effect=[ValueError("partial"), {"status": "done"}]), \
            patch("atm.mine.time.sleep") as sleep:
        assert mine._wait_run("r1") == "done"
    sleep.assert_called_once()


def _e(c, views=None):
    """Scanned entry with id c*11; no view_count key when views is None."""
    e = {"id": c * 11, "title": c}
    if views is not None:
        e["view_count"] = views
    return e


def _scan(entries, limit=50):
    from atm.mine import _mine
    with patch("atm.mine.subprocess.run", return_value=_proc({"channel": "C", "entries": entries})):
        return _mine("https://www.youtube.com/@c/shorts", limit)


def test_outlier_is_views_over_channel_median_rounded_to_one_decimal():
    r = _scan([_e("a", 10), _e("b", 500), _e("c", 100), _e("d", 200)])
    assert r["channel"]["median_views"] == 150
    assert {v["title"]: v["outlier"] for v in r["videos"]} == {"a": 0.1, "b": 3.3, "c": 0.7, "d": 1.3}
    assert {v["title"]: v["views"] for v in r["videos"]} == {"a": 10, "b": 500, "c": 100, "d": 200}


def test_videos_sorted_by_outlier_desc_with_none_last_and_limit_applied_after():
    entries = [_e("a", 10), _e("n"), _e("b", 500), _e("c", 100), _e("d", 200)]
    assert [v["title"] for v in _scan(entries)["videos"]] == ["b", "d", "c", "a", "n"]
    assert [v["title"] for v in _scan(entries, limit=2)["videos"]] == ["b", "d"]


def test_missing_or_zero_views_have_no_outlier_and_do_not_count_toward_median():
    r = _scan([_e("a", 10), _e("b", 300), _e("n"), _e("z", 0)])
    assert r["channel"]["median_views"] == 155
    by_title = {v["title"]: v for v in r["videos"]}
    assert by_title["b"]["outlier"] == 1.9 and by_title["a"]["outlier"] == 0.1
    assert by_title["n"]["outlier"] is None and by_title["n"]["views"] == 0
    assert by_title["z"]["outlier"] is None and by_title["z"]["views"] == 0


def test_no_views_at_all_gives_no_median_and_no_outliers():
    r = _scan([_e("a"), _e("b")])
    assert r["channel"]["median_views"] is None
    assert [v["outlier"] for v in r["videos"]] == [None, None]
