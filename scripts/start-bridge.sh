#!/bin/sh
# start-bridge.sh — launch the host-side claude bridge.
#
# Used both for manual runs and by the launchd agent
# (com.reelbot.claude-bridge.plist). Resolves the repo root from this script's
# own location so ANALYZE_FRAME_DIR is always an absolute path — claude runs in
# a clean temp cwd and reads frames by absolute path only.
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# Frame dir: prefer the protected ReelBot store if present (this Mac), else fall
# back to the repo dir (VPS / other hosts). Must match the host side of the
# pipeline-api /app/analyze-frames mount (see docker-compose.mac.yml).
if [ -z "$ANALYZE_FRAME_DIR" ]; then
  if [ -d "$HOME/Downloads/ReelBot/frames" ]; then
    ANALYZE_FRAME_DIR="$HOME/Downloads/ReelBot/frames"
  else
    ANALYZE_FRAME_DIR="$REPO_ROOT/analyze-frames"
  fi
fi
export ANALYZE_FRAME_DIR
export CLAUDE_BRIDGE_PORT="${CLAUDE_BRIDGE_PORT:-9999}"
# CLAUDE_BIN defaults inside claude_bridge.py to the nodenv path; override here if needed.

# Pure-stdlib bridge — system python3 is sufficient and stable under launchd.
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

exec "$PYTHON_BIN" "$REPO_ROOT/scripts/claude_bridge.py"
