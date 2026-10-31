"""Per-beat AI voiceover into the songs library (kind='voiceover'). Never merged into video."""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class VoiceRequest(BaseModel):
    beat: Optional[int] = Field(default=None, ge=1, le=500)  # 1-based


def _beats(item_id: int):
    """(title, voice_mode, [vo text per beat]) or 404."""
    import main
    conn = main._db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="db unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT title, voice_mode, blueprint FROM content_items WHERE id = %s", (item_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="item not found")
    title, mode, bp = row
    beats = ((bp or {}).get("narration") or {}).get("beats") if isinstance(bp, dict) else None
    texts = [str((b or {}).get("vo") or "") for b in beats] if isinstance(beats, list) else []
    return title, mode, texts


@router.get("/items/{item_id}/voice/estimate")
def voice_estimate(item_id: int):
    from voiceover import voiceover as vo
    _, _, texts = _beats(item_id)
    return {"chars": sum(len(t) for t in texts), "beats": len(texts),
            "provider": "elevenlabs" if vo.ELEVENLABS_KEY else "gtts"}


@router.post("/items/{item_id}/voice")
def generate_voice(item_id: int, body: Optional[VoiceRequest] = None):
    import main
    from voiceover import voiceover as vo
    title, mode, texts = _beats(item_id)
    if mode != "ai" or not texts:
        raise HTTPException(status_code=400, detail="voice_mode harus 'ai' dan blueprint harus punya beat narasi")
    beat = body.beat if body else None
    if beat is not None and beat > len(texts):
        raise HTTPException(status_code=400, detail=f"beat harus 1..{len(texts)}")
    wanted = [beat] if beat else range(1, len(texts) + 1)
    out_dir = main._REPO_ROOT / "data" / "songs" / "voiceover" / str(item_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = []
    conn = main._db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="db unavailable")
    try:
        for n in wanted:
            text = texts[n - 1].strip()
            if not text:
                continue
            path = out_dir / f"beat_{n:02d}.mp3"
            try:
                vo.text_to_speech(text, str(path))
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"TTS gagal di beat {n}: {exc}")
            with conn.cursor() as cur:
                cur.execute("DELETE FROM songs WHERE kind = 'voiceover' AND audio_path = %s", (str(path),))
                cur.execute(
                    """INSERT INTO songs (title, audio_path, source, kind, tags)
                       VALUES (%s, %s, 'tts', 'voiceover', %s) RETURNING id""",
                    (f"{title} · beat {n}", str(path), json.dumps(["voiceover", f"item:{item_id}"])),
                )
                song_id = cur.fetchone()[0]
            conn.commit()
            files.append({"beat": n, "song_id": song_id, "url": f"/songs/{song_id}/download"})
    finally:
        conn.close()
    return {"files": files}
