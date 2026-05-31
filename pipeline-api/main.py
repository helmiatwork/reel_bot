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


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    if DASHBOARD.exists():
        return HTMLResponse(DASHBOARD.read_text())
    return HTMLResponse("<h1>Pipeline API</h1><p>Dashboard not built.</p>")


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


_research_runs: dict = {}


@app.post("/pipeline/research")
def start_research(req: ResearchRequest, bg: BackgroundTasks):
    """Start yt-pipeline research job in background."""
    import uuid, subprocess, threading
    run_id = str(uuid.uuid4())[:8]
    _research_runs[run_id] = {"status": "running", "result": None, "error": None}

    def _run():
        try:
            cmd = [
                "python", "-m", "yt_pipeline.main",
                "--topic", req.topic,
                "--max-videos", str(req.max_videos),
            ]
            if req.channel_url:
                cmd += ["--channel", req.channel_url]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if proc.returncode == 0:
                import json as _json
                _research_runs[run_id]["result"] = _json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {"raw": proc.stdout}
                _research_runs[run_id]["status"] = "done"
            else:
                _research_runs[run_id]["error"] = proc.stderr
                _research_runs[run_id]["status"] = "error"
        except Exception as e:
            _research_runs[run_id]["error"] = str(e)
            _research_runs[run_id]["status"] = "error"

    bg.add_task(_run)
    return {"status": "started", "run_id": run_id}


@app.get("/pipeline/research/status/{run_id}")
def research_status(run_id: str):
    if run_id not in _research_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "status": _research_runs[run_id]["status"]}


@app.get("/pipeline/research/result/{run_id}")
def research_result(run_id: str):
    if run_id not in _research_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    run = _research_runs[run_id]
    if run["status"] != "done":
        raise HTTPException(status_code=400, detail=f"Run status: {run['status']}")
    return {"run_id": run_id, "result": run["result"]}
