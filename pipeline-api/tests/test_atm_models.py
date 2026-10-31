import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

# Pin every model/effort constant so the test does not depend on the local .env.
DEFAULTS = {
    "main.ANALYZE_SYNTHESIS_MODEL": "claude-sonnet-5-5",
    "atm.models.ATM_MODEL": "claude-sonnet-5-5",
    "atm.common.ATM_EFFORT": "",
    "atm.common.ATM_LIGHT_MODEL": "claude-haiku-5-5",
    "atm.common.ATM_LIGHT_EFFORT": "",
    "atm.models.ATM_LIGHT_MODEL": "claude-haiku-5-5",
    "atm.models.ATM_LIGHT_EFFORT": "",
    "atm.models.ATM_EVAL_MODEL": "claude-haiku-5-5",
    "atm.models.ATM_EVAL_EFFORT": "high",
}

EXPECTED = [
    {"key": "frames", "job": "Baca frame video (analisa tahap 1)", "model": "claude-haiku-5-5", "effort": "high",
     "reason": "Banyak panggilan (5 frame per batch). Haiku cepat dan hemat; deskripsi frame akurat di tes."},
    {"key": "synthesis", "job": "Sintesis analisa + prompt", "model": "claude-sonnet-5-5", "effort": "low",
     "reason": "Tes 4 video (31 Okt 2026): low, medium, high hasilnya setara; low paling hemat token."},
    {"key": "blueprint", "job": "Blueprint ATM", "model": "claude-sonnet-5-5", "effort": "low",
     "reason": "Tes 4 video: lolos 4/4, blueprint 34 detik (Haiku 61 detik). "
               "Haiku pernah gagal format JSON dan membocorkan nama channel referensi."},
    {"key": "evaluation", "job": "Evaluasi draft + pasca-upload", "model": "claude-haiku-5-5", "effort": "high",
     "reason": "A/B: Haiku high valid, setara Sonnet, dan menangkap video reupload."},
    {"key": "learn", "job": "Ringkas pelajaran", "model": "claude-haiku-5-5", "effort": "high",
     "reason": "Teks pendek dan sederhana, cukup Haiku."},
    {"key": "clipper", "job": "Clipper + grup shot Decompose", "model": "claude-sonnet-5-5", "effort": "low",
     "reason": "Perlu memahami transkrip panjang dan urutan shot. Belum diuji per effort."},
    {"key": "seo", "job": "Saran judul/hashtag halaman SEO", "model": "gemini-2.5-flash-lite", "effort": "-",
     "reason": "Lewat cliproxy (bukan Claude), murah. Butuh cliproxy menyala."},
]


def _get(**overrides):
    values = {**DEFAULTS, **overrides}
    with ExitStack() as stack:
        for target, value in values.items():
            stack.enter_context(patch(target, value))
        r = client.get("/atm/models")
    assert r.status_code == 200
    return r.json()


def _job(body, key):
    return next(j for j in body["jobs"] if j["key"] == key)


def test_models_returns_seven_jobs_in_order():
    assert _get() == {"jobs": EXPECTED}


def test_blueprint_effort_falls_back_to_bridge_default():
    # ATM_EFFORT empty -> bridge default for sonnet is "low"; haiku would be "high".
    assert _job(_get(), "blueprint")["effort"] == "low"
    assert _job(_get(**{"atm.models.ATM_MODEL": "claude-haiku-5-5"}), "blueprint")["effort"] == "high"


def test_blueprint_explicit_effort_wins_over_default():
    assert _job(_get(**{"atm.common.ATM_EFFORT": "medium"}), "blueprint")["effort"] == "medium"


def test_blueprint_effort_follows_light_branch_like_run_claude():
    # run_claude picks ATM_LIGHT_EFFORT when the model is the light model; the view must match.
    light = {"atm.models.ATM_MODEL": "claude-haiku-5-5", "atm.common.ATM_LIGHT_MODEL": "claude-haiku-5-5",
             "atm.common.ATM_EFFORT": "medium"}
    assert _job(_get(**light, **{"atm.common.ATM_LIGHT_EFFORT": ""}), "blueprint")["effort"] == "high"
    assert _job(_get(**light, **{"atm.common.ATM_LIGHT_EFFORT": "low"}), "blueprint")["effort"] == "low"


def test_unknown_claude_model_without_explicit_effort_shows_default():
    body = _get(**{"atm.models.ATM_MODEL": "claude-opus-5-5"})
    assert _job(body, "blueprint") == {**EXPECTED[2], "model": "claude-opus-5-5", "effort": "default"}


def test_env_overridden_models_are_reflected():
    body = _get(**{"main.ANALYZE_SYNTHESIS_MODEL": "claude-haiku-5-5",
                   "atm.models.ATM_LIGHT_MODEL": "claude-sonnet-5-5",
                   "atm.models.ATM_EVAL_MODEL": "claude-sonnet-5-5",
                   "atm.models.ATM_EVAL_EFFORT": "medium"})
    assert _job(body, "synthesis")["model"] == "claude-haiku-5-5"
    assert _job(body, "synthesis")["effort"] == "high"
    assert _job(body, "learn")["model"] == "claude-sonnet-5-5"
    assert _job(body, "evaluation") == {**EXPECTED[3], "model": "claude-sonnet-5-5", "effort": "medium"}
