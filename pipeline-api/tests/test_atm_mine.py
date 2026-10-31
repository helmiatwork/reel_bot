import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    assert body["channel"] == {"name": "Kucing TV", "url": "https://www.youtube.com/channel/UC1", "followers": 900}
    argv = run.call_args.args[0]
    assert "--no-cookies" in argv and not any(a.startswith("--cookies") for a in argv)
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
        r = client.post("/atm/mine/import", json={"urls": [u], "niche": "kucing", "titles": {u: "Judul A"}})
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
