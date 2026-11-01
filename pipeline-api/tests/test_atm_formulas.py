import json
import sys
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from atm import formulas as fm  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
COLS = ["id", "slug", "name", "fits", "beats", "active", "sort", "created_at", "updated_at"]
SEED_SLUGS = ["pas", "in_medias_res", "underdog", "open_loop", "rollercoaster", "investigasi",
              "before_after_bridge", "story_circle", "kronologi", "pro_kontra", "pixar", "freytag", "wsj", "sparkline"]


def _good():
    return {"slug": "uji", "name": "Uji", "fits": "x", "active": True, "sort": 0, "beats": [
        {"name": "A", "pct": 40, "emotion": "sedih", "goal": "g"},
        {"name": "B", "pct": 60, "emotion": "haru", "goal": "g"}]}


def _dup_conn():
    """Every SQL statement raises the driver's unique violation (duplicate slug)."""
    conn = FakeConn()

    def cursor():
        cur = FakeConn.cursor(conn)

        def boom(sql, params=()):
            raise psycopg.errors.UniqueViolation("duplicate key value violates unique constraint")
        cur.execute = boom
        return cur
    conn.cursor = cursor
    return conn


def test_seed_has_14_valid_formulas_with_expected_slugs():
    assert [s for s, *_ in fm.SEED] == SEED_SLUGS
    for slug, name, fits, beats in fm.SEED:
        f = {"slug": slug, "name": name, "fits": fits, "active": True, "sort": 0,
             "beats": [{"name": n, "pct": p, "emotion": e, "goal": g} for n, p, e, g in beats]}
        assert fm.validate_formula(f) == [], slug


def test_seed_sql_is_insert_do_nothing_and_never_updates():
    conn = FakeConn()
    with patch("main._db_conn", return_value=conn):
        fm.init_formulas_db()
    inserts = conn.sqls("INSERT INTO narration_formulas")
    assert len(inserts) == 14
    assert all("ON CONFLICT (slug) DO NOTHING" in sql for sql, _ in inserts)
    assert not any("DO UPDATE" in sql for sql, _ in conn.log)
    assert conn.sqls("CREATE TABLE IF NOT EXISTS narration_formulas")
    assert conn.commits == 1 and conn.closed


def test_seed_skipped_when_table_has_rows():
    conn = FakeConn([("SELECT EXISTS", (["e"], [(True,)]))])
    with patch("main._db_conn", return_value=conn):
        fm.init_formulas_db()
    assert not conn.sqls("INSERT INTO narration_formulas")
    assert conn.commits == 1 and conn.closed


def test_startup_runs_formula_init():
    import main
    # DB patched to None: the other startup inits must not touch a real database from a unit test
    with patch("main._db_conn", return_value=None), patch("atm.formulas.init_formulas_db") as init:
        main.startup_event()
    init.assert_called_once_with()


def test_validate_formula_ok():
    assert fm.validate_formula(_good()) == []


@pytest.mark.parametrize("mutate,frag", [
    (lambda f: f.update(slug="A"), "slug"),
    (lambda f: f.update(slug="Ab"), "slug"),
    (lambda f: f.update(slug="x" * 41), "slug"),
    (lambda f: f.update(slug=None), "slug"),
    (lambda f: f.update(name="  "), "name"),
    (lambda f: f.update(fits=5), "fits"),
    (lambda f: f.update(active="yes"), "active"),
    (lambda f: f.update(sort=True), "sort"),
    (lambda f: f.update(sort=2 ** 40), "sort"),
    (lambda f: f.update(beats=[]), "beats"),
    (lambda f: f.update(beats="x"), "beats"),
    (lambda f: f["beats"].__setitem__(0, 5), "bukan objek"),
    (lambda f: f["beats"][0].update(emotion="bosan"), "emotion"),
    (lambda f: f["beats"][0].update(pct=0), "pct"),
    (lambda f: f["beats"][0].update(pct=True), "pct"),
    (lambda f: f["beats"][0].update(pct="40"), "pct"),
    (lambda f: f["beats"][0].update(pct=float("nan")), "pct"),
    (lambda f: f["beats"][0].update(pct=float("inf")), "pct"),
    (lambda f: f["beats"][0].update(pct=10 ** 400), "pct"),
    (lambda f: f["beats"][0].update(pct=30), "berjumlah 100"),
    (lambda f: f["beats"][0].update(goal=3), "goal"),
    (lambda f: f["beats"][0].update(name=None), "name"),
    (lambda f: f["beats"][0].update(name="  "), "name"),
    (lambda f: f["beats"][0].update(goal="x" * 301), "maksimal 300"),
    (lambda f: f.update(name="x" * 301), "maksimal 300"),
    (lambda f: f.update(beats=[{"name": "b", "pct": 100 / 13, "emotion": "sedih", "goal": ""}] * 13), "maksimal 12"),
])
def test_validate_formula_failures(mutate, frag):
    f = _good()
    mutate(f)
    assert any(frag in e for e in fm.validate_formula(f)), fm.validate_formula(f)


