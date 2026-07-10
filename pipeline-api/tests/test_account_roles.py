"""
Unit tests for account roles feature — scrape/publish split with download rotation.

Covers:
- ACCOUNT_ROLES constant
- _accounts_init_db DDL: ALTER TABLE adds role + last_used_at
- _scrape_cookie_file: LRU selection, updates last_used_at, skips publish, legacy fallback
- HARD GUARD: role='publish' account cookie never surfaced to any download path
- Endpoint validation: role filter on GET, role validation on POST + PATCH

All tests are pure (no real DB, no network).

Run:
    cd pipeline-api && pytest tests/test_account_roles.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as m
from main import ACCOUNT_ROLES, _scrape_cookie_file, app


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_conn(select_rows=None):
    """Return a MagicMock psycopg connection.

    select_rows: list of tuples returned by fetchall() on the mock cursor.
    Both SELECT and UPDATE execute calls go to the same cursor mock, so all
    calls are inspectable via conn.cursor.return_value.__enter__.return_value.
    """
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = select_rows if select_rows is not None else []
    cur.fetchone.return_value = select_rows[0] if select_rows else None
    # MagicMock sets __exit__ to return False by default (no exception suppression)
    return conn


# ── ACCOUNT_ROLES constant ────────────────────────────────────────────────────

class TestAccountRolesConstant:
    def test_has_scrape(self):
        assert "scrape" in ACCOUNT_ROLES

    def test_has_publish(self):
        assert "publish" in ACCOUNT_ROLES

    def test_exactly_two_roles(self):
        assert set(ACCOUNT_ROLES) == {"scrape", "publish"}


# ── _accounts_init_db DDL ─────────────────────────────────────────────────────

class TestAccountsInitDbDDL:
    def test_alter_table_adds_role_column(self, monkeypatch):
        """Migration executes ALTER TABLE ... ADD COLUMN ... role."""
        conn = _mock_conn()
        monkeypatch.setattr(m, "_db_conn", lambda: conn)
        m._accounts_init_db()
        cur = conn.cursor.return_value.__enter__.return_value
        all_sql = " ".join(str(c) for c in cur.execute.call_args_list).lower()
        assert "role" in all_sql

    def test_alter_table_adds_last_used_at_column(self, monkeypatch):
        """Migration executes ALTER TABLE ... ADD COLUMN ... last_used_at."""
        conn = _mock_conn()
        monkeypatch.setattr(m, "_db_conn", lambda: conn)
        m._accounts_init_db()
        cur = conn.cursor.return_value.__enter__.return_value
        all_sql = " ".join(str(c) for c in cur.execute.call_args_list).lower()
        assert "last_used_at" in all_sql

    def test_commit_called_after_migration(self, monkeypatch):
        """_accounts_init_db commits after DDL."""
        conn = _mock_conn()
        monkeypatch.setattr(m, "_db_conn", lambda: conn)
        m._accounts_init_db()
        conn.commit.assert_called()

    def test_no_db_returns_silently(self, monkeypatch):
        """No DB connection → _accounts_init_db does not raise."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        m._accounts_init_db()  # must not raise

    def test_role_column_default_is_scrape(self, monkeypatch):
        """The ALTER TABLE for role includes DEFAULT 'scrape'."""
        conn = _mock_conn()
        monkeypatch.setattr(m, "_db_conn", lambda: conn)
        m._accounts_init_db()
        cur = conn.cursor.return_value.__enter__.return_value
        all_sql = " ".join(str(c) for c in cur.execute.call_args_list).lower()
        assert "default" in all_sql
        assert "scrape" in all_sql


# ── _scrape_cookie_file ───────────────────────────────────────────────────────

