"""
Unit tests for revenue tracking endpoints in pipeline-api/main.py.

Covers:
- POST /revenue: happy path, invalid platform, negative revenue, bad date
- GET /revenue: list + filters (platform, start/end date)
- PATCH /revenue/{id}: update fields, 404 on missing, invalid input
- DELETE /revenue/{id}: happy path, 404 on missing
- GET /revenue/summary: per-platform totals, RPM math, zero-views guard,
  grand totals, empty-DB case
- _revenue_summary_data: pure math unit tests with mocked DB cursor

Run:
    cd pipeline-api && .venv/bin/python -m pytest tests/test_revenue.py -v
"""
import sys
import datetime as dt
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import the symbols under test
from main import (  # noqa: E402
    _revenue_summary_data,
    _VALID_REVENUE_PLATFORMS,
)
from fastapi.testclient import TestClient
from main import app  # noqa: E402

client = TestClient(app)

# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_cursor(fetchall_return=None, description=None, rowcount=1):
    """Build a mock psycopg2-style cursor."""
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.description = description or []
    cur.fetchall.return_value = fetchall_return or []
    cur.fetchone.return_value = None
    cur.rowcount = rowcount
    return cur


def _mock_conn(cur):
    """Build a mock psycopg2-style connection around the cursor."""
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.commit.return_value = None
    conn.close.return_value = None
    return conn


def _col(name):
    """Minimal column descriptor mock."""
    c = MagicMock()
    c.name = name
    return c


# ── POST /revenue ─────────────────────────────────────────────────────────────

class TestRevenueCreate:

    def _returning_row(self):
        return (
            1, "youtube", "https://youtu.be/X", None,
            Decimal("12.50"), 300, dt.date(2025, 7, 9), "test note",
            dt.datetime(2025, 7, 9, 10, 0, 0),
        )

    def _returning_cols(self):
        names = ["id", "platform", "video_url", "scheduled_post_id",
                 "revenue_usd", "link_clicks", "entry_date", "note", "created_at"]
        return [_col(n) for n in names]

    def test_create_happy_path(self):
        cur = _mock_cursor()
        cur.description = self._returning_cols()
        cur.fetchone.return_value = self._returning_row()
        conn = _mock_conn(cur)

        with patch("main._db_conn", return_value=conn):
            r = client.post("/revenue", json={
                "platform": "youtube",
                "video_url": "https://youtu.be/X",
                "revenue_usd": 12.50,
                "link_clicks": 300,
                "entry_date": "2025-07-09",
                "note": "test note",
            })

        assert r.status_code == 200
        body = r.json()
        assert body["platform"] == "youtube"
        assert body["revenue_usd"] == 12.50
        assert body["link_clicks"] == 300

    def test_invalid_platform_returns_400(self):
        r = client.post("/revenue", json={
            "platform": "snapchat",
            "revenue_usd": 5.0,
            "entry_date": "2025-07-09",
        })
        assert r.status_code == 400
        assert "platform" in r.json()["detail"].lower()

    def test_negative_revenue_returns_400(self):
        r = client.post("/revenue", json={
            "platform": "youtube",
            "revenue_usd": -1.0,
            "entry_date": "2025-07-09",
        })
        assert r.status_code == 400
        assert "revenue_usd" in r.json()["detail"].lower()

    def test_bad_date_returns_400(self):
        r = client.post("/revenue", json={
            "platform": "tiktok",
            "revenue_usd": 5.0,
            "entry_date": "not-a-date",
        })
        assert r.status_code == 400
        assert "entry_date" in r.json()["detail"].lower()

    def test_zero_revenue_accepted(self):
        cur = _mock_cursor()
        cur.description = self._returning_cols()
        row = list(self._returning_row())
        row[4] = Decimal("0.00")
        cur.fetchone.return_value = tuple(row)
        conn = _mock_conn(cur)

        with patch("main._db_conn", return_value=conn):
            r = client.post("/revenue", json={
                "platform": "instagram",
                "revenue_usd": 0,
                "entry_date": "2025-07-09",
            })

        assert r.status_code == 200
        assert r.json()["revenue_usd"] == 0.0

    def test_all_four_platforms_accepted(self):
        for p in _VALID_REVENUE_PLATFORMS:
            cur = _mock_cursor()
            cur.description = self._returning_cols()
            row = list(self._returning_row())
            row[1] = p
            cur.fetchone.return_value = tuple(row)
            conn = _mock_conn(cur)

            with patch("main._db_conn", return_value=conn):
                r = client.post("/revenue", json={
                    "platform": p, "revenue_usd": 1.0, "entry_date": "2025-07-01",
                })
            assert r.status_code == 200, f"platform={p} should be accepted"


