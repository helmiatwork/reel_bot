"""Channel mining: top public Shorts of a channel by views (yt-dlp, never cookies) -> ATM ideas."""
import json
import re
import subprocess
import time
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from . import blueprint as bpm
from .common import ytdlp_bin
from .items import insert_item

router = APIRouter()

_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_CHANNEL_PATH = re.compile(r"^/(@[\w.\-]+|channel/[\w\-]+|c/[\w.\-%]+|user/[\w.\-%]+)(/(shorts|videos|featured))?/?$")
_VIDEO_ID = re.compile(r"^[\w\-]{6,20}$")
_POLL_S = 5
_MAX_POLLS = 20 * 60 // _POLL_S  # give up on an analysis run after 20 min


class MineRequest(BaseModel):
    channel_url: str = Field(max_length=300)
    limit: int = Field(default=20, ge=1, le=50)


class ImportRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=10)
    niche: str = Field(default="", max_length=100)
    titles: dict[str, str] = {}  # optional url -> video title from the mine result
    auto_blueprint: bool = True


def channel_shorts_url(raw: str) -> str:
    """Canonical `<channel>/shorts` URL, or HTTPException 400 when it is not a YouTube channel URL."""
    p = urlparse(raw.strip())
    m = _CHANNEL_PATH.match(p.path) if p.scheme in ("http", "https") and p.hostname in _HOSTS else None
    if not m:
        raise HTTPException(status_code=400, detail="Isi URL channel YouTube, mis. https://www.youtube.com/@nama")
    return f"https://www.youtube.com/{m.group(1)}/shorts"


def _mine(shorts_url: str, limit: int) -> dict:
    scan = min(max(limit * 3, 60), 150)  # wider than `limit` so older hits still make "top by views"
    cmd = [ytdlp_bin(), "--ignore-config", "--no-cookies", "--flat-playlist", "-J", "--playlist-end", str(scan), "--", shorts_url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        data = json.loads(proc.stdout) if proc.returncode == 0 else None
    except Exception as exc:
        print(f"[atm] mine failed: {type(exc).__name__}")
        data = None
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Gagal mengambil channel. Cek URL atau coba lagi nanti.")
    videos = []
    for e in data.get("entries") or []:
        vid = e.get("id") if isinstance(e, dict) else None
        if isinstance(vid, str) and _VIDEO_ID.match(vid):
            views = e.get("view_count")
            videos.append({"video_id": vid, "url": f"https://www.youtube.com/shorts/{vid}",
                           "title": str(e.get("title") or ""), "views": views if isinstance(views, int) else 0})
    videos.sort(key=lambda v: v["views"], reverse=True)
    return {"channel": {"name": data.get("channel") or data.get("uploader") or data.get("title"),
                        "url": data.get("channel_url") or data.get("uploader_url") or shorts_url,
                        "followers": data.get("channel_follower_count")},
            "videos": videos[:limit]}


@router.post("/mine")
def mine_channel(body: MineRequest):
    return _mine(channel_shorts_url(body.channel_url), body.limit)


def _wait_run(run_id: str) -> Optional[str]:
    """'done' or 'error' when the analyze run ends, None after 20 min. Reads the state /analyze/claude/status serves."""
    import main
    for _ in range(_MAX_POLLS):
        try:
            status = (main._load_run(run_id) or {}).get("status")
        except (OSError, ValueError):  # run file caught mid-write: poll again
            status = None
        if status in ("done", "error"):
            return status
        time.sleep(_POLL_S)
    return None


def _start_blueprint(item_id: int) -> bool:
    """Mark the item building under the same lock and stale rule as POST /items/{id}/blueprint. False = do not start."""
    import main
    conn = main._db_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT reference_url, (blueprint_status = 'building' AND blueprint_started_at > now() - interval '15 minutes') "
                        "FROM content_items WHERE id = %s FOR UPDATE", (item_id,))
            row = cur.fetchone()
            if not row or row[1]:
                return False
            cur.execute("SELECT 1 FROM video_analysis WHERE youtube_url = %s LIMIT 1", (row[0],))
            if not cur.fetchone():  # same gate as the manual endpoint: no blueprint without an analysis
                return False
            cur.execute("UPDATE content_items SET blueprint_status = 'building', blueprint_error = NULL, "
                        "blueprint_started_at = now(), updated_at = now() WHERE id = %s", (item_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def _auto_blueprint(targets: list) -> None:
    """Background: (item_id, analyze run_id or None when already analysed), one at a time (the claude bridge is single-threaded)."""
    for item_id, run_id in targets:
        try:
            if run_id is not None and _wait_run(run_id) != "done":
                continue  # error or timeout: the item stays an idea
            if _start_blueprint(item_id):
                bpm._run_blueprint(item_id, None)
        except Exception as exc:  # one item's failure must not stop the rest
            print(f"[atm] auto blueprint for item {item_id} skipped: {type(exc).__name__}")


@router.post("/mine/import")
def import_mined(body: ImportRequest, background: BackgroundTasks):
    """One idea item per URL, then the existing Claude analysis of the reference starts in the background."""
    import main
    from .items import _conn, _out
    urls = []
    for u in body.urls:
        u = u.strip()
        main._validate_source_url(u)  # 400 on bad / SSRF url, before anything is written
        if main._detect_platform(u) != "youtube":
            raise HTTPException(status_code=400, detail="Hanya URL YouTube")
        urls.append(u)
    created = []
    conn = _conn()
    try:
        with conn.cursor() as cur:
            for u in urls:
                title = (body.titles.get(u) or "").strip()[:200] or f"Referensi {u.rsplit('/', 1)[-1][:40]}"
                created.append(insert_item(cur, title, body.niche, u))
        conn.commit()
    finally:
        conn.close()
    for item in created:
        try:
            r = main.analyze_claude_async(main.AnalyzeClaudeRequest(youtube_url=item["reference_url"]), background)
            item["analysis"] = {"run_id": r.get("run_id")} if "run_id" in r else {"already_exists": True}
        except HTTPException as exc:
            item["analysis"] = {"error": str(exc.detail)[:200]}
    targets = []
    for item in created:
        if "run_id" in item["analysis"]:
            targets.append((item["id"], item["analysis"]["run_id"]))
        elif item["analysis"].get("already_exists"):
            targets.append((item["id"], None))
    if body.auto_blueprint and targets:
        background.add_task(_auto_blueprint, targets)
    return _out({"items": created})
