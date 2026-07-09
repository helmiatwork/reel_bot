"""
Unit tests for Accounts helpers in pipeline-api/main.py.

Covers:
- _cookie_file path resolution (legacy + per-account)
- _account_cookie_file path construction
- _validate_netscape_content validation + normalisation
- _account_has_cookies (filesystem check, no DB)
- ACCOUNT_PLATFORMS membership

All tests are pure (no network, no DB).

Run:
    cd pipeline-api && pytest tests/test_accounts.py -v
"""
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# Make pipeline-api/main.py importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import (  # noqa: E402
    ACCOUNT_PLATFORMS,
    COOKIE_PLATFORMS,
    COOKIES_DIR,
    _account_cookie_file,
    _account_has_cookies,
    _cookie_file,
    _validate_netscape_content,
)


# ── _cookie_file ──────────────────────────────────────────────────────────────

class TestCookieFile:
    def test_legacy_path_no_account(self):
        p = _cookie_file("tiktok")
        assert p == COOKIES_DIR / "tiktok.txt"

    def test_legacy_path_account_id_none_explicit(self):
        p = _cookie_file("instagram", account_id=None)
        assert p == COOKIES_DIR / "instagram.txt"

    def test_per_account_path(self):
        p = _cookie_file("youtube", account_id=42)
        assert p == COOKIES_DIR / "youtube" / "42.txt"

    def test_per_account_path_account_id_1(self):
        p = _cookie_file("tiktok", account_id=1)
        assert p == COOKIES_DIR / "tiktok" / "1.txt"

    def test_legacy_paths_all_cookie_platforms(self):
        for plat in COOKIE_PLATFORMS:
            p = _cookie_file(plat)
            assert p.name == f"{plat}.txt"
            assert p.parent == COOKIES_DIR


# ── _account_cookie_file ──────────────────────────────────────────────────────

class TestAccountCookieFile:
    def test_path_structure(self):
        p = _account_cookie_file(7, "instagram")
        assert p == COOKIES_DIR / "instagram" / "7.txt"

    def test_is_same_as_cookie_file_with_account_id(self):
        assert _account_cookie_file(3, "tiktok") == _cookie_file("tiktok", account_id=3)

    def test_different_ids_different_paths(self):
        assert _account_cookie_file(1, "youtube") != _account_cookie_file(2, "youtube")

    def test_different_platforms_different_paths(self):
        assert _account_cookie_file(1, "youtube") != _account_cookie_file(1, "tiktok")


# ── ACCOUNT_PLATFORMS ─────────────────────────────────────────────────────────

class TestAccountPlatforms:
    def test_youtube_included(self):
        assert "youtube" in ACCOUNT_PLATFORMS

    def test_cookie_platforms_are_subset(self):
        for p in COOKIE_PLATFORMS:
            assert p in ACCOUNT_PLATFORMS

    def test_all_expected_platforms_present(self):
        expected = {"youtube", "instagram", "tiktok", "xiaohongshu"}
        assert expected == set(ACCOUNT_PLATFORMS)


# ── _validate_netscape_content ────────────────────────────────────────────────

class TestValidateNetscapeCookies:
    def test_empty_string_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_netscape_content("")
        assert exc_info.value.status_code == 400

    def test_whitespace_only_raises(self):
        with pytest.raises(HTTPException):
            _validate_netscape_content("   \n  ")

    def test_no_tab_no_header_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_netscape_content("just some random text without tabs")
        assert exc_info.value.status_code == 400

    def test_tab_separated_accepted(self):
        content = "example.com\tFALSE\t/\tFALSE\t0\tsession\tabc123"
        result = _validate_netscape_content(content)
        assert "# Netscape HTTP Cookie File" in result
        assert "session\tabc123" in result

    def test_netscape_header_accepted(self):
        content = "# Netscape HTTP Cookie File\nexample.com\tFALSE\t/\tFALSE\t0\tkey\tval"
        result = _validate_netscape_content(content)
        assert result.startswith("# Netscape HTTP Cookie File")

    def test_header_prepended_when_missing(self):
        content = "example.com\tFALSE\t/\tFALSE\t0\tkey\tval"
        result = _validate_netscape_content(content)
        assert result.startswith("# Netscape HTTP Cookie File\n")

    def test_header_not_duplicated_when_present(self):
        content = "# Netscape HTTP Cookie File\nexample.com\tFALSE\t/\tFALSE\t0\tkey\tval"
        result = _validate_netscape_content(content)
        assert result.count("# Netscape HTTP Cookie File") == 1

    def test_trailing_newline_ensured(self):
        content = "example.com\tFALSE\t/\tFALSE\t0\tkey\tval"
        result = _validate_netscape_content(content)
        assert result.endswith("\n")

    def test_none_raises(self):
        with pytest.raises(HTTPException):
            _validate_netscape_content(None)


# ── _account_has_cookies (filesystem, tmpdir) ─────────────────────────────────

class TestAccountHasCookies:
    def test_missing_file_returns_false(self, tmp_path, monkeypatch):
        # Redirect COOKIES_DIR to tmp_path so we don't touch real data.
        import main as m
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        assert _account_has_cookies(99, "youtube") is False

    def test_empty_file_returns_false(self, tmp_path, monkeypatch):
        import main as m
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        (tmp_path / "youtube").mkdir()
        (tmp_path / "youtube" / "99.txt").write_text("")
        assert _account_has_cookies(99, "youtube") is False

    def test_nonempty_file_returns_true(self, tmp_path, monkeypatch):
        import main as m
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        (tmp_path / "youtube").mkdir()
        (tmp_path / "youtube" / "5.txt").write_text("# Netscape HTTP Cookie File\nexample.com\t...\n")
        assert _account_has_cookies(5, "youtube") is True
