"""Blueprint generation: one claude call per item (or per section), validated before anything is saved."""
import json
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .common import ATM_MODEL, item_row, parse_json, run_claude

router = APIRouter()

BLUEPRINT_SECTIONS = ("atm", "titles", "hook", "narration", "shots", "audio", "assets",
                      "capcut_steps", "thumbnail", "upload", "recording_tips")

_SCHEMA = """{
  "atm": {"tiru": ["..."], "modifikasi": ["..."], "checklist_orisinalitas": ["..."]},
  "titles": ["tepat 5 judul, memuat keyword utama"],
  "hook": {"line": "kalimat hook 3 detik", "visual": "visual pembuka"},
  "narration": {"style": "gaya bicara awam", "beats": [{"t": "00:00-00:03", "vo": "naskah", "note": "jeda/penekanan"}]},
  "shots": [{"n": 1, "duration_s": 3, "record": "apa yang direkam", "framing": "", "camera": "", "on_screen_text": "", "transition": "efek/transisi CapCut"}],
  "audio": {"bgm_song_id": 0, "bgm_reason": "", "sfx": [{"moment": "", "sfx": ""}]},
  "assets": {"have": [{"song_id": 0, "label": ""}], "need": ["harus direkam/dicari"]},
  "capcut_steps": ["langkah edit bernomor untuk pemula"],
  "thumbnail": {"concepts": [{"prompt": "prompt AI gambar", "overlay_text": "maks 4 kata", "why_ctr": "alasan CTR"}], "rules": ["kontras", "1 fokus", "terbaca di HP"], "cover_frame": {"shot": 1, "moment": "momen di shot untuk cover in-app (hanya format short)", "overlay_text": "teks di cover"}},
  "upload": {"description": "2 baris pertama memuat keyword", "tags": [], "hashtags": [], "pinned_comment": "", "playlist": "", "end_screen": "", "checklist": []},
  "recording_tips": ["jarak mic, ruangan, rekam per beat"]
}"""

_MAX_CTX_CHARS = 6000
_DURATION_TOLERANCE = 0.15
_TIME = re.compile(r"\d+(?::\d+){1,2}|\d+(?:\.\d+)?")


def _seconds(token: str) -> float:
    secs = 0.0
    for part in token.split(":"):
        secs = secs * 60 + float(part)
    return secs


def _narration_end(beats: list) -> Optional[float]:
    """Largest end time (s) over beats; `t` is 'mm:ss-mm:ss', 'mm:ss' or a number, or `end_s`/`end` is numeric."""
    ends = []
    for b in beats:
        if not isinstance(b, dict):
            continue
        for key in ("end_s", "end"):
            if isinstance(b.get(key), (int, float)) and not isinstance(b[key], bool):
                ends.append(float(b[key]))
                break
        else:
            t = b.get("t")
            if isinstance(t, (int, float)) and not isinstance(t, bool):
                ends.append(float(t))
            elif isinstance(t, str) and (found := _TIME.findall(t)):
                ends.append(_seconds(found[-1]))
    return max(ends) if ends else None


