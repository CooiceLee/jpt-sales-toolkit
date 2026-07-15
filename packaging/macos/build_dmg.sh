#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:-0.10.0-internal}"
ARCH="${2:-$(uname -m)}"
APP_PATH="${3:-$ROOT_DIR/dist/JPT Sales Toolkit.app}"
OUTPUT_DIR="${4:-$ROOT_DIR/release}"
OUTPUT_PATH="$OUTPUT_DIR/JPT-Sales-Toolkit-${VERSION}-macOS-${ARCH}-UNSIGNED-INTERNAL.dmg"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Missing frozen app: $APP_PATH" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT
ditto "$APP_PATH" "$STAGING_DIR/JPT Sales Toolkit.app"
ln -s /Applications "$STAGING_DIR/Applications"
hdiutil create \
  -volname "JPT Sales Toolkit" \
  -srcfolder "$STAGING_DIR" \
  -ov -format UDZO \
  "$OUTPUT_PATH"
echo "$OUTPUT_PATH"
