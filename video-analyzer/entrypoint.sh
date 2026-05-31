#!/bin/bash
set -e
if [ "$1" = "--help" ] || [ $# -eq 0 ]; then
    echo "Usage: docker compose --profile tools run --rm video-analyzer /videos/input.mp4 [OPTIONS]"
    echo "Env: CLIPROXY_URL, CLIPROXY_KEY, MODEL, WHISPER_MODEL"
    video-analyzer --help
    exit 0
fi
VIDEO_FILE=$1; shift
[ ! -f "$VIDEO_FILE" ] && echo "ERROR: File not found: $VIDEO_FILE" && exit 1
echo "Analyzing: $VIDEO_FILE | Model: $MODEL | Whisper: $WHISPER_MODEL"
exec video-analyzer "$VIDEO_FILE" \
    --client openai_api \
    --api-key "$CLIPROXY_KEY" \
    --api-url "$CLIPROXY_URL" \
    --model "$MODEL" \
    --whisper-model "$WHISPER_MODEL" \
    --output /output/analysis.json \
    "$@"
