"""
Unit tests for the Prep Bundle endpoints and helpers in pipeline-api/main.py.

Covers:
- GET /prep/list          — returns list; empty on DB failure
- GET /prep/{id}          — all keys present; graceful nulls when data missing
- PATCH /prep/{id}        — upserts bgm_song_id; asserts SQL + params
- GET /prep/{id}/zip      — valid zip with generated text files; 404 when source absent
- POST /prep/{id}/roughcut — status transitions; captions flag; ffmpeg mocked
- RoughcutRequest         — captions field defaults to True
- _prep_transcribe        — SRT write, graceful degradation on no speech / errors
- _prep_build_roughcut    — subtitles filter present/absent based on srt_path

Run:
    cd pipeline-api && .venv/bin/python -m pytest tests/test_prep.py -v
"""

import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as _main
from fastapi.testclient import TestClient
from main import (  # noqa: E402
    app,
    _prep_build_transcript,
    _prep_build_strategy_md,
    _prep_seo,
    _prep_build_roughcut,
    _prep_source_hd_path,
    _prep_transcribe,
    RoughcutRequest,
)

client = TestClient(app, raise_server_exceptions=False)


# ── DB mock factory ────────────────────────────────────────────────────────────

def _make_conn(fetchone_returns=None, fetchall_returns=None, commit=True):
    """Build a psycopg connection mock with a cursor that returns canned data."""
    cursor = MagicMock()
    # Support multiple sequential fetchone calls via side_effect list
    if isinstance(fetchone_returns, list):
        cursor.fetchone.side_effect = fetchone_returns
    else:
        cursor.fetchone.return_value = fetchone_returns
    cursor.fetchall.return_value = fetchall_returns or []
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit.return_value = None
    conn.close.return_value = None
    return conn, cursor


# ── GET /prep/list ─────────────────────────────────────────────────────────────

class TestPrepList:
    def test_returns_list_of_sources(self):
        """Returns a JSON array of source records from DB."""
        rows = [
            (1, "My Reel", "youtube", "https://youtube.com/watch?v=abc", "2026-01-01"),
            (2, "TikTok clip", "tiktok", "https://tiktok.com/@u/video/123", "2026-01-02"),
        ]
        conn, _ = _make_conn(fetchall_returns=rows)
        with patch("main._db_conn", return_value=conn):
            r = client.get("/prep/list")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["source_id"] == 1
        assert data[0]["title"] == "My Reel"
        assert data[0]["platform"] == "youtube"
        assert "thumb_url" in data[0]

    def test_returns_empty_list_when_db_unavailable(self):
        """Never 500 — empty list when _db_conn returns None."""
        with patch("main._db_conn", return_value=None):
            r = client.get("/prep/list")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_empty_list_on_query_error(self):
        """Never 500 — empty list when cursor raises."""
        conn, cursor = _make_conn()
        cursor.execute.side_effect = Exception("DB exploded")
        with patch("main._db_conn", return_value=conn):
            r = client.get("/prep/list")
        assert r.status_code == 200
        assert r.json() == []


# ── GET /prep/{source_id} ──────────────────────────────────────────────────────

