import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


def _item_conn():
    return FakeConn([("SELECT 1 FROM content_items", (["x"], [(1,)]))])


def _post(tmp_path, name, data=b"abc", conn=None):
    with patch("main._REPO_ROOT", tmp_path), patch("main._db_conn", return_value=conn or _item_conn()):
        return client.post("/atm/items/7/draft", files={"file": (name, data, "application/octet-stream")})


def test_draft_rejects_txt_400(tmp_path):
    assert _post(tmp_path, "notes.txt").status_code == 400
    assert not (tmp_path / "data").exists()


def test_draft_rejects_oversize_413(tmp_path):
    with patch("atm.evaluate.MAX_DRAFT_BYTES", 10):
        r = _post(tmp_path, "v.mp4", b"x" * 25)
    assert r.status_code == 413
    assert list((tmp_path / "data" / "drafts" / "7").iterdir()) == []  # partial file removed


def test_draft_ignores_traversal_filename(tmp_path):
    r = _post(tmp_path, "../../x.mp4")
    assert r.status_code == 200
    saved = (tmp_path / r.json()["draft_video_path"]).resolve()
    assert saved.parent == (tmp_path / "data" / "drafts" / "7").resolve()
    assert saved.suffix == ".mp4" and saved.name != "x.mp4" and saved.read_bytes() == b"abc"
    assert not (tmp_path.parent / "x.mp4").exists()


def test_draft_sets_review(tmp_path):
    conn = _item_conn()
    r = _post(tmp_path, "v.MOV", conn=conn)
    assert r.status_code == 200 and conn.commits == 1
    sql, params = conn.sqls("UPDATE content_items")[0]
    assert "ELSE 'review'" in sql and params[0] == r.json()["draft_video_path"] and params[2] == 7


def test_draft_missing_item_404(tmp_path):
    assert _post(tmp_path, "v.mp4", conn=FakeConn()).status_code == 404
    assert not (tmp_path / "data").exists()


# ---------------------------------------------------------------- evaluation rounds
import json  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from atm import evaluate  # noqa: E402


def _good_eval(**over):
    d = {"scores": {a: 7 for a in evaluate.EVAL_ASPECTS},
         "findings": [{"t_start": "00:04", "t_end": "00:07", "aspect": "pacing", "issue": "lambat"}],
         "fixes": [{"no": 1, "instruction": "potong 1,5 detik"}], "summary": "Cukup baik.",
         "resolved_prev": {"done": 1, "total": 2, "notes": "ok"}}
    d.update(over)
    return d


def test_validate_evaluation_ok():
    assert evaluate.validate_evaluation(_good_eval()) == []


def test_validate_evaluation_score_range():
    for bad in (0, 11, 7.5, "7", True, None):
        d = _good_eval()
        d["scores"]["hook"] = bad
        assert any("hook" in e for e in evaluate.validate_evaluation(d)), bad
    d = _good_eval()
    del d["scores"]["audio"]
    assert evaluate.validate_evaluation(d)


def test_validate_evaluation_shapes():
    assert evaluate.validate_evaluation(_good_eval(findings=[{"t_start": "0", "issue": "x"}]))
    assert evaluate.validate_evaluation(_good_eval(fixes=[{"no": 1}]))
    assert evaluate.validate_evaluation(_good_eval(summary="  "))
    assert evaluate.validate_evaluation(_good_eval(findings="x"))
    assert evaluate.validate_evaluation("nope")


def test_evaluate_requires_draft_400():
    conn = FakeConn([("SELECT draft_video_path", (["d"], [(None,)]))])
    with patch("main._db_conn", return_value=conn):
        assert client.post("/atm/items/7/evaluate").status_code == 400
    assert conn.sqls("INSERT INTO content_evaluations") == []


def test_evaluate_missing_item_404():
    with patch("main._db_conn", return_value=FakeConn()):
        assert client.post("/atm/items/7/evaluate").status_code == 404


def test_evaluate_round_increments():
    conn = FakeConn([("SELECT draft_video_path", (["d"], [("data/drafts/7/a.mp4",)])),
                     ("SELECT COALESCE(MAX(round)", (["m"], [(2,)])),
                     ("INSERT INTO content_evaluations", (["id"], [(41,)]))])
    with patch("main._db_conn", return_value=conn), patch("atm.evaluate._run_evaluation") as job:
        r = client.post("/atm/items/7/evaluate")
    assert r.json() == {"evaluation_id": 41, "round": 3, "status": "building"}
    assert conn.sqls("INSERT INTO content_evaluations")[0][1] == (7, 3, evaluate.ATM_EVAL_MODEL)
    job.assert_called_once_with(41, 7, 3)


