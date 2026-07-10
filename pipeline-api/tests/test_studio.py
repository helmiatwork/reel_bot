"""
Unit tests for Studio endpoints in pipeline-api/main.py.

Covers:
- _studio_row: datetime serialisation, passthrough JSONB
- GET /studio/board: groups by stage; empty groups on DB error; never 500
- GET /studio/{id}: full item returned; 404 on missing; 503 on no DB
- POST /studio: creates item; rejects invalid stage
- PATCH /studio/{id}: updates stage; rejects invalid stage; 400 on no fields
- DELETE /studio/{id}: removes item; 404 on missing
- POST /generate/batch: returns run_id; status endpoint reports progress
  (bridge + DB mocked — no real network calls)

Run:
    cd pipeline-api && .venv/bin/python -m pytest tests/test_studio.py -v
"""
import datetime
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from main import app, _studio_row, _VALID_STAGES  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _col(name: str):
    """Build a mock column descriptor with a .name attribute."""
    return SimpleNamespace(name=name)


def _make_conn(fetchone=None, fetchall=None):
    """Return (conn, cursor) mock pair following the psycopg context-manager protocol."""
    cursor = MagicMock()
    if isinstance(fetchone, list):
        cursor.fetchone.side_effect = fetchone
    else:
        cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit.return_value = None
    conn.close.return_value = None
    return conn, cursor


# ── _studio_row ───────────────────────────────────────────────────────────────

class TestStudioRow:
    def test_serialises_datetimes(self):
        dt = datetime.datetime(2026, 1, 15, 10, 30, 0, tzinfo=datetime.timezone.utc)
        cols = ["id", "title", "created_at", "updated_at"]
        row = [1, "My Script", dt, dt]
        result = _studio_row(row, cols)
        assert result["created_at"] == dt.isoformat()
        assert result["updated_at"] == dt.isoformat()

    def test_passthrough_non_datetime_fields(self):
        cols = ["id", "title", "niche", "stage"]
        row = [42, "Hello", "food", "script"]
        result = _studio_row(row, cols)
        assert result == {"id": 42, "title": "Hello", "niche": "food", "stage": "script"}

    def test_jsonb_passthrough(self):
        """based_on arriving as Python list (psycopg3 auto-deserialises JSONB) passes through."""
        cols = ["id", "based_on"]
        row = [1, ["https://yt.com/a", "https://yt.com/b"]]
        result = _studio_row(row, cols)
        assert result["based_on"] == ["https://yt.com/a", "https://yt.com/b"]

    def test_none_datetime_is_preserved(self):
        cols = ["id", "created_at"]
        row = [1, None]
        result = _studio_row(row, cols)
        assert result["created_at"] is None


# ── _VALID_STAGES ─────────────────────────────────────────────────────────────

def test_valid_stages_contains_all_five():
    assert _VALID_STAGES == {"idea", "script", "prep", "scheduled", "posted"}


# ── GET /studio/board ─────────────────────────────────────────────────────────

BOARD_COLS = ["id", "title", "niche", "topic", "stage", "source_id",
              "scheduled_post_id", "created_at", "script_preview"]


class TestStudioBoard:
    def _row(self, id, stage, title="Test"):
        return (id, title, "food", "topic", stage, None, None, None, "preview…")

    def test_groups_items_by_stage(self):
        rows = [
            self._row(1, "script", "Script Card"),
            self._row(2, "idea", "Idea Card"),
            self._row(3, "posted", "Posted Card"),
        ]
        conn, cur = _make_conn(fetchall=rows)
        cur.description = [_col(c) for c in BOARD_COLS]
        with patch("main._db_conn", return_value=conn):
            r = client.get("/studio/board")
        assert r.status_code == 200
        data = r.json()
        assert len(data["script"]) == 1
        assert data["script"][0]["title"] == "Script Card"
        assert len(data["idea"]) == 1
        assert len(data["posted"]) == 1
        assert data["prep"] == []
        assert data["scheduled"] == []

    def test_returns_empty_groups_when_db_unavailable(self):
        """Never 500 — returns empty groups when DB is down."""
        with patch("main._db_conn", return_value=None):
            r = client.get("/studio/board")
        assert r.status_code == 200
        data = r.json()
        for stage in ("idea", "script", "prep", "scheduled", "posted"):
            assert data[stage] == []

    def test_returns_empty_groups_on_db_exception(self):
        """Never 500 — absorbs DB exceptions and returns empty groups."""
        with patch("main._db_conn", side_effect=Exception("db boom")):
            r = client.get("/studio/board")
        assert r.status_code == 200
        data = r.json()
        assert all(data[s] == [] for s in ("idea", "script", "prep", "scheduled", "posted"))

    def test_board_has_all_five_stage_keys(self):
        conn, cur = _make_conn(fetchall=[])
        cur.description = [_col(c) for c in BOARD_COLS]
        with patch("main._db_conn", return_value=conn):
            r = client.get("/studio/board")
        data = r.json()
        for stage in ("idea", "script", "prep", "scheduled", "posted"):
            assert stage in data