def _shots_total(shots: list) -> Optional[float]:
    vals = [s.get("duration_s") for s in shots if isinstance(s, dict)]
    nums = [float(v) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(nums) if nums else None


def validate_blueprint(bp: dict, song_ids: set, channel: Optional[str] = None, fmt: Optional[str] = None,
                       niche: Optional[str] = None) -> list[str]:
    """Return a list of problems (empty = ok). Unknown bgm_song_id is nulled in place, not an error."""
    if not isinstance(bp, dict):
        return ["blueprint is not an object"]
    errors = [f"bagian '{s}' hilang" for s in BLUEPRINT_SECTIONS if s not in bp]
    titles = bp.get("titles")
    if "titles" in bp and (not isinstance(titles, list) or len(titles) != 5):
        errors.append("titles harus tepat 5")
    name = (channel or "").strip().lstrip("@").lower()
    if name and isinstance(titles, list):
        for t in titles:
            if name in str(t).lower():
                errors.append(f"judul memuat nama channel referensi '{channel}': {t}")
    niche_name = (niche or "").strip().lower()
    if niche_name and isinstance(titles, list):
        lead = re.compile(re.escape(niche_name) + r"\s*[:|-]")
        for t in titles:
            if lead.match(str(t).strip().lower()):
                errors.append(f"judul diawali nama niche '{niche}': {t}")
    thumb = bp.get("thumbnail")
    if "thumbnail" in bp:
        concepts = thumb.get("concepts") if isinstance(thumb, dict) else None
        if not isinstance(concepts, list) or len(concepts) != 3:
            errors.append("thumbnail.concepts harus tepat 3")
        else:
            for i, c in enumerate(concepts, 1):
                if not isinstance(c, dict) or not all(c.get(k) for k in ("prompt", "overlay_text", "why_ctr")):
                    errors.append(f"thumbnail konsep {i} butuh prompt, overlay_text, why_ctr")
                elif len(str(c["overlay_text"]).split()) > 4:
                    errors.append(f"thumbnail konsep {i}: overlay_text maksimal 4 kata")
    if "shots" in bp and not (isinstance(bp["shots"], list) and bp["shots"]):
        errors.append("shots kosong")
    narr = bp.get("narration")
    if "narration" in bp and not (isinstance(narr, dict) and isinstance(narr.get("beats"), list) and narr["beats"]):
        errors.append("narration.beats kosong")
    shots, beats = bp.get("shots"), (narr or {}).get("beats") if isinstance(narr, dict) else None
    if isinstance(shots, list) and isinstance(beats, list):
        total, end = _shots_total(shots), _narration_end(beats)
        if total and end and abs(total - end) > _DURATION_TOLERANCE * end:
            errors.append(f"total durasi shots ({total:g}s) harus sama dengan akhir narasi ({end:g}s) dengan selisih maksimal 15%")
    if fmt == "short":
        texts = [str(t) for t in (bp.get("recording_tips") if isinstance(bp.get("recording_tips"), list) else [])]
        texts += [str(s.get("camera") or "") for s in shots if isinstance(s, dict)] if isinstance(shots, list) else []
        if any(w in t.lower() for t in texts for w in ("horizontal", "landscape")):
            errors.append("format short harus vertikal 9:16: hapus 'horizontal'/'landscape' dari recording_tips dan camera")
        cf = thumb.get("cover_frame") if isinstance(thumb, dict) else None
        if "thumbnail" in bp and not (isinstance(cf, dict) and all(cf.get(k) for k in ("shot", "moment", "overlay_text"))):
            errors.append("thumbnail.cover_frame (shot, moment, overlay_text) wajib untuk format short")
    audio = bp.get("audio")
    if isinstance(audio, dict) and audio.get("bgm_song_id") not in song_ids:
        audio["bgm_song_id"] = None
    return errors


def build_blueprint_prompt(item: dict, ctx: dict, section: Optional[str] = None) -> str:
    def block(label, data):
        if not data:
            return ""
        return f"\n## {label}\n{json.dumps(data, ensure_ascii=False, default=str)[:_MAX_CTX_CHARS]}\n"

    parts = [
        "Kamu adalah ATM (Amati-Tiru-Modifikasi) coach untuk kreator YouTube pemula. "
        "Buat Blueprint Konten dalam bahasa Indonesia.\n",
        f"Judul kerja: {item.get('title')}\nNiche: {item.get('niche') or 'umum'}\n"
        f"Format: {item.get('format')}\nVoice: {item.get('voice_mode')}\n",
        "Aturan orisinalitas: jangan memakai footage referensi sebagai materi; semua footage dan narasi "
        "direkam/ditulis sendiri. Tiru struktur dan pola, modifikasi sudut cerita.\n",
        "Judul, deskripsi, dan tag TIDAK BOLEH memuat nama atau handle channel referensi"
        + (f" ('{ctx['reference_channel']}')" if ctx.get("reference_channel") else "") + ".\n",
        f"Judul (titles) TIDAK BOLEH diawali nama niche ('{item.get('niche') or 'umum'}') atau prefix \"Kategori:\"; "
        "langsung mulai judul dari hook atau manfaatnya.\n",
        block("Analisa referensi", ctx.get("analysis")),
        block("Ide dari referensi", ctx.get("ideas")),
        block("Efek referensi", ctx.get("effects")),
        block("Lagu/klip audio di pustaka (pilih bgm_song_id dari sini)", ctx.get("songs")),
        block("Pelajaran sebelumnya", ctx.get("learnings")),
        block("Keyword SEO", ctx.get("keywords")),
    ]
    parts.append(
        "\nDurasi: jumlah shots[].duration_s HARUS sama dengan waktu akhir narasi (beat terakhir), selisih maksimal 15%.\n"
        "Thumbnail: thumbnail.concepts berisi TEPAT 3 konsep berbeda; cover_frame terpisah dan TIDAK dihitung sebagai konsep.\n")
    if item.get("format") == "short":
        parts.append(
            "Format short: SEMUA vertikal 9:16 (tips rekaman, kamera, CapCut); jangan tulis horizontal/landscape. "
            "thumbnail.cover_frame WAJIB: nomor shot + momen untuk cover frame in-app dan teks overlay.\n")
    else:
        parts.append("Format long: semua horizontal 16:9 (tips rekaman, kamera, CapCut).\n")
    if item.get("voice_mode") == "self":
        parts.append("\nvoice_mode=self: recording_tips WAJIB diisi (jarak mic, ruangan, rekam per beat).\n")
    else:
        parts.append("\nvoice_mode=ai: recording_tips boleh berupa daftar kosong.\n")
    if section:
        parts.append(
            f"\nBuat ulang HANYA bagian \"{section}\". Blueprint saat ini:\n"
            f"{json.dumps(item.get('blueprint'), ensure_ascii=False, default=str)[:_MAX_CTX_CHARS * 2]}\n"
            f"Balas JSON saja, satu objek dengan satu kunci: {{\"{section}\": ...}} dengan bentuk yang sama.\n"
        )
    else:
        parts.append(f"\nBalas JSON saja (tanpa teks lain) dengan bentuk persis:\n{_SCHEMA}\n")
    return "".join(parts)


def _rows(cur, sql, params=()):
    """Best-effort read: [] (and a clean transaction) when a table/column is missing."""
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception as exc:
        print(f"[atm] context query skipped: {exc}")
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return []


def gather_context(cur, item: dict) -> dict:
    url, niche = item.get("reference_url"), item.get("niche") or "general"
    ctx: dict = {}
    if url:
        rows = _rows(cur, "SELECT hook, structure, retention, content_summary, content_detail "
                          "FROM video_analysis WHERE youtube_url = %s ORDER BY id DESC LIMIT 1", (url,))
        ctx["analysis"] = dict(zip(("hook", "structure", "retention", "summary", "detail"), rows[0])) if rows else None
        rows = _rows(cur, "SELECT detail, candidates FROM source_ideas WHERE youtube_url = %s", (url,))
        ctx["ideas"] = dict(zip(("detail", "candidates"), rows[0])) if rows else None
        rows = _rows(cur, "SELECT effects FROM source_effects WHERE youtube_url = %s", (url,))
        ctx["effects"] = rows[0][0] if rows else None
        rows = _rows(cur, "SELECT channel FROM sources WHERE youtube_url = %s AND channel IS NOT NULL LIMIT 1", (url,))
        ctx["reference_channel"] = rows[0][0] if rows else None
    rows = _rows(cur, "SELECT id, title, mood, bpm, genre, is_viral FROM songs WHERE kind IN ('song','clip') "
                      "ORDER BY is_viral DESC, created_at DESC LIMIT 20")
    ctx["songs"] = [dict(zip(("id", "title", "mood", "bpm", "genre", "is_viral"), r)) for r in rows]
    rows = _rows(cur, "SELECT kind, content FROM learnings WHERE niche IN (%s, 'general') "
                      "ORDER BY hits DESC LIMIT 10", (niche,))
    ctx["learnings"] = [{"kind": r[0], "content": r[1]} for r in rows]
    rows = _rows(cur, "SELECT keyword, score FROM keywords WHERE niche = %s "
                      "ORDER BY score DESC NULLS LAST LIMIT 10", (niche,))
    ctx["keywords"] = [{"keyword": r[0], "score": r[1]} for r in rows]
    return ctx


def _fail(conn, item_id: int, message: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE content_items SET blueprint_status = 'error', blueprint_error = %s, "
                    "updated_at = now() WHERE id = %s", (message[:300], item_id))
    conn.commit()


def _run_blueprint(item_id: int, section: Optional[str]) -> None:
    """Background job: never writes `blueprint` unless the result validated."""
    import main
    conn = main._db_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM content_items WHERE id = %s", (item_id,))
            row = cur.fetchone()
            if not row:
                return
            item = item_row(cur.description, row)
            ctx = gather_context(cur, item)
        song_ids = {s["id"] for s in ctx["songs"]}
        base_prompt = build_blueprint_prompt(item, ctx, section)
        prompt, errors = base_prompt, []
        for attempt in (1, 2):  # one retry with the validation errors appended
            text = run_claude(prompt, agent="atm_blueprint", model=ATM_MODEL)
            if text is None:
                return _fail(conn, item_id, "Claude tidak bisa dihubungi. Coba lagi nanti.")
            parsed = parse_json(text)
            if parsed is None:
                return _fail(conn, item_id, "Jawaban Claude bukan JSON yang valid. Coba buat ulang.")
            if section:
                if section not in parsed or not isinstance(item.get("blueprint"), dict):
                    return _fail(conn, item_id, f"Bagian '{section}' tidak ada di jawaban Claude.")
                bp = {**item["blueprint"], section: parsed[section]}
            else:
                bp = parsed
            errors = validate_blueprint(bp, song_ids, ctx.get("reference_channel"), item.get("format"), item.get("niche"))
            if not errors:
                break
            prompt = base_prompt + "\n\nJawaban sebelumnya ditolak karena:\n- " + "\n- ".join(errors) + \
                "\nPerbaiki semua masalah di atas dan balas JSON saja."
        if errors:
            return _fail(conn, item_id, "Blueprint tidak lengkap: " + "; ".join(errors))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE content_items SET blueprint = %s::jsonb, blueprint_version = blueprint_version + 1, "
                "blueprint_status = 'ready', blueprint_error = NULL, "
                "stage = CASE WHEN stage = 'idea' THEN 'blueprint' ELSE stage END, updated_at = now() "
                "WHERE id = %s AND blueprint_status = 'building'", (json.dumps(bp), item_id))
        conn.commit()
    except Exception as exc:
        print(f"[atm] blueprint job {item_id} failed: {exc}")
        try:
            conn.rollback()
            _fail(conn, item_id, "Gagal membuat blueprint. Coba lagi.")
        except Exception:
            pass
    finally:
        conn.close()


