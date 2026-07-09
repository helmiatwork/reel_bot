#!/bin/bash
# Daily performance snapshot collector.
# Calls POST /performance/refresh on the local pipeline-api.
# Install via launchd: see scripts/com.reelbot.performance-collector.plist
set -euo pipefail

curl -s --max-time 300 -X POST http://localhost:8000/performance/refresh \
  -H 'content-type: application/json' \
  -d '{}' \
  | tee -a /tmp/reelbot_performance.log
echo
