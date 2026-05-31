# ═══════════════════════════════════════════════════════════════
# pipeline.py — Complete automation pipeline orchestrator
# Connects all gaps: voiceover + quality check + publish + analytics
#
# Full flow:
#   1. Research (yt-dlp + video-analyzer) — existing
#   2. Script generation (OpenClaw) — existing
#   3. Visual generation (ArcReel) — existing
#   4. Voiceover (ElevenLabs) — NEW
#   5. Quality check (vision AI) — NEW
#   6. Human approval gate — NEW
#   7. Publish to platforms — NEW
#   8. Analytics collection — NEW
#   9. Feedback loop — NEW
# ═══════════════════════════════════════════════════════════════

import os, json, time, httpx
from pathlib import Path
from datetime import datetime

from voiceover.voiceover import generate_full_voiceover, merge_with_video
from quality_check.quality_check import quality_check_video
from publisher.publisher import publish_all
from analytics.analytics import (
    save_analytics, fetch_youtube_analytics,
    get_feedback_for_script
)

CLIPROXY_URL = os.getenv("CLIPROXY_URL", "http://cliproxy:8317/v1")
CLIPROXY_KEY = os.getenv("CLIPROXY_KEY", "local-proxy-key")
N8N_URL      = os.getenv("N8N_URL", "http://n8n:5678")
ARCREEL_URL  = os.getenv("ARCREEL_URL", "http://arcreel:1241")
ARCREEL_TOKEN = os.getenv("ARCREEL_TOKEN", "")


def notify_telegram(message: str, user_id: str = None):
    """Send notification via OpenClaw → Telegram."""
    try:
        httpx.post(
            f"{N8N_URL}/webhook/notify",
            json={"message": message, "user_id": user_id},
            timeout=5
        )
    except:
        print(f"[Notify] {message}")


