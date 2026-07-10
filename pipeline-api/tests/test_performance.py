"""
Unit tests for _build_performance_view in pipeline-api/main.py.

Exercises: 2 platforms, multiple days, upsert dedup, empty input,
missing fields, totals, video_count, series ordering.

Run:
    cd pipeline-api && pytest tests/test_performance.py -v
"""
import inspect
import re
import sys
import datetime as dt
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import _build_performance_view, _performance_init_db, _collect_performance_snapshots  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _snap(platform, url, views, date, title=None, account_id=None):
    return {
        "platform": platform,
        "url": url,
        "title": title or f"Video {url[-1]}",
        "views": views,
        "captured_at": date,
        "account_id": account_id,
    }


# Two platforms, two videos each, three days
_D1 = dt.date(2025, 7, 1)
_D2 = dt.date(2025, 7, 2)
_D3 = dt.date(2025, 7, 3)

_ROWS = [
    # youtube: video A
    _snap("youtube", "https://youtu.be/A", 1000, _D1, "Video A"),
    _snap("youtube", "https://youtu.be/A", 1500, _D2, "Video A"),
    _snap("youtube", "https://youtu.be/A", 2000, _D3, "Video A"),
    # youtube: video B
    _snap("youtube", "https://youtu.be/B", 500,  _D1, "Video B"),
    _snap("youtube", "https://youtu.be/B", 800,  _D3, "Video B"),
    # tiktok: video C
    _snap("tiktok", "https://tiktok.com/C", 300, _D2, "Video C"),
    _snap("tiktok", "https://tiktok.com/C", 900, _D3, "Video C"),
]


