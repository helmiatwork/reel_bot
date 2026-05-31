#!/bin/bash
set -e
if [ "$1" = "--help" ] || [ $# -eq 0 ]; then
    echo "Split by seconds:   docker compose --profile tools run --rm video-splitter -f /videos/in.mp4 -s 600 -o /videos/chunks"
    echo "Split by manifest:  docker compose --profile tools run --rm video-splitter -f /videos/in.mp4 -m /videos/manifest.json"
    python3 ffmpeg-split.py --help
    exit 0
fi
echo "video-splitter: $@"
exec python3 /app/ffmpeg-split.py "$@"
