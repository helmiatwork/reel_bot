"""Olah Sampah recipe rules: time parsing and validate_recipe (pure, no I/O, no DB)."""
import re
from typing import Optional

from .blueprint import _seconds

EMOTIONS = ("sedih", "senang", "tegang", "marah", "haru", "lucu", "penasaran")
RISKS = ("rendah", "sedang", "tinggi")
_MAX_SECONDS = 1e7
_TIME_RE = re.compile(r"\d+(?::\d+){1,2}|\d+(?:\.\d+)?")
TREATMENTS = ("normal", "freeze", "slowmo", "loop")
_WPS_MIN, _WPS_MAX = 1.6, 3.0  # Indonesian VO words per second, per beat
_TARGET_TOL = 0.15
_SHARE_TOL = 10.0  # percentage points


def _t(value) -> Optional[float]:
    """Seconds from 'mm:ss', 'hh:mm:ss' or a number; None when not a time."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if 0 <= value <= _MAX_SECONDS else None  # False for NaN/inf; int compare never overflows
    if isinstance(value, str) and _TIME_RE.fullmatch(value.strip()):
        t = _seconds(value.strip())
        return t if t <= _MAX_SECONDS else None  # also rejects inf from huge digit strings
    return None


def _pos_num(value) -> Optional[float]:
    """Finite number > 0 within the seconds cap; bool, NaN and inf give None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= _MAX_SECONDS:
        return None
    return float(value)


def _clip_errors(clip, tag: str, duration_s: Optional[float], seen: list) -> list[str]:
    """`seen` collects the source ranges of earlier clips (any beat); a repeat must overlap one of them."""
    if not isinstance(clip, dict):
        return [f"{tag} bukan objek"]
    errors = []
    s_s, s_e = _t(clip.get("source_start")), _t(clip.get("source_end"))
    if s_s is None or s_e is None:
        errors.append(f"{tag}: waktu sumber tidak valid (pakai mm:ss)")
    else:
        if s_e <= s_s:
            errors.append(f"{tag}: source_end harus lebih besar dari source_start")
        if duration_s and (s_e > duration_s + 1 or s_s > duration_s + 1):
            errors.append(f"{tag}: rentang sumber melebihi durasi video ({duration_s:g}s)")
    if clip.get("treatment") not in TREATMENTS:
        errors.append(f"{tag}: treatment harus salah satu dari {list(TREATMENTS)}")
    if not isinstance(clip.get("repeat"), bool):
        errors.append(f"{tag}: repeat harus true/false")
    elif clip["repeat"] and (s_s is None or s_e is None or not any(s_s < pe and ps < s_e for ps, pe in seen)):
        errors.append(f"{tag}: repeat=true harus mengulang rentang sumber klip sebelumnya")
    if not isinstance(clip.get("note"), str):
        errors.append(f"{tag}: note harus teks")
    if s_s is not None and s_e is not None:
        seen.append((s_s, s_e))
    return errors


