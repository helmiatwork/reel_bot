# pipeline-api/main.py
# FastAPI service exposing all pipeline gaps as REST endpoints

import os, sys, json
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List

sys.path.insert(0, "/app")

app = FastAPI(title="Content Pipeline API", version="1.0")

DASHBOARD = Path("/app/dashboard/index.html")


class VoiceoverRequest(BaseModel):
    script: dict
    output_dir: str
    voice: str = "male_neutral"


class MergeRequest(BaseModel):
    video_path: str
    audio_path: str
    output_path: str
    bg_music: Optional[str] = None
    music_vol: float = 0.12


class QualityCheckRequest(BaseModel):
    video_path: str
    script: dict
    min_score: int = 65


class PublishRequest(BaseModel):
    video_path: str
    public_video_url: str
    script: dict
    platforms: List[str]


class AnalyticsSaveRequest(BaseModel):
    run_id: str
    data: dict


class PipelineRequest(BaseModel):
    run_id: str
    script: dict
    arcreel_project_id: str
    user_id: Optional[str] = None
    platforms: List[str] = ["youtube"]
    voice: str = "male_neutral"
    bg_music_path: Optional[str] = None
    auto_publish: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "service": "pipeline-api"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    """Serve the Reelbot dashboard UI."""
    if DASHBOARD.exists():
        return FileResponse(str(DASHBOARD))
    return HTMLResponse("<h2>Reelbot API running</h2><p><a href='/docs'>API docs</a></p>")


