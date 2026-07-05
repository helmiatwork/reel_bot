"""
Tests for video decompose functions (_detect_scene_cuts, _scenes_to_shots, _split_segments, etc).

Runnable two ways:
  - pytest test_decompose.py
  - python3 test_decompose.py        (assert-based fallback, no pytest needed)

Tests cover:
1. _scenes_to_shots: pure logic, converts scene list to shot dicts
2. _build_video_segment_insert_tuples: pure logic, builds DB insert tuples
3. _parse_grouping_json: parse claude-vision grouping output
4. _grouped_clips_to_segment_rows: convert clips to DB insert tuples
5. Empty and edge cases
6. Video ID path safety guard
"""

from unittest.mock import MagicMock, patch

from main import (
    _scenes_to_shots, _build_video_segment_insert_tuples,
    _parse_grouping_json, _grouped_clips_to_segment_rows
)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_scenes_to_shots_basic():
    """_scenes_to_shots should convert tuple list to indexed shot dicts."""
    scene_list = [(0.0, 2.5), (2.5, 6.0), (6.0, 9.3)]
    shots = _scenes_to_shots(scene_list)

    assert len(shots) == 3
    assert shots[0] == {"index": 0, "start_sec": 0.0, "end_sec": 2.5}
    assert shots[1] == {"index": 1, "start_sec": 2.5, "end_sec": 6.0}
    assert shots[2] == {"index": 2, "start_sec": 6.0, "end_sec": 9.3}


def test_scenes_to_shots_empty():
    """_scenes_to_shots with empty list should return empty list."""
    shots = _scenes_to_shots([])
    assert shots == []


def test_scenes_to_shots_single():
    """_scenes_to_shots with one scene should return one shot."""
    scene_list = [(0.0, 10.0)]
    shots = _scenes_to_shots(scene_list)

    assert len(shots) == 1
    assert shots[0] == {"index": 0, "start_sec": 0.0, "end_sec": 10.0}


def test_scenes_to_shots_with_get_seconds_method():
    """_scenes_to_shots should handle scene objects with get_seconds() method."""
    mock_start = MagicMock()
    mock_start.get_seconds.return_value = 1.5

    mock_end = MagicMock()
    mock_end.get_seconds.return_value = 4.2

    scene_list = [(mock_start, mock_end)]
    shots = _scenes_to_shots(scene_list)

    assert len(shots) == 1
    assert shots[0]["index"] == 0
    assert shots[0]["start_sec"] == 1.5
    assert shots[0]["end_sec"] == 4.2


def test_build_video_segment_insert_tuples_basic():
    """_build_video_segment_insert_tuples should create insert tuples with defaults."""
    shots = [
        {"index": 0, "start_sec": 0.0, "end_sec": 2.5},
        {"index": 1, "start_sec": 2.5, "end_sec": 6.0},
    ]
    source_id = 42

    tuples = _build_video_segment_insert_tuples(shots, source_id)

    assert len(tuples) == 2

    # First tuple: (source_id, clip_index, start_sec, end_sec, credit_handle, original_url, origin_status, confidence, segment_path)
    assert tuples[0] == (42, 0, 0.0, 2.5, None, None, "pending", None, None)
    assert tuples[1] == (42, 1, 2.5, 6.0, None, None, "pending", None, None)


def test_build_video_segment_insert_tuples_with_segment_path():
    """_build_video_segment_insert_tuples should include segment_path when present."""
    shots = [
        {
            "index": 0,
            "start_sec": 0.0,
            "end_sec": 2.5,
            "segment_path": "/data/segments/abc123/seg_00.mp4",
        },
    ]
    source_id = 99

    tuples = _build_video_segment_insert_tuples(shots, source_id)

    assert len(tuples) == 1
    assert tuples[0][8] == "/data/segments/abc123/seg_00.mp4"  # segment_path is last field


def test_build_video_segment_insert_tuples_empty():
    """_build_video_segment_insert_tuples with empty shots should return empty list."""
    tuples = _build_video_segment_insert_tuples([], 42)
    assert tuples == []


def test_build_video_segment_insert_tuples_origin_status_pending():
    """All tuples should have origin_status='pending' for Step 1 (no original-finder yet)."""
    shots = [
        {"index": 0, "start_sec": 0.0, "end_sec": 1.0},
        {"index": 1, "start_sec": 1.0, "end_sec": 2.0},
    ]

    tuples = _build_video_segment_insert_tuples(shots, 1)

    # origin_status is at index 6
    assert all(tup[6] == "pending" for tup in tuples)


def test_video_id_path_safety_regex():
    """
    Video ID should only contain [A-Za-z0-9_-] to prevent directory traversal.
    This test documents the regex used in the codebase.
    """
    import re

    # Valid IDs (used in actual paths)
    valid_ids = ["abc123", "ABC-123_def", "test_video-id"]
    for vid in valid_ids:
        assert re.match(r"^[A-Za-z0-9_-]+$", vid), f"Valid ID {vid} rejected"

    # Invalid IDs (should be rejected before any path operation)
    invalid_ids = ["../etc/passwd", "a/b/c", "a.b", "a b", "a@b"]
    for vid in invalid_ids:
        assert not re.match(r"^[A-Za-z0-9_-]+$", vid), f"Invalid ID {vid} accepted"



# New test functions for Step 2a

