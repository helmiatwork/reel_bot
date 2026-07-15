"""Tests for brands endpoints (product grouping layer)."""
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


def test_brands_list_empty():
    """GET /brands returns empty list initially."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "name", "description", "created_at", "account_count"],
        rows=[]
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.get("/brands")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_brands_create_minimal():
    """POST /brands creates a brand with name only."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "name", "description", "created_at"],
        single_row=(1, "Meowlody Test", None, datetime.now())
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.post("/brands", json={"name": "Meowlody Test"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Meowlody Test"
    assert data["id"] == 1
    assert data.get("account_count") == 0


def test_brands_create_with_description():
    """POST /brands creates a brand with name and description."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "name", "description", "created_at"],
        single_row=(1, "Test Brand", "A test brand", datetime.now())
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.post("/brands", json={
            "name": "Test Brand",
            "description": "A test brand"
        })
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "A test brand"


def test_brands_create_duplicate_name():
    """POST /brands returns 409 if name already exists."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "name", "description", "created_at"],
        single_row=None  # ON CONFLICT DO NOTHING returns no row
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.post("/brands", json={"name": "Duplicate"})
    assert response.status_code == 409


def test_brands_create_empty_name():
    """POST /brands returns 400 if name is empty."""
    response = client.post("/brands", json={"name": ""})
    assert response.status_code == 400


def test_brands_update_name():
    """PATCH /brands/{id} updates brand name."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "name", "description", "created_at"],
        single_row=(1, "Updated Name", None, datetime.now())
    )
    with patch("main._db_conn", return_value=mock_conn):
        # Need to also mock the count query
        def execute_side_effect(query, params=None):
            if "COUNT(*)" in query:
                mock_cursor.fetchone.return_value = (2,)
        mock_cursor.execute.side_effect = execute_side_effect

        response = client.patch("/brands/1", json={"name": "Updated Name"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


def test_brands_update_description():
    """PATCH /brands/{id} updates brand description."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "name", "description", "created_at"],
        single_row=(1, "Brand", "New desc", datetime.now())
    )
    with patch("main._db_conn", return_value=mock_conn):
        def execute_side_effect(query, params=None):
            if "COUNT(*)" in query:
                mock_cursor.fetchone.return_value = (1,)
        mock_cursor.execute.side_effect = execute_side_effect

        response = client.patch("/brands/1", json={"description": "New desc"})
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "New desc"


def test_brands_update_nonexistent():
    """PATCH /brands/{id} returns 404 for nonexistent brand."""
    mock_conn, mock_cursor = mock_db_context(single_row=None)
    with patch("main._db_conn", return_value=mock_conn):
        response = client.patch("/brands/99999", json={"name": "Test"})
    assert response.status_code == 404


def test_brands_update_nothing():
    """PATCH /brands/{id} returns 400 when nothing to update."""
    response = client.patch("/brands/1", json={})
    assert response.status_code == 400


def test_brands_update_empty_name():
    """PATCH /brands/{id} returns 400 if name is empty (#3)."""
    response = client.patch("/brands/1", json={"name": "  "})
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_brands_delete():
    """DELETE /brands/{id} removes a brand and sets brand_id=NULL on accounts (#4)."""
    mock_conn, mock_cursor = mock_db_context(single_row=(1,))  # SELECT returns the id
    with patch("main._db_conn", return_value=mock_conn):
        response = client.delete("/brands/1")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"
    # (#4) Verify the NULL update was executed
    assert any("brand_id=NULL" in str(call) for call in mock_cursor.execute.call_args_list), \
        "Expected UPDATE accounts SET brand_id=NULL in delete flow"


def test_brands_delete_nonexistent():
    """DELETE /brands/{id} returns 404 for nonexistent brand."""
    mock_conn, mock_cursor = mock_db_context(single_row=None)
    with patch("main._db_conn", return_value=mock_conn):
        response = client.delete("/brands/99999")
    assert response.status_code == 404


def test_brands_get_by_id():
    """GET /brands/{id} returns a specific brand."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "name", "description", "created_at", "account_count"],
        single_row=(1, "Test Brand", None, datetime.now(), 2)
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.get("/brands/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Test Brand"


def test_brands_get_nonexistent():
    """GET /brands/{id} returns 404 for nonexistent brand."""
    mock_conn, mock_cursor = mock_db_context(single_row=None)
    with patch("main._db_conn", return_value=mock_conn):
        response = client.get("/brands/99999")
    assert response.status_code == 404


def test_brands_list_with_account_count():
    """GET /brands returns account_count for each brand."""
    mock_conn, mock_cursor = mock_db_context(
        description=["id", "name", "description", "created_at", "account_count"],
        rows=[
            (1, "Brand A", None, datetime.now(), 2),
            (2, "Brand B", "Desc", datetime.now(), 1),
        ]
    )
    with patch("main._db_conn", return_value=mock_conn):
        response = client.get("/brands")
    assert response.status_code == 200
    brands = response.json()
    assert len(brands) == 2
    assert brands[0]["account_count"] == 2
    assert brands[1]["account_count"] == 1


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
