# pipeline-api/test_sources_upload.py
# Unit tests for POST /sources/upload.
# Frame extraction, bridge call, and DB are fully mocked — no network, no subprocess.

import json
import pytest
from unittest.mock import MagicMock, patch, ANY
from fastapi.testclient import TestClient
from io import BytesIO


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bridge_response(result_payload: dict, ok: bool = True,
                          cost_usd: float = 0.01, error_type: str = None) -> MagicMock:
    """Build a mock httpx.Response for the bridge POST /run call."""
    mock_resp = MagicMock()
    if ok:
        mock_resp.json.return_value = {
            "ok": True,
            "result": json.dumps(result_payload),
            "raw_usage": {"input_tokens": 100, "output_tokens": 50},
            "cost_usd": cost_usd,
            "model": "claude-sonnet-4-6",
        }
    else:
        payload = {"ok": False, "error": "bridge_test_error"}
        if error_type:
            payload["error_type"] = error_type
        mock_resp.json.return_value = payload
    return mock_resp


_SAMPLE_RESULT = {
    "summary": "A motivational short about overcoming obstacles",
    "detail": "The video uses pattern interrupts and emotional hooks to retain viewers",
    "hook": "Opens with a shocking statistic about failure rates",
    "structure": "Problem → Solution → Inspiration → CTA",
    "retention": "Pattern interrupts every 12 seconds with B-roll changes",
    "retention_score": 8,
    "tags": ["motivation", "shorts", "viral"],
}

_SAMPLE_FRAMES = [
    "/app/analyze-frames/run1/frame_000.jpg",
    "/app/analyze-frames/run1/frame_001.jpg",
    "/app/analyze-frames/run1/frame_002.jpg",
]

# Valid magic bytes for video formats
def _make_valid_mp4_content():
    """Create fake MP4 with valid ftyp magic bytes."""
    return b"xxxx" + b"ftyp" + b"x" * 92  # ftyp at offset 4

def _make_valid_mov_content():
    """Create fake MOV (ISO base media) with valid ftyp magic bytes."""
    return b"xxxx" + b"ftyp" + b"x" * 92

def _make_valid_webm_content():
    """Create fake WebM with valid EBML magic bytes."""
    return b"\x1a\x45\xdf\xa3" + b"x" * 96

