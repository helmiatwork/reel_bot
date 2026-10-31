"""Tests for accounts brand_id handling."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime
import main

client = TestClient(main.app)


def mock_db_context(description=None, rows=None, single_row=None):
    """Helper to create a mock database context."""
    rows = rows or []
    mock_cursor = MagicMock()
    # Create description with proper name attributes
    desc_objs = []
    for col in (description or []):
        col_obj = MagicMock()
        col_obj.name = col
        desc_objs.append(col_obj)
    mock_cursor.description = desc_objs
    mock_cursor.fetchall.return_value = rows
    mock_cursor.fetchone.return_value = single_row

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn, mock_cursor


def test_accounts_create_with_brand_id():
    """POST /accounts accepts optional brand_id."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at", "brand_id"],
        single_row=(1, "youtube", "test_handle", "test_label", True, "scrape", None, datetime.now(), 5)
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.post("/accounts", json={
            "platform": "youtube",
            "handle": "test_handle",
            "brand_id": 5
        })
    assert response.status_code == 200
    data = response.json()
    assert data.get("brand_id") == 5


def test_accounts_create_without_brand_id():
    """POST /accounts works without brand_id (backward compat)."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at", "brand_id"],
        single_row=(1, "youtube", "test_handle", "test_label", True, "scrape", None, datetime.now(), None)
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.post("/accounts", json={
            "platform": "youtube",
            "handle": "test_handle"
        })
    assert response.status_code == 200
    data = response.json()
    assert "id" in data


def test_accounts_update_brand_id():
    """PATCH /accounts/{id} can update brand_id."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at", "brand_id"],
        single_row=(1, "youtube", "test_handle", "test_label", True, "scrape", None, datetime.now(), 5)
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.patch("/accounts/1", json={"brand_id": 5})
    assert response.status_code == 200
    data = response.json()
    assert data.get("brand_id") == 5


def test_accounts_update_unset_brand_id():
    """PATCH /accounts/{id} with brand_id=null unsetting brand (I-2)."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at", "brand_id"],
        single_row=(1, "youtube", "test_handle", "test_label", True, "scrape", None, datetime.now(), None)
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.patch("/accounts/1", json={"brand_id": None})
    assert response.status_code == 200
    data = response.json()
    assert data.get("brand_id") is None
    # (#4) Verify that brand_id=NULL was actually set in the SQL
    assert any("brand_id=NULL" in str(call) for call in mock_cursor.execute.call_args_list)


def test_accounts_list_filter_by_brand_id():
    """GET /accounts?brand_id=X filters by brand."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "platform", "handle", "label", "active", "role", "last_used_at", "created_at", "brand_id"],
        rows=[
            (1, "youtube", "in_brand", "label", True, "scrape", None, datetime.now(), 5),
        ]
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.get("/accounts?brand_id=5")
    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) == 1
    assert accounts[0].get("brand_id") == 5
