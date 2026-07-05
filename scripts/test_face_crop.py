#!/usr/bin/env python3
"""
Unit tests for face_crop.compute_crop_xy (pure math, no video I/O or cv2).

Runnable as:
  python3 scripts/test_face_crop.py
  pytest scripts/test_face_crop.py
"""

from face_crop import compute_crop_xy


def test_landscape_to_portrait_centered_face():
    """Landscape 1920x1080 → portrait 1080x1920, face at center (fx=0.5)."""
    # Scale = max(1080/1920, 1920/1080) = max(0.5625, 1.7778) = 1.7778
    # sw = round(1920 * 1.7778) = 3413
    # sh = round(1080 * 1.7778) = 1920
    # With face at fx=0.5: x = round(0.5*3413 - 1080/2) = round(1706.5 - 540) = 1167
    # Clamp to [0, 3413-1080] = [0, 2333] → 1167, then force even → 1166
    x, y = compute_crop_xy(1920, 1080, [(0.5, 0.5)], 1080, 1920)
    assert x == 1166, f"expected x≈1166 (center-ish), got {x}"
    assert y == 0, f"expected y=0, got {y}"
    # Both x and y must be even for yuv420.
    assert x % 2 == 0 and y % 2 == 0, f"x={x}, y={y} not both even"


def test_landscape_to_portrait_face_left():
    """Landscape 1920x1080 → portrait, face off-center left (fx=0.25)."""
    x, y = compute_crop_xy(1920, 1080, [(0.25, 0.5)], 1080, 1920)
    # With fx=0.25, x should be smaller (crop window shifts left).
    # Centered x at fx=0.5 was ~1166; at fx=0.25 should be ~583 (roughly half).
    assert x < 1166, f"expected x < 1166 for left face, got {x}"
    assert x % 2 == 0, f"x={x} not even"
    assert y % 2 == 0, f"y={y} not even"


def test_landscape_to_portrait_face_right():
    """Landscape 1920x1080 → portrait, face off-center right (fx=0.95)."""
    x, y = compute_crop_xy(1920, 1080, [(0.95, 0.5)], 1080, 1920)
    # With fx=0.95, x should be clamped to sw - W.
    # sw = 3413, W = 1080, so max x = 2333.
    assert x >= 2330, f"expected x clamped high, got {x}"
    assert x % 2 == 0, f"x={x} not even"
    assert y % 2 == 0, f"y={y} not even"


def test_no_faces_defaults_to_centered():
    """Empty face_centers list → centered crop (fx=fy=0.5)."""
    x1, y1 = compute_crop_xy(1920, 1080, [(0.5, 0.5)], 1080, 1920)
    x2, y2 = compute_crop_xy(1920, 1080, [], 1080, 1920)
    # Both should produce the same centered crop.
    assert x1 == x2, f"face center should match empty (centered): {x1} vs {x2}"
    assert y1 == y2, f"face center should match empty (centered): {y1} vs {y2}"


def test_portrait_source_to_portrait_target_y_response():
    """Portrait source 1080x1920 → portrait target 1080x1920, face shifts y."""
    # scale = max(1080/1080, 1920/1920) = 1.0
    # sw = 1080, sh = 1920 (no upscaling)
    # With fy=0.25: y = round(0.25*1920 - 1920/2) = round(480 - 960) = -480
    # Clamped to [0, 1920-1920] = [0, 0] → y = 0
    x, y = compute_crop_xy(1080, 1920, [(0.5, 0.25)], 1080, 1920)
    assert y == 0, f"expected y=0 (clamped to top), got {y}"
    assert y % 2 == 0, f"y={y} not even"

    # With fy=0.95: y = round(0.95*1920 - 1920/2) = round(1824 - 960) = 864
    # Clamped to [0, 0] → y = 0 (no vertical crop margin)
    x, y = compute_crop_xy(1080, 1920, [(0.5, 0.95)], 1080, 1920)
    assert y == 0, f"expected y=0 (no margin), got {y}"


def test_median_with_multiple_faces():
    """Multiple faces → median position used."""
    # Three faces at fx = 0.2, 0.5, 0.8 → median = 0.5.
    faces = [(0.2, 0.5), (0.5, 0.5), (0.8, 0.5)]
    x1, _ = compute_crop_xy(1920, 1080, faces, 1080, 1920)
    x2, _ = compute_crop_xy(1920, 1080, [(0.5, 0.5)], 1080, 1920)
    assert x1 == x2, f"median of 0.2,0.5,0.8 should match 0.5: {x1} vs {x2}"


def test_clamp_bounds():
    """Crop offset must stay within [0, sw-W] and [0, sh-H]."""
    x, y = compute_crop_xy(1920, 1080, [(1.0, 1.0)], 1080, 1920)
    # Extreme right/bottom face should clamp, not go negative or beyond bounds.
    assert x >= 0, f"x={x} should be >= 0"
    assert y >= 0, f"y={y} should be >= 0"
    assert x % 2 == 0 and y % 2 == 0, f"x={x}, y={y} not both even"


def test_square_to_portrait():
    """Square source 1080x1080 → portrait 1080x1920."""
    # scale = max(1080/1080, 1920/1080) = max(1, 1.7778) = 1.7778
    # sw = 1920, sh = 1920
    x, y = compute_crop_xy(1080, 1080, [(0.5, 0.5)], 1080, 1920)
    assert x % 2 == 0 and y % 2 == 0, f"x={x}, y={y} not both even"
    assert 0 <= x <= 1920 - 1080, f"x={x} out of bounds [0, {1920-1080}]"
    assert 0 <= y <= 1920 - 1920, f"y={y} out of bounds [0, {1920-1920}]"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