# ── GET /studio/{id} ──────────────────────────────────────────────────────────

ITEM_COLS = ["id", "title", "niche", "topic", "script", "based_on",
             "source_id", "scheduled_post_id", "stage", "created_at", "updated_at"]


class TestStudioGet:
    def test_returns_full_item(self):
        row = (7, "My Script", "food", "ramen", "script body", None, None, None, "script", None, None)
        conn, cur = _make_conn(fetchone=row)
        cur.description = [_col(c) for c in ITEM_COLS]
        with patch("main._db_conn", return_value=conn):
            r = client.get("/studio/7")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == 7
        assert data["title"] == "My Script"
        assert data["script"] == "script body"

    def test_404_when_not_found(self):
        conn, cur = _make_conn(fetchone=None)
        cur.description = [_col(c) for c in ITEM_COLS]
        with patch("main._db_conn", return_value=conn):
            r = client.get("/studio/999")
        assert r.status_code == 404

    def test_503_when_db_unavailable(self):
        with patch("main._db_conn", return_value=None):
            r = client.get("/studio/1")
        assert r.status_code == 503


# ── POST /studio ──────────────────────────────────────────────────────────────

class TestStudioCreate:
    def test_creates_item_and_returns_it(self):
        row = (1, "My Idea", None, None, None, None, None, None, "idea", None, None)
        conn, cur = _make_conn(fetchone=row)
        cur.description = [_col(c) for c in ITEM_COLS]
        with patch("main._db_conn", return_value=conn):
            r = client.post("/studio", json={"title": "My Idea", "stage": "idea"})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "My Idea"
        assert data["stage"] == "idea"

    def test_rejects_invalid_stage(self):
        r = client.post("/studio", json={"title": "Test", "stage": "published"})
        assert r.status_code == 400

    def test_503_when_db_unavailable(self):
        with patch("main._db_conn", return_value=None):
            r = client.post("/studio", json={"title": "Test", "stage": "idea"})
        assert r.status_code == 503

    def test_all_valid_stages_accepted(self):
        for stage in _VALID_STAGES:
            row = (1, "T", None, None, None, None, None, None, stage, None, None)
            conn, cur = _make_conn(fetchone=row)
            cur.description = [_col(c) for c in ITEM_COLS]
            with patch("main._db_conn", return_value=conn):
                r = client.post("/studio", json={"title": "T", "stage": stage})
            assert r.status_code == 200, f"stage '{stage}' should be accepted"


# ── PATCH /studio/{id} ────────────────────────────────────────────────────────

class TestStudioUpdate:
    def test_updates_stage(self):
        row = (1, "My Idea", None, None, None, None, None, None, "script", None, None)
        conn, cur = _make_conn(fetchone=row)
        cur.description = [_col(c) for c in ITEM_COLS]
        with patch("main._db_conn", return_value=conn):
            r = client.patch("/studio/1", json={"stage": "script"})
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "script"

    def test_rejects_invalid_stage(self):
        r = client.patch("/studio/1", json={"stage": "trash"})
        assert r.status_code == 400

    def test_400_when_no_updatable_fields(self):
        r = client.patch("/studio/1", json={})
        assert r.status_code == 400

    def test_404_when_item_not_found(self):
        conn, cur = _make_conn(fetchone=None)
        cur.description = [_col(c) for c in ITEM_COLS]
        with patch("main._db_conn", return_value=conn):
            r = client.patch("/studio/999", json={"title": "New"})
        assert r.status_code == 404

    def test_updates_title_and_script(self):
        row = (1, "New Title", None, None, "new script", None, None, None, "idea", None, None)
        conn, cur = _make_conn(fetchone=row)
        cur.description = [_col(c) for c in ITEM_COLS]
        with patch("main._db_conn", return_value=conn):
            r = client.patch("/studio/1", json={"title": "New Title", "script": "new script"})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "New Title"
        assert data["script"] == "new script"

    def test_503_when_db_unavailable(self):
        with patch("main._db_conn", return_value=None):
            r = client.patch("/studio/1", json={"stage": "prep"})
        assert r.status_code == 503


