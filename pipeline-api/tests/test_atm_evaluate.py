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
