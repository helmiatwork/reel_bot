import json
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
BP = {"narration": {"beats": [{"vo": "Halo kucing"}, {"vo": "Sampai jumpa"}]}}


def _conn(mode="ai", bp=BP):
    return FakeConn([("SELECT title, voice_mode", (["t", "m", "b"], [("Judul", mode, bp)])),
                     ("INSERT INTO songs", (["id"], [(55,)]))])


def test_voice_requires_ai_mode():
    with patch("main._db_conn", return_value=_conn("self")):
        assert client.post("/atm/items/3/voice", json={}).status_code == 400


def test_voice_requires_beats_and_valid_beat_number():
    with patch("main._db_conn", return_value=_conn("ai", {})):
        assert client.post("/atm/items/3/voice", json={}).status_code == 400
    with patch("main._db_conn", return_value=_conn()):
        assert client.post("/atm/items/3/voice", json={"beat": 3}).status_code == 400
        assert client.post("/atm/items/3/voice", json={"beat": 0}).status_code == 422


def test_voice_missing_item_404():
    with patch("main._db_conn", return_value=FakeConn()):
        assert client.get("/atm/items/3/voice/estimate").status_code == 404


def test_voice_estimate_counts_chars():
    with patch("main._db_conn", return_value=_conn()), patch("voiceover.voiceover.ELEVENLABS_KEY", ""):
        r = client.get("/atm/items/3/voice/estimate")
    assert r.json() == {"chars": len("Halo kucing") + len("Sampai jumpa"), "beats": 2, "provider": "gtts"}
    with patch("main._db_conn", return_value=_conn()), patch("voiceover.voiceover.ELEVENLABS_KEY", "k"):
        assert client.get("/atm/items/3/voice/estimate").json()["provider"] == "elevenlabs"


def test_voice_generates_per_beat(tmp_path):
    def fake_tts(text, path, *a, **k):
        Path(path).write_bytes(b"mp3")
        return path

    conn = _conn()
    with patch("main._db_conn", return_value=conn), patch("main._REPO_ROOT", tmp_path), \
            patch("voiceover.voiceover.text_to_speech", side_effect=fake_tts) as tts:
        r = client.post("/atm/items/3/voice", json={})
    assert r.status_code == 200
    assert [f["beat"] for f in r.json()["files"]] == [1, 2]
    assert r.json()["files"][0]["url"] == "/songs/55/download"
    inserts = conn.sqls("INSERT INTO songs")
    assert len(inserts) == 2 and tts.call_count == 2
    assert inserts[1][1][0] == "Judul · beat 2" and json.loads(inserts[0][1][2]) == ["voiceover", "item:3"]
    assert (tmp_path / "data/songs/voiceover/3/beat_01.mp3").exists()
    assert len(conn.sqls("DELETE FROM songs")) == 2  # replace, not duplicate


def test_voice_single_beat_and_tts_failure(tmp_path):
    conn = _conn()
    with patch("main._db_conn", return_value=conn), patch("main._REPO_ROOT", tmp_path), \
            patch("voiceover.voiceover.text_to_speech", side_effect=RuntimeError("quota")):
        r = client.post("/atm/items/3/voice", json={"beat": 2})
    assert r.status_code == 502 and "beat 2" in r.json()["detail"]
    assert not conn.sqls("INSERT INTO songs")
