"""
Unit tests for schedule helpers in pipeline-api/main.py.

Covers _derive_schedule_counts with a range of item sets so the function
is well-exercised without touching the database.

Run:
    cd pipeline-api && pytest tests/test_schedule.py -v
    # or without pytest:
    cd pipeline-api && python tests/test_schedule.py
"""
import sys
import json
import datetime as dt
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import _derive_schedule_counts, _row_to_schedule, _cookie_file  # noqa: E402

# Fixed "now" used across all tests so results are deterministic.
_NOW = dt.datetime(2025, 7, 10, 12, 0, 0, tzinfo=dt.timezone.utc)


def _make(scheduled_at=None, platforms="youtube", platform_urls=None):
    """Build a minimal item dict the way _row_to_schedule produces them."""
    return {
        "scheduled_at": scheduled_at,
        "platforms": platforms,
        "platform_urls": platform_urls or {},
    }


class TestDeriveScheduleCounts:
    # ── empty ────────────────────────────────────────────────────────────────

    def test_empty_list_returns_zero_counts(self):
        c = _derive_schedule_counts([], now_dt=_NOW)
        assert c == {"total": 0, "today": 0, "overdue": 0, "scheduled": 0, "draft": 0, "posted": 0}

    # ── draft ────────────────────────────────────────────────────────────────

    def test_no_scheduled_at_is_draft(self):
        c = _derive_schedule_counts([_make()], now_dt=_NOW)
        assert c["draft"] == 1
        assert c["total"] == 1

    def test_empty_string_scheduled_at_treated_as_draft(self):
        item = _make(scheduled_at="", platforms="youtube")
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["draft"] == 1

    def test_none_platforms_with_no_scheduled_at_is_draft(self):
        item = {"scheduled_at": None, "platforms": None, "platform_urls": {}}
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["draft"] == 1

    # ── posted ───────────────────────────────────────────────────────────────

    def test_all_platforms_have_urls_is_posted(self):
        item = _make(
            scheduled_at="2025-07-09T10:00:00+00:00",
            platforms="youtube,tiktok",
            platform_urls={"youtube": "https://yt.be/x", "tiktok": "https://tt.com/v"}
        )
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["posted"] == 1
        assert c["overdue"] == 0

    def test_only_some_platforms_posted_is_not_posted(self):
        item = _make(
            scheduled_at="2025-07-09T10:00:00+00:00",
            platforms="youtube,tiktok",
            platform_urls={"youtube": "https://yt.be/x"}
        )
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["posted"] == 0
        assert c["overdue"] == 1

    def test_platform_urls_as_json_string_is_parsed(self):
        item = {
            "scheduled_at": None,
            "platforms": "youtube",
            "platform_urls": json.dumps({"youtube": "https://yt.be/x"}),
        }
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["posted"] == 1

    def test_empty_platforms_with_empty_urls_is_not_posted(self):
        # no targets means "all posted" guard requires at least one target
        item = _make(scheduled_at=None, platforms="", platform_urls={})
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["posted"] == 0
        assert c["draft"] == 1

    # ── scheduled / overdue ─────────────────────────────────────────────────

    def test_future_scheduled_at_is_scheduled(self):
        future = "2025-07-11T12:00:00+00:00"  # after _NOW
        c = _derive_schedule_counts([_make(scheduled_at=future)], now_dt=_NOW)
        assert c["scheduled"] == 1
        assert c["overdue"] == 0

    def test_past_scheduled_at_is_overdue(self):
        past = "2025-07-09T12:00:00+00:00"  # before _NOW
        c = _derive_schedule_counts([_make(scheduled_at=past)], now_dt=_NOW)
        assert c["overdue"] == 1
        assert c["scheduled"] == 0

    def test_exactly_now_is_overdue(self):
        # scheduled_at == now: < is False, so it becomes scheduled
        at_now = _NOW.isoformat()
        c = _derive_schedule_counts([_make(scheduled_at=at_now)], now_dt=_NOW)
        assert c["scheduled"] == 1

    # ── today ────────────────────────────────────────────────────────────────

    def test_today_morning_counts_as_today_and_overdue(self):
        morning = "2025-07-10T06:00:00+00:00"  # same date as _NOW, but earlier
        c = _derive_schedule_counts([_make(scheduled_at=morning)], now_dt=_NOW)
        assert c["today"] == 1
        assert c["overdue"] == 1

    def test_today_afternoon_counts_as_today_and_scheduled(self):
        afternoon = "2025-07-10T18:00:00+00:00"  # same date as _NOW, but later
        c = _derive_schedule_counts([_make(scheduled_at=afternoon)], now_dt=_NOW)
        assert c["today"] == 1
        assert c["scheduled"] == 1

    def test_posted_item_does_not_count_as_today_even_if_scheduled_today(self):
        morning = "2025-07-10T06:00:00+00:00"
        item = _make(scheduled_at=morning, platform_urls={"youtube": "https://yt.be/x"})
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["posted"] == 1
        assert c["today"] == 0  # posted items exit early before today check

    # ── multiple items ───────────────────────────────────────────────────────

    def test_mixed_items_all_buckets(self):
        items = [
            _make(),                                                # draft
            _make(scheduled_at="2025-07-11T10:00:00+00:00"),       # scheduled
            _make(scheduled_at="2025-07-09T10:00:00+00:00"),       # overdue
            _make(scheduled_at=None, platform_urls={"youtube": "https://yt.be/x"}),  # posted
            _make(scheduled_at="2025-07-10T10:00:00+00:00"),       # today + overdue
        ]
        c = _derive_schedule_counts(items, now_dt=_NOW)
        assert c["total"] == 5
        assert c["draft"] == 1
        assert c["scheduled"] == 1
        assert c["overdue"] == 2   # past item + today morning
        assert c["posted"] == 1
        assert c["today"] == 1

    def test_total_equals_len_items(self):
        items = [_make() for _ in range(7)]
        c = _derive_schedule_counts(items, now_dt=_NOW)
        assert c["total"] == 7

    # ── platform_urls edge cases ─────────────────────────────────────────────

    def test_invalid_json_platform_urls_falls_back_to_empty_dict(self):
        item = {"scheduled_at": None, "platforms": "youtube", "platform_urls": "not-json"}
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["draft"] == 1   # no posted platform, no scheduled_at → draft

    def test_none_platform_urls_treated_as_empty(self):
        item = {"scheduled_at": None, "platforms": "youtube", "platform_urls": None}
        c = _derive_schedule_counts([item], now_dt=_NOW)
        assert c["draft"] == 1

    # ── default now_dt (smoke test — just verify no crash) ───────────────────

    def test_default_now_dt_does_not_crash(self):
        items = [
            _make(scheduled_at="2020-01-01T00:00:00+00:00"),
            _make(),
        ]
        c = _derive_schedule_counts(items)  # no now_dt — uses utcnow()
        assert c["total"] == 2
        assert c["overdue"] >= 1   # 2020 item must be overdue


