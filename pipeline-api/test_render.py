"""
Tests for pipeline-api render pipeline helper functions.
Covers: EDL builder, video ID extractor, EDL structure validation.
"""

import pytest
from pathlib import Path
from uuid import uuid4

# Import from main.py
import sys
sys.path.insert(0, str(Path(__file__).parent))
from main import _build_clip_edl, _extract_video_id_from_youtube_url


class TestBuildClipEDL:
    """Unit tests for _build_clip_edl — no I/O required."""

    def test_edl_basic_structure(self):
        """EDL should have required keys."""
        clips = [{"start_sec": 10, "end_sec": 20, "title": "Test", "recommended": True}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), None)
        assert all(k in edl for k in ["title", "aspect", "fps", "clips", "captions"])

    def test_edl_aspect_and_fps(self):
        """EDL aspect should be 1080x1920 and fps should be 30."""
        clips = [{"start_sec": 0, "end_sec": 5}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), None)
        assert edl["aspect"] == "1080x1920"
        assert edl["fps"] == 30

    def test_edl_clip_in_out(self):
        """EDL clips should map start_sec→in, end_sec→out."""
        clips = [{"start_sec": 5.5, "end_sec": 15.3}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), None)
        assert edl["clips"][0]["in"] == 5
        assert edl["clips"][0]["out"] == 15
        assert "/video.mp4" in edl["clips"][0]["src"]

    def test_chosen_index_uses_specified_clip(self):
        """chosen_index should select that clip index."""
        clips = [
            {"start_sec": 0, "end_sec": 5, "title": "Clip 0"},
            {"start_sec": 10, "end_sec": 20, "title": "Clip 1"},
        ]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), chosen_index=1)
        assert edl["title"] == "Clip 1"
        assert edl["clips"][0]["in"] == 10

    def test_recommended_flag_overrides_index(self):
        """If any clip has recommended=True, it should be chosen."""
        clips = [
            {"start_sec": 0, "end_sec": 5, "title": "Clip 0"},
            {"start_sec": 10, "end_sec": 20, "title": "Clip 1", "recommended": True},
            {"start_sec": 30, "end_sec": 40, "title": "Clip 2"},
        ]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), chosen_index=0)
        assert edl["title"] == "Clip 1"

    def test_defaults_to_index_0(self):
        """If no chosen_index and no recommended, should use index 0."""
        clips = [{"start_sec": 0, "end_sec": 5, "title": "First"}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), None)
        assert edl["title"] == "First"

    def test_empty_clips_raises_error(self):
        """Empty clips array should raise ValueError."""
        with pytest.raises(ValueError):
            _build_clip_edl([], Path("/tmp/video.mp4"), None)

    def test_chosen_index_out_of_range_uses_fallback(self):
        """Out of range chosen_index should fall back to default logic."""
        clips = [{"start_sec": 0, "end_sec": 5, "title": "Only"}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), chosen_index=99)
        assert edl["title"] == "Only"

    def test_edl_captions_empty_by_default(self):
        """Captions array should be empty by default."""
        clips = [{"start_sec": 0, "end_sec": 5}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), None)
        assert edl["captions"] == []

    def test_edl_with_caption(self):
        """EDL should include caption if present."""
        clips = [{"start_sec": 5, "end_sec": 10, "caption": "Test caption"}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), None)
        assert len(edl["captions"]) == 1
        assert edl["captions"][0]["text"] == "Test caption"

    def test_edl_json_serializable(self):
        """EDL should be JSON serializable."""
        import json
        clips = [{"start_sec": 0, "end_sec": 5, "title": "Test"}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), None)
        # Should not raise
        json.dumps(edl)

    def test_edl_title_defaults_to_empty(self):
        """Title should default to empty string."""
        clips = [{"start_sec": 0, "end_sec": 5}]
        edl = _build_clip_edl(clips, Path("/tmp/video.mp4"), None)
        assert edl["title"] == ""


class TestExtractVideoID:
    """Unit tests for _extract_video_id_from_youtube_url."""

    def test_youtu_be_format(self):
        """Should extract from youtu.be/XXX format."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert _extract_video_id_from_youtube_url(url) == "dQw4w9WgXcQ"

    def test_youtube_com_watch_format(self):
        """Should extract from youtube.com/watch?v=XXX format."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert _extract_video_id_from_youtube_url(url) == "dQw4w9WgXcQ"

    def test_youtube_com_watch_with_params(self):
        """Should extract with extra query params."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s&list=PL123"
        assert _extract_video_id_from_youtube_url(url) == "dQw4w9WgXcQ"

    def test_fallback_hash_on_invalid(self):
        """Invalid URL should return 11-char hash fallback."""
        url = "https://example.com/invalid"
        video_id = _extract_video_id_from_youtube_url(url)
        assert len(video_id) == 11
        assert all(c in "0123456789abcdef" for c in video_id)


class TestRenderIDGeneration:
    """Tests for render ID format and uniqueness."""

    def test_render_id_format(self):
        """Render ID should be UUID format (36 chars)."""
        render_id = str(uuid4())
        assert len(render_id) == 36
        assert all(c in "0123456789abcdef-" for c in render_id.lower())

    def test_render_id_uniqueness(self):
        """Multiple render IDs should be unique."""
        render_ids = [str(uuid4()) for _ in range(100)]
        assert len(render_ids) == len(set(render_ids))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