class TestPrepGet:
    def _source_row(self):
        return ("Cool Reel", "youtube", "https://youtube.com/watch?v=abc123")

    def test_returns_all_keys(self):
        """All bundle keys are present even when analysis/segments/bgm are missing."""
        conn, cursor = _make_conn(
            fetchone_returns=[
                self._source_row(),   # sources query
                None,                  # video_analysis (no row)
                None,                  # prep_bundles (no row)
            ],
            fetchall_returns=[],       # video_segments (empty)
        )
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_seo", return_value={"titles": [], "hashtags": [], "description": ""}),
        ):
            r = client.get("/prep/12")
        assert r.status_code == 200
        data = r.json()
        for key in ("source_id", "title", "platform", "preview", "source_hd",
                    "clips", "transcript", "strategy", "seo", "bgm", "roughcut"):
            assert key in data, f"missing key: {key}"

    def test_source_hd_null_when_not_downloaded(self):
        """source_hd is null when the HD file doesn't exist on disk."""
        conn, cursor = _make_conn(
            fetchone_returns=[self._source_row(), None, None],
            fetchall_returns=[],
        )
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_seo", return_value={}),
        ):
            r = client.get("/prep/12")
        assert r.json()["source_hd"] is None

    def test_clips_list_from_segments(self):
        """clips list is built from video_segments rows."""
        seg_rows = [
            (0, 0.0, 4.5, None, None, "found", 0.9, "/data/seg_00.mp4"),
            (1, 4.5, 9.0, None, None, "found", 0.8, "/data/seg_01.mp4"),
        ]
        conn, cursor = _make_conn(
            fetchone_returns=[self._source_row(), None, None],
            fetchall_returns=seg_rows,
        )
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_seo", return_value={}),
        ):
            r = client.get("/prep/12")
        clips = r.json()["clips"]
        assert len(clips) == 2
        assert clips[0]["index"] == 0
        assert clips[0]["start"] == 0.0
        assert clips[0]["end"] == 4.5
        assert clips[0]["url"] == "/prep/12/clip/0"

    def test_bgm_null_when_not_set(self):
        """bgm is null when no bgm_song_id in prep_bundles."""
        conn, cursor = _make_conn(
            fetchone_returns=[self._source_row(), None, None],
            fetchall_returns=[],
        )
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_seo", return_value={}),
        ):
            r = client.get("/prep/12")
        assert r.json()["bgm"] is None

    def test_roughcut_status_none_default(self):
        """roughcut.status is 'none' when no prep_bundles row."""
        conn, cursor = _make_conn(
            fetchone_returns=[self._source_row(), None, None],
            fetchall_returns=[],
        )
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_seo", return_value={}),
        ):
            r = client.get("/prep/12")
        rc = r.json()["roughcut"]
        assert rc["status"] == "none"
        assert rc["url"] is None

    def test_404_when_source_not_found(self):
        """Returns 404 when source_id not in DB."""
        conn, cursor = _make_conn(fetchone_returns=None)
        with patch("main._db_conn", return_value=conn):
            r = client.get("/prep/999")
        assert r.status_code == 404

    def test_strategy_keys_present(self):
        """strategy dict has hook/structure/retention/retention_score."""
        conn, cursor = _make_conn(
            fetchone_returns=[self._source_row(), None, None],
            fetchall_returns=[],
        )
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_seo", return_value={}),
        ):
            r = client.get("/prep/12")
        strat = r.json()["strategy"]
        assert "hook" in strat
        assert "structure" in strat
        assert "retention" in strat
        assert "retention_score" in strat


# ── PATCH /prep/{source_id} ───────────────────────────────────────────────────

class TestPrepPatch:
    def test_upserts_bgm_song_id(self):
        """PATCH inserts/updates bgm_song_id and commits."""
        conn, cursor = _make_conn(fetchone_returns=(12,))  # source exists
        with patch("main._db_conn", return_value=conn):
            r = client.patch("/prep/12", json={"bgm_song_id": 7})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["bgm_song_id"] == 7
        # Verify the upsert SQL was called (second execute call after source-check)
        calls = cursor.execute.call_args_list
        upsert_call = calls[1]
        sql = upsert_call[0][0]
        assert "INSERT INTO prep_bundles" in sql
        assert "ON CONFLICT" in sql
        params = upsert_call[0][1]
        assert params[0] == 12   # source_id
        assert params[1] == 7    # bgm_song_id
        conn.commit.assert_called_once()

    def test_clears_bgm_with_null(self):
        """PATCH with bgm_song_id=null clears the BGM."""
        conn, cursor = _make_conn(fetchone_returns=(12,))
        with patch("main._db_conn", return_value=conn):
            r = client.patch("/prep/12", json={"bgm_song_id": None})
        assert r.status_code == 200
        assert r.json()["bgm_song_id"] is None

    def test_404_when_source_not_found(self):
        """PATCH returns 404 when source_id not in sources table."""
        conn, cursor = _make_conn(fetchone_returns=None)
        with patch("main._db_conn", return_value=conn):
            r = client.patch("/prep/999", json={"bgm_song_id": 3})
        assert r.status_code == 404