def _beat_errors(beats, duration_s, formula: Optional[dict], target_s: Optional[float], recipe: dict) -> list[str]:
    if not isinstance(beats, list) or not beats:
        return ["beats kosong"]
    errors, emotions, seen, spans = [], set(), [], []
    timing_ok, prev_end = True, None
    for i, row in enumerate(beats, 1):
        if not isinstance(row, dict):
            errors.append(f"beat {i} bukan objek")
            timing_ok = False
            continue
        o_s, o_e = _t(row.get("out_start")), _t(row.get("out_end"))
        if o_s is None or o_e is None:
            errors.append(f"beat {i}: waktu tidak valid (pakai mm:ss)")
            timing_ok, prev_end = False, None
        else:
            if o_e <= o_s:
                errors.append(f"beat {i}: out_end harus lebih besar dari out_start")
            if i == 1 and o_s > 1:
                errors.append("beat 1: out_start harus 00:00")
            elif i > 1 and prev_end is not None and abs(o_s - prev_end) > 1:
                errors.append(f"beat {i}: out_start harus sama dengan out_end beat sebelumnya")
            spans.append((o_s, o_e))
            prev_end = o_e
        narr = row.get("narration")
        if not isinstance(narr, str) or not narr.strip():
            errors.append(f"beat {i}: narration harus teks tidak kosong")
        elif o_s is not None and o_e is not None and o_e > o_s:
            wps = len(narr.split()) / (o_e - o_s)
            if not _WPS_MIN <= wps <= _WPS_MAX:
                errors.append(f"beat {i}: kecepatan narasi {wps:.1f} kata/detik di luar {_WPS_MIN}-{_WPS_MAX}")
        if row.get("emotion") not in EMOTIONS:
            errors.append(f"beat {i}: emotion harus salah satu dari {list(EMOTIONS)}")
        else:
            emotions.add(row["emotion"])
        if not isinstance(row.get("music"), str):
            errors.append(f"beat {i}: music harus teks")
        clips = row.get("clips")
        if not isinstance(clips, list) or not clips:
            errors.append(f"beat {i}: clips kosong")
        else:
            for j, clip in enumerate(clips, 1):
                errors += _clip_errors(clip, f"beat {i} klip {j}", duration_s, seen)
    if len(emotions) < 2:
        errors.append("beats butuh minimal 2 emosi berbeda")
    if formula is not None:
        want = [fb["name"] for fb in formula["beats"]]
        got = [row.get("beat") if isinstance(row, dict) else None for row in beats]
        if got != want:
            errors.append("beat harus sesuai urutan formula: " + " > ".join(want))
        elif timing_ok and spans[-1][1] > 0:
            total = spans[-1][1]
            for i, ((o_s, o_e), fb) in enumerate(zip(spans, formula["beats"]), 1):
                share = (o_e - o_s) / total * 100
                if abs(share - fb["pct"]) > _SHARE_TOL:
                    errors.append(f"beat {i}: porsi {share:.0f}% vs formula {fb['pct']}%")
    target = target_s if target_s is not None else _pos_num(recipe.get("target_duration_s"))
    if target is None:
        errors.append("target_duration_s harus angka > 0")
    elif timing_ok and spans:
        total = spans[-1][1]
        if abs(total - target) > _TARGET_TOL * target:
            errors.append(f"durasi total {total:g}s di luar 15% dari target {target:g}s")
    return errors


def validate_recipe(recipe: dict, duration_s: Optional[float], formula: Optional[dict],
                    target_s: Optional[float] = None) -> list[str]:
    """Return a list of problems (empty = ok). `formula` is the formula actually used (None = unknown or inactive)."""
    if not isinstance(recipe, dict):
        return ["resep bukan objek"]
    errors = []
    for key in ("angle", "credit", "formula_reason"):
        if not isinstance(recipe.get(key), str):
            errors.append(f"{key} harus teks")
    if formula is None:
        errors.append("formula tidak dikenal atau nonaktif")
    elif recipe.get("formula") != formula["slug"]:
        errors.append(f"formula harus '{formula['slug']}'")
    titles = recipe.get("titles")
    if not isinstance(titles, list) or len(titles) != 3:
        errors.append("titles harus tepat 3")
    elif not all(isinstance(t, str) and t.strip() for t in titles):
        errors.append("titles harus teks tidak kosong")
    errors += _beat_errors(recipe.get("beats"), duration_s, formula, target_s, recipe)
    av = recipe.get("added_value")
    score = av.get("score") if isinstance(av, dict) else None
    if not (isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 10):
        errors.append("added_value.score harus bilangan bulat 1-10")
    if not isinstance(av, dict) or not isinstance(av.get("why"), str):
        errors.append("added_value.why harus teks")
    tips = av.get("tips") if isinstance(av, dict) else None
    if not (isinstance(tips, list) and all(isinstance(t, str) for t in tips)):
        errors.append("added_value.tips harus daftar teks")
    if not isinstance(av, dict) or av.get("reused_content_risk") not in RISKS:
        errors.append(f"added_value.reused_content_risk harus salah satu dari {list(RISKS)}")
    return errors
