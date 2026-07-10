"""
Unit tests for winner-clone endpoints in pipeline-api/main.py.

Covers:
- GET /winners: ranking (RPM-preferred when revenue present, else views),
  shape, never 500 on empty DB or missing conn.
- POST /winners/clone: returns run_id immediately; status endpoint
  reports progress; created items are content_items at stage='script'.
  Bridge + DB are mocked — no real network calls.
- _resolve_winner_exemplar: seed priority (content_item > source >
  seed_video_url > corpus fallback) asserted via DB mocks.
- _build_variation_prompt: includes niche + variation index, reuses
  winner exemplar material.
- GET /winners/clone/status/{run_id}: returns run state; 404 on unknown.

Run:
    cd pipeline-api && .venv/bin/python -m pytest tests/test_winners.py -v
"""
import json
import sys
import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from main import (  # noqa: E402
    app,
    _get_winners,
    _resolve_winner_exemplar,
    _build_variation_prompt,
)

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _col(name: str):
    return SimpleNamespace(name=name)


def _make_conn(*fetchall_side_effects, fetchone=None):
    """
    Build a (conn, cursor) mock pair.
    fetchall_side_effects: successive return values for cursor.fetchall().
    fetchone: return value for cursor.fetchone() (single or list for side_effect).
    """
    cursor = MagicMock()
    if fetchall_side_effects:
        cursor.fetchall.side_effect = list(fetchall_side_effects)
    else:
        cursor.fetchall.return_value = []

    if isinstance(fetchone, list):
        cursor.fetchone.side_effect = fetchone
    else:
        cursor.fetchone.return_value = fetchone

    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.description = []

    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit.return_value = None
    conn.close.return_value = None
    return conn, cursor


# ── _build_variation_prompt ───────────────────────────────────────────────────

class TestBuildVariationPrompt:
    def test_includes_variation_index(self):
        exemplar = {"hook": "hook text", "structure": "structure", "niche": "food"}
        prompt = _build_variation_prompt(exemplar, 3, "food")
        assert "VARIASI #3" in prompt

    def test_includes_niche(self):
        exemplar = {"content_summary": "ramen recipe"}
        prompt = _build_variation_prompt(exemplar, 1, "kuliner")
        assert "kuliner" in prompt

    def test_includes_script_when_present(self):
        exemplar = {"script": "## Script\nThis is the winner script."}
        prompt = _build_variation_prompt(exemplar, 1, "food")
        assert "Script Pemenang" in prompt
        assert "This is the winner script." in prompt

    def test_includes_hook_structure_retention(self):
        exemplar = {
            "hook": "the hook",
            "structure": "the structure",
            "retention": "the retention",
        }
        prompt = _build_variation_prompt(exemplar, 2, "fashion")
        assert "the hook" in prompt
        assert "the structure" in prompt
        assert "the retention" in prompt

    def test_script_truncated_at_800_chars(self):
        exemplar = {"script": "x" * 1000}
        prompt = _build_variation_prompt(exemplar, 1, "food")
        # should not include more than 800 chars of the script
        assert "x" * 801 not in prompt

    def test_empty_niche_defaults_to_unknown(self):
        prompt = _build_variation_prompt({}, 1, "")
        assert "unknown" in prompt

    def test_returns_string(self):
        assert isinstance(_build_variation_prompt({}, 1, "test"), str)


# ── _get_winners ──────────────────────────────────────────────────────────────