def _make_valid_mkv_content():
    """Create fake Matroska with valid EBML magic bytes."""
    return b"\x1a\x45\xdf\xa3" + b"x" * 96


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient with frame extraction and DB both mocked."""
    import main as m
    with patch.object(m, "_extract_frames_from_file", return_value=_SAMPLE_FRAMES), \
         patch.object(m, "_db_conn", return_value=None):
        from fastapi.testclient import TestClient
        yield TestClient(m.app)


@pytest.fixture
def client_with_db():
    """TestClient with frame extraction mocked and DB connection mocked to record calls."""
    import main as m
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = (123,)  # source_id
    mock_conn.cursor.return_value = mock_cursor
    with patch.object(m, "_extract_frames_from_file", return_value=_SAMPLE_FRAMES), \
         patch.object(m, "_db_conn", return_value=mock_conn), \
         patch.object(m, "_log_api_usage"):
        from fastapi.testclient import TestClient
        yield TestClient(m.app), mock_conn, mock_cursor


# ── Validation tests ──────────────────────────────────────────────────────────

class TestSourcesUploadValidation:
    def test_400_on_unsupported_extension(self, client):
        """Reject unsupported file extensions."""
        bad_file = BytesIO(b"fake file content")
        r = client.post(
            "/sources/upload",
            data={"intent": "test"},
            files={"file": ("video.txt", bad_file, "text/plain")},
        )
        assert r.status_code == 400
        data = r.json()
        assert "Unsupported format" in data.get("detail", "")

    def test_400_on_zip_extension(self, client):
        """Explicitly reject .zip files."""
        bad_file = BytesIO(b"fake zip content")
        r = client.post(
            "/sources/upload",
            data={"intent": "test"},
            files={"file": ("video.zip", bad_file, "application/zip")},
        )
        assert r.status_code == 400

    def test_413_on_oversized_file(self, client):
        """Reject files larger than 200 MB."""
        # Create a file larger than the 200 MB limit
        oversized = BytesIO(b"x" * (201 * 1024 * 1024))
        r = client.post(
            "/sources/upload",
            data={"intent": "test"},
            files={"file": ("video.mp4", oversized, "video/mp4")},
        )
        assert r.status_code == 413
        data = r.json()
        assert "too large" in data.get("detail", "").lower()
        assert "200" in data.get("detail", "")

    def test_200_on_valid_mp4(self, client_with_db):
        """Accept valid .mp4 file."""
        tc, _, _ = client_with_db
        valid_file = BytesIO(_make_valid_mp4_content())
        bridge_mock = _make_bridge_response(_SAMPLE_RESULT)
        with patch("httpx.post", return_value=bridge_mock), \
             patch("shutil.copy"):
            r = tc.post(
                "/sources/upload",
                data={"intent": "analyze hook"},
                files={"file": ("video.mp4", valid_file, "video/mp4")},
            )
        assert r.status_code == 200
        data = r.json()
        assert "source_id" in data
        assert data["source_id"] == 123  # from mock fetchone

    def test_200_on_valid_mov(self, client_with_db):
        """Accept valid .mov file."""
        tc, _, _ = client_with_db
        valid_file = BytesIO(_make_valid_mov_content())
        bridge_mock = _make_bridge_response(_SAMPLE_RESULT)
        with patch("httpx.post", return_value=bridge_mock), \
             patch("shutil.copy"):
            r = tc.post(
                "/sources/upload",
                data={"intent": "test"},
                files={"file": ("video.mov", valid_file, "video/quicktime")},
            )
        assert r.status_code == 200
        assert r.json()["source_id"] == 123

    def test_200_on_valid_webm(self, client_with_db):
        """Accept valid .webm file."""
        tc, _, _ = client_with_db
        valid_file = BytesIO(_make_valid_webm_content())
        bridge_mock = _make_bridge_response(_SAMPLE_RESULT)
        with patch("httpx.post", return_value=bridge_mock), \
             patch("shutil.copy"):
            r = tc.post(
                "/sources/upload",
                data={},
                files={"file": ("video.webm", valid_file, "video/webm")},
            )
        assert r.status_code == 200
        assert r.json()["source_id"] == 123


# ── Success path tests ────────────────────────────────────────────────────────

class TestSourcesUploadSuccess:
    def test_response_contains_analysis(self, client_with_db):
        """Successful upload returns analysis fields."""
        tc, _, _ = client_with_db
        bridge_mock = _make_bridge_response(_SAMPLE_RESULT)
        with patch("httpx.post", return_value=bridge_mock), \
             patch("shutil.copy"):
            r = tc.post(
                "/sources/upload",
                data={"intent": "test"},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["hook"] == _SAMPLE_RESULT["hook"]
        assert data["structure"] == _SAMPLE_RESULT["structure"]
        assert data["retention"] == _SAMPLE_RESULT["retention"]
        assert data["tags"] == _SAMPLE_RESULT["tags"]
        assert data["retention_score"] == 8
        assert "summary" in data
        assert "detail" in data

    def test_source_id_in_response(self, client_with_db):
        """Response includes the created source_id."""
        tc, _, _ = client_with_db
        bridge_mock = _make_bridge_response(_SAMPLE_RESULT)
        with patch("httpx.post", return_value=bridge_mock), \
             patch("shutil.copy"):
            r = tc.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 200
        assert r.json()["source_id"] == 123

    def test_db_insert_called_with_file_key(self, client_with_db):
        """DB insert uses file://<uuid> as the youtube_url key."""
        tc, mock_conn, mock_cursor = client_with_db
        bridge_mock = _make_bridge_response(_SAMPLE_RESULT)
        with patch("httpx.post", return_value=bridge_mock), \
             patch("shutil.copy"):
            tc.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        # Check that execute was called with INSERT statements
        assert mock_cursor.execute.called
        # At least two calls: one for sources, one for video_analysis
        assert mock_cursor.execute.call_count >= 2

        # Check the first INSERT (sources table)
        first_call_sql = mock_cursor.execute.call_args_list[0][0][0]
        assert "INSERT INTO sources" in first_call_sql
        first_call_args = mock_cursor.execute.call_args_list[0][0][1]
        source_key = first_call_args[0]
        assert source_key.startswith("file://")

    def test_cost_usd_in_response(self, client_with_db):
        """Response includes the API cost_usd."""
        tc, _, _ = client_with_db
        bridge_mock = _make_bridge_response(_SAMPLE_RESULT, cost_usd=0.042)
        with patch("httpx.post", return_value=bridge_mock), \
             patch("shutil.copy"):
            r = tc.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 200
        assert r.json()["cost_usd"] == 0.042


# ── Error handling ────────────────────────────────────────────────────────────

