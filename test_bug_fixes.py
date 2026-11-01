#!/usr/bin/env python3
"""
Test suite for pipeline bug fixes:
  FIX 3: voiceover schema mismatch (beats vs segments)
  FIX 1 (analytics): repo-relative YouTube token path
"""

import os, sys, json, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add package paths for imports
sys.path.insert(0, str(Path(__file__).parent))

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
        test_fix3_voiceover_schema()
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
