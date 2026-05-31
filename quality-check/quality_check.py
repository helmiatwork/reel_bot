# ═══════════════════════════════════════════════════════════════
# quality_check.py — Gap 2: AI quality verification
# Checks video quality before publishing using vision AI
# Scores: visual quality, content accuracy, brand safety
# ═══════════════════════════════════════════════════════════════

import os, json, base64, subprocess, httpx
from pathlib import Path

CLIPROXY_URL = os.getenv("CLIPROXY_URL", "http://cliproxy:8317/v1")
CLIPROXY_KEY = os.getenv("CLIPROXY_KEY", "local-proxy-key")
VISION_MODEL = "gemini/gemini-2.5-flash-lite"

QUALITY_SYSTEM_PROMPT = """
You are a video quality reviewer for a social media content automation system.

Your job: analyze video frames and return a structured quality assessment.

Check for:
1. VISUAL QUALITY — is the image clear, well-composed, not blurry or distorted?
2. CONTENT ACCURACY — does the visual match what the script says should be here?
3. CHARACTER CONSISTENCY — do characters/subjects look consistent across frames?
4. BRAND SAFETY — is there any inappropriate, offensive, or problematic content?
5. TECHNICAL — correct aspect ratio? No black bars? No watermarks?

Output JSON only:
{
  "overall_score": 0-100,
  "approved": true/false,
  "issues": ["issue1", "issue2"],
  "warnings": ["warning1"],
  "frame_scores": [
    {
      "timestamp": "00:00:05",
      "score": 0-100,
      "issues": []
    }
  ],
  "recommendation": "approve | review | reject",
  "rejection_reason": "only if rejected"
}

Approve if score >= 70. Review if 50-69. Reject if < 50 or brand safety issue.
"""


def extract_sample_frames(video_path: str, n_frames: int = 5) -> list:
    """Extract N evenly-spaced frames for quality checking."""
    out_dir = Path("/tmp/qc_frames")
    out_dir.mkdir(exist_ok=True)

    # Get video duration
    result = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path
    ], capture_output=True, text=True)

    try:
        duration = float(result.stdout.strip())
    except:
        duration = 60.0

    frames = []
    interval = duration / (n_frames + 1)

    for i in range(1, n_frames + 1):
        t = interval * i
        frame_path = str(out_dir / f"frame_{i:03d}.jpg")
        subprocess.run([
            "ffmpeg", "-ss", str(t), "-i", video_path,
            "-vframes", "1", "-q:v", "3",
            frame_path, "-y"
        ], capture_output=True)

        if Path(frame_path).exists():
            frames.append({
                "path": frame_path,
                "timestamp": f"{int(t//60):02d}:{int(t%60):02d}"
            })

    return frames


def check_frame(frame: dict, script_context: str) -> dict:
    """Run quality check on a single frame using vision AI."""
    img_b64 = base64.b64encode(Path(frame["path"]).read_bytes()).decode()

    response = httpx.post(
        f"{CLIPROXY_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {CLIPROXY_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": VISION_MODEL,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                        },
                        {
                            "type": "text",
                            "text": f"Timestamp: {frame['timestamp']}\nScript context: {script_context[:300]}\n\nAnalyze this frame. Return JSON only."
                        }
                    ]
                }
            ]
        },
        timeout=30
    )

    content = response.json()["choices"][0]["message"]["content"]
    content = content.strip().replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(content)
        result["timestamp"] = frame["timestamp"]
        return result
    except:
        return {
            "timestamp": frame["timestamp"],
            "score": 50,
            "issues": ["parse_error"],
            "raw": content
        }


def quality_check_video(
    video_path: str,
    script: dict,
    min_score: int = 70
) -> dict:
    """
    Full quality check on a video.
    Returns assessment with approve/review/reject recommendation.
    """
    print(f"[QC] Checking video quality: {video_path}")

    # Extract sample frames
    frames = extract_sample_frames(video_path, n_frames=5)
    if not frames:
        return {
            "approved": False,
            "overall_score": 0,
            "recommendation": "reject",
            "rejection_reason": "Could not extract frames from video"
        }

    script_context = f"Title: {script.get('title', '')}\nTone: {script.get('tone', '')}"

    # Check each frame
    frame_results = []
    for frame in frames:
        result = check_frame(frame, script_context)
        frame_results.append(result)
        score = result.get("overall_score", result.get("score", 50))
        print(f"[QC] Frame {result['timestamp']}: score={score} issues={result.get('issues', [])}")

    # Calculate overall score
    scores = [r.get("overall_score", r.get("score", 50)) for r in frame_results]
    overall = sum(scores) / len(scores) if scores else 0

    # Collect all issues
    all_issues = []
    for r in frame_results:
        all_issues.extend(r.get("issues", []))
    all_issues = list(set(all_issues))  # deduplicate

    # Brand safety check — any frame fails = full reject
    brand_safety_issues = [i for i in all_issues if any(
        kw in i.lower() for kw in ["inappropriate", "offensive", "adult", "violence", "hate"]
    )]

    if brand_safety_issues:
        recommendation = "reject"
    elif overall >= min_score:
        recommendation = "approve"
    elif overall >= 50:
        recommendation = "review"
    else:
        recommendation = "reject"

    result = {
        "video_path": video_path,
        "overall_score": round(overall, 1),
        "approved": recommendation == "approve",
        "recommendation": recommendation,
        "issues": all_issues,
        "frame_count": len(frame_results),
        "frame_results": frame_results,
        "min_score_required": min_score
    }

    if recommendation == "reject" and brand_safety_issues:
        result["rejection_reason"] = f"Brand safety: {brand_safety_issues}"
    elif recommendation == "reject":
        result["rejection_reason"] = f"Quality score {overall:.0f} below minimum {min_score}"

    print(f"\n[QC] Result: {recommendation.upper()} (score={overall:.0f})")
    if all_issues:
        print(f"[QC] Issues: {all_issues}")

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python quality_check.py <video.mp4> [script.json]")
        sys.exit(1)

    video = sys.argv[1]
    script = {}
    if len(sys.argv) > 2:
        with open(sys.argv[2]) as f:
            script = json.load(f)

    result = quality_check_video(video, script)
    print(json.dumps(result, indent=2))
