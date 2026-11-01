"""Narration formulas for Olah Sampah recipes: table, seed (never overwrites user edits) and CRUD under /atm/formulas."""
import json
import re

import psycopg
from fastapi import APIRouter, HTTPException, Path
from typing import Any

from pydantic import BaseModel

from .common import item_row
from .recycle import _db
from .recycle_rules import EMOTIONS

router = APIRouter()

_SLUG = re.compile(r"[a-z0-9_]{2,40}")
_MAX_BIGINT = 2**63 - 1
_MAX_INT4 = 2**31 - 1
_MAX_TEXT = 300
_MAX_BEATS = 12

# (slug, name, fits, beats); beat = (name, pct, emotion, goal). pct per formula sums to 100.
SEED = [
    ("pas", "PAS (Masalah–Diperparah–Solusi)", "sidak, keluhan warga", [
        ("Masalah", 15, "penasaran", "perkenalkan masalah yang dialami warga"),
        ("Diperparah", 45, "marah", "tunjukkan masalah makin parah dan dampaknya"),
        ("Solusi/aksi", 30, "haru", "tampilkan solusi atau aksi yang menyelesaikan"),
        ("Ajakan", 10, "penasaran", "ajak penonton ikut bertindak atau berkomentar"),
    ]),
    ("in_medias_res", "In Medias Res (mulai dari klimaks)", "konfrontasi, kejadian viral", [
        ("Momen puncak", 10, "tegang", "buka dengan momen paling menegangkan"),
        ("Mundur ke awal", 25, "penasaran", "jelaskan bagaimana semua dimulai"),
        ("Naik lagi", 40, "tegang", "bangun ketegangan menuju klimaks"),
        ("Klimaks penuh", 15, "marah", "tampilkan klimaks dengan lengkap"),
        ("Penutup", 10, "haru", "tutup dengan dampak dan pesan"),
    ]),
    ("underdog", "Underdog (rakyat kecil vs sistem)", "bantu warga, nenek, anak yatim", [
        ("Kenalkan korban", 20, "sedih", "perkenalkan orang kecil dan situasinya"),
        ("Penderitaan", 25, "sedih", "tunjukkan beratnya penderitaan"),
        ("Penolong datang", 15, "haru", "munculkan pihak yang membantu"),
        ("Perlawanan", 25, "marah", "tunjukkan perlawanan terhadap sistem"),
        ("Kemenangan kecil", 15, "senang", "akhiri dengan kemenangan kecil yang nyata"),
    ]),
    ("open_loop", "Open Loop Berlapis", "video panjang, jaga retensi", [
        ("Pertanyaan besar", 5, "penasaran", "ajukan pertanyaan besar di awal"),
        ("Loop kecil buka-tutup", 75, "tegang", "buka dan tutup pertanyaan kecil berulang untuk menahan penonton"),
        ("Jawaban besar", 15, "haru", "jawab pertanyaan besar di akhir"),
        ("Pertanyaan komentar", 5, "penasaran", "ajukan pertanyaan untuk memancing komentar"),
    ]),
    ("rollercoaster", "Rollercoaster Emosi", "kompilasi momen campur", [
        ("Sedih", 20, "sedih", "puncak tiap 30–60 detik; emosi sama maksimal 2 beat berurutan"),
        ("Lucu", 20, "lucu", "puncak tiap 30–60 detik; emosi sama maksimal 2 beat berurutan"),
        ("Marah", 20, "marah", "puncak tiap 30–60 detik; emosi sama maksimal 2 beat berurutan"),
        ("Haru", 20, "haru", "puncak tiap 30–60 detik; emosi sama maksimal 2 beat berurutan"),
        ("Bahagia", 20, "senang", "puncak tiap 30–60 detik; emosi sama maksimal 2 beat berurutan"),
    ]),
    ("investigasi", "Investigasi", "kasus, kejanggalan", [
        ("Kejanggalan", 10, "penasaran", "perkenalkan kejanggalan pertama"),
        ("Bukti", 60, "tegang", "tampilkan bukti satu per satu"),
        ("Twist", 15, "tegang", "ungkap fakta yang mengejutkan"),
        ("Kesimpulan", 15, "haru", "simpulkan dan sampaikan dampaknya"),
    ]),
    ("before_after_bridge", "Before–After–Bridge", "transformasi, perbaikan", [
        ("Dulu", 30, "sedih", "kondisi sebelum perubahan"),
        ("Sekarang", 30, "haru", "kondisi setelah perubahan"),
        ("Yang mengubah", 40, "senang", "jelaskan apa yang mengubahnya"),
    ]),
    ("story_circle", "Story Circle (8 langkah)", "8+ menit satu tokoh", [
        ("Nyaman", 12, "senang", "tokoh di kondisi normalnya"),
        ("Butuh", 12, "sedih", "tokoh menginginkan sesuatu"),
        ("Masuk situasi asing", 12, "penasaran", "tokoh masuk dunia baru"),
        ("Berusaha", 13, "tegang", "tokoh berusaha keras"),
        ("Mendapat", 13, "senang", "tokoh mendapat yang dicari"),
        ("Membayar harga", 13, "sedih", "tokoh membayar harga"),
        ("Kembali", 12, "marah", "tokoh kembali ke tempat asal"),
        ("Berubah", 13, "haru", "tokoh sudah berubah"),
    ]),
    ("kronologi", "Kronologi + Komentar", "berita bertahap", [
        ("Awal", 25, "penasaran", "kejadian pertama"),
        ("Tengah", 25, "tegang", "perkembangan"),
        ("Akhir", 25, "tegang", "puncak berita"),
        ("Komentar", 25, "haru", "reaksi dan komentar warga"),
    ]),
    ("pro_kontra", "Pro–Kontra", "kebijakan kontroversial", [
        ("Isu", 10, "penasaran", "jelaskan isu kebijakan"),
        ("Sisi A", 35, "marah", "argumen pihak pertama"),
        ("Sisi B", 35, "tegang", "argumen pihak kedua"),
        ("Sikap", 20, "penasaran", "ajak penonton menentukan sikap"),
    ]),
    ("pixar", "Pixar (6 kalimat)", "cerita satu tokoh, short 1–3 menit", [
        ("Dahulu kala", 15, "penasaran", "perkenalkan tokoh dan dunianya"),
        ("Setiap hari", 15, "sedih", "rutinitas yang membosankan"),
        ("Sampai suatu hari", 15, "tegang", "kejadian yang mengganggu"),
        ("Karena itu", 20, "tegang", "tokoh bertindak"),
        ("Karena itu lagi", 20, "marah", "akibat yang makin besar"),
        ("Sampai akhirnya", 15, "haru", "penyelesaian"),
    ]),
    ("freytag", "Piramida Freytag", "kejadian dengan puncak jelas", [
        ("Eksposisi", 15, "penasaran", "latar dan tokoh"),
        ("Aksi naik", 35, "tegang", "konflik meningkat"),
        ("Klimaks", 15, "marah", "puncak konflik"),
        ("Aksi turun", 20, "haru", "konflik mereda"),
        ("Penyelesaian", 15, "senang", "akhir cerita"),
    ]),
    ("wsj", "Formula Wall Street Journal", "satu warga → isu yang lebih besar", [
        ("Kisah satu orang", 25, "sedih", "ceritakan satu orang"),
        ("Perluas ke isu besar", 30, "penasaran", "hubungkan ke isu yang lebih luas"),
        ("Bukti/dampak", 25, "tegang", "tampilkan data dan dampak"),
        ("Kembali ke orang itu", 20, "haru", "kembali ke orang tadi"),
    ]),
    ("sparkline", "Sparkline (Apa adanya vs Seharusnya)", "pidato, kebijakan, visi pemimpin", [
        ("Kondisi sekarang", 20, "sedih", "apa adanya; beat ganjil = apa adanya, genap = seharusnya, bergantian"),
        ("Bisa seperti ini", 20, "senang", "gambaran seharusnya; beat ganjil = apa adanya, genap = seharusnya, bergantian"),
        ("Kondisi sekarang lagi", 20, "marah", "apa adanya; beat ganjil = apa adanya, genap = seharusnya, bergantian"),
        ("Bisa seperti ini lagi", 20, "haru", "gambaran seharusnya; beat ganjil = apa adanya, genap = seharusnya, bergantian"),
        ("Ajakan", 20, "senang", "ajak penonton bertindak"),
    ]),
]

