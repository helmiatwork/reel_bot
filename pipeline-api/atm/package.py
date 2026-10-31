"""Production package: one ZIP per item with the blueprint (readable + JSON), thumbnail prompts, upload text and audio."""
import io
import json
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

router = APIRouter()


def _lines(v, indent=0) -> list[str]:
    """Generic readable rendering: dicts become 'Key: value' lines, lists become bullets."""
    pad = "  " * indent
    if isinstance(v, dict):
        out = []
        for k, x in v.items():
            if isinstance(x, (dict, list)) and x:
                out += [f"{pad}- {k}:"] + _lines(x, indent + 1)
            elif x not in (None, "", [], {}):
                out.append(f"{pad}- {k}: {x}")
        return out
    if isinstance(v, list):
        out = []
        for x in v:
            if isinstance(x, (dict, list)):
                out += [f"{pad}-"] + _lines(x, indent + 1)
            else:
                out.append(f"{pad}- {x}")
        return out
    return [f"{pad}{v}"]


_SECTION_TITLES = (
    ("atm", "ATM: Tiru, Modifikasi, Orisinalitas"), ("titles", "Pilihan Judul"), ("hook", "Hook"),
    ("narration", "Narasi per Beat"), ("shots", "Daftar Shot"), ("audio", "Audio"), ("assets", "Aset"),
    ("capcut_steps", "Langkah Edit CapCut"), ("thumbnail", "Thumbnail"), ("upload", "Upload"),
    ("recording_tips", "Tips Rekaman"),
)


def blueprint_markdown(title: str, bp: dict) -> str:
    parts = [f"# Blueprint: {title}\n"]
    for key, label in _SECTION_TITLES:
        if bp.get(key):
            parts.append(f"## {label}\n\n" + "\n".join(_lines(bp[key])) + "\n")
    return "\n".join(parts)


def thumbnail_prompts(bp: dict) -> str:
    concepts = (bp.get("thumbnail") or {}).get("concepts") or []
    return "\n\n".join(f"Konsep {i}\nPrompt: {c.get('prompt', '')}\nTeks overlay: {c.get('overlay_text', '')}\n"
                       f"Alasan CTR: {c.get('why_ctr', '')}" for i, c in enumerate(concepts, 1) if isinstance(c, dict))


def upload_text(bp: dict) -> str:
    up = bp.get("upload") or {}
    titles = "\n".join(f"{i}. {t}" for i, t in enumerate(bp.get("titles") or [], 1))
    return (f"PILIHAN JUDUL\n{titles}\n\nDESKRIPSI\n{up.get('description', '')}\n\n"
            f"TAG\n{', '.join(map(str, up.get('tags') or []))}\n\n"
            f"HASHTAG\n{' '.join(map(str, up.get('hashtags') or []))}\n\nKOMENTAR PIN\n{up.get('pinned_comment', '')}\n")


def _inside_data(path_str, data_dir: Path):
    """Resolved Path when it is an existing file under data/, else None."""
    if not path_str:
        return None
    p = Path(path_str).resolve()
    return p if p.is_file() and p.is_relative_to(data_dir) else None


@router.get("/items/{item_id}/package")
def item_package(item_id: int):
    import main
    data_dir = (Path(main._REPO_ROOT) / "data").resolve()
    conn = main._db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="db unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT title, blueprint FROM content_items WHERE id = %s", (item_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="item not found")
            title, bp = row
            if not isinstance(bp, dict) or not bp:
                raise HTTPException(status_code=409, detail="Blueprint belum dibuat")
            # voiceover files live in data/songs/voiceover/<item_id>/ and are tagged item:<item_id>
            cur.execute("SELECT audio_path FROM songs WHERE kind = 'voiceover' AND audio_path LIKE %s ORDER BY id",
                        (f"%/voiceover/{item_id}/%",))
            audio = [("voiceover/" + Path(r[0]).name, r[0]) for r in cur.fetchall()]
            bgm_id = (bp.get("audio") or {}).get("bgm_song_id")
            if isinstance(bgm_id, int) and not isinstance(bgm_id, bool):
                cur.execute("SELECT audio_path FROM songs WHERE id = %s", (bgm_id,))
                r = cur.fetchone()
                if r and r[0]:
                    audio.append(("bgm/" + Path(r[0]).name, r[0]))
    finally:
        conn.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("blueprint.md", blueprint_markdown(title, bp))
        z.writestr("blueprint.json", json.dumps(bp, ensure_ascii=False, indent=2))
        z.writestr("thumbnail_prompts.txt", thumbnail_prompts(bp))
        z.writestr("upload.txt", upload_text(bp))
        for arcname, path_str in audio:
            p = _inside_data(path_str, data_dir)
            if p:
                z.write(p, arcname)
            else:
                print(f"[atm] package {item_id}: skipped audio outside data/ or missing")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:40] or "konten"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="atm-{item_id}-{slug}.zip"'})