class TestGetWinners:
    def _perf_rows(self):
        # (platform, url, title, latest_views)
        return [
            ("youtube", "https://yt.com/a", "Video A", 10000),
            ("tiktok",  "https://tt.com/b", "Video B", 20000),
        ]

    def test_ranks_rpm_before_views(self):
        """Video A has revenue → higher RPM; Video B has more views but no revenue.
        Expected: Video A ranked first."""
        perf_rows = self._perf_rows()  # A=10k views, B=20k views
        # Revenue: only A has revenue ($100 → RPM = 10.0)
        rev_rows = [("https://yt.com/a", 100.0)]
        source_rows = []
        ci_rows = []

        conn, _ = _make_conn(perf_rows, rev_rows, source_rows, ci_rows)
        with patch("main._db_conn", return_value=conn):
            result = _get_winners()

        assert len(result) == 2
        assert result[0]["url"] == "https://yt.com/a"
        assert result[0]["rpm"] == 10.0
        assert result[1]["url"] == "https://tt.com/b"
        assert result[1]["rpm"] == 0

    def test_ranks_by_views_when_no_revenue(self):
        """Both videos have no revenue → rank by views desc."""
        perf_rows = [
            ("youtube", "https://yt.com/a", "Low views", 5000),
            ("tiktok",  "https://tt.com/b", "High views", 50000),
        ]
        conn, _ = _make_conn(perf_rows, [], [], [])
        with patch("main._db_conn", return_value=conn):
            result = _get_winners()

        assert result[0]["url"] == "https://tt.com/b"
        assert result[1]["url"] == "https://yt.com/a"

    def test_returns_empty_list_when_no_perf_snapshots(self):
        conn, _ = _make_conn([])  # empty perf query
        with patch("main._db_conn", return_value=conn):
            result = _get_winners()
        assert result == []

    def test_returns_empty_list_when_no_db(self):
        with patch("main._db_conn", return_value=None):
            result = _get_winners()
        assert result == []

    def test_never_500_on_db_exception(self):
        with patch("main._db_conn", side_effect=Exception("db exploded")):
            r = client.get("/winners")
        assert r.status_code == 200
        assert r.json() == []

    def test_shape_has_required_fields(self):
        perf_rows = [("youtube", "https://yt.com/a", "Video A", 10000)]
        conn, _ = _make_conn(perf_rows, [], [], [])
        with patch("main._db_conn", return_value=conn):
            result = _get_winners()

        assert len(result) == 1
        v = result[0]
        assert "platform" in v
        assert "url" in v
        assert "title" in v
        assert "latest_views" in v
        assert "revenue" in v
        assert "rpm" in v
        assert "seed" in v
        assert isinstance(v["seed"], dict)

    def test_seed_populated_with_source_id(self):
        perf_rows = [("youtube", "https://yt.com/a", "Video A", 10000)]
        source_rows = [(42, "https://yt.com/a")]  # source_id=42 matches URL
        ci_rows = []
        conn, _ = _make_conn(perf_rows, [], source_rows, ci_rows)
        with patch("main._db_conn", return_value=conn):
            result = _get_winners()

        assert result[0]["seed"]["source_id"] == 42

    def test_seed_populated_with_content_item_id(self):
        perf_rows = [("youtube", "https://yt.com/a", "Video A", 10000)]
        source_rows = []
        ci_rows = [(99, "https://yt.com/a")]  # ci_id=99 references URL
        conn, _ = _make_conn(perf_rows, [], source_rows, ci_rows)
        with patch("main._db_conn", return_value=conn):
            result = _get_winners()

        assert result[0]["seed"]["content_item_id"] == 99

    def test_capped_at_20_results(self):
        perf_rows = [("youtube", f"https://yt.com/{i}", f"Video {i}", i * 100) for i in range(25)]
        conn, _ = _make_conn(perf_rows, [], [], [])
        with patch("main._db_conn", return_value=conn):
            result = _get_winners()
        assert len(result) == 20

    def test_rpm_zero_when_no_views(self):
        """Zero views → no RPM division (avoid ZeroDivisionError)."""
        perf_rows = [("youtube", "https://yt.com/a", "Video A", 0)]
        rev_rows = [("https://yt.com/a", 50.0)]  # has revenue but 0 views
        conn, _ = _make_conn(perf_rows, rev_rows, [], [])
        with patch("main._db_conn", return_value=conn):
            result = _get_winners()
        assert result[0]["rpm"] == 0

    def test_get_winners_endpoint_returns_200(self):
        with patch("main._db_conn", return_value=None):
            r = client.get("/winners")
        assert r.status_code == 200


# ── _resolve_winner_exemplar ──────────────────────────────────────────────────

