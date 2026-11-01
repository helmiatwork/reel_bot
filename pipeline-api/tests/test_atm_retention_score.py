import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import _build_claude_prompt, _retention_score  # noqa: E402

KEYS = ["hook_2s", "curiosity_gap", "payoff", "fast_pacing", "loopable"]


def _checklist(n_true):
    return {k: (i < n_true) for i, k in enumerate(KEYS)}


def test_all_five_checks_true_gives_10():
    assert _retention_score({"retention_checklist": _checklist(5)}) == 10


def test_no_checks_true_gives_1():
    assert _retention_score({"retention_checklist": _checklist(0)}) == 1


def test_three_checks_true_gives_6():
    assert _retention_score({"retention_checklist": _checklist(3)}) == 6


def test_checklist_wins_over_model_integer():
    parsed = {"retention_score": 7, "retention_checklist": _checklist(0)}
    assert _retention_score(parsed) == 1


def test_missing_checklist_clamps_model_integer():
    assert _retention_score({"retention_score": 42}) == 10
    assert _retention_score({"retention_score": 0}) == 1
    assert _retention_score({"retention_score": 7}) == 7


def test_missing_checklist_accepts_numeric_string():
    assert _retention_score({"retention_score": " 8 "}) == 8


def test_garbage_gives_none():
    assert _retention_score({}) is None
    assert _retention_score({"retention_score": None}) is None
    assert _retention_score({"retention_score": "lots"}) is None
    assert _retention_score({"retention_score": "7.5"}) is None
    assert _retention_score({"retention_score": True}) is None
    assert _retention_score({"retention_score": [7]}) is None
    assert _retention_score({"retention_score": {"v": 7}}) is None
    assert _retention_score({"retention_score": float("nan")}) is None
    assert _retention_score({"retention_score": float("inf")}) is None


def test_huge_integer_is_clamped_not_error():
    assert _retention_score({"retention_score": 10**400}) == 10


def test_checklist_with_non_bool_values_falls_back_to_integer():
    checklist = {k: "yes" for k in KEYS}
    assert _retention_score({"retention_checklist": checklist, "retention_score": 4}) == 4


def test_checklist_missing_a_key_falls_back_to_integer():
    checklist = _checklist(5)
    del checklist["loopable"]
    assert _retention_score({"retention_checklist": checklist, "retention_score": 4}) == 4


def test_claude_prompt_asks_for_all_retention_checks():
    prompt = _build_claude_prompt("test", "none")
    for key in KEYS:
        assert f'"{key}"' in prompt, f"prompt must ask for {key}"
    assert '"retention_checklist": {' in prompt


def test_upload_source_scores_retention_from_checklist(tmp_path):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from main import app
    from _atm_fakes import FakeConn
    parsed = {"hook": "h", "structure": "s", "retention": "r", "summary": "x", "detail": "d",
              "retention_score": 9, "retention_checklist": _checklist(0)}
    conn = FakeConn([("INSERT INTO sources", (["id"], [(5,)]))])
    frames = [{"path": str(tmp_path / "missing.jpg")}]
    with patch("main._REPO_ROOT", tmp_path), patch("main.ANALYZE_AUDIO_TAGS", False), \
            patch("main._extract_frames_timed", return_value=frames), \
            patch("main._analyze_frames_sequential", return_value=parsed), patch("main._db_conn", return_value=conn):
        r = TestClient(app).post("/sources/upload", files={"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, "video/mp4")})
    assert r.status_code == 200, r.text
    params = conn.sqls("INSERT INTO video_analysis")[0][1]
    assert params[9] == 1  # retention_score column: checklist all false -> 1, not the model's 9
