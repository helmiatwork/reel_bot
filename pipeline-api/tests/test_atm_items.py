import datetime as dt
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
COLS = ["id", "title", "stage", "published_url", "created_at"]
ROW = (1, "T", "idea", None, dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))


def _db(*rules):
    conn = FakeConn(rules)
    return conn, patch("main._db_conn", return_value=conn)


def test_create_item_minimal():
    conn, p = _db(("INSERT INTO content_items", (COLS, [ROW])))
    with p:
        r = client.post("/atm/items", json={"title": "T"})
    assert r.status_code == 200
    assert r.json()["status"] == "idea" and r.json()["created_at"].startswith("2026")
    sql, params = conn.sqls("INSERT INTO content_items")[0]
    assert params == ("T", "", None, None, "short", "self") and conn.commits == 1


def test_create_item_looks_up_reference_source():
    conn, p = _db(("SELECT id FROM sources", (["id"], [(9,)])), ("INSERT INTO content_items", (COLS, [ROW])))
    with p, patch("main._validate_source_url", side_effect=lambda u: u):
        r = client.post("/atm/items", json={"title": "T", "reference_url": "https://youtu.be/x"})
    assert r.status_code == 200
    assert conn.sqls("INSERT INTO content_items")[0][1][2:4] == ("https://youtu.be/x", 9)


def test_create_item_bad_reference_url_400():
    conn, p = _db()
    with p:
        r = client.post("/atm/items", json={"title": "T", "reference_url": "ftp://x.com/a"})
    assert r.status_code == 400 and not conn.log


def test_create_item_empty_title_422():
    assert client.post("/atm/items", json={"title": ""}).status_code == 422


def test_create_503_without_db():
    with patch("main._db_conn", return_value=None):
        assert client.post("/atm/items", json={"title": "T"}).status_code == 503


def test_patch_invalid_status_422():
    assert client.patch("/atm/items/1", json={"status": "nope"}).status_code == 422


def test_patch_no_fields_400():
    assert client.patch("/atm/items/1", json={}).status_code == 400


def test_patch_published_url_sets_posted():
    conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
    with p, patch("main._validate_source_url", side_effect=lambda u: u):
        r = client.patch("/atm/items/1", json={"published_url": "https://youtu.be/abc", "status": "idea"})
    assert r.status_code == 200
    sql, params = conn.sqls("UPDATE content_items")[0]
    assert "published_at = COALESCE(published_at, now())" in sql
    assert "stage = %s" in sql and params[0] == "posted"  # explicit status is overridden
    assert "https://youtu.be/abc" in params


def test_patch_blueprint_bumps_version():
    conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
    with p:
        r = client.patch("/atm/items/1", json={"blueprint": {"hook": {}}})
    assert r.status_code == 200
    assert "blueprint_version = blueprint_version + 1" in conn.sqls("UPDATE content_items")[0][0]


def test_patch_missing_404():
    conn, p = _db(("UPDATE content_items", (COLS, [])))
    with p:
        assert client.patch("/atm/items/1", json={"title": "x"}).status_code == 404


def test_get_missing_404():
    conn, p = _db(("SELECT * FROM content_items", (COLS, [])))
    with p:
        assert client.get("/atm/items/1").status_code == 404


def test_get_item_includes_evaluations():
    conn, p = _db(("SELECT * FROM content_items", (COLS, [ROW])),
                  ("FROM content_evaluations", (["id", "kind", "round", "summary", "created_at"], [(5, "draft", 1, "ok", None)])))
    with p:
        r = client.get("/atm/items/1")
    assert r.json()["evaluations"][0]["round"] == 1


def test_list_items_filters_status_and_rejects_unknown():
    conn, p = _db(("FROM content_items", (COLS, [ROW])))
    with p:
        r = client.get("/atm/items?status=idea")
    assert r.json()["items"][0]["id"] == 1
    assert conn.log[0][1] == ("idea",) and "scheduled_at NULLS LAST, id DESC" in conn.log[0][0]
    assert client.get("/atm/items?status=bogus").status_code == 422


def test_delete_item_and_404():
    conn, p = _db(("DELETE FROM content_items", (["id"], [(1,)])))
    with p:
        assert client.delete("/atm/items/1").status_code == 200
    conn, p = _db()
    with p:
        assert client.delete("/atm/items/1").status_code == 404


GOOD = {"weekdays": [0, 2, 4], "post_time": "19:00", "tz": "Asia/Jakarta", "per_week": 3,
        "niche": "kucing", "format": "short", "alert_ratio": 0.5}


