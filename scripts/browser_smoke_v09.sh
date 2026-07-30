#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
: "${SMOKE_USER:?Set SMOKE_USER to an isolated smoke-test account}"
: "${SMOKE_PASSWORD:?Set SMOKE_PASSWORD to that account password}"

if [ ! -x "$CHROME" ]; then
  echo "Chrome not found at: $CHROME"
  exit 1
fi

URL="${BASE_URL}/static/smoke-v09.html?username=${SMOKE_USER}&password=${SMOKE_PASSWORD}"
DEBUG_PORT="$(python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
PROFILE_DIR="/tmp/jpt-chrome-smoke-v09-$$"
CHROME_LOG="/tmp/jpt-chrome-smoke-v09-$$.log"

cleanup() {
  if [[ -n "${CHROME_PID:-}" ]]; then
    kill "$CHROME_PID" 2>/dev/null || true
    wait "$CHROME_PID" 2>/dev/null || true
  fi
  rm -rf "$PROFILE_DIR" "$CHROME_LOG"
}
trap cleanup EXIT INT TERM

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
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$DEBUG_PORT" \
  --user-data-dir="$PROFILE_DIR" \
  "$URL" >"$CHROME_LOG" 2>&1 &
CHROME_PID=$!

for _ in $(seq 1 120); do
  TITLE="$(
    curl --noproxy '*' -fsS "http://127.0.0.1:${DEBUG_PORT}/json/list" 2>/dev/null \
      | python3 -c 'import json,sys; print(next((p.get("title", "") for p in json.load(sys.stdin) if p.get("type") == "page" and "JPT v0.9 Smoke" in p.get("title", "")), ""))' \
      2>/dev/null || true
  )"
  case "$TITLE" in
    *" Smoke PASS")
      echo "PASS: browser smoke completed"
      exit 0
      ;;
    *" Smoke FAIL"*)
      echo "$TITLE" >&2
      exit 1
      ;;
  esac
  if ! kill -0 "$CHROME_PID" 2>/dev/null; then
    echo "Chrome exited before the browser smoke reached a result." >&2
    exit 1
  fi
  sleep 0.5
done

echo "Browser smoke timed out before reaching PASS or FAIL." >&2
exit 1
