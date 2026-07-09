"""
Unit tests for _build_performance_view in pipeline-api/main.py.

Exercises: 2 platforms, multiple days, upsert dedup, empty input,
missing fields, totals, video_count, series ordering.

Run:
    cd pipeline-api && pytest tests/test_performance.py -v
"""
import sys
import datetime as dt
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import _build_performance_view  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _snap(platform, url, views, date, title=None):
    return {
        "platform": platform,
        "url": url,
        "title": title or f"Video {url[-1]}",
        "views": views,
        "captured_at": date,
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

    def test_returns_three_keys(self):
        r = _build_performance_view(_ROWS)
        assert set(r.keys()) == {"series", "totals", "videos"}

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
        assert r == {"series": [], "totals": [], "videos": []}

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