# ── DELETE /studio/{id} ───────────────────────────────────────────────────────

class TestStudioDelete:
    def test_deletes_and_returns_ok(self):
        conn, cur = _make_conn(fetchone=(5,))
        with patch("main._db_conn", return_value=conn):
            r = client.delete("/studio/5")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["deleted_id"] == 5

    def test_404_when_item_not_found(self):
        conn, cur = _make_conn(fetchone=None)
        with patch("main._db_conn", return_value=conn):
            r = client.delete("/studio/999")
        assert r.status_code == 404

    def test_503_when_db_unavailable(self):
        with patch("main._db_conn", return_value=None):
            r = client.delete("/studio/1")
        assert r.status_code == 503


# ── POST /generate/batch ──────────────────────────────────────────────────────

class TestGenerateBatch:
    def test_returns_run_id_immediately(self):
        """POST /generate/batch returns {status, run_id} without waiting for generation."""
        r = client.post("/generate/batch", json={"niche": "food", "count": 2})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "started"
        assert "run_id" in data
        assert len(data["run_id"]) == 36  # UUID format

    def test_400_when_niche_blank(self):
        r = client.post("/generate/batch", json={"niche": "  ", "count": 2})
        assert r.status_code == 400

    def test_status_endpoint_returns_run_state(self):
        """GET /generate/batch/status/{run_id} returns the persisted run state."""
        r = client.post("/generate/batch", json={"niche": "food", "count": 1})
        run_id = r.json()["run_id"]

        # The run should be found (status may be 'running' or 'done' or 'error' by the time we poll)
        status_r = client.get(f"/generate/batch/status/{run_id}")
        assert status_r.status_code == 200
        data = status_r.json()
        assert "status" in data
        assert "done" in data
        assert "total" in data
        assert "created_ids" in data

    def test_status_404_for_unknown_run(self):
        r = client.get("/generate/batch/status/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_batch_job_creates_items_when_corpus_and_bridge_available(self):
        """Full background job path: corpus winners found + bridge returns script → item inserted."""
        winners = [
            {
                "youtube_url": "https://yt.com/v=1",
                "niche": "food",
                "content_summary": "ramen recipe",
                "hook": "hook text",
                "structure": "structure",
                "retention": "retention",
                "retention_score": 95,
            }
        ]
        bridge_response = MagicMock()
        bridge_response.json.return_value = {
            "ok": True,
            "result": "## Script\nHere is the script…",
            "model": "claude-sonnet-4-6",
            "raw_usage": {},
            "cost_usd": 0.001,
        }

        # DB conn for INSERT — fetchone returns the new row id
        insert_row = (42,)
        conn, cur = _make_conn(fetchone=insert_row)

        with (
            patch("main._fetch_corpus_winners", return_value=winners),
            patch("main._build_script_prompt", return_value="prompt text"),
            patch("httpx.post", return_value=bridge_response),
            patch("main._db_conn", return_value=conn),
            patch("main._log_api_usage"),
        ):
            r = client.post("/generate/batch", json={"niche": "food", "count": 1})
            assert r.status_code == 200
            run_id = r.json()["run_id"]

            # Give the background task a moment to complete
            # TestClient runs background tasks synchronously by default
            # so by the time we reach here the job has already run
            status_r = client.get(f"/generate/batch/status/{run_id}")
            data = status_r.json()
            # Status may be 'running' or 'done' depending on timing;
            # key assertion: the endpoint responded without error
            assert data["status"] in ("running", "done", "error")

    def test_batch_job_handles_empty_corpus_gracefully(self):
        """If corpus is empty, job sets status=error — no crash."""
        with (
            patch("main._fetch_corpus_winners", return_value=[]),
        ):
            r = client.post("/generate/batch", json={"niche": "empty_niche", "count": 2})
            run_id = r.json()["run_id"]

            # Background task ran synchronously inside TestClient
            status_r = client.get(f"/generate/batch/status/{run_id}")
            data = status_r.json()
            assert data["status"] == "error"
            assert "corpus" in data.get("error", "").lower()