def test_evaluate_marks_stale_building_error_before_409_check():
    conn = FakeConn([("SELECT draft_video_path", (["d"], [("p",)])),
                     ("SELECT COALESCE(MAX(round)", (["m"], [(1,)])),
                     ("INSERT INTO content_evaluations", (["id"], [(9,)]))])
    with patch("main._db_conn", return_value=conn), patch("atm.evaluate._run_evaluation"):
        assert client.post("/atm/items/7/evaluate").status_code == 200
    stale = conn.sqls("SET status = 'error'")[0][0]
    assert "interval '15 minutes'" in stale and "created_at <=" in stale
    assert conn.log.index(next(x for x in conn.log if "SET status = 'error'" in x[0])) < \
        conn.log.index(next(x for x in conn.log if "SELECT 1 FROM content_evaluations" in x[0]))


def test_evaluate_conflicts_409():
    running = FakeConn([("SELECT draft_video_path", (["d"], [("p",)])), ("status = 'building'", (["x"], [(1,)]))])
    with patch("main._db_conn", return_value=running):
        assert client.post("/atm/items/7/evaluate").status_code == 409

    class Boom(FakeConn):
        def cursor(self):
            cur = super().cursor()
            orig = cur.execute

            def ex(sql, params=()):
                if "INSERT INTO content_evaluations" in sql:
                    raise RuntimeError("unique violation")
                return orig(sql, params)
            cur.execute = ex
            return cur
    race = Boom([("SELECT draft_video_path", (["d"], [("p",)])), ("SELECT COALESCE(MAX(round)", (["m"], [(0,)]))])
    with patch("main._db_conn", return_value=race):
        assert client.post("/atm/items/7/evaluate").status_code == 409


def _job_env(tmp_path, bp_text, draft="data/drafts/7/a.mp4", create=True):
    if create:
        f = tmp_path / draft
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"v")
    conn = FakeConn([("SELECT * FROM content_items", (["id", "title", "blueprint", "reference_url", "draft_video_path"],
                                                      [(7, "Kucing", {"hook": {}}, None, draft)])),
                     ("SELECT fixes, human_notes", (["f", "h"], [([{"no": 1, "instruction": "x"}], [])]))])
    frames = [{"name": "frame_000.jpg", "path": "p", "t": 0.5}]
    return conn, frames


def _run(tmp_path, conn, frames, claude_text):
    with patch("main._db_conn", return_value=conn), patch("main._REPO_ROOT", tmp_path), \
            patch("main.ANALYZE_FRAME_DIR", str(tmp_path / "af")), \
            patch("main._extract_frames_timed", return_value=frames) as ext, \
            patch("atm.evaluate.transcribe", return_value=[]), patch("atm.evaluate.audio_levels", return_value={}), \
            patch("atm.evaluate.run_claude", return_value=claude_text) as rc, \
            patch("atm.evaluate.distill_learnings") as distill:
        evaluate._run_evaluation(41, 7, 3)
    rc.distill = distill
    return ext, rc


def test_evaluate_bad_json_sets_error(tmp_path):
    conn, frames = _job_env(tmp_path, "")
    _, rc = _run(tmp_path, conn, frames, "ini bukan json")
    ups = conn.sqls("UPDATE content_evaluations")
    assert len(ups) == 1 and "status = 'error'" in ups[0][0] and "JSON" in ups[0][1][0]
    assert not any("status = 'ready'" in s for s, _ in ups)


def test_evaluate_invalid_scores_sets_error(tmp_path):
    conn, frames = _job_env(tmp_path, "")
    bad = _good_eval()
    bad["scores"]["hook"] = 99
    _run(tmp_path, conn, frames, json.dumps(bad))
    ups = conn.sqls("UPDATE content_evaluations")
    assert "status = 'error'" in ups[0][0] and "hook" in ups[0][1][0]


def test_evaluate_success_writes_ready_and_uses_round_subdir(tmp_path):
    conn, frames = _job_env(tmp_path, "")
    ext, rc = _run(tmp_path, conn, frames, "```json\n" + json.dumps(_good_eval()) + "\n```")
    assert rc.call_args.kwargs["subdir"] == "atm_7_r3" and rc.call_args.kwargs["frames"] == ["frame_000.jpg"]
    assert ext.call_args.args[1] == str(tmp_path / "af" / "atm_7_r3") and ext.call_args.kwargs["n"] == 16
    assert rc.call_args.kwargs["model"] == evaluate.ATM_EVAL_MODEL == "claude-haiku-5-5"
    assert rc.call_args.kwargs["effort"] == evaluate.ATM_EVAL_EFFORT == "high"
    assert "potong 1,5" in rc.call_args.args[0]  # previous round fixes reach the prompt
    ups = conn.sqls("UPDATE content_evaluations")
    assert "status = 'ready'" in ups[0][0] and json.loads(ups[0][1][0])["hook"] == 7
    assert conn.commits == 1
    rc.distill.assert_called_once_with(7, 41)


def test_evaluate_failure_does_not_distill(tmp_path):
    conn, frames = _job_env(tmp_path, "")
    _, rc = _run(tmp_path, conn, frames, "ini bukan json")
    rc.distill.assert_not_called()


