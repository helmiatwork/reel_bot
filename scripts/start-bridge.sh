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

export ANALYZE_FRAME_DIR="${ANALYZE_FRAME_DIR:-$REPO_ROOT/analyze-frames}"
export CLAUDE_BRIDGE_PORT="${CLAUDE_BRIDGE_PORT:-9999}"
# CLAUDE_BIN defaults inside claude_bridge.py to the nodenv path; override here if needed.

# Pure-stdlib bridge — system python3 is sufficient and stable under launchd.
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

exec "$PYTHON_BIN" "$REPO_ROOT/scripts/claude_bridge.py"