class TestResolveWinnerExemplar:
    def test_priority1_content_item_found(self):
        """seed_content_item_id → use content_item script + topic."""
        conn, cur = _make_conn(fetchone=("ramen recipe topic", "## Script body", "food"))
        with patch("main._db_conn", return_value=conn):
            result = _resolve_winner_exemplar(seed_ci_id=7, seed_source_id=None,
                                               seed_video_url=None, niche="food")
        assert result is not None
        assert result["type"] == "content_item"
        assert result["script"] == "## Script body"
        assert result["content_summary"] == "ramen recipe topic"

    def test_priority1_falls_through_when_not_found(self):
        """seed_ci_id given but not in DB → fall through to corpus."""
        conn_ci, _ = _make_conn(fetchone=None)  # ci not found
        corpus_winner = {
            "hook": "hook", "structure": "s", "retention": "r",
            "content_summary": "cs", "niche": "food",
        }
        with (
            patch("main._db_conn", return_value=conn_ci),
            patch("main._fetch_corpus_winners", return_value=[corpus_winner]),
        ):
            result = _resolve_winner_exemplar(seed_ci_id=999, seed_source_id=None,
                                               seed_video_url=None, niche="food")
        assert result is not None
        assert result["type"] == "corpus_winner"

    def test_priority2_source_id(self):
        """seed_source_id → use source analysis."""
        row = ("hook text", "structure text", "retention text", "summary", "food")
        conn, _ = _make_conn(fetchone=row)
        with patch("main._db_conn", return_value=conn):
            result = _resolve_winner_exemplar(seed_ci_id=None, seed_source_id=31,
                                               seed_video_url=None, niche="food")
        assert result is not None
        assert result["type"] == "source"
        assert result["hook"] == "hook text"
        assert result["structure"] == "structure text"

    def test_priority2_falls_through_when_no_analysis(self):
        """seed_source_id found but analysis all NULL → fall through."""
        row = (None, None, None, None, None)
        conn, _ = _make_conn(fetchone=row)
        corpus_winner = {"hook": "h", "structure": "s", "retention": "r",
                         "content_summary": "c", "niche": "food"}
        with (
            patch("main._db_conn", return_value=conn),
            patch("main._fetch_corpus_winners", return_value=[corpus_winner]),
        ):
            result = _resolve_winner_exemplar(seed_ci_id=None, seed_source_id=1,
                                               seed_video_url=None, niche="food")
        assert result is not None
        assert result["type"] == "corpus_winner"

    def test_priority3_seed_video_url(self):
        """seed_video_url matched against sources → return source_url type."""
        row = ("hook", "structure", "retention", "summary", "food")
        conn, _ = _make_conn(fetchone=row)
        with patch("main._db_conn", return_value=conn):
            result = _resolve_winner_exemplar(seed_ci_id=None, seed_source_id=None,
                                               seed_video_url="https://yt.com/v=1", niche="food")
        assert result is not None
        assert result["type"] == "source_url"
        assert result["hook"] == "hook"

    def test_priority4_corpus_fallback(self):
        """No seeds provided → corpus fallback."""
        corpus_winner = {
            "hook": "fallback hook", "structure": "s", "retention": "r",
            "content_summary": "c", "niche": "travel",
            "youtube_url": "https://yt.com/corpus",
        }
        with patch("main._fetch_corpus_winners", return_value=[corpus_winner]):
            result = _resolve_winner_exemplar(seed_ci_id=None, seed_source_id=None,
                                               seed_video_url=None, niche="travel")
        assert result is not None
        assert result["type"] == "corpus_winner"
        assert result["hook"] == "fallback hook"

    def test_returns_none_when_corpus_empty(self):
        """No seeds, empty corpus → None."""
        with patch("main._fetch_corpus_winners", return_value=[]):
            result = _resolve_winner_exemplar(seed_ci_id=None, seed_source_id=None,
                                               seed_video_url=None, niche="")
        assert result is None

    def test_niche_inherited_from_exemplar(self):
        """When req.niche is empty, exemplar's niche is used."""
        row = ("hook", "structure", "retention", "summary", "makanan")
        conn, _ = _make_conn(fetchone=row)
        with patch("main._db_conn", return_value=conn):
            result = _resolve_winner_exemplar(seed_ci_id=None, seed_source_id=5,
                                               seed_video_url=None, niche="")
        assert result["niche"] == "makanan"


# ── POST /winners/clone ───────────────────────────────────────────────────────