def test_evaluate_draft_path_escape_is_refused(tmp_path):
    (tmp_path / "secret.mp4").write_bytes(b"v")
    conn, frames = _job_env(tmp_path, "", draft="secret.mp4", create=False)
    ext, rc = _run(tmp_path, conn, frames, "{}")
    ext.assert_not_called()
    assert "status = 'error'" in conn.sqls("UPDATE content_evaluations")[0][0]


def test_evaluate_claude_down_sets_error(tmp_path):
    conn, frames = _job_env(tmp_path, "")
    _run(tmp_path, conn, frames, None)
    assert "status = 'error'" in conn.sqls("UPDATE content_evaluations")[0][0]


def test_transcribe_never_raises(tmp_path):
    assert evaluate.transcribe(str(tmp_path / "missing.mp4")) == []
    with patch.dict(sys.modules, {"faster_whisper": None}):
        assert evaluate.transcribe("x") == []


def test_transcribe_maps_segments():
    seg = MagicMock(start=0.04, end=1.26, text=" halo ")
    wm = MagicMock()
    wm.return_value.transcribe.return_value = ([seg, MagicMock(start=2, end=3, text=" ")], None)
    with patch.dict(sys.modules, {"faster_whisper": MagicMock(WhisperModel=wm)}):
        assert evaluate.transcribe("x") == [{"start": 0.0, "end": 1.3, "text": "halo"}]


def test_audio_levels_parses_and_never_raises():
    err = "[Parsed_volumedetect_0] mean_volume: -23.4 dB\n[Parsed_volumedetect_0] max_volume: -3.0 dB\n"
    with patch("subprocess.run", return_value=MagicMock(stderr=err)):
        assert evaluate.audio_levels("x.mp4") == {"mean_db": -23.4, "max_db": -3.0}
    with patch("subprocess.run", return_value=MagicMock(stderr="no audio stream")):
        assert evaluate.audio_levels("x.mp4") == {}
    with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg")):
        assert evaluate.audio_levels("x.mp4") == {}


def test_list_evaluations_newest_first():
    conn = FakeConn([("FROM content_evaluations WHERE content_item_id", (["id", "round"], [(5, 2), (4, 1)]))])
    with patch("main._db_conn", return_value=conn):
        r = client.get("/atm/items/7/evaluations")
    assert [e["round"] for e in r.json()["evaluations"]] == [2, 1]
    assert "ORDER BY id DESC" in conn.log[0][0]


def test_notes_saved_and_validated():
    conn = FakeConn([("SELECT findings", (["f"], [([{"a": 1}, {"a": 2}],)]))])
    body = {"notes": [{"finding_index": 1, "agree": False, "note": "tidak setuju"},
                      {"finding_index": 1, "agree": True, "note": "ok"}]}
    with patch("main._db_conn", return_value=conn):
        r = client.patch("/atm/evaluations/5/notes", json=body)
        bad = client.patch("/atm/evaluations/5/notes", json={"notes": [{"finding_index": 2, "agree": True}]})
        neg = client.patch("/atm/evaluations/5/notes", json={"notes": [{"finding_index": -1, "agree": True}]})
    assert r.status_code == 200 and r.json()["notes"] == [{"finding_index": 1, "agree": True, "note": "ok"}]
    assert bad.status_code == 400 and neg.status_code == 422
    assert len(conn.sqls("UPDATE content_evaluations")) == 1


def test_notes_missing_evaluation_404():
    with patch("main._db_conn", return_value=FakeConn()):
        assert client.patch("/atm/evaluations/5/notes", json={"notes": []}).status_code == 404


def test_evaluate_frames_missing_bridge_400_sets_error_not_ready(tmp_path):
    """Bridge answers 400 frames_missing -> run_claude returns None -> row ends 'error', never 'ready'."""
    conn, frames = _job_env(tmp_path, "")
    resp = MagicMock()
    resp.json.return_value = {"ok": False, "error_type": "frames_missing", "error": "none of the requested frames exist"}
    with patch("main._db_conn", return_value=conn), patch("main._REPO_ROOT", tmp_path), \
            patch("main.ANALYZE_FRAME_DIR", str(tmp_path / "af")), \
            patch("main._extract_frames_timed", return_value=frames), \
            patch("atm.evaluate.transcribe", return_value=[]), patch("atm.evaluate.audio_levels", return_value={}), \
            patch("httpx.post", return_value=resp), patch("atm.evaluate.distill_learnings") as distill:
        evaluate._run_evaluation(41, 7, 3)
    updates = conn.sqls("UPDATE content_evaluations")
    assert len(updates) == 1 and "status = 'error'" in updates[0][0] and "status = 'ready'" not in updates[0][0]
    distill.assert_not_called()


def test_evaluate_success_only_writes_a_building_row(tmp_path):
    conn, frames = _job_env(tmp_path, "")
    _run(tmp_path, conn, frames, "```json\n" + json.dumps(_good_eval()) + "\n```")
    (sql, _), = conn.sqls("UPDATE content_evaluations SET scores")
    assert sql.endswith("WHERE id = %s AND status = 'building'")  # a stale-marked row must stay error