def test_list_formulas_filters_active_and_orders():
    conn = FakeConn([("FROM narration_formulas", (COLS, [(1, "uji", "Uji", None, [], True, 0, None, None)]))])
    with patch("main._db_conn", return_value=conn):
        r = client.get("/atm/formulas?active=1")
    assert r.status_code == 200 and r.json()["formulas"][0]["slug"] == "uji"
    sql = conn.sqls("FROM narration_formulas")[0][0]
    assert sql.endswith("WHERE active ORDER BY sort, id")
    conn = FakeConn([("FROM narration_formulas", (COLS, []))])
    with patch("main._db_conn", return_value=conn):
        client.get("/atm/formulas")
    assert conn.sqls("FROM narration_formulas")[0][0].endswith("ORDER BY sort, id")
    assert "WHERE active" not in conn.sqls("FROM narration_formulas")[0][0]


def test_create_formula_400_on_invalid_without_db_write():
    conn = FakeConn()
    bad = _good()
    bad["slug"] = "A"
    with patch("main._db_conn", return_value=conn):
        r = client.post("/atm/formulas", json=bad)
    assert r.status_code == 400 and any("slug" in e for e in r.json()["detail"])
    assert not conn.sqls("INSERT")


def test_create_formula_400_on_huge_sort_not_500():
    with patch("main._db_conn", return_value=FakeConn()):
        r = client.post("/atm/formulas", json={**_good(), "sort": 10 ** 400})
    assert r.status_code == 400


def test_create_formula_ok_strips_unknown_beat_keys():
    body = _good()
    body["beats"][0]["extra"] = "junk"
    conn = FakeConn([("INSERT INTO narration_formulas", (["id"], [(9,)]))])
    with patch("main._db_conn", return_value=conn):
        r = client.post("/atm/formulas", json=body)
    assert r.json() == {"id": 9}
    params = conn.sqls("INSERT INTO narration_formulas")[0][1]
    assert params[:3] == ("uji", "Uji", "x") and params[4:] == (True, 0)
    assert json.loads(params[3]) == [{"name": "A", "pct": 40, "emotion": "sedih", "goal": "g"},
                                     {"name": "B", "pct": 60, "emotion": "haru", "goal": "g"}]


def test_create_formula_409_on_duplicate_slug():
    with patch("main._db_conn", return_value=_dup_conn()):
        r = client.post("/atm/formulas", json=_good())
    assert r.status_code == 409


def test_update_formula_400_invalid_and_409_duplicate():
    bad = _good()
    bad["beats"][0]["pct"] = 1
    with patch("main._db_conn", return_value=FakeConn()):
        assert client.put("/atm/formulas/3", json=bad).status_code == 400
    with patch("main._db_conn", return_value=_dup_conn()):
        assert client.put("/atm/formulas/3", json=_good()).status_code == 409


def test_update_formula_404_and_ok():
    with patch("main._db_conn", return_value=FakeConn()):
        assert client.put("/atm/formulas/3", json=_good()).status_code == 404
    conn = FakeConn([("UPDATE narration_formulas", (["id"], [(3,)]))])
    with patch("main._db_conn", return_value=conn):
        r = client.put("/atm/formulas/3", json=_good())
    assert r.json() == {"ok": True}
    sql, params = conn.sqls("UPDATE narration_formulas")[0]
    assert sql.endswith("WHERE id = %s RETURNING id") and params[-1] == 3


def test_formula_ids_out_of_range_are_422_not_500():
    with patch("main._db_conn", return_value=FakeConn()):
        assert client.put("/atm/formulas/0", json=_good()).status_code == 422
        assert client.put(f"/atm/formulas/{10 ** 30}", json=_good()).status_code == 422
        assert client.delete("/atm/formulas/0").status_code == 422
        assert client.delete(f"/atm/formulas/{10 ** 30}").status_code == 422


def test_delete_formula_404_and_ok():
    with patch("main._db_conn", return_value=FakeConn()):
        assert client.delete("/atm/formulas/3").status_code == 404
    conn = FakeConn([("DELETE FROM narration_formulas", (["id"], [(3,)]))])
    with patch("main._db_conn", return_value=conn):
        assert client.delete("/atm/formulas/3").json() == {"ok": True}
    assert conn.sqls("DELETE FROM narration_formulas")[0][1] == (3,)
