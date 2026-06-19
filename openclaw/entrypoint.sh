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

// Enable OpenAI-compatible HTTP API (POST /v1/chat/completions) so the
// dashboard chat page can reach the agent the same way Telegram does.
config.gateway.http = config.gateway.http || {};
config.gateway.http.endpoints = config.gateway.http.endpoints || {};
config.gateway.http.endpoints.chatCompletions = { enabled: true };
console.log('[entrypoint] OpenAI HTTP API (chatCompletions) enabled');

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

// Scan for multiple Telegram bot tokens via OPENCLAW_TELEGRAM_BOT_TOKEN_FOR_<AGENT_ID>
const botTokenVars = Object.keys(process.env).filter(k => k.startsWith('OPENCLAW_TELEGRAM_BOT_TOKEN_FOR_'));
if (botTokenVars.length > 0) {
    config.agents = config.agents || {};
    config.channels = config.channels || {};
    config.channels.telegram = config.channels.telegram || {};
    config.channels.telegram.accounts = config.channels.telegram.accounts || {};
    config.bindings = config.bindings || [];

    const agents = [];
    let isFirst = true;

    for (const botTokenVar of botTokenVars.sort()) {
        const agentId = botTokenVar.replace('OPENCLAW_TELEGRAM_BOT_TOKEN_FOR_', '').toLowerCase();
        const botToken = process.env[botTokenVar];

        if (!botToken) continue;

        agents.push({
            id: agentId,
            default: isFirst,
            workspace: isFirst ? '/root/.openclaw/workspace' : '/root/.openclaw/workspace-' + agentId
        });

        const accountId = isFirst ? 'default' : agentId;
        config.channels.telegram.accounts[accountId] = { botToken };

        config.bindings.push({
            agentId,
            match: { channel: 'telegram', accountId }
        });

        console.log('[entrypoint] Telegram bot configured for agent:', agentId, 'accountId:', accountId);
        isFirst = false;
    }

    config.agents.list = agents;
    console.log('[entrypoint] agents.list configured with', agents.length, 'agent(s)');
}

// Scan for multiple Telegram owner IDs via OPENCLAW_TELEGRAM_OWNER_ID_FOR_<AGENT_ID>
const ownerIdVars = Object.keys(process.env).filter(k => k.startsWith('OPENCLAW_TELEGRAM_OWNER_ID_FOR_'));
if (ownerIdVars.length > 0) {
    config.commands = config.commands || {};
    const existing = config.commands.ownerAllowFrom || [];

    for (const ownerIdVar of ownerIdVars) {
        const ownerId = process.env[ownerIdVar];
        if (ownerId) {
            const entry = 'telegram:' + ownerId;
            if (!existing.includes(entry)) {
                existing.push(entry);
            }
        }
    }

    config.commands.ownerAllowFrom = existing;
    console.log('[entrypoint] Telegram owners set from env vars, total entries:', existing.length);
}

if (process.env.OPENCLAW_DEFAULT_MODEL) {
    config.agents = config.agents || {};
    config.agents.defaults = config.agents.defaults || {};
    config.agents.defaults.model = process.env.OPENCLAW_DEFAULT_MODEL;
    console.log('[entrypoint] default model set to:', process.env.OPENCLAW_DEFAULT_MODEL);
}

// Force workspace path to container path — VirtioFS serves the Mac host path
// separately from the bind mount, causing OpenClaw to read stale default files.
config.agents = config.agents || {};
config.agents.defaults = config.agents.defaults || {};
config.agents.defaults.workspace = '/root/.openclaw/workspace';
console.log('[entrypoint] workspace forced to /root/.openclaw/workspace');

fs.writeFileSync(path, JSON.stringify(config, null, 2));
console.log('[entrypoint] Gateway token + password configured from environment');
"

# Sync workspace config files from agents into workspace on every startup
# For each agent, sync SOUL.md AGENTS.md IDENTITY.md from its agent directory to its workspace
for agentTokenVar in $(env | grep -E '^OPENCLAW_TELEGRAM_BOT_TOKEN_FOR_' | cut -d= -f1); do
    agentId=$(echo "$agentTokenVar" | sed 's/^OPENCLAW_TELEGRAM_BOT_TOKEN_FOR_//' | tr '[:upper:]' '[:lower:]')

    if [ "$agentId" = "reelbot" ]; then
        AGENTS_DIR="/root/.openclaw/agents/main"
        WORKSPACE_DIR="/root/.openclaw/workspace"
    else
        AGENTS_DIR="/root/.openclaw/agents/$agentId"
        WORKSPACE_DIR="/root/.openclaw/workspace-$agentId"
    fi

    mkdir -p "$WORKSPACE_DIR"
    for f in SOUL.md AGENTS.md IDENTITY.md; do
        if [ -f "$AGENTS_DIR/$f" ]; then
            cp "$AGENTS_DIR/$f" "$WORKSPACE_DIR/$f"
            echo "[entrypoint] $f synced to $WORKSPACE_DIR"
        fi
    done
done

exec "$@"
