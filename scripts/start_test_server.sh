#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-"$ROOT_DIR/deploy/test-server.env"}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
elif [[ -f "$ROOT_DIR/deploy/test-server.env.example" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/deploy/test-server.env.example"
fi

export JPT_DATA_DIR="${JPT_DATA_DIR:-"$ROOT_DIR/data-test-server"}"
HOST="${JPT_TEST_HOST:-0.0.0.0}"
PORT="${JPT_TEST_PORT:-8000}"
PUBLIC_URL="${JPT_PUBLIC_URL:-"http://<LAN-IP>:$PORT"}"

mkdir -p "$JPT_DATA_DIR/attachments" "$JPT_DATA_DIR/backups" "$JPT_DATA_DIR/imports" "$JPT_DATA_DIR/exports"

cat <<EOF
JPT Sales Toolkit v0.9.0 LAN test server

Data directory: $JPT_DATA_DIR
Bind address:   $HOST:$PORT
Team URL:       $PUBLIC_URL

Stop with Ctrl+C.
EOF

cd "$ROOT_DIR"
python3 run.py --host "$HOST" --port "$PORT" --data-dir "$JPT_DATA_DIR" --no-browser