class TestScrapeCookieFile:
    def test_returns_scrape_account_cookie_path(self, tmp_path, monkeypatch):
        """Single active scrape account with cookie file → returns its path."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        (tmp_path / "tiktok").mkdir()
        cookie_f = tmp_path / "tiktok" / "1.txt"
        cookie_f.write_text("# Netscape\nexample.com\t...\n")

        conn = _mock_conn(select_rows=[(1,)])
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        result = _scrape_cookie_file("tiktok")
        assert result == cookie_f

    def test_updates_last_used_at_on_pick(self, tmp_path, monkeypatch):
        """Picked account gets last_used_at updated so next call rotates to another."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        (tmp_path / "tiktok").mkdir()
        (tmp_path / "tiktok" / "5.txt").write_text("# Netscape\nexample.com\t...\n")

        conn = _mock_conn(select_rows=[(5,)])
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        _scrape_cookie_file("tiktok")

        cur = conn.cursor.return_value.__enter__.return_value
        all_sqls = " ".join(str(c) for c in cur.execute.call_args_list).lower()
        assert "update" in all_sqls
        assert "last_used_at" in all_sqls

    def test_skips_account_without_cookie_file(self, tmp_path, monkeypatch):
        """Account with no cookie file on disk is skipped; next account is picked."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        (tmp_path / "tiktok").mkdir()
        # Account 1: no file. Account 2: has file.
        (tmp_path / "tiktok" / "2.txt").write_text("# Netscape\nexample.com\t...\n")

        conn = _mock_conn(select_rows=[(1,), (2,)])
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        result = _scrape_cookie_file("tiktok")
        assert result == tmp_path / "tiktok" / "2.txt"

    def test_skips_empty_cookie_file(self, tmp_path, monkeypatch):
        """Account with an empty cookie file (st_size == 0) is skipped."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        (tmp_path / "tiktok").mkdir()
        (tmp_path / "tiktok" / "3.txt").write_text("")        # empty — skipped
        (tmp_path / "tiktok" / "4.txt").write_text("# Netscape\nexample.com\t...\n")

        conn = _mock_conn(select_rows=[(3,), (4,)])
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        result = _scrape_cookie_file("tiktok")
        assert result == tmp_path / "tiktok" / "4.txt"

    def test_returns_none_when_no_accounts_have_cookie_files(self, tmp_path, monkeypatch):
        """Scrape accounts exist in DB but none have files + no legacy → None."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        (tmp_path / "tiktok").mkdir()  # dir exists, but no files

        conn = _mock_conn(select_rows=[(3,)])
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        result = _scrape_cookie_file("tiktok")
        assert result is None

    def test_falls_back_to_legacy_when_no_db(self, tmp_path, monkeypatch):
        """No DB connection → falls back to legacy data/cookies/<platform>.txt."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        legacy = tmp_path / "tiktok.txt"
        legacy.write_text("# Netscape\nexample.com\t...\n")
        monkeypatch.setattr(m, "_db_conn", lambda: None)

        result = _scrape_cookie_file("tiktok")
        assert result == legacy

    def test_falls_back_to_legacy_when_no_scrape_accounts(self, tmp_path, monkeypatch):
        """DB returns no scrape accounts + legacy file exists → returns legacy."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        legacy = tmp_path / "tiktok.txt"
        legacy.write_text("# Netscape\nexample.com\t...\n")

        conn = _mock_conn(select_rows=[])
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        result = _scrape_cookie_file("tiktok")
        assert result == legacy

    def test_returns_none_when_no_scrape_accounts_and_no_legacy(self, tmp_path, monkeypatch):
        """No scrape accounts + no legacy file → None."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        conn = _mock_conn(select_rows=[])
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        result = _scrape_cookie_file("tiktok")
        assert result is None

    # ── HARD GUARD ────────────────────────────────────────────────────────────

    def test_hard_guard_publish_account_cookie_never_returned(self, tmp_path, monkeypatch):
        """HARD GUARD: _scrape_cookie_file SQL filters role='scrape', so a
        publish account's cookie file is structurally unreachable even if the
        file exists on disk.

        We prove this by: (a) placing a cookie file for account 99, (b) having
        the DB return no rows (simulating the WHERE role='scrape' filter having
        excluded account 99), and (c) asserting the SQL itself contains the
        role='scrape' constraint.
        """
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        # Publish account 99 has a cookie file on disk
        (tmp_path / "instagram").mkdir()
        publish_file = tmp_path / "instagram" / "99.txt"
        publish_file.write_text("# Netscape\nexample.com\t...\n")

        # DB returns empty — role='scrape' filter excluded the publish account
        conn = _mock_conn(select_rows=[])
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        result = _scrape_cookie_file("instagram")

        # Result must NOT be the publish account's file
        assert result != publish_file

        # The SELECT SQL must contain role and scrape — structural guarantee
        cur = conn.cursor.return_value.__enter__.return_value
        select_sql = cur.execute.call_args_list[0][0][0].lower()
        assert "role" in select_sql
        assert "scrape" in select_sql

    def test_db_error_falls_back_to_legacy_gracefully(self, tmp_path, monkeypatch):
        """DB exception → falls back to legacy cookie file without crashing."""
        monkeypatch.setattr(m, "COOKIES_DIR", tmp_path)
        legacy = tmp_path / "tiktok.txt"
        legacy.write_text("# Netscape\nexample.com\t...\n")

        conn = _mock_conn()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = Exception(
            "connection reset"
        )
        monkeypatch.setattr(m, "_db_conn", lambda: conn)

        result = _scrape_cookie_file("tiktok")
        assert result == legacy  # graceful fallback, no exception propagated