class TestBuildPerformanceView:

    # ── basic shape ──────────────────────────────────────────────────────────

    def test_returns_four_keys(self):
        r = _build_performance_view(_ROWS)
        assert set(r.keys()) == {"series", "totals", "videos", "accounts"}

    def test_series_has_one_entry_per_platform(self):
        r = _build_performance_view(_ROWS)
        platforms = {s["platform"] for s in r["series"]}
        assert platforms == {"youtube", "tiktok"}

    def test_totals_has_one_entry_per_platform(self):
        r = _build_performance_view(_ROWS)
        platforms = {t["platform"] for t in r["totals"]}
        assert platforms == {"youtube", "tiktok"}

    # ── totals ───────────────────────────────────────────────────────────────

    def test_totals_youtube_video_count(self):
        r = _build_performance_view(_ROWS)
        yt = next(t for t in r["totals"] if t["platform"] == "youtube")
        assert yt["video_count"] == 2

    def test_totals_tiktok_video_count(self):
        r = _build_performance_view(_ROWS)
        tt = next(t for t in r["totals"] if t["platform"] == "tiktok")
        assert tt["video_count"] == 1

    def test_totals_youtube_views_uses_latest_per_video(self):
        # youtube A latest = 2000 (D3), youtube B latest = 800 (D3) → 2800
        r = _build_performance_view(_ROWS)
        yt = next(t for t in r["totals"] if t["platform"] == "youtube")
        assert yt["total_views"] == 2800

    def test_totals_tiktok_views(self):
        # tiktok C latest = 900 (D3)
        r = _build_performance_view(_ROWS)
        tt = next(t for t in r["totals"] if t["platform"] == "tiktok")
        assert tt["total_views"] == 900

    # ── series points ────────────────────────────────────────────────────────

    def test_series_youtube_dates_sorted(self):
        r = _build_performance_view(_ROWS)
        yt = next(s for s in r["series"] if s["platform"] == "youtube")
        dates = [p["date"] for p in yt["points"]]
        assert dates == sorted(dates)

    def test_series_youtube_d1_views(self):
        # D1: A=1000, B=500 → 1500
        r = _build_performance_view(_ROWS)
        yt = next(s for s in r["series"] if s["platform"] == "youtube")
        pt = next(p for p in yt["points"] if p["date"] == _D1.isoformat())
        assert pt["views"] == 1500

    def test_series_youtube_d2_carries_forward_b(self):
        # D2: A=1500 (latest on D2), B has no D2 snap → carry D1=500 → total 2000
        r = _build_performance_view(_ROWS)
        yt = next(s for s in r["series"] if s["platform"] == "youtube")
        pt = next(p for p in yt["points"] if p["date"] == _D2.isoformat())
        assert pt["views"] == 2000

    def test_series_youtube_d3_views(self):
        # D3: A=2000, B=800 → 2800
        r = _build_performance_view(_ROWS)
        yt = next(s for s in r["series"] if s["platform"] == "youtube")
        pt = next(p for p in yt["points"] if p["date"] == _D3.isoformat())
        assert pt["views"] == 2800

    def test_series_tiktok_only_has_d2_d3(self):
        r = _build_performance_view(_ROWS)
        tt = next(s for s in r["series"] if s["platform"] == "tiktok")
        dates = {p["date"] for p in tt["points"]}
        assert dates == {_D2.isoformat(), _D3.isoformat()}

    # ── videos list ──────────────────────────────────────────────────────────

    def test_videos_count(self):
        r = _build_performance_view(_ROWS)
        assert len(r["videos"]) == 3

    def test_videos_youtube_a_latest_views(self):
        r = _build_performance_view(_ROWS)
        va = next(v for v in r["videos"] if v["url"] == "https://youtu.be/A")
        assert va["latest_views"] == 2000

    def test_videos_first_seen_last_seen(self):
        r = _build_performance_view(_ROWS)
        va = next(v for v in r["videos"] if v["url"] == "https://youtu.be/A")
        assert va["first_seen"] == _D1.isoformat()
        assert va["last_seen"] == _D3.isoformat()

    def test_videos_title_populated(self):
        r = _build_performance_view(_ROWS)
        va = next(v for v in r["videos"] if v["url"] == "https://youtu.be/A")
        assert va["title"] == "Video A"

    # ── edge cases ───────────────────────────────────────────────────────────

    def test_empty_rows(self):
        r = _build_performance_view([])
        assert r == {"series": [], "totals": [], "videos": [], "accounts": []}

    def test_rows_with_missing_views_skipped(self):
        rows = [_snap("youtube", "https://youtu.be/X", None, _D1)]
        r = _build_performance_view(rows)
        assert r["totals"] == []

    def test_rows_with_missing_url_skipped(self):
        row = {"platform": "youtube", "url": "", "views": 100, "captured_at": _D1}
        r = _build_performance_view([row])
        assert r["totals"] == []

    def test_duplicate_snapshots_same_url_same_day_takes_max(self):
        rows = [
            _snap("youtube", "https://youtu.be/Z", 100, _D1),
            _snap("youtube", "https://youtu.be/Z", 999, _D1),  # higher
            _snap("youtube", "https://youtu.be/Z", 50,  _D1),  # lower
        ]
        r = _build_performance_view(rows)
        yt = next(t for t in r["totals"] if t["platform"] == "youtube")
        assert yt["total_views"] == 999

    def test_iso_string_date_accepted(self):
        rows = [_snap("tiktok", "https://tiktok.com/Y", 500, "2025-07-05")]
        r = _build_performance_view(rows)
        tt = next(t for t in r["totals"] if t["platform"] == "tiktok")
        assert tt["total_views"] == 500

    def test_datetime_object_date_accepted(self):
        rows = [_snap("instagram", "https://ig.com/Z", 200,
                      dt.datetime(2025, 7, 5, 10, 0, tzinfo=dt.timezone.utc))]
        r = _build_performance_view(rows)
        ig = next(t for t in r["totals"] if t["platform"] == "instagram")
        assert ig["total_views"] == 200

    def test_single_video_series_has_one_point(self):
        rows = [_snap("youtube", "https://youtu.be/solo", 42, _D1)]
        r = _build_performance_view(rows)
        yt = next(s for s in r["series"] if s["platform"] == "youtube")
        assert len(yt["points"]) == 1
        assert yt["points"][0]["views"] == 42

    def test_accounts_empty_when_no_rows(self):
        r = _build_performance_view([])
        assert r["accounts"] == []


