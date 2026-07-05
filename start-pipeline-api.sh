#!/bin/sh
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR" && pwd)

# Load repo .env if present
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  . "$REPO_ROOT/.env"
  set +a
fi

# Frame dir: prefer the protected ReelBot store if present, else fall back to repo dir
if [ -z "$ANALYZE_FRAME_DIR" ]; then
  if [ -d "$HOME/Downloads/ReelBot/frames" ]; then
    ANALYZE_FRAME_DIR="$HOME/Downloads/ReelBot/frames"
  else
    ANALYZE_FRAME_DIR="$REPO_ROOT/analyze-frames"
  fi
fi
export ANALYZE_FRAME_DIR

# Dashboard: vite builds to analytics-dashboard/ (not dashboard-svelte/dist),
# so point the server there for native mode.
if [ -z "$DASHBOARD_DIR" ] && [ -d "$REPO_ROOT/analytics-dashboard" ]; then
  DASHBOARD_DIR="$REPO_ROOT/analytics-dashboard"
fi
export DASHBOARD_DIR

cd "$REPO_ROOT/pipeline-api" && source .venv/bin/activate && exec uvicorn main:app --host 0.0.0.0 --port 8000
