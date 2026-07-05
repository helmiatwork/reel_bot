#!/usr/bin/env python3
"""
Face-centered crop offset calculator for landscape→portrait render.

CLI: python face_crop.py <video_path> <in_sec> <out_sec> <W> <H>
     Prints "X Y" (two integers) to stdout, or "0 0" on any error.
     Exit code always 0 (never fail the render).

Usage:
  python face_crop.py sample.mp4 0 5 1080 1920  # → "450 0" (example face-centered crop)
"""

import sys
import math


def compute_crop_xy(src_w, src_h, face_centers, W, H):
    """
    Compute crop offsets that center on detected face(s).

    Args:
        src_w, src_h: source video dimensions (pixels).
        face_centers: list of (fx, fy) tuples, where each is a fraction (0..1)
                      of frame width/height. Empty list → centered crop.
        W, H: target crop size (pixels).

    Returns:
        (x, y) tuple: int crop offsets into the scaled frame, forced to even
                      (yuv420 chroma alignment).
    """
    # Scale calculation (mirror ffmpeg scale=...:force_original_aspect_ratio=increase)
    scale = max(W / src_w, H / src_h)
    sw = round(src_w * scale)
    sh = round(src_h * scale)

    # Determine face center: median of detected faces, or 0.5 (centered) if none.
    if face_centers:
        fx_list = [fc[0] for fc in face_centers]
        fy_list = [fc[1] for fc in face_centers]
        fx = sorted(fx_list)[len(fx_list) // 2]
        fy = sorted(fy_list)[len(fy_list) // 2]
    else:
        fx = fy = 0.5

    # Compute crop offsets; clamp to valid range.
    x = max(0, min(round(fx * sw - W / 2), sw - W))
    y = max(0, min(round(fy * sh - H / 2), sh - H))

    # Force x, y to even (yuv420 chroma alignment).
    x = (x // 2) * 2
    y = (y // 2) * 2

    return (x, y)


def detect_faces_in_range(video_path, in_sec, out_sec):
    """
    Detect largest face in ~10 evenly-spaced frames across [in_sec, out_sec].

    Args:
        video_path: path to video file.
        in_sec, out_sec: time range (seconds).

    Returns:
        tuple: (src_w, src_h, face_centers) where face_centers is a list of
               (fx, fy) fractions, or (None, None, []) on any error.
    """
    try:
        import cv2
    except ImportError:
        # opencv-python-headless not installed; degrade gracefully.
        return (None, None, [])

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return (None, None, [])

        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if src_w <= 0 or src_h <= 0:
            cap.release()
            return (None, None, [])

        # Haar cascade for frontal faces
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)

        face_centers = []
        num_frames = 10
        for frame_idx in range(num_frames):
            # Evenly space frames across [in_sec, out_sec]
            t = in_sec + (out_sec - in_sec) * frame_idx / (num_frames - 1) if num_frames > 1 else in_sec
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Detect faces; keep the largest one.
            faces = cascade.detectMultiScale(frame, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            if len(faces) > 0:
                # faces is [x, y, w, h] array; take the largest by area.
                largest = max(faces, key=lambda f: f[2] * f[3])
                cx = (largest[0] + largest[2] / 2) / src_w
                cy = (largest[1] + largest[3] / 2) / src_h
                face_centers.append((cx, cy))

        cap.release()
        return (src_w, src_h, face_centers)
    except Exception:
        # Any error (missing file, corrupt video, etc.) → degrade gracefully.
        return (None, None, [])


def main():
    """CLI: read args, detect faces, compute crop, print result."""
    if len(sys.argv) != 6:
        # Silently degrade: print centered crop.
        print("0 0")
        sys.exit(0)

    video_path = sys.argv[1]
    try:
        in_sec = float(sys.argv[2])
        out_sec = float(sys.argv[3])
        W = int(sys.argv[4])
        H = int(sys.argv[5])
    except (ValueError, TypeError):
        # Silently degrade.
        print("0 0")
        sys.exit(0)

    src_w, src_h, face_centers = detect_faces_in_range(video_path, in_sec, out_sec)

    # If we failed to open/read the video, degrade to centered crop.
    if src_w is None or src_h is None:
        print("0 0")
        sys.exit(0)

    x, y = compute_crop_xy(src_w, src_h, face_centers, W, H)
    print(f"{x} {y}")
    sys.exit(0)


if __name__ == "__main__":
    main()