class TestSourcesUploadErrors:
    def test_502_on_frame_extraction_failure(self, client):
        """If frame extraction fails, return 502."""
        import main as m
        tc = client
        with patch.object(m, "_extract_frames_from_file", side_effect=RuntimeError("ffmpeg failed")):
            r = tc.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 502
        assert "Frame extraction failed" in r.json()["detail"]

    def test_502_on_no_frames_extracted(self, client):
        """If no frames are extracted, return 502."""
        import main as m
        tc = client
        with patch.object(m, "_extract_frames_from_file", return_value=[]):
            r = tc.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 502
        assert "No frames could be extracted" in r.json()["detail"]

    def test_502_on_bridge_failure(self, client):
        """If bridge returns error, return 502."""
        bridge_mock = _make_bridge_response({}, ok=False)
        with patch("httpx.post", return_value=bridge_mock):
            r = client.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 502
        assert "Bridge error" in r.json()["detail"]

    def test_429_on_rate_limit(self, client):
        """If bridge returns rate_limit, return 429."""
        bridge_mock = _make_bridge_response({}, ok=False, error_type="rate_limit")
        with patch("httpx.post", return_value=bridge_mock):
            r = client.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 429
        assert "rate limit" in r.json()["detail"].lower()

    def test_502_on_malformed_bridge_json(self, client):
        """If bridge returns invalid JSON, return 502."""
        bridge_mock = _make_bridge_response({})
        bridge_mock.json.return_value = {
            "ok": True,
            "result": "NOT VALID JSON AT ALL",  # Not JSON-parseable
            "cost_usd": 0.01,
            "model": "claude-sonnet-4-6",
        }
        with patch("httpx.post", return_value=bridge_mock):
            r = client.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 502
        assert "Could not parse claude result as JSON" in r.json()["detail"]


# ── Intent handling (prompt injection guard) ─────────────────────────────────

