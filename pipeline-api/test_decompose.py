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
    _parse_grouping_json, _grouped_clips_to_segment_rows,
    _build_handle_search_query, _rank_candidates, _find_original_tier_a
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
    """_grouped_clips_to_segment_rows should convert clips to insert tuples with original finding."""
    clips = [
        {"clip_index": 1, "start_sec": 0.0, "end_sec": 5.0, "credit_handle": "@alice"},
        {"clip_index": 2, "start_sec": 5.0, "end_sec": 9.0, "credit_handle": None},
    ]
    source_id = 42

    tuples = _grouped_clips_to_segment_rows(clips, source_id)

    assert len(tuples) == 2
    # (source_id, clip_index, start_sec, end_sec, credit_handle, original_url, origin_status, confidence, segment_path)
    # Tuple structure: index 0=source_id, 1=clip_index, 2=start_sec, 3=end_sec, 4=credit_handle, 5=original_url, 6=origin_status, 7=confidence, 8=segment_path
    assert tuples[0][0] == 42  # source_id
    assert tuples[0][1] == 1   # clip_index
    assert tuples[0][4] == "@alice"  # credit_handle
    assert tuples[0][6] in ("found", "not_found")  # origin_status (could be found or not found depending on API)

    assert tuples[1][0] == 42  # source_id
    assert tuples[1][1] == 2   # clip_index
    assert tuples[1][4] is None  # credit_handle is None
    assert tuples[1][6] == "not_found"  # origin_status is always not_found for None credit


def test_grouped_clips_to_segment_rows_empty():
    """_grouped_clips_to_segment_rows should handle empty clips list."""
    tuples = _grouped_clips_to_segment_rows([], 42)
    assert tuples == []


@patch("main._find_original_tier_a", return_value={"original_url": None, "origin_status": "not_found", "confidence": 0.0, "method": "no_credit"})
def test_grouped_clips_to_segment_rows_origin_status_not_found(mock_find):
    """_grouped_clips_to_segment_rows should set origin_status='not_found' (Step 2a)."""
    clips = [
        {"clip_index": 1, "start_sec": 0.0, "end_sec": 5.0, "credit_handle": "@bob"},
    ]

    tuples = _grouped_clips_to_segment_rows(clips, 1)

    # origin_status is at index 6
    assert tuples[0][6] == "not_found"


# ── Tests for Step 2b: Tier A original-finder ──────────────────────────────────

def test_build_handle_search_query_with_at_symbol():
    """_build_handle_search_query should strip leading @ and whitespace."""
    assert _build_handle_search_query("@alice") == "alice"
    assert _build_handle_search_query(" @alice ") == "alice"
    assert _build_handle_search_query("@bob smith") == "bob smith"


def test_build_handle_search_query_without_at_symbol():
    """_build_handle_search_query should normalize handle without @."""
    assert _build_handle_search_query("charlie") == "charlie"
    assert _build_handle_search_query(" dave ") == "dave"


def test_build_handle_search_query_empty():
    """_build_handle_search_query should return empty string for empty/None input."""
    assert _build_handle_search_query("") == ""
    assert _build_handle_search_query(None) == ""
    assert _build_handle_search_query("   ") == ""


def test_rank_candidates_empty():
    """_rank_candidates should return (None, 0.0) for empty candidate list."""
    best, conf = _rank_candidates([], "@alice")
    assert best is None
    assert conf == 0.0


def test_rank_candidates_exact_match():
    """_rank_candidates should return 1.0 confidence for exact channel name match."""
    candidates = [
        {"channel_title": "alice", "title": "video 1", "video_id": "vid1"},
        {"channel_title": "bob", "title": "video 2", "video_id": "vid2"},
    ]
    best, conf = _rank_candidates(candidates, "@alice")
    assert best["video_id"] == "vid1"
    assert conf == 1.0


def test_rank_candidates_substring_match():
    """_rank_candidates should rank substring matches lower than exact matches."""
    candidates = [
        {"channel_title": "alice studio", "title": "video 1", "video_id": "vid1"},
        {"channel_title": "bob", "title": "alice in wonderland", "video_id": "vid2"},
    ]
    best, conf = _rank_candidates(candidates, "@alice")
    # "alice studio" contains "alice" → 0.85 (channel match)
    # "alice in wonderland" contains "alice" → 0.5 (title match)
    # Should pick "alice studio"
    assert best["video_id"] == "vid1"
    assert conf == 0.85


def test_rank_candidates_no_match():
    """_rank_candidates should return (None, 0.0) when no match found."""
    candidates = [
        {"channel_title": "bob", "title": "video 1", "video_id": "vid1"},
    ]
    best, conf = _rank_candidates(candidates, "@alice")
    assert best is None
    assert conf == 0.0


def test_find_original_tier_a_no_credit():
    """_find_original_tier_a should return not_found for empty credit_handle."""
    result = _find_original_tier_a("")
    assert result["origin_status"] == "not_found"
    assert result["confidence"] == 0.0
    assert result["method"] == "no_credit"
    assert result["original_url"] is None


def test_find_original_tier_a_no_credit_none():
    """_find_original_tier_a should return not_found for None credit_handle."""
    result = _find_original_tier_a(None)
    assert result["origin_status"] == "not_found"
    assert result["confidence"] == 0.0
    assert result["method"] == "no_credit"


def test_find_original_tier_a_whitespace_credit():
    """_find_original_tier_a should treat whitespace-only handle as no_credit."""
    result = _find_original_tier_a("   ")
    assert result["origin_status"] == "not_found"
    assert result["method"] == "no_credit"


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
        # Step 2b: Tier A original-finder tests
        test_build_handle_search_query_with_at_symbol,
        test_build_handle_search_query_without_at_symbol,
        test_build_handle_search_query_empty,
        test_rank_candidates_empty,
        test_rank_candidates_exact_match,
        test_rank_candidates_substring_match,
        test_rank_candidates_no_match,
        test_find_original_tier_a_no_credit,
        test_find_original_tier_a_no_credit_none,
        test_find_original_tier_a_whitespace_credit,
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
