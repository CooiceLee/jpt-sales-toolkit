#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

if [ ! -x "$CHROME" ]; then
  echo "Chrome not found at: $CHROME"
  exit 1
fi

URL="${BASE_URL}/static/smoke-v09.html?username=${SMOKE_USER:-leader01}&password=${SMOKE_PASSWORD:-LeaderJPT2026}"
"$CHROME" \
  --headless=new \
  --disable-gpu \
  --disable-background-networking \
  --disable-component-update \
  --disable-sync \
  --disable-default-apps \
  --no-first-run \
  --no-service-autorun \
  --metrics-recording-only \
  --password-store=basic \
  --use-mock-keychain \
  --user-data-dir="/tmp/jpt-chrome-smoke-v09-$$" \
  --virtual-time-budget=35000 \
  --dump-dom "$URL" \
  | sed -n '/<div id="status"/,/<\/div>/p;/<pre id="results">/,/<\/pre>/p'