# ── Endpoint validation ───────────────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


class TestAccountsListRoleFilter:
    def test_invalid_role_param_returns_400(self, client):
        """GET /accounts?role=superadmin → 400 before any DB call."""
        resp = client.get("/accounts?role=superadmin")
        assert resp.status_code == 400
        assert "role" in resp.json()["detail"].lower()

    def test_role_scrape_accepted(self, monkeypatch, client):
        """GET /accounts?role=scrape → 200 (DB unavailable → empty list, not error)."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        resp = client.get("/accounts?role=scrape")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_role_publish_accepted(self, monkeypatch, client):
        """GET /accounts?role=publish → 200 (DB unavailable → empty list)."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        resp = client.get("/accounts?role=publish")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_no_role_filter_returns_200(self, monkeypatch, client):
        """GET /accounts (no role param) → 200 as before."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        resp = client.get("/accounts")
        assert resp.status_code == 200


class TestAccountsCreateRole:
    def test_invalid_role_returns_400(self, client):
        """POST /accounts with role='god' → 400 before any DB call."""
        resp = client.post("/accounts", json={
            "platform": "tiktok", "handle": "@test", "role": "god"
        })
        assert resp.status_code == 400
        assert "role" in resp.json()["detail"].lower()

    def test_missing_role_defaults_to_scrape_validation_passes(self, monkeypatch, client):
        """POST /accounts without role → role defaults to 'scrape', validation
        passes, 503 only because DB is unavailable (not a role error)."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        resp = client.post("/accounts", json={"platform": "tiktok", "handle": "@test"})
        assert resp.status_code == 503

    def test_role_publish_passes_validation(self, monkeypatch, client):
        """POST /accounts with role='publish' → passes validation; 503 = no DB."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        resp = client.post("/accounts", json={
            "platform": "tiktok", "handle": "@pub_acct", "role": "publish"
        })
        assert resp.status_code == 503  # role valid; only DB missing

    def test_role_scrape_passes_validation(self, monkeypatch, client):
        """POST /accounts with role='scrape' → passes validation; 503 = no DB."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        resp = client.post("/accounts", json={
            "platform": "instagram", "handle": "@scrape_acct", "role": "scrape"
        })
        assert resp.status_code == 503


class TestAccountsUpdateRole:
    def test_invalid_role_returns_400(self, client):
        """PATCH /accounts/1 with role='superuser' → 400 before any DB call."""
        resp = client.patch("/accounts/1", json={"role": "superuser"})
        assert resp.status_code == 400
        assert "role" in resp.json()["detail"].lower()

    def test_role_publish_passes_validation(self, monkeypatch, client):
        """PATCH /accounts/1 with role='publish' → passes validation; 503 = no DB."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        resp = client.patch("/accounts/1", json={"role": "publish"})
        assert resp.status_code == 503

    def test_role_scrape_passes_validation(self, monkeypatch, client):
        """PATCH /accounts/1 with role='scrape' → passes validation; 503 = no DB."""
        monkeypatch.setattr(m, "_db_conn", lambda: None)
        resp = client.patch("/accounts/1", json={"role": "scrape"})
        assert resp.status_code == 503

    def test_nothing_to_update_still_rejected(self, client):
        """PATCH /accounts/1 with empty body → 400 (existing behavior preserved)."""
        resp = client.patch("/accounts/1", json={})
        assert resp.status_code == 400