def run_complete_pipeline(
    run_id: str,
    script: dict,               # from yt-pipeline + content writer agent
    arcreel_project_id: str,    # from ArcReel video generation
    user_id: str = None,
    platforms: list = None,
    voice: str = "male_neutral",
    bg_music_path: str = None,
    auto_publish: bool = False,  # False = human approval required
    credentials: dict = {}
) -> dict:
    """
    Complete the pipeline from ArcReel output to published video.
    Fills all 4 gaps: voiceover, quality check, publish, analytics.
    """
    platforms = platforms or ["youtube"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = Path(f"/output/{run_id}")
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f" Complete Pipeline — Run {run_id}")
    print(f" Title: {script.get('title', 'Untitled')}")
    print(f" Platforms: {platforms}")
    print(f"{'='*60}\n")

    result = {
        "run_id": run_id,
        "started_at": datetime.now().isoformat(),
        "steps": {}
    }

    # ── Step 4: Get video from ArcReel ────────────────────────
    notify_telegram(f"⏳ Step 4/8: Downloading video from ArcReel...", user_id)
    try:
        raw_video = _download_arcreel_video(arcreel_project_id, work_dir)
        result["steps"]["arcreel_download"] = {"status": "ok", "path": raw_video}
        print(f"[Pipeline] ArcReel video: {raw_video}")
    except Exception as e:
        result["steps"]["arcreel_download"] = {"status": "failed", "error": str(e)}
        notify_telegram(f"❌ Failed to download from ArcReel: {e}", user_id)
        return result

    # ── Step 5: Generate voiceover ────────────────────────────
    notify_telegram(f"🎙️ Step 5/8: Generating voiceover...", user_id)
    try:
        vo_dir = str(work_dir / "voiceover")
        voiceover_file = generate_full_voiceover(script, vo_dir, voice=voice)

        # Merge voiceover with video
        final_video = str(work_dir / "final_with_audio.mp4")
        merge_with_video(raw_video, voiceover_file, final_video, bg_music=bg_music_path)

        result["steps"]["voiceover"] = {"status": "ok", "path": final_video}
        notify_telegram(f"✅ Voiceover merged with video", user_id)
    except Exception as e:
        # Voiceover failed — use raw video without audio
        print(f"[Pipeline] Voiceover failed: {e} — using raw video")
        final_video = raw_video
        result["steps"]["voiceover"] = {"status": "failed", "error": str(e), "fallback": "raw_video"}

    # ── Step 6: Quality check ─────────────────────────────────
    notify_telegram(f"🔍 Step 6/8: Running quality check...", user_id)
    try:
        qc_result = quality_check_video(final_video, script, min_score=65)
        result["steps"]["quality_check"] = qc_result

        if qc_result["recommendation"] == "reject":
            notify_telegram(
                f"❌ Quality check FAILED (score={qc_result['overall_score']})\n"
                f"Reason: {qc_result.get('rejection_reason', 'Unknown')}\n"
                f"Please regenerate in ArcReel.", user_id
            )
            result["status"] = "rejected"
            return result

        elif qc_result["recommendation"] == "review":
            notify_telegram(
                f"⚠️ Quality check needs REVIEW (score={qc_result['overall_score']})\n"
                f"Issues: {', '.join(qc_result.get('issues', []))}\n"
                f"Video: /output/{run_id}/final_with_audio.mp4\n"
                f"Reply 'approve {run_id}' to publish anyway.", user_id
            )
            if not auto_publish:
                result["status"] = "awaiting_review"
                result["video_path"] = final_video
                return result

        else:
            notify_telegram(f"✅ Quality check PASSED (score={qc_result['overall_score']})", user_id)

    except Exception as e:
        print(f"[Pipeline] Quality check error: {e}")
        result["steps"]["quality_check"] = {"status": "error", "error": str(e)}
        if not auto_publish:
            notify_telegram(
                f"⚠️ Quality check error: {e}\n"
                f"Reply 'approve {run_id}' to publish anyway.", user_id
            )
            result["status"] = "awaiting_approval"
            result["video_path"] = final_video
            return result

    # ── Step 7: Human approval gate (unless auto_publish) ────
    if not auto_publish:
        notify_telegram(
            f"👀 Step 7/8: Ready for your approval!\n\n"
            f"📹 {script.get('title')}\n"
            f"📊 Quality score: {result['steps'].get('quality_check', {}).get('overall_score', 'N/A')}\n"
            f"📁 Video: /output/{run_id}/final_with_audio.mp4\n\n"
            f"Reply 'approve {run_id}' to publish to {', '.join(platforms)}", user_id
        )
        result["status"] = "awaiting_approval"
        result["video_path"] = final_video
        return result

    # ── Step 8: Publish ───────────────────────────────────────
    notify_telegram(f"📤 Step 8/8: Publishing to {', '.join(platforms)}...", user_id)
    try:
        # Upload video to public storage first (required for Instagram)
        public_url = _upload_to_public_storage(final_video, run_id)

        publish_results = publish_all(
            video_path=final_video,
            public_video_url=public_url,
            script=script,
            platforms=platforms,
            credentials=credentials
        )
        result["steps"]["publish"] = publish_results

        # Build success notification
        platform_links = []
        for platform, pr in publish_results.items():
            if "error" not in pr:
                if platform == "youtube":
                    platform_links.append(f"📺 YouTube: {pr.get('url', 'uploaded (private)')}")
                elif platform == "tiktok":
                    platform_links.append(f"🎵 TikTok: check inbox for draft")
                elif platform == "instagram":
                    platform_links.append(f"📸 Instagram: published as Reel")

        notify_telegram(
            f"✅ Video published!\n\n"
            f"📹 {script.get('title')}\n\n" +
            "\n".join(platform_links), user_id
        )

    except Exception as e:
        result["steps"]["publish"] = {"status": "failed", "error": str(e)}
        notify_telegram(f"❌ Publishing failed: {e}", user_id)

    # ── Step 9: Save for analytics ────────────────────────────
    save_analytics(run_id, {
        "title": script.get("title"),
        "topic": script.get("hook", ""),
        "platforms": platforms,
        "publish_results": result["steps"].get("publish", {}),
        "quality_score": result["steps"].get("quality_check", {}).get("overall_score"),
        "created_at": ts
    })

    result["status"] = "published"
    result["completed_at"] = datetime.now().isoformat()
    print(f"\n[Pipeline] Complete! Status: {result['status']}")
    return result


