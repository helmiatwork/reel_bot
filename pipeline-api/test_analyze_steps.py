#!/usr/bin/env python3
"""
Unit tests for _build_analyze_steps helper.
No pytest import — assert-based + __main__ idiom.
"""


def _build_analyze_steps(cached: bool, video_id: str = "", model: str = "", niche_done: bool = False) -> list[str]:
    """
    Build a list of human-readable process steps for analyze/claude response.

    Args:
        cached: True if served from cache, False if fresh analysis
        video_id: extracted video ID (used only for fresh path)
        model: Claude model name (used only for fresh path)
        niche_done: True if niche inference ran (used only for fresh path)

    Returns:
        list[str]: ordered step descriptions
    """
    steps = []

    if cached:
        # Cached path
        steps.append("⚡ Ambil dari cache DB (video_analysis) — tanpa download, tanpa biaya")
        steps.append("🗄️ Backfill creator/source/song (dedup)")
    else:
        # Fresh path
        steps.append("📥 Download video + ekstrak 20 keyframe (yt-dlp + ffmpeg)")
        steps.append("💾 Simpan frame ke data/frames/" + video_id)
        steps.append(f"👁️ Analisa visual frame (Claude vision — {model})")
        if niche_done:
            steps.append("🏷️ Infer niche konten (Claude)")
        steps.append("🗄️ Simpan hasil ke DB (video_analysis) + creator/source/song")

    return steps


def test_cached_path():
    """Test cached path returns 2 steps."""
    steps = _build_analyze_steps(cached=True)
    assert len(steps) == 2
    assert "cache" in steps[0]
    assert "Download" not in " ".join(steps)
    print("✓ test_cached_path passed")


def test_fresh_path_with_niche():
    """Test fresh path with niche inference includes 5 steps."""
    steps = _build_analyze_steps(cached=False, video_id="abc123", model="claude-sonnet-4-6", niche_done=True)
    assert len(steps) == 5
    assert "Download" in steps[0]
    assert "abc123" in steps[1]
    assert "claude-sonnet-4-6" in steps[2]
    assert "Infer niche" in steps[3]
    print("✓ test_fresh_path_with_niche passed")


def test_fresh_path_without_niche():
    """Test fresh path without niche inference includes 4 steps."""
    steps = _build_analyze_steps(cached=False, video_id="xyz789", model="claude-opus", niche_done=False)
    assert len(steps) == 4
    assert "Download" in steps[0]
    assert "xyz789" in steps[1]
    assert "claude-opus" in steps[2]
    assert "Infer niche" not in " ".join(steps)
    print("✓ test_fresh_path_without_niche passed")


if __name__ == "__main__":
    test_cached_path()
    test_fresh_path_with_niche()
    test_fresh_path_without_niche()
    print("\nAll tests passed!")
