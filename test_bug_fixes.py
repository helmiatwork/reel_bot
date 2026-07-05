#!/usr/bin/env python3
"""
Test suite for pipeline bug fixes:
  FIX 1: Docker-hostname defaults (localhost)
  FIX 2: gemini/ prefix in quality_check
  FIX 3: voiceover schema mismatch (beats vs segments)
  FIX 4: Instagram safety guard
"""

import os, sys, json, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add package paths for imports
sys.path.insert(0, str(Path(__file__).parent))

# ============================================================================
# FIX 1: Docker-hostname defaults test
# ============================================================================

def test_fix1_docker_hostnames():
    """Verify pipeline.py and pipeline-api/main.py use localhost defaults."""
    print("\n" + "="*70)
    print("FIX 1: Docker-hostname defaults → localhost")
    print("="*70)

    # pipeline.py
    with open("pipeline.py") as f:
        pipeline_content = f.read()

    assert 'http://localhost:18789' in pipeline_content, \
        "pipeline.py: OPENCLAW_URL default should be http://localhost:18789"
    assert 'http://localhost:1241' in pipeline_content, \
        "pipeline.py: ARCREEL_URL default should be http://localhost:1241"

    # Extract the OPENCLAW_URL and ARCREEL_URL lines
    for line in pipeline_content.split('\n'):
        if 'OPENCLAW_URL = os.getenv' in line:
            assert 'http://openclaw:' not in line, f"OPENCLAW_URL line should not have docker hostname: {line}"
        if 'ARCREEL_URL = os.getenv' in line:
            assert 'http://arcreel:' not in line, f"ARCREEL_URL line should not have docker hostname: {line}"
    print("  ✓ pipeline.py: OPENCLAW_URL default → http://localhost:18789")
    print("  ✓ pipeline.py: ARCREEL_URL default → http://localhost:1241")

    # pipeline-api/main.py
    with open("pipeline-api/main.py") as f:
        main_content = f.read()

    assert 'http://localhost:18789' in main_content, \
        "pipeline-api/main.py: OPENCLAW_URL default should be http://localhost:18789"

    for line in main_content.split('\n'):
        if 'OPENCLAW_URL = os.getenv' in line:
            assert 'http://openclaw:' not in line, f"OPENCLAW_URL line should not have docker hostname: {line}"
    print("  ✓ pipeline-api/main.py: OPENCLAW_URL default → http://localhost:18789")

    # Note: env override test skipped due to module import dependencies
    # The defaults are correctly set in the source code above
    print("✓ FIX 1 PASSED\n")


# ============================================================================
# FIX 2: quality_check model string test
# ============================================================================

def test_fix2_quality_check_model():
    """Verify quality_check.py VISION_MODEL has no gemini/ prefix."""
    print("\n" + "="*70)
    print("FIX 2: quality_check model string (remove gemini/ prefix)")
    print("="*70)

    with open("quality-check/quality_check.py") as f:
        qc_content = f.read()

    # Check model is unprefixed
    assert 'VISION_MODEL = "gemini-2.5-flash-lite"' in qc_content, \
        "VISION_MODEL should be 'gemini-2.5-flash-lite' without gemini/ prefix"
    assert 'VISION_MODEL = "gemini/gemini' not in qc_content, \
        "VISION_MODEL should NOT have gemini/ prefix"
    print('  ✓ VISION_MODEL = "gemini-2.5-flash-lite" (no prefix)')

    # Verify no gemini/ prefix anywhere in the file
    assert "gemini/gemini" not in qc_content.lower(), "File should not contain gemini/gemini"
    print("  ✓ No 'gemini/gemini' prefix anywhere")
    print("✓ FIX 2 PASSED\n")


# ============================================================================
# FIX 3: voiceover schema robustness test
# ============================================================================