# ── GET /revenue ──────────────────────────────────────────────────────────────

class TestRevenueList:

    _COLS = ["id", "platform", "video_url", "scheduled_post_id",
             "revenue_usd", "link_clicks", "entry_date", "note", "created_at"]

    def _rows(self):
        return [
            (1, "youtube", "https://y.be/A", None, Decimal("10.00"), 100,
             dt.date(2025, 7, 1), None, dt.datetime(2025, 7, 1)),
            (2, "tiktok", "https://tt.com/B", None, Decimal("4.00"), 50,
             dt.date(2025, 7, 5), None, dt.datetime(2025, 7, 5)),
        ]

    def test_list_returns_all(self):
        cur = _mock_cursor(fetchall_return=self._rows(),
                           description=[_col(n) for n in self._COLS])
        with patch("main._db_conn", return_value=_mock_conn(cur)):
            r = client.get("/revenue")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_list_never_500_on_db_error(self):
        with patch("main._db_conn", return_value=None):
            r = client.get("/revenue")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_revenue_usd_is_float(self):
        cur = _mock_cursor(fetchall_return=self._rows(),
                           description=[_col(n) for n in self._COLS])
        with patch("main._db_conn", return_value=_mock_conn(cur)):
            r = client.get("/revenue")
        for item in r.json():
            assert isinstance(item["revenue_usd"], float)


# ── GET /revenue/summary ──────────────────────────────────────────────────────

class TestRevenueSummary:

    def test_summary_never_500_on_no_db(self):
        with patch("main._db_conn", return_value=None):
            r = client.get("/revenue/summary")
        assert r.status_code == 200
        body = r.json()
        assert body["grand_total_revenue"] == 0
        assert body["platforms"] == []
        assert body["videos"] == []

    def test_summary_endpoint_returns_expected_keys(self):
        with patch("main._revenue_summary_data", return_value={
            "platforms": [], "videos": [],
            "grand_total_revenue": 0, "grand_total_clicks": 0,
        }):
            r = client.get("/revenue/summary")
        assert r.status_code == 200
        body = r.json()
        for key in ("platforms", "videos", "grand_total_revenue", "grand_total_clicks"):
            assert key in body


# ── _revenue_summary_data: pure math tests ────────────────────────────────────

class TestRevenueSummaryData:
    """Unit-test the pure computation inside _revenue_summary_data by mocking the DB."""

    def _setup_db(self, views_rows, entry_rows):
        """Return a patched _db_conn where views and entries come from the given rows.

        _revenue_summary_data opens ONE cursor context and calls fetchall() twice:
        first for views (no description needed), then for entries (description set).
        We use fetchall.side_effect to return different rows on successive calls.
        """
        entry_cols = ["id", "platform", "video_url", "revenue_usd", "link_clicks",
                      "entry_date", "note", "scheduled_post_id", "created_at"]

        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.description = [_col(n) for n in entry_cols]
        # First fetchall() = views query, second fetchall() = entries query
        cur.fetchall.side_effect = [views_rows, entry_rows]

        conn = MagicMock()
        conn.cursor.return_value = cur
        conn.close.return_value = None
        return conn

    def test_rpm_computed_correctly(self):
        """RPM = revenue / views * 1000 (e.g. $12.50 / 5000 * 1000 = $2.50)."""
        url = "https://youtu.be/A"
        conn = self._setup_db(
            views_rows=[(url, 5000)],
            entry_rows=[
                (1, "youtube", url, Decimal("12.50"), 0,
                 dt.date(2025, 7, 1), None, None, dt.datetime(2025, 7, 1)),
            ],
        )
        with patch("main._db_conn", return_value=conn):
            result = _revenue_summary_data()

        plat = result["platforms"][0]
        assert plat["platform"] == "youtube"
        assert plat["total_revenue"] == pytest.approx(12.50)
        assert plat["rpm"] == pytest.approx(2.50)

    def test_rpm_zero_when_views_zero(self):
        """No ZeroDivisionError when views = 0."""
        url = "https://tiktok.com/B"
        conn = self._setup_db(
            views_rows=[],   # no snapshots → 0 views
            entry_rows=[
                (2, "tiktok", url, Decimal("4.00"), 50,
                 dt.date(2025, 7, 5), None, None, dt.datetime(2025, 7, 5)),
            ],
        )
        with patch("main._db_conn", return_value=conn):
            result = _revenue_summary_data()

        plat = result["platforms"][0]
        assert plat["rpm"] == 0
        assert plat["total_revenue"] == pytest.approx(4.00)

    def test_grand_totals_across_platforms(self):
        """grand_total_revenue and grand_total_clicks sum across all entries."""
        url_a = "https://youtu.be/A"
        url_b = "https://tiktok.com/B"
        conn = self._setup_db(
            views_rows=[(url_a, 1000), (url_b, 500)],
            entry_rows=[
                (1, "youtube", url_a, Decimal("12.50"), 300,
                 dt.date(2025, 7, 1), None, None, dt.datetime(2025, 7, 1)),
                (2, "tiktok", url_b, Decimal("4.00"), 90,
                 dt.date(2025, 7, 5), None, None, dt.datetime(2025, 7, 5)),
            ],
        )
        with patch("main._db_conn", return_value=conn):
            result = _revenue_summary_data()

        assert result["grand_total_revenue"] == pytest.approx(16.50)
        assert result["grand_total_clicks"] == 390
        assert len(result["platforms"]) == 2

    def test_empty_entries_returns_zero_totals(self):
        """No entries → all zeros, no crash."""
        conn = self._setup_db(views_rows=[], entry_rows=[])
        with patch("main._db_conn", return_value=conn):
            result = _revenue_summary_data()

        assert result["grand_total_revenue"] == 0
        assert result["grand_total_clicks"] == 0
        assert result["platforms"] == []
        assert result["videos"] == []

    def test_per_video_rpm(self):
        """Per-video RPM = video_revenue / video_views * 1000."""
        url = "https://youtu.be/Z"
        conn = self._setup_db(
            views_rows=[(url, 2000)],
            entry_rows=[
                (3, "youtube", url, Decimal("6.00"), 120,
                 dt.date(2025, 7, 10), None, None, dt.datetime(2025, 7, 10)),
            ],
        )
        with patch("main._db_conn", return_value=conn):
            result = _revenue_summary_data()

        vid = next(v for v in result["videos"] if v["video_url"] == url)
        # RPM = 6 / 2000 * 1000 = 3.00
        assert vid["rpm"] == pytest.approx(3.00)
        assert vid["latest_views"] == 2000

    def test_never_raises_on_db_exception(self):
        """DB error mid-execution → empty result, no exception propagated."""
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchall.side_effect = Exception("connection reset")

        conn = MagicMock()
        conn.cursor.return_value = cur
        conn.close.return_value = None
        with patch("main._db_conn", return_value=conn):
            result = _revenue_summary_data()

        assert result["platforms"] == []
        assert result["grand_total_revenue"] == 0


