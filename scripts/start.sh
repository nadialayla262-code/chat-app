#!/usr/bin/env bash
# Start everything in the background: the spine, Homei, Handi.
#
#   ./scripts/start.sh            # http://127.0.0.1:8090
#   ./scripts/start.sh --no-seats # the spine only
#
# Logs go to workers/log/spine.log, homei.log, handi.log (append-only).
# Process ids go to .run/. Stop with ./scripts/stop.sh.
#
# Set CXI_SIGNUP_CODE, CXI_SUPERUSER_EMAIL and CXI_SUPERUSER_PASSWORD in this
# shell first if you want closed sign-up and "@handi find".
set -euo pipefail
cd "$(dirname "$0")/.."
PB_PORT="${PB_PORT:-8090}"
RUN=".run"; LOG="workers/log"
mkdir -p "$RUN" "$LOG"

if [ -f "$RUN/spine.pid" ] && kill -0 "$(cat "$RUN/spine.pid")" 2>/dev/null; then
  echo "already running (pid $(cat "$RUN/spine.pid")). ./scripts/stop.sh first."; exit 0
fi

# the binary, once
if [ ! -x ./bin/pocketbase ]; then
  PB_PORT="$PB_PORT" bash -c 'source ./scripts/dev.sh' >/dev/null 2>&1 & sleep 0.1; kill $! 2>/dev/null || true
fi
[ -x ./bin/pocketbase ] || { echo "no ./bin/pocketbase yet; run ./scripts/dev.sh once"; exit 2; }

nohup ./bin/pocketbase serve --http="127.0.0.1:${PB_PORT}" --dir=./pb_data --migrationsDir=./pb_migrations \
  --hooksDir=./pb_hooks --publicDir=./public >>"$LOG/spine.log" 2>&1 &
echo $! > "$RUN/spine.pid"
for i in $(seq 1 40); do curl -sf "http://127.0.0.1:${PB_PORT}/api/health" >/dev/null && break; sleep 0.25; done
curl -sf "http://127.0.0.1:${PB_PORT}/api/health" >/dev/null || { echo "spine did not start; see $LOG/spine.log"; exit 1; }
echo "spine     http://127.0.0.1:${PB_PORT}   (admin: /_/)"

if [ "${1:-}" != "--no-seats" ]; then
  export CXI_PB_URL="http://127.0.0.1:${PB_PORT}"
  ( cd workers; nohup python3 homei.py >>"../$LOG/homei.log" 2>&1 & echo $! > "../$RUN/homei.pid" )
  ( cd workers; nohup python3 handi.py >>"../$LOG/handi.log" 2>&1 & echo $! > "../$RUN/handi.pid" )
  echo "homei     started   (log: $LOG/homei.log)"
  echo "handi     started   (log: $LOG/handi.log)"
fi
echo "stop with ./scripts/stop.sh"
