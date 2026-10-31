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
