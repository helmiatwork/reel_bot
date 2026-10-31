"""Content item CRUD + routine settings."""
import datetime as _dt
import json
import re
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .common import STATUSES, item_row

router = APIRouter()

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    niche: str = ""
    reference_url: Optional[str] = None
    format: Literal["short", "long"] = "short"
    voice_mode: Literal["self", "ai"] = "self"


class ItemPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[str] = None
    blueprint: Optional[dict] = None
    scheduled_at: Optional[_dt.datetime] = None
    published_url: Optional[str] = None
    voice_mode: Optional[Literal["self", "ai"]] = None
    format: Optional[Literal["short", "long"]] = None
    niche: Optional[str] = None


class Settings(BaseModel):
    weekdays: list[int] = Field(min_length=1, max_length=7)
    post_time: str
    tz: str
    per_week: int = Field(ge=1, le=21)
    niche: str = "general"
    format: Literal["short", "long"] = "short"
    alert_ratio: float = Field(ge=0.1, le=1.0)

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, v):
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekdays must be 0..6 (Monday = 0)")
        return sorted(set(v))

    @field_validator("post_time")
    @classmethod
    def _post_time(cls, v):
        if not _HHMM.match(v):
            raise ValueError("post_time must be HH:MM")
        return v

    @field_validator("tz")
    @classmethod
    def _tz(cls, v):
        try:
            ZoneInfo(v)
        except Exception:
            raise ValueError("unknown time zone")
        return v


def _conn():
    import main
    conn = main._db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="db unavailable")
    return conn


def _out(payload):
    import main
    return main._json(payload)


@router.get("/items")
def list_items(status: Optional[str] = None):
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {list(STATUSES)}")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            where, params = ("WHERE stage = %s", (status,)) if status else ("", ())
            cur.execute(f"SELECT * FROM content_items {where} ORDER BY scheduled_at NULLS LAST, id DESC", params)
            return _out({"items": [item_row(cur.description, r) for r in cur.fetchall()]})
    finally:
        conn.close()


def insert_item(cur, title, niche, ref, format="short", voice_mode="self") -> dict:
    """Insert an idea-stage item (links `sources` when the reference is already analyzed); returns the row."""
    source_id = None
    if ref:
        cur.execute("SELECT id FROM sources WHERE youtube_url = %s", (ref,))
        r = cur.fetchone()
        source_id = r[0] if r else None
    cur.execute(
        """INSERT INTO content_items
               (title, niche, reference_url, reference_source_id, format, voice_mode, stage)
           VALUES (%s, %s, %s, %s, %s, %s, 'idea') RETURNING *""",
        (title, niche, ref, source_id, format, voice_mode),
    )
    return item_row(cur.description, cur.fetchone())


@router.post("/items")
def create_item(body: ItemCreate):
    import main
    ref = body.reference_url.strip() if body.reference_url else None
    if ref:
        main._validate_source_url(ref)  # HTTPException 400 on bad / SSRF url
    conn = _conn()
    try:
        with conn.cursor() as cur:
            item = insert_item(cur, body.title, body.niche, ref, body.format, body.voice_mode)
        conn.commit()
        return _out(item)
    finally:
        conn.close()


@router.get("/items/{item_id}")
def get_item(item_id: int):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM content_items WHERE id = %s", (item_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="item not found")
            item = item_row(cur.description, row)
            cur.execute(
                "SELECT id, kind, round, summary, created_at FROM content_evaluations "
                "WHERE content_item_id = %s ORDER BY kind, round",
                (item_id,),
            )
            item["evaluations"] = [item_row(cur.description, r) for r in cur.fetchall()]
        return _out(item)
    finally:
        conn.close()


def _blueprint_shape_ok(bp: dict) -> bool:
    """Cheap isinstance guard so the UI/packager never trip on a malformed hand-edit (not full validation)."""
    def dicts(v):
        return isinstance(v, list) and all(isinstance(x, dict) for x in v)
    audio = bp.get("audio")
    if audio is not None and not isinstance(audio, dict):
        return False
    narration = bp.get("narration")
    if narration is not None and not (isinstance(narration, dict) and (narration.get("beats") is None or dicts(narration["beats"]))):
        return False
    return bp.get("shots") is None or dicts(bp["shots"])


@router.patch("/items/{item_id}")
def patch_item(item_id: int, body: ItemPatch):
    import main
    if body.status is not None and body.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {list(STATUSES)}")
    if body.blueprint is not None and not _blueprint_shape_ok(body.blueprint):
        raise HTTPException(status_code=400, detail="blueprint tidak valid: audio, narration.beats, shots salah bentuk")
    sets, vals = [], []
    # published_url wins over an explicit status: it always means "posted"
    status = "posted" if body.published_url is not None else body.status
    for col, v in (("title", body.title), ("stage", status),
                   ("voice_mode", body.voice_mode), ("format", body.format), ("niche", body.niche)):
        if v is not None:
            sets.append(f"{col} = %s")
            vals.append(v)
    if "scheduled_at" in body.model_fields_set:  # explicit null clears; a changed time re-arms reminders
        # Postgres evaluates every SET expression against the old row, so the CASE sees the old scheduled_at
        sets += ["scheduled_at = %s",
                 "reminded_d1_at = CASE WHEN scheduled_at IS DISTINCT FROM %s THEN NULL ELSE reminded_d1_at END",
                 "reminded_d0_at = CASE WHEN scheduled_at IS DISTINCT FROM %s THEN NULL ELSE reminded_d0_at END"]
        vals.extend([body.scheduled_at] * 3)
    if body.blueprint is not None:
        sets += ["blueprint = %s::jsonb", "blueprint_version = blueprint_version + 1"]
        vals.append(json.dumps(body.blueprint))
    if body.published_url is not None:
        sets += ["published_url = %s", "published_at = COALESCE(published_at, now())"]
        url = main._validate_source_url(body.published_url.strip())
        if main._detect_platform(url) != "youtube":
            raise HTTPException(status_code=400, detail="Hanya URL YouTube")
        vals.append(url)
    if not sets:
        raise HTTPException(status_code=400, detail="no fields to update")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE content_items SET {', '.join(sets)}, updated_at = now() WHERE id = %s RETURNING *",
                vals + [item_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="item not found")
            item = item_row(cur.description, row)
        conn.commit()
        return _out(item)
    finally:
        conn.close()


@router.delete("/items/{item_id}")
def delete_item(item_id: int):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM content_items WHERE id = %s RETURNING id", (item_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="item not found")
        conn.commit()
        return _out({"deleted": item_id})
    finally:
        conn.close()


@router.get("/settings")
def get_settings():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT weekdays, post_time, tz, per_week, niche, format, alert_ratio "
                        "FROM routine_settings WHERE id = 1")
            return _out(dict(zip([c.name for c in cur.description], cur.fetchone())))
    finally:
        conn.close()


@router.put("/settings")
def put_settings(body: Settings):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO routine_settings (id, weekdays, post_time, tz, per_week, niche, format, alert_ratio)
                   VALUES (1, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET weekdays = EXCLUDED.weekdays, post_time = EXCLUDED.post_time,
                       tz = EXCLUDED.tz, per_week = EXCLUDED.per_week, niche = EXCLUDED.niche,
                       format = EXCLUDED.format, alert_ratio = EXCLUDED.alert_ratio""",
                (body.weekdays, body.post_time, body.tz, body.per_week, body.niche, body.format, body.alert_ratio),
            )
        conn.commit()
        return _out(body.model_dump())
    finally:
        conn.close()