_CREATE = """CREATE TABLE IF NOT EXISTS narration_formulas (
    id          BIGSERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    fits        TEXT,
    beats       JSONB NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT true,
    sort        INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
)"""
_SEED_SQL = ("INSERT INTO narration_formulas (slug, name, fits, beats, sort) VALUES (%s, %s, %s, %s::jsonb, %s) "
             "ON CONFLICT (slug) DO NOTHING")


def validate_formula(f: dict) -> list[str]:
    """Return a list of problems (empty = ok). Every field is checked: the input is untrusted JSON."""
    errors = []
    name, slug, fits = f.get("name"), f.get("slug"), f.get("fits")
    if not isinstance(name, str) or not name.strip():
        errors.append("name harus teks tidak kosong")
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
        errors.append("slug harus 2-40 karakter huruf kecil, angka atau _")
    if fits is not None and not isinstance(fits, str):
        errors.append("fits harus teks")
    if not isinstance(f.get("active"), bool):
        errors.append("active harus true/false")
    sort = f.get("sort")
    if isinstance(sort, bool) or not isinstance(sort, int) or not -_MAX_INT4 <= sort <= _MAX_INT4:
        errors.append("sort harus bilangan bulat")
    beats = f.get("beats")
    if not isinstance(beats, list) or not beats:
        return errors + ["beats harus daftar tidak kosong"]
    if len(beats) > _MAX_BEATS:
        return errors + [f"beats maksimal {_MAX_BEATS}"]
    texts = [name, fits] + [b.get(k) for b in beats if isinstance(b, dict) for k in ("name", "goal")]
    if any(isinstance(t, str) and len(t) > _MAX_TEXT for t in texts):
        errors.append(f"teks formula maksimal {_MAX_TEXT} karakter")
    pcts = []
    for i, b in enumerate(beats, 1):
        if not isinstance(b, dict):
            errors.append(f"beat {i} bukan objek")
            continue
        if not isinstance(b.get("name"), str) or not b["name"].strip():
            errors.append(f"beat {i}: name harus teks tidak kosong")
        if not isinstance(b.get("goal"), str):
            errors.append(f"beat {i}: goal harus teks")
        if b.get("emotion") not in EMOTIONS:
            errors.append(f"beat {i}: emotion harus salah satu dari {list(EMOTIONS)}")
        pct = b.get("pct")
        if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not 0 < pct <= 100:  # NaN/inf fail here
            errors.append(f"beat {i}: pct harus angka > 0")
        else:
            pcts.append(pct)
    if len(pcts) == len(beats) and abs(sum(pcts) - 100) > 1:
        errors.append("pct harus berjumlah 100 (±1)")
    return errors