# ── Per-account breakdown tests ───────────────────────────────────────────────

# Dataset: 2 platforms × 2 named accounts + 1 null-account (legacy) row
_ACCT_LOOKUP = {
    1: {"handle": "@yt_main", "label": "YouTube Main"},
    2: {"handle": "@yt_second", "label": "YouTube Second"},
    3: {"handle": "@tt_main", "label": "TikTok Main"},
}

_ACCT_ROWS = [
    # youtube account 1: video A (D1–D3)
    _snap("youtube", "https://youtu.be/A", 1000, _D1, "Video A", account_id=1),
    _snap("youtube", "https://youtu.be/A", 1500, _D2, "Video A", account_id=1),
    _snap("youtube", "https://youtu.be/A", 2000, _D3, "Video A", account_id=1),
    # youtube account 2: video B (D1, D3)
    _snap("youtube", "https://youtu.be/B", 500,  _D1, "Video B", account_id=2),
    _snap("youtube", "https://youtu.be/B", 800,  _D3, "Video B", account_id=2),
    # youtube legacy (no account): video C
    _snap("youtube", "https://youtu.be/C", 300,  _D2, "Video C", account_id=None),
    # tiktok account 3: video D
    _snap("tiktok", "https://tiktok.com/D", 400,  _D2, "Video D", account_id=3),
    _snap("tiktok", "https://tiktok.com/D", 900,  _D3, "Video D", account_id=3),
]


class TestBuildPerformanceViewAccounts:

    # ── accounts key structure ────────────────────────────────────────────────

    def test_accounts_key_present(self):
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        assert "accounts" in r

    def test_accounts_count(self):
        # yt: acct1, acct2, None(Tanpa akun) → 3; tt: acct3 → 1 → total 4
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        assert len(r["accounts"]) == 4

    def test_accounts_platforms_present(self):
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        platforms = {a["platform"] for a in r["accounts"]}
        assert platforms == {"youtube", "tiktok"}

    # ── named account totals ──────────────────────────────────────────────────

    def test_yt_acct1_total_views(self):
        # latest for video A = 2000 (D3)
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        a = next(a for a in r["accounts"] if a["account_id"] == 1)
        assert a["total_views"] == 2000

    def test_yt_acct2_total_views(self):
        # latest for video B = 800 (D3)
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        a = next(a for a in r["accounts"] if a["account_id"] == 2)
        assert a["total_views"] == 800

    def test_yt_acct1_video_count(self):
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        a = next(a for a in r["accounts"] if a["account_id"] == 1)
        assert a["video_count"] == 1

    def test_tt_acct3_total_views(self):
        # latest for video D = 900 (D3)
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        a = next(a for a in r["accounts"] if a["account_id"] == 3)
        assert a["total_views"] == 900

    # ── handle / label resolution ─────────────────────────────────────────────

    def test_named_account_handle(self):
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        a = next(a for a in r["accounts"] if a["account_id"] == 1)
        assert a["handle"] == "@yt_main"
        assert a["label"] == "YouTube Main"

    def test_unknown_account_id_falls_back(self):
        # account_id=99 not in lookup → "Akun #99"
        rows = [_snap("youtube", "https://youtu.be/X", 100, _D1, account_id=99)]
        r = _build_performance_view(rows, _ACCT_LOOKUP)
        a = next(a for a in r["accounts"] if a["account_id"] == 99)
        assert a["handle"] == "Akun #99"

    # ── Tanpa akun bucket ─────────────────────────────────────────────────────

    def test_tanpa_akun_bucket_present(self):
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        tanpa = [a for a in r["accounts"] if a["account_id"] is None and a["platform"] == "youtube"]
        assert len(tanpa) == 1

    def test_tanpa_akun_handle(self):
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        tanpa = next(a for a in r["accounts"] if a["account_id"] is None and a["platform"] == "youtube")
        assert tanpa["handle"] == "Tanpa akun"
        assert tanpa["label"] == "Tanpa akun"

    def test_tanpa_akun_total_views(self):
        # video C latest = 300 (only D2 snapshot)
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        tanpa = next(a for a in r["accounts"] if a["account_id"] is None and a["platform"] == "youtube")
        assert tanpa["total_views"] == 300

    # ── per-account series ────────────────────────────────────────────────────

    def test_acct1_series_ordered(self):
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        a = next(a for a in r["accounts"] if a["account_id"] == 1)
        dates = [p["date"] for p in a["series"]]
        assert dates == sorted(dates)

    def test_acct1_series_d3_views(self):
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        a = next(a for a in r["accounts"] if a["account_id"] == 1)
        pt = next(p for p in a["series"] if p["date"] == _D3.isoformat())
        assert pt["views"] == 2000

    # ── platform roll-up unaffected ───────────────────────────────────────────

    def test_platform_totals_still_correct(self):
        # yt total = latest(A)=2000 + latest(B)=800 + latest(C)=300 = 3100
        r = _build_performance_view(_ACCT_ROWS, _ACCT_LOOKUP)
        yt = next(t for t in r["totals"] if t["platform"] == "youtube")
        assert yt["total_views"] == 3100

    def test_no_accounts_lookup_still_works(self):
        # Without lookup: account_id falls back to "Akun #N" or "Tanpa akun"
        r = _build_performance_view(_ACCT_ROWS)
        assert len(r["accounts"]) == 4
        tanpa = next(a for a in r["accounts"] if a["account_id"] is None)
        assert tanpa["handle"] == "Tanpa akun"


