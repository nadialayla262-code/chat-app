#!/usr/bin/env bash
# Stop what ./scripts/start.sh started. By process id, never by name.
set -uo pipefail
cd "$(dirname "$0")/.."
RUN=".run"
[ -d "$RUN" ] && ls "$RUN"/*.pid >/dev/null 2>&1 || { echo "nothing running"; exit 0; }
for name in handi homei spine; do
  f="$RUN/$name.pid"
  [ -f "$f" ] || continue
  pid="$(cat "$f")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null
    for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    echo "$name stopped"
  else
    echo "$name was not running"
  fi
  rm -f "$f"
done