# ── POST /prep/{source_id}/roughcut ──────────────────────────────────────────

class TestPrepRoughcut:
    def test_returns_building_immediately(self):
        """Endpoint returns {status: 'building'} without waiting for ffmpeg."""
        conn, cursor = _make_conn(
            fetchone_returns=[
                ("https://youtube.com/watch?v=abc",),  # source youtube_url
                None,                                    # prep_bundles (no bgm)
            ],
            fetchall_returns=[],  # no segments
        )
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_set_roughcut_status") as mock_set_status,
            patch("main._prep_build_roughcut") as mock_build,
        ):
            r = client.post("/prep/12/roughcut", json={})

        assert r.status_code == 200
        assert r.json()["status"] == "building"
        assert r.json()["url"] is None

    def test_sets_building_status_before_job(self):
        """_prep_set_roughcut_status is called with 'building' before the job runs."""
        conn, cursor = _make_conn(
            fetchone_returns=[("https://youtube.com/watch?v=abc",), None],
            fetchall_returns=[],
        )
        status_calls = []

        def _track_status(sid, status, path):
            status_calls.append((sid, status, path))

        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_set_roughcut_status", side_effect=_track_status),
            patch("main._prep_build_roughcut"),
        ):
            client.post("/prep/12/roughcut", json={})

        # First call must be 'building'
        assert status_calls[0] == (12, "building", None)

    def test_404_when_source_not_found(self):
        """POST /roughcut returns 404 when source_id not in DB."""
        conn, cursor = _make_conn(fetchone_returns=None)
        with patch("main._db_conn", return_value=conn):
            r = client.post("/prep/999/roughcut", json={})
        assert r.status_code == 404


# ── GET /prep/{source_id}/zip ─────────────────────────────────────────────────

class TestPrepZip:
    def _source_conn(self, title="My Reel", platform="youtube"):
        return _make_conn(
            fetchone_returns=[
                (title, platform, "https://youtube.com/watch?v=abc"),  # source
                None,  # prep_bundles (no roughcut/bgm)
            ],
            fetchall_returns=[],  # no segments
        )

    def test_returns_valid_zip_with_text_files(self):
        """ZIP response is parseable and contains transcript.txt, strategy.md, seo.json."""
        conn, _ = self._source_conn()
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_seo", return_value={
                "titles": ["T1"], "hashtags": ["#food"], "description": "desc"
            }),
        ):
            r = client.get("/prep/12/zip")

        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert 'attachment; filename=prep_12.zip' in r.headers["content-disposition"]

        # Parse the zip body
        buf = io.BytesIO(r.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "transcript.txt" in names
            assert "strategy.md" in names
            assert "seo.json" in names
            seo_data = json.loads(zf.read("seo.json"))
            assert "titles" in seo_data

    def test_strategy_md_contains_title(self):
        """strategy.md in the zip contains the source title."""
        conn, _ = self._source_conn(title="Epic Food Reel")
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_seo", return_value={}),
        ):
            r = client.get("/prep/12/zip")

        buf = io.BytesIO(r.content)
        with zipfile.ZipFile(buf) as zf:
            strategy = zf.read("strategy.md").decode()
        assert "Epic Food Reel" in strategy

    def test_404_when_source_not_found(self):
        """ZIP returns 404 when source_id not in sources table."""
        conn, cursor = _make_conn(fetchone_returns=None)
        with patch("main._db_conn", return_value=conn):
            r = client.get("/prep/999/zip")
        assert r.status_code == 404

    def test_503_when_db_unavailable(self):
        """ZIP returns 503 when _db_conn returns None."""
        with patch("main._db_conn", return_value=None):
            r = client.get("/prep/12/zip")
        assert r.status_code == 503


# ── Helper unit tests ─────────────────────────────────────────────────────────

