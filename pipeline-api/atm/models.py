"""Read-only view: which model + effort each job uses, and why. Shown on the dashboard; no edits here."""
from fastapi import APIRouter

from .common import (
    ATM_EVAL_EFFORT,
    ATM_EVAL_MODEL,
    ATM_LIGHT_EFFORT,
    ATM_LIGHT_MODEL,
    ATM_MODEL,
    effort_for,
)

router = APIRouter()

# Must match DEFAULT_EFFORT in claude_runner.py (applied when no explicit effort is sent).
_BRIDGE_DEFAULT_EFFORT = {"claude-haiku-5-5": "high", "claude-sonnet-5-5": "low"}


def _effort(model: str, explicit: str) -> str:
    return explicit or _BRIDGE_DEFAULT_EFFORT.get(model, "default")


@router.get("/models")
def list_models():
    import main
    return {"jobs": [
        {"key": "frames", "job": "Baca frame video (analisa tahap 1)", "model": "claude-haiku-5-5",
         "effort": _effort("claude-haiku-5-5", ""),
         "reason": "Banyak panggilan (5 frame per batch). Haiku cepat dan hemat; deskripsi frame akurat di tes."},
        {"key": "synthesis", "job": "Sintesis analisa + prompt", "model": main.ANALYZE_SYNTHESIS_MODEL,
         "effort": _effort(main.ANALYZE_SYNTHESIS_MODEL, ""),
         "reason": "Tes 4 video (31 Okt 2026): low, medium, high hasilnya setara; low paling hemat token."},
        {"key": "blueprint", "job": "Blueprint ATM", "model": ATM_MODEL,
         "effort": _effort(ATM_MODEL, effort_for(ATM_MODEL)),
         "reason": "Tes 4 video: lolos 4/4, blueprint 34 detik (Haiku 61 detik). "
                   "Haiku pernah gagal format JSON dan membocorkan nama channel referensi."},
        {"key": "evaluation", "job": "Evaluasi draft + pasca-upload", "model": ATM_EVAL_MODEL,
         "effort": _effort(ATM_EVAL_MODEL, ATM_EVAL_EFFORT),
         "reason": "A/B: Haiku high valid, setara Sonnet, dan menangkap video reupload."},
        {"key": "learn", "job": "Ringkas pelajaran + alert monitor", "model": ATM_LIGHT_MODEL,
         "effort": _effort(ATM_LIGHT_MODEL, ATM_LIGHT_EFFORT),
         "reason": "Teks pendek dan sederhana, cukup Haiku."},
        {"key": "tagging", "job": "Tag kreator (gender/niche)", "model": "claude-haiku-5-5",
         "effort": _effort("claude-haiku-5-5", ""),
         "reason": "Klasifikasi singkat dari judul/deskripsi, cukup Haiku."},
        {"key": "clipper", "job": "Clipper + grup shot Decompose", "model": "claude-sonnet-5-5",
         "effort": _effort("claude-sonnet-5-5", ""),
         "reason": "Perlu memahami transkrip panjang dan urutan shot. Belum diuji per effort."},
        {"key": "seo", "job": "Saran judul/hashtag halaman SEO", "model": main._SEO_SYNTH_MODEL, "effort": "-",
         "reason": "Lewat SumoPod (bukan Claude), murah. Butuh SUMOPOD_KEY."},
    ]}
