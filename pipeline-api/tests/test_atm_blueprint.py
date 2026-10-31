import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from atm import blueprint as bpm  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
OK = json.loads((Path(__file__).parent / "fixtures" / "atm_blueprint_ok.json").read_text())
ITEM_COLS = ["id", "title", "niche", "stage", "reference_url", "format", "voice_mode", "blueprint"]
SONGS = (["id", "title", "mood", "bpm", "genre", "is_viral"], [(7, "Ceria", "happy", 120, "pop", True)])


def _item(stage="idea", url=None, blueprint=None):
    return (1, "T", "kucing", stage, url, "short", "self", blueprint)


def _updates(conn, needle):
    return [s for s, _ in conn.log if s.startswith("UPDATE content_items") and needle in s]


def test_validate_blueprint_ok():
    assert bpm.validate_blueprint(copy.deepcopy(OK), {7}) == []


def test_validate_blueprint_wrong_title_count():
    bp = copy.deepcopy(OK)
    bp["titles"] = bp["titles"][:4]
    assert "titles harus tepat 5" in bpm.validate_blueprint(bp, {7})


def test_validate_unknown_song_id_nulls():
    bp = copy.deepcopy(OK)
    assert bpm.validate_blueprint(bp, {99}) == []
    assert bp["audio"]["bgm_song_id"] is None


def test_validate_missing_section_and_thumbnail_rules():
    bp = copy.deepcopy(OK)
    del bp["hook"]
    bp["thumbnail"]["concepts"][0]["overlay_text"] = "satu dua tiga empat lima"
    bp["thumbnail"]["concepts"][1]["why_ctr"] = ""
    bp["shots"] = []
    bp["narration"]["beats"] = []
    errs = " | ".join(bpm.validate_blueprint(bp, {7}))
    for frag in ("'hook' hilang", "maksimal 4 kata", "konsep 2 butuh", "shots kosong", "narration.beats kosong"):
        assert frag in errs
    assert bpm.validate_blueprint("x", set()) == ["blueprint is not an object"]


def test_prompt_has_originality_rule_and_voice_mode_tips():
    p = bpm.build_blueprint_prompt({"title": "T", "voice_mode": "self"}, {"songs": [{"id": 7}]})
    assert "jangan memakai footage referensi sebagai materi" in p and "recording_tips WAJIB" in p
    p = bpm.build_blueprint_prompt({"title": "T", "voice_mode": "ai", "blueprint": OK}, {}, section="hook")
    assert 'HANYA bagian "hook"' in p and "boleh berupa daftar kosong" in p


def test_blueprint_409_without_analysis():
    conn = FakeConn([("SELECT reference_url, blueprint", (["a", "b"], [("https://youtu.be/x", None)]))])
    with patch("main._db_conn", return_value=conn), patch("atm.blueprint._run_blueprint") as job:
        r = client.post("/atm/items/1/blueprint", json={})
    assert r.status_code == 409 and r.json()["detail"] == "Referensi belum dianalisa"
    job.assert_not_called()
    assert not conn.sqls("blueprint_status = 'building'")


def test_blueprint_without_reference_allowed_and_runs_in_background():
    conn = FakeConn([("SELECT reference_url, blueprint", (["a", "b"], [(None, None)]))])
    with patch("main._db_conn", return_value=conn), patch("atm.blueprint._run_blueprint") as job:
        r = client.post("/atm/items/1/blueprint")
    assert r.json() == {"status": "building"}
    job.assert_called_once_with(1, None)
    assert conn.sqls("blueprint_status = 'building'") and conn.commits == 1


def test_blueprint_404_bad_section_and_section_without_blueprint():
    conn = FakeConn()
    with patch("main._db_conn", return_value=conn):
        assert client.post("/atm/items/1/blueprint", json={}).status_code == 404
        assert client.post("/atm/items/1/blueprint", json={"section": "nope"}).status_code == 400
    conn = FakeConn([("SELECT reference_url, blueprint", (["a", "b"], [(None, None)]))])
    with patch("main._db_conn", return_value=conn):
        assert client.post("/atm/items/1/blueprint", json={"section": "hook"}).status_code == 400


def _run(item, claude_text, section=None):
    conn = FakeConn([("SELECT * FROM content_items", (ITEM_COLS, [item])), ("FROM songs", SONGS)])
    with patch("main._db_conn", return_value=conn), patch("atm.blueprint.run_claude", return_value=claude_text):
        bpm._run_blueprint(1, section)
    return conn


def test_blueprint_background_success_writes_and_promotes_idea():
    conn = _run(_item(), json.dumps(OK))
    (sql, params), = conn.sqls("SET blueprint = ")
    assert "blueprint_status = 'ready'" in sql and "THEN 'blueprint'" in sql
    assert json.loads(params[0])["titles"] == OK["titles"] and conn.commits == 1


def test_blueprint_background_error_keeps_old():
    conn = _run(_item(blueprint=OK), "not json")
    assert not conn.sqls("SET blueprint = ")
    (sql, params), = conn.sqls("blueprint_status = 'error'")
    assert "valid" in params[0]


def test_blueprint_background_truncated_json_is_error():
    conn = _run(_item(blueprint=OK), '```json\n{"atm": {"tiru": ["a"')
    assert not conn.sqls("SET blueprint = ") and conn.sqls("blueprint_status = 'error'")


def test_blueprint_background_invalid_blueprint_not_written():
    bad = {**OK, "titles": ["a"]}
    conn = _run(_item(), json.dumps(bad))
    assert not conn.sqls("SET blueprint = ")
    assert "titles harus tepat 5" in conn.sqls("blueprint_status = 'error'")[0][1][0]


def test_blueprint_background_bridge_down_is_error():
    conn = _run(_item(blueprint=OK), None)
    assert not conn.sqls("SET blueprint = ") and "Claude tidak bisa" in conn.sqls("blueprint_status = 'error'")[0][1][0]


def test_blueprint_section_merge():
    new_hook = {"line": "BARU", "visual": "v"}
    conn = _run(_item(stage="shoot", blueprint=OK), json.dumps({"hook": new_hook}), section="hook")
    (sql, params), = conn.sqls("SET blueprint = ")
    saved = json.loads(params[0])
    assert saved["hook"] == new_hook
    assert {k: v for k, v in saved.items() if k != "hook"} == {k: v for k, v in OK.items() if k != "hook"}


def test_blueprint_section_missing_in_answer_is_error():
    conn = _run(_item(blueprint=OK), json.dumps({"titles": []}), section="hook")
    assert not conn.sqls("SET blueprint = ") and conn.sqls("blueprint_status = 'error'")


def test_gather_context_missing_table_does_not_crash():
    class Cur:
        connection = type("C", (), {"rollback": lambda s: None})()
        def execute(self, *a):
            raise RuntimeError("no table")
    ctx = bpm.gather_context(Cur(), {"reference_url": "u", "niche": "n"})
    assert ctx["songs"] == [] and ctx["analysis"] is None
