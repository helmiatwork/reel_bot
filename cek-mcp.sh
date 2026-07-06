#!/usr/bin/env bash
# cek-mcp.sh — verify reelbot MCP prerequisites before connecting Antigravity.
# Run: ./cek-mcp.sh   (from the repo root)
set -uo pipefail
cd "$(dirname "$0")"
[ -f .env ] && { set -a; . ./.env; set +a; }
BRIDGE="${CLAUDE_BRIDGE_URL:-http://localhost:9999}"
PY="./pipeline-api/.venv/bin/python"
ok=0; fail=0
say(){ printf "%-34s %s\n" "$1" "$2"; }

# 1. postgres reachable
if psql "${DATABASE_URL:-}" -tAc "SELECT 1" >/dev/null 2>&1; then
  say "postgres (DATABASE_URL)" "✅ up"; ok=$((ok+1))
else
  say "postgres (DATABASE_URL)" "❌ DOWN — start postgres :5432"; fail=$((fail+1))
fi

# 2. claude bridge reachable
if curl -sf -o /dev/null --max-time 5 "$BRIDGE/health" 2>/dev/null || curl -sf -o /dev/null --max-time 5 "$BRIDGE" 2>/dev/null; then
  say "claude bridge ($BRIDGE)" "✅ up"; ok=$((ok+1))
else
  say "claude bridge ($BRIDGE)" "⚠️  no response — start it (needed for generate_shot_prompts / make_brief)"; fail=$((fail+1))
fi

# 3. mcp python + server module load
if [ -x "$PY" ] && "$PY" -c "import mcp" >/dev/null 2>&1; then
  say "mcp package (venv)" "✅ installed"; ok=$((ok+1))
else
  say "mcp package (venv)" "❌ missing — pipeline-api/.venv/bin/pip install 'mcp[cli]'"; fail=$((fail+1))
fi

# 4. MCP server handshake (what Antigravity does)
if "$PY" - <<'PYEOF' >/dev/null 2>&1
import asyncio, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def m():
    p=StdioServerParameters(command="./pipeline-api/.venv/bin/python", args=["mcp/reelbot_mcp.py"], env=dict(os.environ))
    async with stdio_client(p) as (r,w):
        async with ClientSession(r,w) as s:
            await s.initialize(); await s.list_tools()
asyncio.run(m())
PYEOF
then
  say "MCP handshake + tools/list" "✅ ok"; ok=$((ok+1))
else
  say "MCP handshake + tools/list" "❌ failed — check DATABASE_URL + server file"; fail=$((fail+1))
fi

echo "-----------------------------------------"
if [ "$fail" -eq 0 ]; then
  echo "ALL GOOD ($ok/4) — Antigravity siap connect ke server 'reelbot'."
else
  echo "$fail masalah — beresin dulu sebelum colok Antigravity."
fi
exit $fail