def test_fix3_voiceover_schema():
    """Verify voiceover.py handles both beats (new) and segments (legacy) schemas."""
    print("\n" + "="*70)
    print("FIX 3: voiceover schema mismatch (beats vs segments)")
    print("="*70)

    # Import locally after sys.path is set
    sys.path.insert(0, str(Path(__file__).parent / "voiceover"))
    from voiceover import generate_full_voiceover

    with tempfile.TemporaryDirectory() as tmpdir:
        # Test 1: New beats schema (from yt_pipeline.py)
        beats_script = {
            "hook": "Did you know this amazing fact?",
            "beats": [
                {"t": "0-3s", "visual": "shot A", "vo": "First beat voiceover line", "caption": "Beat 1"},
                {"t": "3-6s", "visual": "shot B", "vo": "Second beat voiceover line", "caption": "Beat 2"},
                {"t": "6-9s", "visual": "shot C", "vo": "Third beat voiceover line", "caption": "Beat 3"},
            ],
            "conclusion": "Thanks for watching!"
        }

        # Mock text_to_speech to avoid ElevenLabs calls
        tts_calls = []
        def mock_tts(text, output_path, voice="male_neutral"):
            tts_calls.append(text)
            Path(output_path).write_text(f"mock audio for: {text}")
            return output_path

        def mock_subprocess_run(cmd, **kwargs):
            # Don't actually run ffmpeg, just pretend it worked
            if "voiceover_full.mp3" in str(cmd):
                Path(cmd[-2]).write_text("mock final audio")
            return MagicMock(returncode=0)

        with patch("voiceover.text_to_speech", side_effect=mock_tts), \
             patch("voiceover.subprocess.run", side_effect=mock_subprocess_run):
            result = generate_full_voiceover(beats_script, tmpdir, voice="male_neutral")

        # Should have called TTS 5 times: hook + 3 beats + conclusion
        assert len(tts_calls) == 5, f"Expected 5 TTS calls for beats schema, got {len(tts_calls)}"
        assert "Did you know" in tts_calls[0], "Hook not first"
        assert "First beat" in tts_calls[1], "Beat 0 not in order"
        assert "Second beat" in tts_calls[2], "Beat 1 not in order"
        assert "Third beat" in tts_calls[3], "Beat 2 not in order"
        assert "Thanks for watching" in tts_calls[4], "Conclusion not last"
        print("  ✓ Beats schema: hook + 3 beats + conclusion → 5 TTS calls in order")

        # Test 2: Legacy segments schema (old format)
        tts_calls.clear()
        legacy_script = {
            "hook": "Old hook line",
            "segments": [
                {"narration": "Segment one narration"},
                {"narration": "Segment two narration"},
                {"narration": "Segment three narration"},
            ],
            "conclusion": "Legacy conclusion"
        }

        with patch("voiceover.text_to_speech", side_effect=mock_tts), \
             patch("voiceover.subprocess.run", side_effect=mock_subprocess_run):
            result = generate_full_voiceover(legacy_script, tmpdir, voice="male_neutral")

        assert len(tts_calls) == 5, f"Expected 5 TTS calls for legacy schema, got {len(tts_calls)}"
        assert "Old hook" in tts_calls[0], "Hook not first"
        assert "Segment one" in tts_calls[1], "Seg 0 not in order"
        assert "Segment two" in tts_calls[2], "Seg 1 not in order"
        assert "Segment three" in tts_calls[3], "Seg 2 not in order"
        assert "Legacy conclusion" in tts_calls[4], "Conclusion not last"
        print("  ✓ Segments schema: hook + 3 segments + conclusion → 5 TTS calls in order")

        # Test 3: Empty/missing lines are skipped
        tts_calls.clear()
        sparse_script = {
            "hook": "Hook",
            "beats": [
                {"vo": ""},  # empty
                {"vo": "   "},  # whitespace only
                {"vo": "Valid line"},
            ],
            "conclusion": ""
        }

        with patch("voiceover.text_to_speech", side_effect=mock_tts), \
             patch("voiceover.subprocess.run", side_effect=mock_subprocess_run):
            result = generate_full_voiceover(sparse_script, tmpdir, voice="male_neutral")

        assert len(tts_calls) == 2, f"Expected 2 TTS calls (empty lines skipped), got {len(tts_calls)}"
        assert "Hook" in tts_calls[0], "Hook missing"
        assert "Valid line" in tts_calls[1], "Valid beat missing"
        print("  ✓ Empty/whitespace lines correctly skipped")

    print("✓ FIX 3 PASSED\n")


# ============================================================================
# FIX 4: Instagram safety guard test
# ============================================================================