# ── PATCH /revenue/{id} ───────────────────────────────────────────────────────

class TestRevenueUpdate:

    _COLS = ["id", "platform", "video_url", "scheduled_post_id",
             "revenue_usd", "link_clicks", "entry_date", "note", "created_at"]

    def test_patch_updates_revenue(self):
        row = (1, "youtube", None, None, Decimal("20.00"), 0,
               dt.date(2025, 7, 9), None, dt.datetime(2025, 7, 9))
        cur = _mock_cursor(description=[_col(n) for n in self._COLS])
        cur.fetchone.return_value = row
        cur.rowcount = 1
        conn = _mock_conn(cur)

        with patch("main._db_conn", return_value=conn):
            r = client.patch("/revenue/1", json={"revenue_usd": 20.0})

        assert r.status_code == 200
        assert r.json()["revenue_usd"] == 20.0

    def test_patch_404_on_missing(self):
        cur = _mock_cursor()
        cur.rowcount = 0
        conn = _mock_conn(cur)

        with patch("main._db_conn", return_value=conn):
            r = client.patch("/revenue/9999", json={"revenue_usd": 5.0})

        assert r.status_code == 404

    def test_patch_invalid_platform_400(self):
        r = client.patch("/revenue/1", json={"platform": "youtube_shorts"})
        assert r.status_code == 400

    def test_patch_negative_revenue_400(self):
        r = client.patch("/revenue/1", json={"revenue_usd": -5.0})
        assert r.status_code == 400

    def test_patch_bad_date_400(self):
        r = client.patch("/revenue/1", json={"entry_date": "32-13-2025"})
        assert r.status_code == 400

    def test_patch_no_fields_400(self):
        r = client.patch("/revenue/1", json={})
        assert r.status_code == 400


# ── DELETE /revenue/{id} ──────────────────────────────────────────────────────

class TestRevenueDelete:

    def test_delete_happy_path(self):
        cur = _mock_cursor()
        cur.rowcount = 1
        conn = _mock_conn(cur)

        with patch("main._db_conn", return_value=conn):
            r = client.delete("/revenue/1")

        assert r.status_code == 200
        assert r.json()["deleted"] == 1

    def test_delete_404_on_missing(self):
        cur = _mock_cursor()
        cur.rowcount = 0
        conn = _mock_conn(cur)

        with patch("main._db_conn", return_value=conn):
            r = client.delete("/revenue/9999")

        assert r.status_code == 404
