# ═══════════════════════════════════════════════════════════════
# voiceover.py — Gap 1: Text-to-Speech
# Converts script narration to audio using ElevenLabs
# Then merges audio + video using FFmpeg
# ═══════════════════════════════════════════════════════════════

import os, json, httpx, subprocess
from pathlib import Path

ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_URL = "https://api.elevenlabs.io/v1"

FREE_VOICES = {
    "male_neutral":   "pNInz6obpgDQGcFmaJgB",  # Adam
    "female_neutral": "EXAVITQu4vr4xnSDxMaL",  # Bella
    "male_warm":      "VR6AewLTigWG4xSOukaG",  # Arnold
    "female_warm":    "MF3mGyEYCl7XYWbV9V6O",  # Elli
}

def text_to_speech(text: str, output_path: str,
                   voice: str = "male_neutral",
                   model: str = "eleven_multilingual_v2") -> str:
    """Convert text to speech. Falls back to gTTS if no API key."""
    if not ELEVENLABS_KEY:
        return _gtts_fallback(text, output_path)

    voice_id = FREE_VOICES.get(voice, voice)
    print(f"[TTS] Generating {len(text)} chars → {voice} ({model})")

    r = httpx.post(
        f"{ELEVENLABS_URL}/text-to-speech/{voice_id}",
        headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
        json={
            "text": text[:4900],
            "model_id": model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "use_speaker_boost": True
            },
            "output_format": "mp3_44100_128"
        },
        timeout=120
    )
    if r.status_code != 200:
        raise Exception(f"ElevenLabs {r.status_code}: {r.text}")

    Path(output_path).write_bytes(r.content)
    print(f"[TTS] Saved: {output_path} ({Path(output_path).stat().st_size//1024}KB)")
    return output_path


def _gtts_fallback(text: str, output_path: str) -> str:
    """Free fallback: Google TTS via gTTS library."""
    from gtts import gTTS
    gTTS(text=text, lang="en").save(output_path)
    print(f"[TTS] gTTS fallback: {output_path}")
    return output_path


def generate_full_voiceover(script: dict, output_dir: str,
                             voice: str = "male_neutral") -> str:
    """
    Generate complete voiceover for a script.
    Produces individual segment files then concatenates.
    Returns path to final voiceover_full.mp3
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    parts = []
    if script.get("hook"):
        parts.append(("hook", script["hook"]))
    for i, seg in enumerate(script.get("segments", [])):
        if seg.get("narration"):
            parts.append((f"seg_{i}", seg["narration"]))
    if script.get("conclusion"):
        parts.append(("conclusion", script["conclusion"]))

    files = []
    for name, text in parts:
        fp = str(out / f"{name}.mp3")
        text_to_speech(text, fp, voice=voice)
        files.append(fp)

    # Concatenate with FFmpeg
    list_f = str(out / "concat_list.txt")
    with open(list_f, "w") as f:
        for fp in files:
            f.write(f"file '{fp}'\n")

    final = str(out / "voiceover_full.mp3")
    subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", list_f, "-c", "copy", final, "-y"
    ], check=True, capture_output=True)

    print(f"[TTS] Full voiceover ready: {final}")
    return final


def merge_with_video(video_path: str, audio_path: str,
                     output_path: str, bg_music: str = None,
                     music_vol: float = 0.12) -> str:
    """
    Merge voiceover + optional background music with video.
    video_path:  ArcReel output video
    audio_path:  ElevenLabs voiceover MP3
    bg_music:    optional royalty-free music file
    """
    print(f"[Merge] video + voiceover → {output_path}")

    if bg_music and Path(bg_music).exists():
        cmd = [
            "ffmpeg", "-i", video_path, "-i", audio_path, "-i", bg_music,
            "-filter_complex",
            f"[1:a]volume=1.0[v];[2:a]volume={music_vol}[m];[v][m]amix=inputs=2:duration=first[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            output_path, "-y"
        ]
    else:
        cmd = [
            "ffmpeg", "-i", video_path, "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            output_path, "-y"
        ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"FFmpeg failed: {r.stderr}")
    print(f"[Merge] Done: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python voiceover.py <script.json> <output_dir> [voice]")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        script = json.load(f)
    result = generate_full_voiceover(script, sys.argv[2],
                                      sys.argv[3] if len(sys.argv) > 3 else "male_neutral")
    print(f"Done: {result}")