def test_fix4_instagram_safety():
    """Verify Instagram publish is opt-in to prevent accidental public posts."""
    print("\n" + "="*70)
    print("FIX 4: Instagram accidental public publish (safety guard)")
    print("="*70)

    sys.path.insert(0, str(Path(__file__).parent / "publisher"))
    from publisher import publish_instagram
    from unittest.mock import patch, call

    # Check publisher.py source for the safety guard
    with open("publisher/publisher.py") as f:
        pub_content = f.read()

    # Verify allow_publish parameter exists
    assert "allow_publish" in pub_content, \
        "publisher.py should have allow_publish parameter in publish_instagram"
    assert "INSTAGRAM_ALLOW_PUBLISH" in pub_content, \
        "publisher.py should check INSTAGRAM_ALLOW_PUBLISH env variable"
    assert "prepared_not_published" in pub_content, \
        "publisher.py should return 'prepared_not_published' when safety guard blocks publish"
    assert "share_to_feed: bool = True" not in pub_content.split("def publish_instagram")[1].split("def ")[0] or \
           "share_to_feed = False" in pub_content.split("def publish_instagram")[1].split("def ")[0], \
        "share_to_feed default behavior should be guarded"

    print("  ✓ Safety guard parameter (allow_publish) present")
    print("  ✓ INSTAGRAM_ALLOW_PUBLISH env check present")
    print("  ✓ prepared_not_published status returned when blocked")

    # Simple behavioral check: mock the httpx calls
    with patch("publisher.httpx.post") as mock_post, \
         patch("publisher.httpx.get") as mock_get:

        # Default mock setup
        mock_post.return_value.json.return_value = {"id": "test_container"}
        mock_post.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {"status_code": "FINISHED"}

        # Test 1: Default (no publish allowed)
        os.environ.pop("INSTAGRAM_ALLOW_PUBLISH", None)
        result = publish_instagram(
            video_url="https://storage.com/video.mp4",
            caption="Test",
            ig_user_id="123456",
            access_token="token_xyz"
        )
        assert result["status"] == "prepared_not_published", \
            f"Default should not publish, got {result['status']}"
        assert "share_to_feed" not in result.get("reason", "") or "not published" in result.get("reason", ""), \
            "Should indicate publish was blocked"
        print("  ✓ Default behavior: publish blocked (safety guard active)")

        # Test 2: Env allows publish
        mock_post.reset_mock()
        mock_get.reset_mock()
        mock_post.return_value.json.return_value = {"id": "test_container2"}
        os.environ["INSTAGRAM_ALLOW_PUBLISH"] = "1"
        result = publish_instagram(
            video_url="https://storage.com/video.mp4",
            caption="Test",
            ig_user_id="123456",
            access_token="token_xyz"
        )
        assert result["status"] == "published", \
            f"With env=1 should publish, got {result['status']}"
        print("  ✓ With INSTAGRAM_ALLOW_PUBLISH=1: publish allowed")

    print("✓ FIX 4 PASSED\n")


# ============================================================================
# FIX 1 (analytics): YouTube token path test
# ============================================================================

def test_fix1_analytics_youtube_token():
    """Verify analytics.py uses repo-relative youtube_token.json path."""
    print("\n" + "="*70)
    print("FIX 1 (analytics): YouTube token path → repo-relative")
    print("="*70)

    with open("analytics/analytics.py") as f:
        analytics_content = f.read()

    # Check _REPO_ROOT is defined
    assert "_REPO_ROOT = Path(__file__).resolve().parent.parent" in analytics_content, \
        "analytics.py should define _REPO_ROOT"
    print("  ✓ _REPO_ROOT defined: Path(__file__).resolve().parent.parent")

    # Check youtube_token.json uses _REPO_ROOT
    assert 'str(_REPO_ROOT / "youtube_token.json")' in analytics_content, \
        "fetch_youtube_analytics should use _REPO_ROOT / 'youtube_token.json'"
    assert "/app/credentials/youtube_token.json" not in analytics_content, \
        "Old Docker path should be removed"
    print("  ✓ Token path: str(_REPO_ROOT / 'youtube_token.json')")

    # Verify old path is gone
    assert "/app/credentials" not in analytics_content, \
        "Old Docker credentials path should be completely removed"
    print("  ✓ Old Docker path /app/credentials removed")

    print("✓ FIX 1 (analytics) PASSED\n")


# ============================================================================
# Main test runner
# ============================================================================

if __name__ == "__main__":
    print("\n" + "▀"*70)
    print("PIPELINE BUG FIXES TEST SUITE")
    print("▀"*70)

    try:
        test_fix1_docker_hostnames()
        test_fix2_quality_check_model()
        test_fix3_voiceover_schema()
        test_fix4_instagram_safety()
        test_fix1_analytics_youtube_token()

        print("\n" + "▄"*70)
        print("ALL TESTS PASSED ✓")
        print("▄"*70 + "\n")
        sys.exit(0)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
