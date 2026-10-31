"""Draft upload and draft evaluation rounds."""
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter()

MAX_DRAFT_BYTES = 300 * 1024 * 1024  # tests patch this
_CHUNK = 1024 * 1024
_LOCKED_STATUSES = ("scheduled", "posted", "monitored")  # re-upload never moves these back to review


def _draft_dir(item_id: int) -> Path:
    import main
    return main._REPO_ROOT / "data" / "drafts" / str(item_id)


@router.post("/items/{item_id}/draft")
def upload_draft(item_id: int, file: UploadFile = File(...)):
    import main
    ext = Path(file.filename or "").suffix.lower()  # only the whitelisted suffix is used; the name is ignored
    if ext not in main._SOURCE_UPLOAD_VIDEO_EXTS:
        raise HTTPException(status_code=400, detail=f"file harus video: {sorted(main._SOURCE_UPLOAD_VIDEO_EXTS)}")
    conn = main._db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="db unavailable")
    dest = None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM content_items WHERE id = %s", (item_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="item not found")
        out_dir = _draft_dir(item_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{uuid.uuid4()}{ext}"
        size = 0
        with open(dest, "wb") as fh:
            while chunk := file.file.read(_CHUNK):
                size += len(chunk)
                if size > MAX_DRAFT_BYTES:
                    raise HTTPException(status_code=413, detail=f"file terlalu besar (maks {MAX_DRAFT_BYTES // 2**20} MB)")
                fh.write(chunk)
        rel = str(dest.relative_to(main._REPO_ROOT))
        with conn.cursor() as cur:
            cur.execute("UPDATE content_items SET draft_video_path = %s, "
                        "stage = CASE WHEN stage = ANY(%s) THEN stage ELSE 'review' END, updated_at = now() "
                        "WHERE id = %s", (rel, list(_LOCKED_STATUSES), item_id))
        conn.commit()
        return {"draft_video_path": rel}
    except BaseException:
        if dest is not None:
            dest.unlink(missing_ok=True)
        raise
    finally:
        conn.close()