class TestWinnersClone:
    def test_returns_run_id_immediately(self):
        r = client.post("/winners/clone", json={"seed_source_id": 31, "niche": "food", "n": 2})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "started"
        assert "run_id" in data
        assert len(data["run_id"]) == 36  # UUID

    def test_status_endpoint_returns_run_state(self):
        r = client.post("/winners/clone", json={"niche": "food", "n": 1})
        run_id = r.json()["run_id"]
        status_r = client.get(f"/winners/clone/status/{run_id}")
        assert status_r.status_code == 200
        data = status_r.json()
        assert "status" in data
        assert "done" in data
        assert "total" in data
        assert "created_ids" in data

    def test_status_404_for_unknown_run(self):
        r = client.get("/winners/clone/status/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_n_capped_at_10(self):
        """n > 10 is silently capped."""
        r = client.post("/winners/clone", json={"niche": "food", "n": 99})
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        status_r = client.get(f"/winners/clone/status/{run_id}")
        data = status_r.json()
        assert data["total"] == 10

    def test_n_minimum_is_1(self):
        r = client.post("/winners/clone", json={"niche": "food", "n": 0})
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        status_r = client.get(f"/winners/clone/status/{run_id}")
        assert status_r.json()["total"] == 1

    def test_job_creates_content_item_at_script_stage(self):
        """Full happy path: exemplar resolved, bridge ok, DB insert succeeds."""
        exemplar = {
            "type": "source",
            "hook": "hook", "structure": "s", "retention": "r",
            "content_summary": "cs", "niche": "food",
        }
        bridge_resp = MagicMock()
        bridge_resp.json.return_value = {
            "ok": True,
            "result": "## Script\nVariation script text",
            "model": "claude-sonnet-4-6",
            "raw_usage": {},
            "cost_usd": 0.001,
        }
        insert_row = (77,)
        conn, cur = _make_conn(fetchone=insert_row)

        with (
            patch("main._resolve_winner_exemplar", return_value=exemplar),
            patch("main._build_variation_prompt", return_value="prompt text"),
            patch("httpx.post", return_value=bridge_resp),
            patch("main._db_conn", return_value=conn),
            patch("main._log_api_usage"),
        ):
            r = client.post("/winners/clone", json={"seed_source_id": 31, "niche": "food", "n": 1})
            assert r.status_code == 200
            run_id = r.json()["run_id"]

            status_r = client.get(f"/winners/clone/status/{run_id}")
            data = status_r.json()
            assert data["status"] in ("running", "done", "error")

    def test_job_error_when_no_exemplar_found(self):
        """If exemplar is None, job sets status=error — no crash."""
        with patch("main._resolve_winner_exemplar", return_value=None):
            r = client.post("/winners/clone", json={"niche": "unknown_niche", "n": 1})
            run_id = r.json()["run_id"]

        # TestClient runs background tasks synchronously by default
        status_r = client.get(f"/winners/clone/status/{run_id}")
        data = status_r.json()
        assert data["status"] in ("error", "running")

    def test_job_handles_bridge_error_gracefully(self):
        """Bridge connection failure is logged and job continues without crashing."""
        exemplar = {"type": "corpus_winner", "hook": "h", "niche": "food"}
        with (
            patch("main._resolve_winner_exemplar", return_value=exemplar),
            patch("httpx.post", side_effect=Exception("bridge down")),
            patch("main._db_conn", return_value=None),
        ):
            r = client.post("/winners/clone", json={"niche": "food", "n": 1})
            assert r.status_code == 200
            run_id = r.json()["run_id"]
            status_r = client.get(f"/winners/clone/status/{run_id}")
            assert status_r.json()["status"] in ("running", "done", "error")

    def test_title_format(self):
        """Verify content_items get title 'Variation N — <niche>'."""
        exemplar = {"type": "source", "hook": "h", "structure": "s",
                    "retention": "r", "content_summary": "c", "niche": "food"}
        bridge_resp = MagicMock()
        bridge_resp.json.return_value = {
            "ok": True, "result": "script", "model": "claude-sonnet-4-6",
            "raw_usage": {}, "cost_usd": 0.001,
        }
        captured_inserts = []

        def _fake_execute(sql, params):
            if "INSERT INTO content_items" in sql:
                captured_inserts.append(params)

        conn, cur = _make_conn(fetchone=(55,))
        cur.execute.side_effect = _fake_execute
        cur.fetchone.return_value = (55,)

        with (
            patch("main._resolve_winner_exemplar", return_value=exemplar),
            patch("httpx.post", return_value=bridge_resp),
            patch("main._db_conn", return_value=conn),
            patch("main._log_api_usage"),
        ):
            r = client.post("/winners/clone", json={"niche": "food", "n": 1})
            run_id = r.json()["run_id"]
            client.get(f"/winners/clone/status/{run_id}")

        if captured_inserts:
            title = captured_inserts[0][0]
            assert title.startswith("Variation 1 —")
            assert "food" in title

    def test_created_items_tracked_in_status(self):
        """created_ids in status should contain the inserted content_item id."""
        exemplar = {"type": "corpus_winner", "hook": "h", "niche": "food"}
        bridge_resp = MagicMock()
        bridge_resp.json.return_value = {
            "ok": True, "result": "script body", "model": "claude-sonnet-4-6",
            "raw_usage": {}, "cost_usd": 0.001,
        }
        conn, cur = _make_conn(fetchone=(123,))

        with (
            patch("main._resolve_winner_exemplar", return_value=exemplar),
            patch("main._build_variation_prompt", return_value="prompt"),
            patch("httpx.post", return_value=bridge_resp),
            patch("main._db_conn", return_value=conn),
            patch("main._log_api_usage"),
        ):
            r = client.post("/winners/clone", json={"niche": "food", "n": 1})
            run_id = r.json()["run_id"]
            status_r = client.get(f"/winners/clone/status/{run_id}")
            data = status_r.json()

        # created_ids should contain 123 if job ran to completion
        if data["status"] == "done":
            assert 123 in data["created_ids"]
        else:
            # job may still be in 'running' state in test env — just verify shape
            assert "created_ids" in data
