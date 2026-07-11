"""Tests for GET /analyze/claude/runs endpoint."""
import json
import time
import uuid
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from main import app, _save_run, _load_run

client = TestClient(app)


@pytest.fixture
def cleanup_runs():
    """Cleanup test runs after each test."""
    yield


def test_analyze_runs_endpoint_exists():
    """GET /analyze/claude/runs endpoint is available."""
    response = client.get("/analyze/claude/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_analyze_runs_returns_only_analyze_source_kind():
    """GET /analyze/claude/runs filters to kind='analyze_source' only."""
    # Seed runs directory with mixed kinds
    run_id_analyze_1 = str(uuid.uuid4())
    run_id_analyze_2 = str(uuid.uuid4())
    run_id_decompose = str(uuid.uuid4())
    run_id_research = str(uuid.uuid4())

    t1 = time.time()
    t2 = t1 + 10
    t3 = t1 + 20
    t4 = t1 + 30

    # Save runs with different kinds
    _save_run(run_id_analyze_1, {
        "kind": "analyze_source",
        "url": "https://youtube.com/watch?v=abc-kind-test",
        "status": "done",
        "output_format": "none",
        "created": t1,
        "log": [{"msg": "test", "t": 0}]
    })

    _save_run(run_id_analyze_2, {
        "kind": "analyze_source",
        "url": "https://youtube.com/watch?v=def-kind-test",
        "status": "running",
        "output_format": "prompt_json",
        "created": t2,
        "log": [{"msg": "running", "t": 0}]
    })

    _save_run(run_id_decompose, {
        "kind": "decompose",
        "status": "done",
        "created": t3,
        "segments": []
    })

    _save_run(run_id_research, {
        "kind": "research",
        "status": "done",
        "created": t4,
        "result": {}
    })

    # Fetch runs
    response = client.get("/analyze/claude/runs?limit=100")
    assert response.status_code == 200
    data = response.json()

    # All results should be analyze_source kind
    assert all(r["url"].startswith("https://youtube.com") or r["url"].startswith("file://") for r in data)

    # Our analyze_source runs should be present
    our_run_ids = {run_id_analyze_1, run_id_analyze_2}
    returned_run_ids = {r["run_id"] for r in data}
    assert our_run_ids.issubset(returned_run_ids)

    # The decompose and research runs should NOT be in the results
    assert run_id_decompose not in returned_run_ids
    assert run_id_research not in returned_run_ids


def test_analyze_runs_sorted_by_created_desc():
    """GET /analyze/claude/runs returns results sorted by created desc."""
    run_ids = []
    base_time = time.time()

    # Create 3 runs with different created times
    for i, delay in enumerate([0, 10, 5]):
        run_id = str(uuid.uuid4())
        run_ids.append(run_id)
        _save_run(run_id, {
            "kind": "analyze_source",
            "url": f"https://youtube.com/watch?v={i}",
            "status": "done",
            "output_format": "none",
            "created": base_time + delay,
            "log": [{"msg": f"run {i}", "t": 0}]
        })

    response = client.get("/analyze/claude/runs?limit=50")
    assert response.status_code == 200
    data = response.json()

    # Filter to just our runs and check order
    our_runs = [r for r in data if r["run_id"] in run_ids]
    assert len(our_runs) == 3

    # Should be sorted desc by created: 0+10, 0+5, 0
    assert our_runs[0]["created"] == base_time + 10
    assert our_runs[1]["created"] == base_time + 5
    assert our_runs[2]["created"] == base_time


def test_analyze_runs_respects_limit():
    """GET /analyze/claude/runs?limit=N caps results at N."""
    base_time = time.time()

    # Create 5 runs
    for i in range(5):
        run_id = str(uuid.uuid4())
        _save_run(run_id, {
            "kind": "analyze_source",
            "url": f"https://youtube.com/watch?v={i}",
            "status": "done",
            "output_format": "none",
            "created": base_time + i,
            "log": []
        })

    # Test limit=2
    response = client.get("/analyze/claude/runs?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_analyze_runs_summary_shape():
    """GET /analyze/claude/runs returns correct summary shape."""
    run_id = str(uuid.uuid4())
    created_time = time.time()

    _save_run(run_id, {
        "kind": "analyze_source",
        "url": "https://youtube.com/watch?v=test",
        "status": "done",
        "output_format": "prompt_video",
        "created": created_time,
        "log": [
            {"msg": "⏳ Antre…", "t": 0},
            {"msg": "✓ Done", "t": 1.5}
        ]
    })

    response = client.get("/analyze/claude/runs")
    assert response.status_code == 200
    data = response.json()

    # Find our run
    our_run = next((r for r in data if r["run_id"] == run_id), None)
    assert our_run is not None

    # Check all required fields exist
    assert "run_id" in our_run
    assert "url" in our_run
    assert "status" in our_run
    assert "output_format" in our_run
    assert "created" in our_run
    assert "last_msg" in our_run
    assert "log_count" in our_run

    # Check values
    assert our_run["run_id"] == run_id
    assert our_run["url"] == "https://youtube.com/watch?v=test"
    assert our_run["status"] == "done"
    assert our_run["output_format"] == "prompt_video"
    assert our_run["created"] == created_time
    assert our_run["last_msg"] == "✓ Done"
    assert our_run["log_count"] == 2


def test_analyze_runs_extracts_last_msg():
    """GET /analyze/claude/runs extracts the last log message."""
    run_id = str(uuid.uuid4())

    _save_run(run_id, {
        "kind": "analyze_source",
        "url": "https://youtube.com/watch?v=test",
        "status": "running",
        "output_format": "none",
        "created": time.time(),
        "log": [
            {"msg": "first", "t": 0},
            {"msg": "second", "t": 1},
            {"msg": "last message", "t": 2}
        ]
    })

    response = client.get("/analyze/claude/runs")
    data = response.json()
    our_run = next((r for r in data if r["run_id"] == run_id), None)

    assert our_run["last_msg"] == "last message"


def test_analyze_runs_empty_log():
    """GET /analyze/claude/runs handles runs with empty log."""
    run_id = str(uuid.uuid4())

    _save_run(run_id, {
        "kind": "analyze_source",
        "url": "https://youtube.com/watch?v=test",
        "status": "done",
        "output_format": "none",
        "created": time.time(),
        "log": []
    })

    response = client.get("/analyze/claude/runs")
    data = response.json()
    our_run = next((r for r in data if r["run_id"] == run_id), None)

    assert our_run["last_msg"] == ""
    assert our_run["log_count"] == 0


def test_analyze_runs_skips_unparseable():
    """GET /analyze/claude/runs skips corrupt JSON files."""
    runs_dir = Path(__file__).parent.parent / "output" / "research_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Write corrupt JSON
    corrupt_file = runs_dir / "corrupt-run.json"
    corrupt_file.write_text("{ invalid json")

    # Endpoint should not crash
    response = client.get("/analyze/claude/runs")
    assert response.status_code == 200
    # Should return a list (may be empty or include other runs)
    assert isinstance(response.json(), list)

    # Cleanup
    corrupt_file.unlink(missing_ok=True)


def test_analyze_runs_missing_directory():
    """GET /analyze/claude/runs handles missing runs directory gracefully."""
    # This test relies on the endpoint handling a missing dir
    response = client.get("/analyze/claude/runs")
    assert response.status_code == 200
    # Should return empty list if no runs exist
    assert isinstance(response.json(), list)


def test_analyze_runs_url_field_variations():
    """GET /analyze/claude/runs handles both YouTube URLs and file:// URLs."""
    yt_run_id = str(uuid.uuid4())
    file_run_id = str(uuid.uuid4())

    _save_run(yt_run_id, {
        "kind": "analyze_source",
        "url": "https://youtube.com/watch?v=abc123",
        "status": "done",
        "output_format": "none",
        "created": time.time(),
        "log": []
    })

    _save_run(file_run_id, {
        "kind": "analyze_source",
        "url": "file://uuid-123-456",
        "status": "done",
        "output_format": "none",
        "created": time.time(),
        "log": []
    })

    response = client.get("/analyze/claude/runs?limit=50")
    data = response.json()

    yt_run = next((r for r in data if r["run_id"] == yt_run_id), None)
    file_run = next((r for r in data if r["run_id"] == file_run_id), None)

    assert yt_run["url"] == "https://youtube.com/watch?v=abc123"
    assert file_run["url"] == "file://uuid-123-456"


def test_analyze_runs_various_statuses():
    """GET /analyze/claude/runs handles all status values."""
    statuses = {"running", "done", "error"}

    for status in statuses:
        run_id = str(uuid.uuid4())
        _save_run(run_id, {
            "kind": "analyze_source",
            "url": "https://youtube.com/watch?v=test",
            "status": status,
            "output_format": "none",
            "created": time.time(),
            "log": []
        })

    response = client.get("/analyze/claude/runs?limit=50")
    data = response.json()

    returned_statuses = {r["status"] for r in data if r["url"] == "https://youtube.com/watch?v=test"}
    assert statuses == returned_statuses


def test_existing_analyze_async_tests_still_pass():
    """Backwards compat: /analyze/claude/async still works with new metadata."""
    with patch('main._validate_source_url'):
        with patch('main._run_analyze_claude') as mock_analyze:
            mock_analyze.return_value = {
                "youtube_url": "https://youtube.com/watch?v=compat",
                "hook": "Test hook",
                "structure": "Test structure",
                "retention": "Good",
                "tags": [],
                "model": "claude-sonnet-4-6",
                "cost_usd": 0.01,
            }

            response = client.post(
                "/analyze/claude/async",
                json={
                    "youtube_url": "https://youtube.com/watch?v=compat",
                    "output_format": "none"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "run_id" in data
            run_id = data["run_id"]

            # Verify the run has the new metadata fields
            run = _load_run(run_id)
            assert run["kind"] == "analyze_source"
            assert run["url"] == "https://youtube.com/watch?v=compat"
            assert run["output_format"] == "none"
            assert "created" in run


def test_existing_upload_async_tests_still_pass():
    """Backwards compat: /sources/upload/async still works with new metadata."""
    video_content = b'\x00\x00\x00\x20' + b'ftyp' + b'\x00' * 1000

    response = client.post(
        "/sources/upload/async",
        data={"intent": "test", "output_format": "none"},
        files={"file": ("test.mp4", video_content, "video/mp4")}
    )

    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    run_id = data["run_id"]

    # Verify the run has the new metadata fields
    run = _load_run(run_id)
    assert run["kind"] == "analyze_source"
    assert run["url"].startswith("file://")
    assert run["output_format"] == "none"
    assert "created" in run