def test_settings_put_ok():
    conn, p = _db()
    with p:
        r = client.put("/atm/settings", json={**GOOD, "weekdays": [4, 0, 0]})
    assert r.status_code == 200 and r.json()["weekdays"] == [0, 4]
    assert conn.commits == 1


def test_settings_get():
    cols = list(GOOD)
    conn, p = _db(("FROM routine_settings", (cols, [tuple(GOOD.values())])))
    with p:
        assert client.get("/atm/settings").json()["tz"] == "Asia/Jakarta"


def test_settings_put_rejects_bad_tz():
    assert client.put("/atm/settings", json={**GOOD, "tz": "Mars/Base"}).status_code == 422


def test_settings_put_rejects_weekday_7():
    assert client.put("/atm/settings", json={**GOOD, "weekdays": [7]}).status_code == 422


def test_settings_put_rejects_bad_time_and_ranges():
    for bad in ({"post_time": "25:00"}, {"per_week": 0}, {"per_week": 22}, {"alert_ratio": 0.05},
                {"alert_ratio": 1.5}, {"weekdays": []}, {"weekdays": [0, 1, 2, 3, 4, 5, 6, 0]}):
        assert client.put("/atm/settings", json={**GOOD, **bad}).status_code == 422, bad


def test_patch_scheduled_at_rearms_reminders():
    conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
    with p:
        r = client.patch("/atm/items/1", json={"scheduled_at": "2026-02-01T12:00:00Z"})
    assert r.status_code == 200
    sql, params = conn.sqls("UPDATE content_items")[0]
    assert "reminded_d1_at = CASE WHEN scheduled_at IS DISTINCT FROM %s THEN NULL ELSE reminded_d1_at END" in sql
    assert "reminded_d0_at = CASE WHEN scheduled_at IS DISTINCT FROM %s THEN NULL ELSE reminded_d0_at END" in sql
    assert params[0].isoformat().startswith("2026-02-01T12:00:00")
    assert params[0] == params[1] == params[2]  # scheduled_at, then the two CASE comparisons


def test_patch_scheduled_at_null_clears():
    conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
    with p:
        r = client.patch("/atm/items/1", json={"scheduled_at": None})
    assert r.status_code == 200
    sql, params = conn.sqls("UPDATE content_items")[0]
    assert "scheduled_at = %s" in sql and "reminded_d1_at = CASE" in sql and params[0] is None


def test_patch_without_scheduled_at_leaves_reminders():
    conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
    with p:
        client.patch("/atm/items/1", json={"title": "x"})
    assert "reminded_d1_at" not in conn.sqls("UPDATE content_items")[0][0]


def test_patch_published_url_must_be_youtube():
    conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
    with p, patch("main._validate_source_url", side_effect=lambda u: u):
        r = client.patch("/atm/items/1", json={"published_url": "https://www.tiktok.com/@a/video/1"})
    assert r.status_code == 400 and not conn.sqls("UPDATE content_items")


def test_patch_blueprint_bad_shapes_400():
    bad = [{"audio": "x"}, {"narration": {"beats": "x"}}, {"narration": {"beats": ["x"]}},
           {"narration": "x"}, {"shots": {"a": 1}}, {"shots": [1]}]
    conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
    with p:
        for bp in bad:
            assert client.patch("/atm/items/1", json={"blueprint": bp}).status_code == 400, bp
        assert client.patch("/atm/items/1", json={"blueprint": "x"}).status_code == 422  # not a dict
    assert not conn.sqls("UPDATE content_items")


def test_patch_blueprint_good_shape_ok():
    bp = {"audio": {}, "narration": {"beats": [{"t": "00:00"}]}, "shots": [{"n": 1}]}
    conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
    with p:
        assert client.patch("/atm/items/1", json={"blueprint": bp}).status_code == 200


def test_patch_published_url_needs_exact_youtube_host():
    for u in ("https://youtube.com.evil.tld/x", "https://youtube.com@evil.tld/x",
              "https://evilyoutube.com/x", "https://notyoutu.be/x"):
        conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
        with p, patch("main._validate_source_url", side_effect=lambda u: u):
            r = client.patch("/atm/items/1", json={"published_url": u})
        assert r.status_code == 400 and not conn.sqls("UPDATE content_items"), u
    for u in ("https://m.youtube.com/shorts/x", "https://youtu.be/abc", "https://YouTube.com/watch?v=x"):
        conn, p = _db(("UPDATE content_items", (COLS, [ROW])))
        with p, patch("main._validate_source_url", side_effect=lambda u: u):
            r = client.patch("/atm/items/1", json={"published_url": u})
        assert r.status_code == 200 and u in conn.sqls("UPDATE content_items")[0][1], u