@app.post("/voiceover/generate")
def generate_voiceover(req: VoiceoverRequest):
    """Gap 1: Generate voiceover from script using ElevenLabs."""
    from voiceover.voiceover import generate_full_voiceover
    try:
        result = generate_full_voiceover(req.script, req.output_dir, req.voice)
        return {"status": "ok", "audio_path": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/voiceover/merge")
def merge_audio_video(req: MergeRequest):
    """Gap 1: Merge voiceover audio with video file."""
    from voiceover.voiceover import merge_with_video
    try:
        result = merge_with_video(
            req.video_path, req.audio_path, req.output_path,
            bg_music=req.bg_music, music_vol=req.music_vol
        )
        return {"status": "ok", "video_path": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/quality/check")
def quality_check(req: QualityCheckRequest):
    """Gap 2: Run AI quality check on video."""
    from quality_check.quality_check import quality_check_video
    try:
        result = quality_check_video(req.video_path, req.script, req.min_score)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/publish")
def publish(req: PublishRequest):
    """Gap 3: Publish video to platforms."""
    from publisher.publisher import publish_all
    creds = {
        "tiktok_token": os.getenv("TIKTOK_ACCESS_TOKEN", ""),
        "ig_user_id": os.getenv("IG_USER_ID", ""),
        "ig_token": os.getenv("IG_ACCESS_TOKEN", "")
    }
    try:
        results = publish_all(
            req.video_path, req.public_video_url,
            req.script, req.platforms, creds
        )
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analytics/save")
def save_analytics(req: AnalyticsSaveRequest):
    """Gap 4: Save analytics record."""
    from analytics.analytics import save_analytics as _save
    try:
        _save(req.run_id, req.data)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/insights")
def get_insights():
    """Gap 4: Get AI insights from recent analytics."""
    from analytics.analytics import load_recent_analytics, generate_insights
    try:
        recent = load_recent_analytics(limit=20)
        insights = generate_insights(recent) if recent else {}
        return {"status": "ok", "count": len(recent), "insights": insights}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/feedback")
def get_feedback(topic: str = ""):
    """Gap 4: Get feedback string to inject into next script."""
    from analytics.analytics import get_feedback_for_script
    try:
        feedback = get_feedback_for_script(topic)
        return {"status": "ok", "feedback": feedback}
    except Exception as e:
        return {"status": "ok", "feedback": ""}


@app.post("/pipeline/run")
def run_pipeline(req: PipelineRequest, bg: BackgroundTasks):
    """Run complete pipeline in background."""
    from pipeline import run_complete_pipeline
    def _run():
        run_complete_pipeline(
            run_id=req.run_id,
            script=req.script,
            arcreel_project_id=req.arcreel_project_id,
            user_id=req.user_id,
            platforms=req.platforms,
            voice=req.voice,
            bg_music_path=req.bg_music_path,
            auto_publish=req.auto_publish
        )
    bg.add_task(_run)
    return {"status": "started", "run_id": req.run_id}


# ── Analytics dashboard endpoints ────────────────────────────

ANALYTICS_DB_PATH = os.getenv("ANALYTICS_DB", "/output/analytics.json")

@app.get("/analytics/data")
def analytics_data():
    """Return all analytics as JSON for the dashboard."""
    db_path = Path(ANALYTICS_DB_PATH)
    if not db_path.exists():
        return JSONResponse({"records": [], "total": 0})
    try:
        db = json.loads(db_path.read_text())
        records = list(db.values())
        records.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return JSONResponse({"records": records, "total": len(records)})
    except Exception as e:
        return JSONResponse({"records": [], "total": 0, "error": str(e)})

@app.get("/analytics/summary")
def analytics_summary():
    """Return summary stats for dashboard cards."""
    db_path = Path(ANALYTICS_DB_PATH)
    if not db_path.exists():
        return JSONResponse({"total_videos": 0, "platforms": {}, "avg_quality": 0})
    try:
        db = json.loads(db_path.read_text())
        records = list(db.values())
        platforms = {}
        quality_scores = []
        for r in records:
            for p in r.get("platforms", []):
                platforms[p] = platforms.get(p, 0) + 1
            if r.get("qc_score"):
                quality_scores.append(r["qc_score"])
        return JSONResponse({
            "total_videos": len(records),
            "platforms": platforms,
            "avg_quality": round(sum(quality_scores)/len(quality_scores), 1) if quality_scores else 0,
            "recent_titles": [r.get("title","") for r in records[:5]]
        })
    except Exception as e:
        return JSONResponse({"total_videos": 0, "error": str(e)})


# ── Research Pipeline endpoints ──────────────────────────────

class ResearchRequest(BaseModel):
    topic: str
    channel_url: Optional[str] = None
    max_videos: int = 20


def _runs_path(run_id: str) -> Path:
    return Path(f"/output/research_runs/{run_id}.json")

def _save_run(run_id: str, data: dict):
    p = _runs_path(run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))

def _load_run(run_id: str):
    p = _runs_path(run_id)
    return json.loads(p.read_text()) if p.exists() else None


@app.post("/pipeline/research")
def start_research(req: ResearchRequest, bg: BackgroundTasks):
    """Start yt-pipeline research job in background."""
    import uuid, subprocess
    from urllib.parse import urlparse

    if req.topic.startswith("-"):
        raise HTTPException(status_code=400, detail="Invalid topic")
    if req.channel_url:
        parsed = urlparse(req.channel_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=400, detail="channel_url must be an http(s) URL")

    run_id = str(uuid.uuid4())
    _save_run(run_id, {"status": "running", "result": None, "error": None})

    def _run():
        try:
            cmd = [
                "python", "-m", "yt_pipeline.main",
                f"--topic={req.topic}",
                f"--max-videos={req.max_videos}",
            ]
            if req.channel_url:
                cmd.append(f"--channel={req.channel_url}")
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if proc.returncode == 0:
                import json as _json
                run_data = _load_run(run_id) or {}
                run_data["result"] = _json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {"raw": proc.stdout}
                run_data["status"] = "done"
                _save_run(run_id, run_data)
            else:
                run_data = _load_run(run_id) or {}
                run_data["error"] = proc.stderr
                run_data["status"] = "error"
                _save_run(run_id, run_data)
        except Exception as e:
            run_data = _load_run(run_id) or {}
            run_data["error"] = str(e)
            run_data["status"] = "error"
            _save_run(run_id, run_data)

    bg.add_task(_run)
    return {"status": "started", "run_id": run_id}


@app.get("/pipeline/research/status/{run_id}")
def research_status(run_id: str):
    run = _load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "status": run["status"]}


@app.get("/pipeline/research/result/{run_id}")
def research_result(run_id: str):
    run = _load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] != "done":
        raise HTTPException(status_code=400, detail=f"Run status: {run['status']}")
    return {"run_id": run_id, "result": run["result"]}
