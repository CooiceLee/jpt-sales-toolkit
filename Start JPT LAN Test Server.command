#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

exec "$SCRIPT_DIR/scripts/one_click_lan_test_server.sh"