class TestPrepBuildTranscript:
    def test_prefers_detail_over_summary(self):
        analysis = {"detail": "detailed text", "summary": "short summary"}
        assert _prep_build_transcript([], analysis) == "detailed text"

    def test_falls_back_to_summary(self):
        analysis = {"detail": "", "summary": "short summary"}
        assert _prep_build_transcript([], analysis) == "short summary"

    def test_empty_when_no_analysis(self):
        assert _prep_build_transcript([], {}) == ""


class TestPrepBuildStrategyMd:
    def test_contains_title(self):
        md = _prep_build_strategy_md("My Video", {})
        assert "My Video" in md

    def test_includes_hook_section(self):
        md = _prep_build_strategy_md("T", {"hook": "Start with a bang"})
        assert "Hook" in md
        assert "Start with a bang" in md

    def test_includes_retention_score(self):
        md = _prep_build_strategy_md("T", {"retention_score": 8})
        assert "8/10" in md

    def test_skips_empty_fields(self):
        md = _prep_build_strategy_md("T", {"hook": "", "structure": "", "retention": ""})
        assert "Hook" not in md


class TestPrepSeo:
    def test_returns_empty_when_no_title(self):
        result = _prep_seo("", "youtube")
        assert result == {"titles": [], "hashtags": [], "description": ""}

    def test_returns_empty_on_autocomplete_error(self):
        with patch("main._seo_autocomplete", side_effect=Exception("network down")):
            result = _prep_seo("food", "youtube")
        assert result == {"titles": [], "hashtags": [], "description": ""}

    def test_passes_title_to_autocomplete(self):
        with (
            patch("main._seo_autocomplete", return_value=[]) as mock_ac,
            patch("main._seo_synthesize", return_value={}),
        ):
            _prep_seo("ramen recipe", "youtube")
        mock_ac.assert_called_once_with("ramen recipe", "youtube")


