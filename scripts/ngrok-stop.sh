#!/bin/bash
# Stops ngrok and removes Telegram webhook.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)
fi

echo "[1/2] Removing Telegram webhook..."
if [ -n "$OPENCLAW_TELEGRAM_BOT_TOKEN" ]; then
    curl -s "https://api.telegram.org/bot${OPENCLAW_TELEGRAM_BOT_TOKEN}/deleteWebhook" | python3 -c "import sys,json; r=json.load(sys.stdin); print('   ', r.get('description','done'))"
fi

echo "Done. (ngrok left running — stop it manually if needed)"
