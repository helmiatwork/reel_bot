"""Channel mining: top public Shorts of a channel by views (yt-dlp, never cookies) -> ATM ideas."""
import json
import re
import subprocess
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from .common import ytdlp_bin
from .items import insert_item

router = APIRouter()

_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_CHANNEL_PATH = re.compile(r"^/(@[\w.\-]+|channel/[\w\-]+|c/[\w.\-%]+|user/[\w.\-%]+)(/(shorts|videos|featured))?/?$")
_VIDEO_ID = re.compile(r"^[\w\-]{6,20}$")


class MineRequest(BaseModel):
    channel_url: str = Field(max_length=300)
    limit: int = Field(default=20, ge=1, le=50)


class ImportRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=10)
    niche: str = Field(default="", max_length=100)
    titles: dict[str, str] = {}  # optional url -> video title from the mine result


def channel_shorts_url(raw: str) -> str:
    """Canonical `<channel>/shorts` URL, or HTTPException 400 when it is not a YouTube channel URL."""
    p = urlparse(raw.strip())
    m = _CHANNEL_PATH.match(p.path) if p.scheme in ("http", "https") and p.hostname in _HOSTS else None
    if not m:
        raise HTTPException(status_code=400, detail="Isi URL channel YouTube, mis. https://www.youtube.com/@nama")
    return f"https://www.youtube.com/{m.group(1)}/shorts"


def _mine(shorts_url: str, limit: int) -> dict:
    cmd = [ytdlp_bin(), "--no-cookies", "--flat-playlist", "-J", "--playlist-end", str(limit * 2), "--", shorts_url]
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
    return _out({"items": created})