class TestPrepBuildRoughcut:
    def test_raises_when_no_sources(self):
        with pytest.raises(RuntimeError, match="no video sources"):
            _prep_build_roughcut([], None, None, Path("/tmp/out.mp4"))

    def test_calls_ffmpeg_with_segment_paths(self, tmp_path):
        """ffmpeg subprocess is called with segment inputs when segment files exist."""
        seg_file = tmp_path / "seg_00.mp4"
        seg_file.write_bytes(b"fake")
        out = tmp_path / "roughcut.mp4"

        segments = [{"clip_index": 0, "segment_path": str(seg_file), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            _prep_build_roughcut(segments, None, None, out)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd
        assert str(seg_file) in cmd
        assert str(out) in cmd
        assert "-filter_complex" in cmd

    def test_falls_back_to_hd_when_no_segments(self, tmp_path):
        """Uses HD source when no segment files exist."""
        hd = tmp_path / "source.mp4"
        hd.write_bytes(b"fake")
        out = tmp_path / "roughcut.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            _prep_build_roughcut([], hd, None, out)

        cmd = mock_run.call_args[0][0]
        assert str(hd) in cmd

    def test_includes_bgm_when_provided(self, tmp_path):
        """BGM is added as a looped input; volume filter applied; no amix (direct map)."""
        seg_file = tmp_path / "seg_00.mp4"
        seg_file.write_bytes(b"fake")
        bgm = tmp_path / "bgm.mp3"
        bgm.write_bytes(b"fake")
        out = tmp_path / "roughcut.mp4"

        segments = [{"clip_index": 0, "segment_path": str(seg_file), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            _prep_build_roughcut(segments, None, bgm, out)

        cmd = mock_run.call_args[0][0]
        assert str(bgm) in cmd
        # BGM input must be looped
        assert "-stream_loop" in cmd
        # BGM mapped as audio; no amix needed
        fc_idx = cmd.index("-filter_complex")
        filter_val = cmd[fc_idx + 1]
        assert "volume=0.3" in filter_val
        assert "amix" not in filter_val
        # Concat must be video-only (a=0)
        assert "a=0" in filter_val
        assert "a=1" not in filter_val
        # No segment audio stream references (segments are inputs 0..n-1; BGM is
        # the last input and its [n:a] pad is legitimately used for the audio track)
        assert "[0:a]" not in filter_val
        # -shortest keeps mux length tied to video
        assert "-shortest" in cmd

    def test_raises_on_ffmpeg_failure(self, tmp_path):
        """RuntimeError raised when ffmpeg returns non-zero."""
        seg_file = tmp_path / "seg_00.mp4"
        seg_file.write_bytes(b"fake")
        out = tmp_path / "roughcut.mp4"

        segments = [{"clip_index": 0, "segment_path": str(seg_file), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "some ffmpeg error"

        with (
            patch("subprocess.run", return_value=mock_proc),
            pytest.raises(RuntimeError, match="ffmpeg roughcut failed"),
        ):
            _prep_build_roughcut(segments, None, None, out)


# ── RoughcutRequest model ─────────────────────────────────────────────────────

class TestRoughcutRequest:
    def test_captions_defaults_to_true(self):
        """captions field defaults to True when not supplied."""
        req = RoughcutRequest()
        assert req.captions is True

    def test_captions_can_be_false(self):
        """captions field accepts False."""
        req = RoughcutRequest(captions=False)
        assert req.captions is False

    def test_endpoint_accepts_captions_field(self):
        """POST /roughcut with captions=false parses without error."""
        conn, cursor = _make_conn(
            fetchone_returns=[("https://youtube.com/watch?v=abc",), None],
            fetchall_returns=[],
        )
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_set_roughcut_status"),
            patch("main._prep_build_roughcut"),
            patch("main._prep_transcribe", return_value=None),
        ):
            r = client.post("/prep/12/roughcut", json={"captions": False})
        assert r.status_code == 200
        assert r.json()["status"] == "building"


# ── _prep_build_roughcut captions ────────────────────────────────────────────

class TestPrepBuildRoughcutCaptions:
    def _mock_seg(self, tmp_path, name="seg_00.mp4"):
        f = tmp_path / name
        f.write_bytes(b"fake")
        return f

    def test_includes_subtitles_filter_when_srt_exists(self, tmp_path):
        """When srt_path exists, filter_complex includes subtitles= referencing the file."""
        seg = self._mock_seg(tmp_path)
        srt = tmp_path / "captions.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")
        out = tmp_path / "roughcut.mp4"
        segments = [{"clip_index": 0, "segment_path": str(seg), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            _prep_build_roughcut(segments, None, None, out, srt_path=srt)

        cmd = mock_run.call_args[0][0]
        fc_idx = cmd.index("-filter_complex")
        filter_val = cmd[fc_idx + 1]
        assert "subtitles" in filter_val
        assert str(srt.absolute()) in filter_val

    def test_output_label_is_vsub_when_srt_provided(self, tmp_path):
        """ffmpeg is invoked with -map [vsub] when an SRT is present."""
        seg = self._mock_seg(tmp_path)
        srt = tmp_path / "captions.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHi\n\n", encoding="utf-8")
        out = tmp_path / "roughcut.mp4"
        segments = [{"clip_index": 0, "segment_path": str(seg), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            _prep_build_roughcut(segments, None, None, out, srt_path=srt)

        cmd = mock_run.call_args[0][0]
        assert "[vsub]" in cmd
        assert "[vout]" not in cmd[cmd.index("-map"):]

    def test_no_subtitles_filter_when_srt_none(self, tmp_path):
        """No subtitles filter when srt_path is None."""
        seg = self._mock_seg(tmp_path)
        out = tmp_path / "roughcut.mp4"
        segments = [{"clip_index": 0, "segment_path": str(seg), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            _prep_build_roughcut(segments, None, None, out, srt_path=None)

        cmd = mock_run.call_args[0][0]
        fc_idx = cmd.index("-filter_complex")
        filter_val = cmd[fc_idx + 1]
        assert "subtitles" not in filter_val
        assert "-map" in cmd
        map_idx = cmd.index("-map")
        assert cmd[map_idx + 1] == "[vout]"

    def test_no_subtitles_filter_when_srt_missing_on_disk(self, tmp_path):
        """SRT path given but file absent → subtitles filter skipped (no crash)."""
        seg = self._mock_seg(tmp_path)
        out = tmp_path / "roughcut.mp4"
        segments = [{"clip_index": 0, "segment_path": str(seg), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            _prep_build_roughcut(
                segments, None, None, out,
                srt_path=tmp_path / "nonexistent.srt"
            )

        cmd = mock_run.call_args[0][0]
        fc_idx = cmd.index("-filter_complex")
        assert "subtitles" not in cmd[fc_idx + 1]

    def test_uses_ffmpeg_full_bin_when_srt_present(self, tmp_path):
        """The ffmpeg-full binary (with libass) is used when captions are burned."""
        seg = self._mock_seg(tmp_path)
        srt = tmp_path / "captions.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n\n", encoding="utf-8")
        out = tmp_path / "roughcut.mp4"
        segments = [{"clip_index": 0, "segment_path": str(seg), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with (
            patch("subprocess.run", return_value=mock_proc) as mock_run,
            patch.object(_main, "_FFMPEG_SUBTITLES_BIN", "/fake/ffmpeg-full"),
        ):
            _prep_build_roughcut(segments, None, None, out, srt_path=srt)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/fake/ffmpeg-full"

    def test_uses_plain_ffmpeg_when_no_srt(self, tmp_path):
        """Plain 'ffmpeg' is used when no SRT is involved."""
        seg = self._mock_seg(tmp_path)
        out = tmp_path / "roughcut.mp4"
        segments = [{"clip_index": 0, "segment_path": str(seg), "start_sec": 0, "end_sec": 5}]

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            _prep_build_roughcut(segments, None, None, out, srt_path=None)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"


# ── _prep_transcribe ──────────────────────────────────────────────────────────

class TestPrepTranscribe:
    def test_returns_none_when_hd_path_is_none(self):
        """Returns None immediately when hd_path is None (file won't exist)."""
        result = _prep_transcribe(None, 999)
        assert result is None

    def test_returns_none_when_file_missing(self, tmp_path):
        """Returns None when hd_path points to a non-existent file."""
        result = _prep_transcribe(tmp_path / "nonexistent.mp4", 999)
        assert result is None

    def test_returns_none_when_no_speech_detected(self, tmp_path):
        """Returns None when transcription yields zero segments (silent video)."""
        hd = tmp_path / "source.mp4"
        hd.write_bytes(b"fake")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        with patch("faster_whisper.WhisperModel", return_value=mock_model):
            result = _prep_transcribe(hd, 999)

        assert result is None

    def test_writes_srt_and_returns_path(self, tmp_path):
        """Writes a valid SRT file and returns its path when speech is detected."""
        hd = tmp_path / "source.mp4"
        hd.write_bytes(b"fake video")

        seg1 = MagicMock()
        seg1.start = 0.0
        seg1.end = 2.5
        seg1.text = " Hello world"

        seg2 = MagicMock()
        seg2.start = 2.5
        seg2.end = 5.0
        seg2.text = " Second line"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg1, seg2]), MagicMock())

        with (
            patch("faster_whisper.WhisperModel", return_value=mock_model),
            patch.object(_main, "_REPO_ROOT", tmp_path),
        ):
            result = _prep_transcribe(hd, 42)

        assert result is not None
        assert result.exists()
        content = result.read_text(encoding="utf-8")
        assert "Hello world" in content
        assert "Second line" in content
        assert "00:00:00,000 --> 00:00:02,500" in content
        # SRT index lines
        assert "1\n" in content
        assert "2\n" in content

    def test_returns_none_on_model_error(self, tmp_path):
        """Never raises — returns None when WhisperModel itself fails."""
        hd = tmp_path / "source.mp4"
        hd.write_bytes(b"fake")

        with patch("faster_whisper.WhisperModel", side_effect=RuntimeError("GPU OOM")):
            result = _prep_transcribe(hd, 999)

        assert result is None

    def test_skips_empty_text_segments(self, tmp_path):
        """Segments with empty text after strip() are not written to SRT."""
        hd = tmp_path / "source.mp4"
        hd.write_bytes(b"fake")

        empty_seg = MagicMock()
        empty_seg.start = 0.0
        empty_seg.end = 1.0
        empty_seg.text = "   "  # whitespace only

        real_seg = MagicMock()
        real_seg.start = 1.0
        real_seg.end = 2.0
        real_seg.text = " Real caption"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([empty_seg, real_seg]), MagicMock())

        with (
            patch("faster_whisper.WhisperModel", return_value=mock_model),
            patch.object(_main, "_REPO_ROOT", tmp_path),
        ):
            result = _prep_transcribe(hd, 99)

        assert result is not None
        content = result.read_text(encoding="utf-8")
        assert "Real caption" in content
        # Only one index entry (empty_seg skipped)
        assert "1\n" in content
        assert "2\n" not in content


# ── Roughcut endpoint captions integration ────────────────────────────────────

class TestPrepRoughcutCaptionsEndpoint:
    def _make_roughcut_conn(self):
        return _make_conn(
            fetchone_returns=[("https://youtube.com/watch?v=abc",), None],
            fetchall_returns=[],
        )

    def test_calls_transcribe_when_captions_true(self):
        """_prep_transcribe is called in the background job when captions=True."""
        conn, _ = self._make_roughcut_conn()
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_set_roughcut_status"),
            patch("main._prep_build_roughcut"),
            patch("main._prep_transcribe", return_value=None) as mock_tx,
        ):
            client.post("/prep/12/roughcut", json={"captions": True})

        mock_tx.assert_called_once()

    def test_skips_transcribe_when_captions_false(self):
        """_prep_transcribe is NOT called when captions=False."""
        conn, _ = self._make_roughcut_conn()
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_set_roughcut_status"),
            patch("main._prep_build_roughcut"),
            patch("main._prep_transcribe", return_value=None) as mock_tx,
        ):
            client.post("/prep/12/roughcut", json={"captions": False})

        mock_tx.assert_not_called()

    def test_default_body_calls_transcribe(self):
        """Empty body (captions defaults to True) still triggers transcription."""
        conn, _ = self._make_roughcut_conn()
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_set_roughcut_status"),
            patch("main._prep_build_roughcut"),
            patch("main._prep_transcribe", return_value=None) as mock_tx,
        ):
            client.post("/prep/12/roughcut", json={})

        mock_tx.assert_called_once()

    def test_roughcut_succeeds_even_when_transcribe_returns_none(self):
        """Build proceeds and ends up 'ready' even when _prep_transcribe returns None."""
        conn, _ = self._make_roughcut_conn()
        status_calls = []

        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_set_roughcut_status", side_effect=lambda sid, s, p: status_calls.append(s)),
            patch("main._prep_build_roughcut"),
            patch("main._prep_transcribe", return_value=None),
        ):
            client.post("/prep/12/roughcut", json={"captions": True})

        assert "ready" in status_calls

    def test_srt_path_passed_to_build_roughcut(self, tmp_path):
        """The SRT returned by _prep_transcribe is forwarded to _prep_build_roughcut."""
        conn, _ = self._make_roughcut_conn()
        fake_srt = tmp_path / "captions.srt"
        fake_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n\n")

        build_calls = []

        def _capture_build(*args, **kwargs):
            build_calls.append(kwargs.get("srt_path") or (args[4] if len(args) > 4 else None))

        with (
            patch("main._db_conn", return_value=conn),
            patch("main._prep_source_hd_path", return_value=None),
            patch("main._prep_set_roughcut_status"),
            patch("main._prep_build_roughcut", side_effect=_capture_build),
            patch("main._prep_transcribe", return_value=fake_srt),
        ):
            client.post("/prep/12/roughcut", json={"captions": True})

        assert len(build_calls) == 1
        assert build_calls[0] == fake_srt
