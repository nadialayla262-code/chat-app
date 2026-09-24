#!/usr/bin/env bash
# Download PocketBase (once) and serve the chat app.
#
#   ./scripts/dev.sh            # http://127.0.0.1:8090
#   PB_PORT=9000 ./scripts/dev.sh
#
# Everything lives in this folder. The database is ./pb_data (gitignored).
# CXI_DESK_OWNERS=you@example.com opens the Desk (see README) to that person.
set -euo pipefail
cd "$(dirname "$0")/.."

PB_VERSION="${PB_VERSION:-0.40.4}"
PB_PORT="${PB_PORT:-8090}"
BIN="./bin/pocketbase"

if [ ! -x "$BIN" ]; then
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"   # linux | darwin
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) arch="amd64" ;;
    arm64|aarch64) arch="arm64" ;;
    *) echo "Unsupported CPU architecture: $arch" >&2; exit 1 ;;
  esac
  url="https://github.com/pocketbase/pocketbase/releases/download/v${PB_VERSION}/pocketbase_${PB_VERSION}_${os}_${arch}.zip"
  echo "Downloading PocketBase ${PB_VERSION} for ${os}/${arch}..."
  mkdir -p bin
  curl -fsSL -o bin/pocketbase.zip "$url"
  unzip -o -q bin/pocketbase.zip pocketbase -d bin
  rm bin/pocketbase.zip
  chmod +x "$BIN"
fi

exec "$BIN" serve \
  --http="127.0.0.1:${PB_PORT}" \
  --dir=./pb_data \
  --migrationsDir=./pb_migrations \
  --hooksDir=./pb_hooks \
  --publicDir=./public