# ── DDL / ON CONFLICT consistency tests ──────────────────────────────────────
# These check that the index expression and the upsert arbiter match exactly,
# and that the old broken form (bare captured_at::date) is gone everywhere.

_IMMUTABLE_EXPR = "(captured_at AT TIME ZONE 'UTC')::date"
_BROKEN_EXPR = re.compile(r"\(captured_at::date\)")  # the IMMUTABLE-violating form


def _source(fn) -> str:
    return inspect.getsource(fn)


class TestPerformanceDDLConsistency:

    def test_init_db_uses_immutable_index_expr(self):
        src = _source(_performance_init_db)
        assert _IMMUTABLE_EXPR in src, (
            "_performance_init_db must use the IMMUTABLE expression "
            f"'{_IMMUTABLE_EXPR}' for the unique index"
        )

    def test_init_db_has_no_broken_timestamptz_cast(self):
        src = _source(_performance_init_db)
        assert not _BROKEN_EXPR.search(src), (
            "_performance_init_db still contains bare (captured_at::date) "
            "which is not IMMUTABLE and will fail on Postgres"
        )

    def test_collector_on_conflict_uses_immutable_expr(self):
        src = _source(_collect_performance_snapshots)
        assert _IMMUTABLE_EXPR in src, (
            "_collect_performance_snapshots ON CONFLICT must use "
            f"'{_IMMUTABLE_EXPR}' to match the unique index arbiter"
        )

    def test_collector_has_no_broken_timestamptz_cast(self):
        src = _source(_collect_performance_snapshots)
        assert not _BROKEN_EXPR.search(src), (
            "_collect_performance_snapshots still contains bare (captured_at::date) "
            "which won't match the fixed index and will error on upsert"
        )

    def test_index_expr_and_on_conflict_are_identical(self):
        """The exact expression in the CREATE INDEX and the ON CONFLICT must match."""
        init_src = _source(_performance_init_db)
        coll_src = _source(_collect_performance_snapshots)
        assert _IMMUTABLE_EXPR in init_src and _IMMUTABLE_EXPR in coll_src, (
            "Both _performance_init_db and _collect_performance_snapshots must "
            f"contain the identical expression: '{_IMMUTABLE_EXPR}'"
        )
