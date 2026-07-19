#!/bin/sh
# Start pipeline-api (:8000) natively, with the repo .env loaded. One command:
#   sh scripts/start-pipeline-api.sh          # foreground
#   nohup sh scripts/start-pipeline-api.sh &  # background
#
# DASHBOARD_DIR is optional — main.py falls back to analytics-dashboard/ automatically.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/pipeline-api"

# Load repo .env (DATABASE_URL, CLAUDE_BRIDGE_URL, keys, …) if present
if [ -f "$ROOT/.env" ]; then
  set -a
  . "$ROOT/.env"
  set +a
fi

VENV="$ROOT/pipeline-api/.venv/bin/uvicorn"
if [ ! -x "$VENV" ]; then
  echo "error: $VENV not found — run 'uv sync' (or create the venv) in pipeline-api first" >&2
  exit 1
fi

exec "$VENV" main:app --host "${PIPELINE_API_HOST:-127.0.0.1}" --port "${PIPELINE_API_PORT:-8000}"