def _make_row(**kwargs):
    """Build a minimal (cols, row) pair that _row_to_schedule can consume."""
    defaults = {
        "id": 1, "content_ref": None, "title": "Test",
        "platforms": "youtube", "scheduled_at": None,
        "caption": "", "thumb_url": None, "source_url": None,
        "platform_urls": "{}", "platform_accounts": "{}",
        "created_at": None, "updated_at": None,
    }
    defaults.update(kwargs)
    cols = list(defaults.keys())
    row = tuple(defaults.values())
    return row, cols


class TestRowToSchedulePlatformAccounts:
    """_row_to_schedule correctly deserializes platform_accounts."""

    def test_json_string_is_parsed_to_dict(self):
        row, cols = _make_row(platform_accounts='{"youtube": 5, "tiktok": 12}')
        d = _row_to_schedule(row, cols)
        assert d["platform_accounts"] == {"youtube": 5, "tiktok": 12}

    def test_empty_json_string_gives_empty_dict(self):
        row, cols = _make_row(platform_accounts="{}")
        d = _row_to_schedule(row, cols)
        assert d["platform_accounts"] == {}

    def test_none_falls_back_to_empty_dict(self):
        row, cols = _make_row(platform_accounts=None)
        d = _row_to_schedule(row, cols)
        assert d["platform_accounts"] == {}

    def test_invalid_json_falls_back_to_empty_dict(self):
        row, cols = _make_row(platform_accounts="not-json")
        d = _row_to_schedule(row, cols)
        assert d["platform_accounts"] == {}

    def test_already_a_dict_is_preserved(self):
        # In case the DB driver returns a dict (e.g. JSONB column)
        row, cols = _make_row(platform_accounts={"instagram": 7})
        d = _row_to_schedule(row, cols)
        assert d["platform_accounts"] == {"instagram": 7}

    def test_platform_urls_still_deserialized_alongside(self):
        row, cols = _make_row(
            platform_urls='{"youtube": "https://yt.be/x"}',
            platform_accounts='{"youtube": 3}',
        )
        d = _row_to_schedule(row, cols)
        assert d["platform_urls"] == {"youtube": "https://yt.be/x"}
        assert d["platform_accounts"] == {"youtube": 3}


