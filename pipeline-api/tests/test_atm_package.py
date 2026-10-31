import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402
from _atm_fakes import FakeConn  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
BP = {"titles": ["Satu", "Dua"], "hook": {"line": "Halo kucing"}, "audio": {"bgm_song_id": 8},
      "thumbnail": {"concepts": [{"prompt": "kucing kaget", "overlay_text": "WOW", "why_ctr": "kontras"}]},
      "upload": {"description": "desk", "tags": ["a", "b"], "hashtags": ["#x"], "pinned_comment": "pin"}}


def _get(tmp_path, voice_paths, bgm_path, bp=BP):
    conn = FakeConn([("SELECT title, blueprint", (["t", "b"], [("Judul Kucing!", bp)])),
                     ("kind = 'voiceover'", (["p"], [(p,) for p in voice_paths])),
                     ("WHERE id = %s", (["p"], [(bgm_path,)] if bgm_path else []))])
    with patch("main._db_conn", return_value=conn), patch("main._REPO_ROOT", tmp_path):
        return client.get("/atm/items/3/package"), conn


def test_package_contains_texts_and_audio(tmp_path):
    vo = tmp_path / "data" / "songs" / "voiceover" / "3"
    vo.mkdir(parents=True)
    (vo / "beat_01.mp3").write_bytes(b"VO")
    bgm = tmp_path / "data" / "songs" / "bgm.mp3"
    bgm.write_bytes(b"BGM")
    r, conn = _get(tmp_path, [str(vo / "beat_01.mp3")], str(bgm))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ["bgm/bgm.mp3", "blueprint.json", "blueprint.md", "rekam.html",
                                    "thumbnail_prompts.txt", "upload.txt", "voiceover/beat_01.mp3"]
    assert json.loads(z.read("blueprint.json")) == BP
    assert "Halo kucing" in z.read("blueprint.md").decode() and "kucing kaget" in z.read("thumbnail_prompts.txt").decode()
    up = z.read("upload.txt").decode()
    assert "1. Satu" in up and "a, b" in up and "pin" in up
    assert z.read("voiceover/beat_01.mp3") == b"VO" and "atm-3-Judul-Kucing" in r.headers["content-disposition"]


def test_package_refuses_paths_outside_data(tmp_path):
    (tmp_path / "data").mkdir()
    secret = tmp_path / "secret.mp3"
    secret.write_bytes(b"SECRET")
    sneaky = str(tmp_path / "data" / ".." / "secret.mp3")
    r, _ = _get(tmp_path, [sneaky], str(secret))
    assert r.status_code == 200
    assert b"SECRET" not in r.content
    assert not any(n.endswith(".mp3") for n in zipfile.ZipFile(io.BytesIO(r.content)).namelist())


def test_package_404_and_409(tmp_path):
    with patch("main._db_conn", return_value=FakeConn()), patch("main._REPO_ROOT", tmp_path):
        assert client.get("/atm/items/3/package").status_code == 404
    r, _ = _get(tmp_path, [], None, bp={})
    assert r.status_code == 409


def test_blueprint_markdown_is_readable():
    from atm.package import blueprint_markdown
    bp = json.loads((Path(__file__).parent / "fixtures" / "atm_blueprint_ok.json").read_text())
    bp["extra_key"] = {"catatan": "tambahan"}
    bp["shots"][0]["mood"] = "hangat"
    bp["upload"]["checklist"] = ["cek judul"]
    md = blueprint_markdown("Kucing", bp)
    assert "1. hook pertanyaan" in md and "1. Judul 1" in md and "5. Judul 5" in md
    assert "| Waktu | Kalimat VO | Catatan |" in md and "| 00:00-00:03 | Kucingku nolak makan. | jeda |" in md
    assert "| # | Durasi | Yang direkam | Framing / kamera | Teks layar | Transisi |" in md
    assert "| 1 | 8 dtk | close-up kucing | close / statis | Kenapa? | zoom |" in md
    assert "| Momen | SFX |" in md and "- [ ] rekam kucing" in md and "- [ ] lagu ceria" in md and "- [ ] cek judul" in md
    assert "2. Potong" in md and "### Konsep 3" in md and "### Cover frame" in md and "kucing menatap kamera" in md
    assert "## Lainnya" in md and "**extra_key**" in md and "**mood**: hangat" in md
    assert "-\n" not in md and ": None" not in md and not any(l.strip() in ("-", "- ") for l in md.splitlines())
    assert "tiru:" not in md and "- line:" not in md


FIXTURE = Path(__file__).parent / "fixtures" / "atm_blueprint_ok.json"
EVIL = "</script><img src=x onerror=alert(1)>"


def _data_block(html):
    return html.split('<script type="application/json" id="data">', 1)[1].split("</script>", 1)[0]


def test_package_rekam_html_is_offline_single_file(tmp_path):
    r, _ = _get(tmp_path, [], None)
    html = zipfile.ZipFile(io.BytesIO(r.content)).read("rekam.html").decode()
    assert "http://" not in html and "https://" not in html
    assert '<html lang="id">' in html and '<meta charset="utf-8">' in html
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    data = json.loads(_data_block(html))
    assert data["title"] == "Judul Kucing!" and data["hook"] == "Halo kucing" and data["shots"] == []


def test_rekam_html_embeds_shot_beat_and_cover_subset():
    from atm.package import rekam_html
    data = json.loads(_data_block(rekam_html("Kucing", json.loads(FIXTURE.read_text()))))
    assert data["hook"] == "Kucingku nolak makan?" and data["tips"] == ["rekam per beat"]
    assert data["beats"][1] == {"t": "00:03-00:08", "vo": "Ternyata ini sebabnya."}
    assert data["shots"][0]["record"] == "close-up kucing" and data["shots"][0]["duration_s"] == "8"
    assert data["cover"] == {"shot": "1", "moment": "kucing menatap kamera", "overlay_text": "KENAPA?"}


def test_rekam_html_keeps_untrusted_text_inside_json_data():
    from atm.package import rekam_html
    bp = json.loads(FIXTURE.read_text())
    bp["hook"]["line"] = EVIL
    bp["shots"][0]["record"] = EVIL
    html = rekam_html("Kucing", bp)
    block = _data_block(html)
    assert "</script" not in block and "<img" not in block
    assert html.count("</script>") == 2
    data = json.loads(block)
    assert data["hook"] == EVIL and data["shots"][0]["record"] == EVIL


def test_rekam_js_renders_with_textcontent_only():
    from atm.package import rekam_html
    html = rekam_html("Kucing", json.loads(FIXTURE.read_text()))
    assert "textContent" in html
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert banned not in html


def test_package_builds_with_malformed_blueprint(tmp_path):
    r, _ = _get(tmp_path, [], None, bp=dict(BP, shots="x", narration=None))
    assert r.status_code == 200
    html = zipfile.ZipFile(io.BytesIO(r.content)).read("rekam.html").decode()
    assert json.loads(_data_block(html))["shots"] == []


def test_rekam_html_skips_odd_shapes():
    from atm.package import rekam_html
    bp = {"shots": ["x", {"n": 1, "record": "a", "duration_s": 8}], "narration": {"beats": "x"},
          "recording_tips": "nope", "hook": ["odd"], "thumbnail": {"cover_frame": "x"}}
    data = json.loads(_data_block(rekam_html(None, bp)))
    assert data["title"] == "" and data["hook"] == "" and data["tips"] == [] and data["beats"] == []
    assert data["shots"] == [{"n": "1", "record": "a", "duration_s": "8"}] and data["cover"] == {}
