#!/bin/bash
# Usage: ./scripts/ngrok-start.sh
# Starts ngrok, updates openclaw.json allowedOrigins, sets Telegram webhook, restarts openclaw.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"

# Load .env
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)
fi

if [ -z "$OPENCLAW_TELEGRAM_BOT_TOKEN" ]; then
    echo "ERROR: OPENCLAW_TELEGRAM_BOT_TOKEN not set in .env" >&2
    exit 1
fi

echo "[1/4] Starting ngrok on port 18789..."
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json; t=json.load(sys.stdin)['tunnels']; print([x['public_url'] for x in t if x['proto']=='https'][0])" 2>/dev/null)
if [ -z "$NGROK_URL" ]; then
    ngrok http 18789 --log=stdout > /tmp/ngrok.log 2>&1 &
    NGROK_PID=$!
else
    echo "    ngrok already running, reusing existing tunnel"
fi

# Wait for ngrok to be ready
for i in $(seq 1 30); do
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json; t=json.load(sys.stdin)['tunnels']; print([x['public_url'] for x in t if x['proto']=='https'][0])" 2>/dev/null)
    if [ -n "$NGROK_URL" ]; then break; fi
    sleep 1
done

if [ -z "$NGROK_URL" ]; then
    echo "ERROR: ngrok did not start. Check /tmp/ngrok.log" >&2
    exit 1
fi

echo "    ngrok URL: $NGROK_URL"

echo "[2/4] Updating openclaw.json allowedOrigins..."
node -e "
const fs = require('fs');
const path = '$OPENCLAW_CONFIG';
const config = JSON.parse(fs.readFileSync(path, 'utf8'));
const origins = config.gateway.controlUi.allowedOrigins.filter(o =>
    o.startsWith('http://localhost') || o.startsWith('http://127.0.0.1')
);
origins.push('$NGROK_URL');
config.gateway.controlUi.allowedOrigins = origins;
fs.writeFileSync(path, JSON.stringify(config, null, 2));
console.log('    allowedOrigins updated');
"

echo "[3/4] Restarting OpenClaw..."
cd "$SCRIPT_DIR"
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d openclaw
sleep 3

echo "[4/4] Setting Telegram webhook..."
WEBHOOK_RESP=$(curl -s "https://api.telegram.org/bot${OPENCLAW_TELEGRAM_BOT_TOKEN}/setWebhook?url=${NGROK_URL}/telegram")
echo "    $WEBHOOK_RESP"

echo ""
echo "Done!"
echo "  Control UI : $NGROK_URL"
echo "  Webhook    : ${NGROK_URL}/telegram"
echo ""
echo "Open $NGROK_URL in browser, enter gateway token + password."
echo "To stop: ./scripts/ngrok-stop.sh"