def init_formulas_db() -> None:
    import main
    conn = main._db_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(_CREATE)
            # seed an empty table only: a formula the user deleted or renamed must not come back on restart
            cur.execute("SELECT EXISTS (SELECT 1 FROM narration_formulas)")
            row = cur.fetchone()
            for sort, (slug, name, fits, beats) in enumerate(SEED if not (row and row[0]) else (), 1):
                # DO NOTHING: two processes starting together must not fail or duplicate
                beat_dicts = [{"name": n, "pct": p, "emotion": e, "goal": g} for n, p, e, g in beats]
                cur.execute(_SEED_SQL, (slug, name, fits, json.dumps(beat_dicts, ensure_ascii=False), sort))
        conn.commit()
    finally:
        conn.close()


class FormulaIn(BaseModel):
    # typed as Any so every bad value gets a 400 from validate_formula, not a framework 422
    slug: Any = None
    name: Any = None
    fits: Any = None
    beats: Any = None
    active: Any = True
    sort: Any = 0


def _checked(body: FormulaIn) -> dict:
    data = body.model_dump()
    errors = validate_formula(data)
    if errors:
        raise HTTPException(status_code=400, detail=errors)
    return data


def _values(f: dict) -> tuple:
    beats = [{k: b[k] for k in ("name", "pct", "emotion", "goal")} for b in f["beats"]]
    return (f["slug"], f["name"], f["fits"], json.dumps(beats, ensure_ascii=False), f["active"], f["sort"])


@router.get("/formulas")
def list_formulas(active: bool = False):
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, slug, name, fits, beats, active, sort, created_at, updated_at FROM narration_formulas"
                        + (" WHERE active" if active else "") + " ORDER BY sort, id")
            return {"formulas": [item_row(cur.description, r) for r in cur.fetchall()]}
    finally:
        conn.close()


@router.post("/formulas")
def create_formula(body: FormulaIn):
    data = _checked(body)
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO narration_formulas (slug, name, fits, beats, active, sort) "
                        "VALUES (%s, %s, %s, %s::jsonb, %s, %s) RETURNING id", _values(data))
            row = cur.fetchone()
        conn.commit()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="slug sudah dipakai")
    finally:
        conn.close()
    return {"id": row[0]}


@router.put("/formulas/{fid}")
def update_formula(body: FormulaIn, fid: int = Path(..., ge=1, le=_MAX_BIGINT)):
    data = _checked(body)
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE narration_formulas SET slug = %s, name = %s, fits = %s, beats = %s::jsonb, "
                        "active = %s, sort = %s, updated_at = now() WHERE id = %s RETURNING id", (*_values(data), fid))
            row = cur.fetchone()
        conn.commit()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="slug sudah dipakai")
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="formula tidak ditemukan")
    return {"ok": True}


@router.delete("/formulas/{fid}")
def delete_formula(fid: int = Path(..., ge=1, le=_MAX_BIGINT)):
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM narration_formulas WHERE id = %s RETURNING id", (fid,))
            row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="formula tidak ditemukan")
    return {"ok": True}