class TestSourcesUploadIntentSafety:
    def test_intent_sanitized_removes_special_chars(self, client_with_db):
        """Intent is sanitized to remove special characters before sending to bridge."""
        tc, _, _ = client_with_db
        bridge_mock = _make_bridge_response(_SAMPLE_RESULT)
        captured = {}
        def _fake_post(url, json=None, timeout=None):
            captured["json"] = json
            return bridge_mock
        with patch("httpx.post", side_effect=_fake_post), \
             patch("shutil.copy"):
            tc.post(
                "/sources/upload",
                data={"intent": "find hooks<<>>script tags@#$%^&*()"},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        prompt = captured["json"]["prompt"]
        # Special chars like <<>> @ # $ % ^ & should be stripped
        assert "<<>>" not in prompt
        assert "@#$%^&" not in prompt
        # Word characters and allowed punctuation should remain
        assert "find hooks" in prompt


# ── P1 fixes: Code review findings ──────────────────────────────────────────

class TestSourcesUploadP1Fixes:
    def test_422_on_claude_refusal(self, client_with_db):
        """Claude refusal (analysis_ok False) → 422 not 500."""
        tc, _, _ = client_with_db
        # Return a response that triggers the refusal check
        refusal_result = {
            "summary": "Video cannot be analyzed",
            "detail": "No usable content",
            "hook": "cannot be analyzed",  # triggers refusal
            "structure": "",
            "retention": "",
            "retention_score": None,
            "tags": [],
        }
        bridge_mock = _make_bridge_response(refusal_result)
        with patch("httpx.post", return_value=bridge_mock), \
             patch("shutil.copy"):
            r = tc.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 422
        assert "could not analyze" in r.json()["detail"].lower()

    def test_502_on_bridge_non_json(self, client):
        """Bridge returns non-JSON body → 502."""
        bridge_mock = MagicMock()
        bridge_mock.json.side_effect = Exception("Invalid JSON")
        with patch("httpx.post", return_value=bridge_mock):
            r = client.post(
                "/sources/upload",
                data={},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )
        assert r.status_code == 502
        assert "non-JSON" in r.json()["detail"]

    def test_400_on_magic_bytes_mismatch_mp4(self, client):
        """Magic-bytes mismatch (.mp4 with non-ftyp content) → 400."""
        bad_content = b"NOT_FTYP_HEADER_XXXXX" * 10
        r = client.post(
            "/sources/upload",
            data={},
            files={"file": ("video.mp4", BytesIO(bad_content), "video/mp4")},
        )
        assert r.status_code == 400
        assert "does not match declared format" in r.json()["detail"]

    def test_400_on_magic_bytes_mismatch_webm(self, client):
        """Magic-bytes mismatch (.webm with non-webm content) → 400."""
        bad_content = b"NOTWEBM_CONTENT" * 10
        r = client.post(
            "/sources/upload",
            data={},
            files={"file": ("video.webm", BytesIO(bad_content), "video/webm")},
        )
        assert r.status_code == 400
        assert "does not match declared format" in r.json()["detail"]

    def test_file_cleanup_on_failed_analysis(self, client_with_db):
        """Upload file is removed from data/sources/uploaded/ after analysis failure."""
        import main as m
        import tempfile
        from pathlib import Path as PathlibPath

        tc, _, _ = client_with_db

        # Use a real temp dir to verify file cleanup
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch _REPO_ROOT to use temp dir
            orig_repo_root = m._REPO_ROOT
            m._REPO_ROOT = PathlibPath(tmpdir)

            try:
                # Create upload dir
                upload_dir = PathlibPath(tmpdir) / "data" / "sources" / "uploaded"
                upload_dir.mkdir(parents=True, exist_ok=True)

                # Make analysis fail (refusal)
                refusal_result = {
                    "summary": "", "detail": "",
                    "hook": "cannot analyze", "structure": "", "retention": "",
                    "retention_score": None, "tags": [],
                }
                bridge_mock = _make_bridge_response(refusal_result)

                with patch("httpx.post", return_value=bridge_mock), \
                     patch("shutil.copy"), \
                     patch.object(m, "_extract_frames_from_file", return_value=_SAMPLE_FRAMES), \
                     patch.object(m, "_REPO_ROOT", PathlibPath(tmpdir)):
                    r = tc.post(
                        "/sources/upload",
                        data={},
                        files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
                    )

                # Verify 422 response
                assert r.status_code == 422

                # Verify file was cleaned up (no files in upload_dir)
                uploaded_files = list(upload_dir.glob("*"))
                assert len(uploaded_files) == 0, f"Uploaded file not cleaned up: {uploaded_files}"
            finally:
                m._REPO_ROOT = orig_repo_root

    def test_file_cleanup_on_frame_extraction_failure(self, client_with_db):
        """Upload file is removed from data/sources/uploaded/ when frame extraction fails."""
        import main as m
        import tempfile
        from pathlib import Path as PathlibPath

        tc, _, _ = client_with_db

        # Use a real temp dir to verify file cleanup
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch _REPO_ROOT to use temp dir
            orig_repo_root = m._REPO_ROOT
            m._REPO_ROOT = PathlibPath(tmpdir)

            try:
                # Create upload dir
                upload_dir = PathlibPath(tmpdir) / "data" / "sources" / "uploaded"
                upload_dir.mkdir(parents=True, exist_ok=True)

                # Make frame extraction fail
                with patch.object(m, "_extract_frames_from_file", side_effect=RuntimeError("ffmpeg failed")), \
                     patch.object(m, "_REPO_ROOT", PathlibPath(tmpdir)):
                    r = tc.post(
                        "/sources/upload",
                        data={},
                        files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
                    )

                # Verify 502 response
                assert r.status_code == 502
                assert "Frame extraction failed" in r.json()["detail"]

                # Verify file was cleaned up (no files in upload_dir)
                uploaded_files = list(upload_dir.glob("*"))
                assert len(uploaded_files) == 0, f"Uploaded file not cleaned up: {uploaded_files}"
            finally:
                m._REPO_ROOT = orig_repo_root

    def test_sources_upload_persists_gen_prompt(self, client_with_db):
        """After /sources/upload with output_format=prompt_json, gen_prompt should be persisted."""
        import main as m
        import httpx as _httpx

        tc, mock_conn, mock_cursor = client_with_db

        # Mock cursor to return source_id on INSERT
        gen_prompt_json = '{"scene_order":[{"scene":1,"description":"Opening"}]}'
        result_payload = {
            **_SAMPLE_RESULT,
            "gen_prompt_storyboard": json.loads(gen_prompt_json)
        }

        with patch.object(_httpx, "post", return_value=_make_bridge_response(result_payload)):
            r = tc.post(
                "/sources/upload",
                data={"output_format": "prompt_json"},
                files={"file": ("video.mp4", BytesIO(_make_valid_mp4_content()), "video/mp4")},
            )

        assert r.status_code == 200
        resp_data = r.json()
        assert resp_data.get("gen_prompt_format") == "prompt_json"

        # Verify that UPDATE was called with gen_prompt
        update_calls = [call for call in mock_cursor.execute.call_args_list
                        if len(call[0]) > 0 and "UPDATE sources SET gen_prompt" in str(call[0][0])]
        assert len(update_calls) > 0, "UPDATE gen_prompt should have been called in /sources/upload"

    def test_sources_analysis_returns_gen_prompt(self, client_with_db):
        """GET /sources/{source_id}/analysis should return gen_prompt and gen_prompt_format."""
        import main as m

        tc, mock_conn, mock_cursor = client_with_db

        # Mock the SELECT to return gen_prompt data
        gen_prompt_text = "A cinematic video"
        mock_cursor.fetchone.return_value = (
            "Opening hook",  # hook
            "Problem → Solution",  # structure
            "Pattern interrupts",  # retention
            8,  # retention_score
            "Summary",  # content_summary
            "Detail",  # content_detail
            '["tag1", "tag2"]',  # tags
            gen_prompt_text,  # gen_prompt
            "prompt_video"  # gen_prompt_format
        )

        r = tc.get("/sources/1/analysis")

        assert r.status_code == 200
        resp_data = r.json()
        assert resp_data.get("gen_prompt") == gen_prompt_text
        assert resp_data.get("gen_prompt_format") == "prompt_video"
        assert resp_data.get("hook") == "Opening hook"
