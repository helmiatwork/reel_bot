#!/bin/sh
set -e

if [ -z "$OPENCLAW_GATEWAY_TOKEN" ]; then
    echo "[entrypoint] ERROR: OPENCLAW_GATEWAY_TOKEN is not set. Set it in .env and restart." >&2
    exit 1
fi

if [ -z "$OPENCLAW_PASSWORD" ]; then
    echo "[entrypoint] ERROR: OPENCLAW_PASSWORD is not set. Set it in .env and restart." >&2
    exit 1
fi

node -e "
const fs = require('fs');
const path = '/root/.openclaw/openclaw.json';
if (!fs.existsSync(path)) { console.error('[entrypoint] openclaw.json not found'); process.exit(1); }
const config = JSON.parse(fs.readFileSync(path, 'utf8'));
config.gateway = config.gateway || {};
config.gateway.auth = {
    mode: 'token',
    token: process.env.OPENCLAW_GATEWAY_TOKEN,
    password: process.env.OPENCLAW_PASSWORD
};
config.gateway.controlUi = config.gateway.controlUi || {};
config.gateway.controlUi.dangerouslyDisableDeviceAuth = true;

if (process.env.CLIPROXY_URL || process.env.CLIPROXY_KEY) {
    config.models = config.models || {};
    config.models.providers = config.models.providers || {};
    config.models.providers.cliproxy = config.models.providers.cliproxy || {};
    if (process.env.CLIPROXY_URL) {
        config.models.providers.cliproxy.baseUrl = process.env.CLIPROXY_URL;
        console.log('[entrypoint] cliproxy baseUrl set to:', process.env.CLIPROXY_URL);
    }
    if (process.env.CLIPROXY_KEY) {
        config.models.providers.cliproxy.apiKey = process.env.CLIPROXY_KEY;
        console.log('[entrypoint] cliproxy apiKey updated from CLIPROXY_KEY');
    }
}

if (process.env.OPENCLAW_TELEGRAM_OWNER_ID) {
    config.commands = config.commands || {};
    const entry = 'telegram:' + process.env.OPENCLAW_TELEGRAM_OWNER_ID;
    const existing = config.commands.ownerAllowFrom || [];
    if (!existing.includes(entry)) {
        config.commands.ownerAllowFrom = [...existing, entry];
    }
    console.log('[entrypoint] Telegram owner set from OPENCLAW_TELEGRAM_OWNER_ID:', entry);
}
fs.writeFileSync(path, JSON.stringify(config, null, 2));
console.log('[entrypoint] Gateway token + password configured from environment');
"

exec "$@"