class BlueprintRequest(BaseModel):
    section: Optional[str] = None


@router.post("/items/{item_id}/blueprint")
def create_blueprint(item_id: int, background: BackgroundTasks, body: Optional[BlueprintRequest] = None):
    import main
    section = body.section if body else None
    if section is not None and section not in BLUEPRINT_SECTIONS:
        raise HTTPException(status_code=400, detail=f"section must be one of {list(BLUEPRINT_SECTIONS)}")
    conn = main._db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="db unavailable")
    try:
        with conn.cursor() as cur:
            # FOR UPDATE: two concurrent POSTs must not both pass the "already building" check
            cur.execute("SELECT reference_url, blueprint, "
                        "(blueprint_status = 'building' AND blueprint_started_at > now() - interval '15 minutes') "
                        "FROM content_items WHERE id = %s FOR UPDATE", (item_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="item not found")
            url, existing, building = row
            if building:  # a build running > 15 min (or with no start time) counts as crashed and may restart
                raise HTTPException(status_code=409, detail="blueprint masih dibuat")
            if section and not existing:
                raise HTTPException(status_code=400, detail="buat blueprint lengkap dulu sebelum membuat ulang satu bagian")
            if url:
                cur.execute("SELECT 1 FROM video_analysis WHERE youtube_url = %s LIMIT 1", (url,))
                if not cur.fetchone():
                    raise HTTPException(status_code=409, detail="Referensi belum dianalisa")
            cur.execute("UPDATE content_items SET blueprint_status = 'building', blueprint_error = NULL, "
                        "blueprint_started_at = now(), updated_at = now() WHERE id = %s", (item_id,))
        conn.commit()
    finally:
        conn.close()
    background.add_task(_run_blueprint, item_id, section)
    return {"status": "building"}