def approve_and_publish(run_id: str, user_id: str = None,
                         platforms: list = None, credentials: dict = {}):
    """
    Called when human approves a video that was pending review.
    Looks up the stored pipeline state and continues to publish step.
    """
    state_file = Path(f"/output/{run_id}/state.json")
    if not state_file.exists():
        notify_telegram(f"❌ Run {run_id} not found", user_id)
        return

    with open(state_file) as f:
        state = json.load(f)

    video_path = state.get("video_path")
    script = state.get("script", {})
    platforms = platforms or state.get("platforms", ["youtube"])

    if not video_path or not Path(video_path).exists():
        notify_telegram(f"❌ Video file not found for run {run_id}", user_id)
        return

    notify_telegram(f"👍 Approved! Publishing {script.get('title')}...", user_id)

    public_url = _upload_to_public_storage(video_path, run_id)
    results = publish_all(
        video_path=video_path,
        public_video_url=public_url,
        script=script,
        platforms=platforms,
        credentials=credentials
    )

    notify_telegram(
        f"✅ Published!\n" +
        "\n".join(f"- {p}: {r.get('url', 'done')}" for p, r in results.items()),
        user_id
    )
    return results


def _download_arcreel_video(project_id: str, work_dir: Path) -> str:
    """Download final video from ArcReel project."""
    output_path = str(work_dir / "arcreel_output.mp4")

    r = httpx.get(
        f"{ARCREEL_URL}/api/projects/{project_id}/export",
        headers={"Authorization": f"Bearer {ARCREEL_TOKEN}"},
        timeout=60
    )

    if r.status_code == 200 and r.headers.get("content-type", "").startswith("video"):
        with open(output_path, "wb") as f:
            f.write(r.content)
        return output_path

    data = r.json()
    video_url = data.get("video_url") or data.get("download_url")
    if not video_url:
        raise Exception(f"ArcReel export failed: {r.text}")

    video_r = httpx.get(video_url, timeout=120)
    with open(output_path, "wb") as f:
        f.write(video_r.content)
    return output_path


def _upload_to_public_storage(video_path: str, run_id: str) -> str:
    """
    Upload video to public storage for Instagram API.
    Configure one of: Supabase Storage, Cloudflare R2, AWS S3.
    Returns public URL.
    """
    storage_type = os.getenv("STORAGE_TYPE", "supabase")

    if storage_type == "supabase":
        return _upload_supabase(video_path, run_id)
    elif storage_type == "s3":
        return _upload_s3(video_path, run_id)
    else:
        # No storage configured — return local path as placeholder
        print("[Storage] No public storage configured — Instagram publish may fail")
        return f"http://{os.getenv('VPS_HOST', 'localhost')}:8000/videos/{run_id}.mp4"


def _upload_supabase(video_path: str, run_id: str) -> str:
    """Upload to Supabase Storage."""
    url  = os.getenv("SUPABASE_URL", "")
    key  = os.getenv("SUPABASE_KEY", "")
    bucket = os.getenv("SUPABASE_BUCKET", "videos")

    if not url or not key:
        raise Exception("SUPABASE_URL and SUPABASE_KEY required for public storage")

    filename = f"{run_id}.mp4"
    with open(video_path, "rb") as f:
        r = httpx.post(
            f"{url}/storage/v1/object/{bucket}/{filename}",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "video/mp4"},
            content=f.read(),
            timeout=300
        )
    if r.status_code not in (200, 201):
        raise Exception(f"Supabase upload failed: {r.text}")

    return f"{url}/storage/v1/object/public/{bucket}/{filename}"


def _upload_s3(video_path: str, run_id: str) -> str:
    """Upload to AWS S3 or Cloudflare R2."""
    import boto3
    s3 = boto3.client("s3",
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("S3_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET")
    )
    bucket = os.getenv("S3_BUCKET", "content-videos")
    key = f"videos/{run_id}.mp4"
    s3.upload_file(video_path, bucket, key, ExtraArgs={"ACL": "public-read"})
    return f"https://{bucket}.s3.amazonaws.com/{key}"


if __name__ == "__main__":
    print("Complete pipeline orchestrator ready.")
    print("Gaps covered: voiceover, quality check, publish, analytics")