def test_parse_grouping_json_well_formed():
    """_parse_grouping_json should parse well-formed JSON with clips array."""
    raw_text = '{"clips":[{"shot_indices":[0,1],"credit_handle":"@alice"}]}'
    shots = [
        {"index": 0, "start_sec": 0.0, "end_sec": 2.5},
        {"index": 1, "start_sec": 2.5, "end_sec": 5.0},
        {"index": 2, "start_sec": 5.0, "end_sec": 9.0},
    ]
    
    clips = _parse_grouping_json(raw_text, shots)
    
    assert len(clips) == 1
    assert clips[0]["clip_index"] == 1
    assert clips[0]["start_sec"] == 0.0
    assert clips[0]["end_sec"] == 5.0
    assert clips[0]["credit_handle"] == "@alice"
    assert clips[0]["shot_indices"] == [0, 1]


def test_parse_grouping_json_multiple_clips():
    """_parse_grouping_json should handle multiple clips."""
    raw_text = '{"clips":[{"shot_indices":[0,1],"credit_handle":"@a"},{"shot_indices":[2],"credit_handle":"@b"}]}'
    shots = [
        {"index": 0, "start_sec": 0.0, "end_sec": 2.5},
        {"index": 1, "start_sec": 2.5, "end_sec": 5.0},
        {"index": 2, "start_sec": 5.0, "end_sec": 9.0},
    ]
    
    clips = _parse_grouping_json(raw_text, shots)
    
    assert len(clips) == 2
    assert clips[0]["clip_index"] == 1
    assert clips[0]["start_sec"] == 0.0
    assert clips[0]["end_sec"] == 5.0
    assert clips[1]["clip_index"] == 2
    assert clips[1]["start_sec"] == 5.0
    assert clips[1]["end_sec"] == 9.0


def test_parse_grouping_json_with_markdown_fences():
    """_parse_grouping_json should strip ```json fences."""
    raw_text = '```json\n{"clips":[{"shot_indices":[0],"credit_handle":null}]}\n```'
    shots = [
        {"index": 0, "start_sec": 0.0, "end_sec": 2.5},
    ]
    
    clips = _parse_grouping_json(raw_text, shots)
    
    assert len(clips) == 1
    assert clips[0]["clip_index"] == 1
    assert clips[0]["credit_handle"] is None


def test_parse_grouping_json_empty_text():
    """_parse_grouping_json should return [] on parse error."""
    clips = _parse_grouping_json("garbage", [])
    assert clips == []


def test_parse_grouping_json_no_clips_key():
    """_parse_grouping_json should return [] if 'clips' is missing."""
    raw_text = '{"error":"no clips"}'
    clips = _parse_grouping_json(raw_text, [])
    assert clips == []


def test_grouped_clips_to_segment_rows_basic():
    """_grouped_clips_to_segment_rows should convert clips to insert tuples."""
    clips = [
        {"clip_index": 1, "start_sec": 0.0, "end_sec": 5.0, "credit_handle": "@alice"},
        {"clip_index": 2, "start_sec": 5.0, "end_sec": 9.0, "credit_handle": None},
    ]
    source_id = 42
    
    tuples = _grouped_clips_to_segment_rows(clips, source_id)
    
    assert len(tuples) == 2
    # (source_id, clip_index, start_sec, end_sec, credit_handle, original_url, origin_status, confidence, segment_path)
    assert tuples[0] == (42, 1, 0.0, 5.0, "@alice", None, "not_found", None, None)
    assert tuples[1] == (42, 2, 5.0, 9.0, None, None, "not_found", None, None)


def test_grouped_clips_to_segment_rows_empty():
    """_grouped_clips_to_segment_rows should handle empty clips list."""
    tuples = _grouped_clips_to_segment_rows([], 42)
    assert tuples == []


def test_grouped_clips_to_segment_rows_origin_status_not_found():
    """_grouped_clips_to_segment_rows should set origin_status='not_found' (Step 2a)."""
    clips = [
        {"clip_index": 1, "start_sec": 0.0, "end_sec": 5.0, "credit_handle": "@bob"},
    ]
    
    tuples = _grouped_clips_to_segment_rows(clips, 1)
    
    # origin_status is at index 6
    assert tuples[0][6] == "not_found"


# ── Main runner (fallback for no pytest) ────────────────────────────────────────

def __main__():
    """Run all tests with assert-based runner (no pytest required)."""
    tests = [
        test_scenes_to_shots_basic,
        test_scenes_to_shots_empty,
        test_scenes_to_shots_single,
        test_scenes_to_shots_with_get_seconds_method,
        test_build_video_segment_insert_tuples_basic,
        test_build_video_segment_insert_tuples_with_segment_path,
        test_build_video_segment_insert_tuples_empty,
        test_build_video_segment_insert_tuples_origin_status_pending,
        test_video_id_path_safety_regex,
        test_parse_grouping_json_well_formed,
        test_parse_grouping_json_multiple_clips,
        test_parse_grouping_json_with_markdown_fences,
        test_parse_grouping_json_empty_text,
        test_parse_grouping_json_no_clips_key,
        test_grouped_clips_to_segment_rows_basic,
        test_grouped_clips_to_segment_rows_empty,
        test_grouped_clips_to_segment_rows_origin_status_not_found,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            print(f"✓ {test_func.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(__main__())