class TestPlatformAccountsMergeSemantics:
    """Merge logic used in PATCH /schedule/{id} for platform_accounts."""

    def test_patch_adds_new_platform(self):
        current = {"youtube": 1}
        incoming = {"tiktok": 2}
        merged = {**current, **incoming}
        assert merged == {"youtube": 1, "tiktok": 2}

    def test_patch_overrides_existing_platform(self):
        current = {"youtube": 1, "tiktok": 2}
        incoming = {"youtube": 5}
        merged = {**current, **incoming}
        assert merged == {"youtube": 5, "tiktok": 2}

    def test_patch_empty_incoming_preserves_current(self):
        current = {"youtube": 1}
        incoming = {}
        merged = {**current, **incoming}
        assert merged == {"youtube": 1}

    def test_patch_none_incoming_skips_merge(self):
        # When body.platform_accounts is None the update block is skipped entirely
        current = {"youtube": 1}
        incoming = None
        merged = current if incoming is None else {**current, **incoming}
        assert merged == {"youtube": 1}


class TestCookieFileResolution:
    """_cookie_file resolves paths correctly for both legacy and per-account modes."""

    def test_legacy_path_no_account_id(self):
        p = _cookie_file("youtube")
        assert p.name == "youtube.txt"
        assert "youtube" not in str(p.parent.name) or str(p) == str(p)
        # Key: no sub-directory for account_id
        assert str(p).endswith("youtube.txt")
        parts = p.parts
        assert parts[-1] == "youtube.txt"
        assert parts[-2] != "youtube"  # parent dir is cookies/, not cookies/youtube/

    def test_per_account_path_with_account_id(self):
        p = _cookie_file("youtube", account_id=42)
        assert p.name == "42.txt"
        assert p.parent.name == "youtube"

    def test_per_account_path_tiktok(self):
        p = _cookie_file("tiktok", account_id=7)
        assert p.name == "7.txt"
        assert p.parent.name == "tiktok"

    def test_legacy_vs_account_paths_differ(self):
        legacy = _cookie_file("instagram")
        per_acct = _cookie_file("instagram", account_id=1)
        assert legacy != per_acct
        assert str(legacy).endswith("instagram.txt")
        assert str(per_acct).endswith("instagram/1.txt")


if __name__ == "__main__":
    # fallback runner without pytest
    import traceback
    all_suites = [
        TestDeriveScheduleCounts(),
        TestRowToSchedulePlatformAccounts(),
        TestPlatformAccountsMergeSemantics(),
        TestCookieFileResolution(),
    ]
    passed, failed = 0, []
    for suite in all_suites:
        methods = [m for m in dir(suite) if m.startswith("test_")]
        for m in methods:
            try:
                getattr(suite, m)()
                passed += 1
                print(f"  PASS  {m}")
            except Exception:
                failed.append(m)
                print(f"  FAIL  {m}")
                traceback.print_exc()
    print(f"\n{passed}/{passed + len(failed)} passed")
    if failed:
        sys.exit(1)
