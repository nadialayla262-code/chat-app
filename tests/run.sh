#!/usr/bin/env bash
# Run everything against a throwaway spine on port 8099. Nothing touches ./pb_data.
#
#   ./tests/run.sh            # all
#   ./tests/run.sh rules      # one of: rules workers browser register corpus backup bates board signup startstop
#
# Needs: node, python3, the PocketBase binary (./scripts/dev.sh fetches it into ./bin).
# Optional: Playwright for the browser suite; pypdf+reportlab+pillow for the Bates suite.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
TMP="$ROOT/tests/.tmp"
PORT="${CXI_TEST_PORT:-8099}"
export CXI_TEST_URL="http://127.0.0.1:$PORT"
export CXI_PB_URL="$CXI_TEST_URL"
export CXI_OLLAMA_HOST="http://127.0.0.1:11435"
PY="${PYTHON:-python3}"
[ -x ./bin/pocketbase ] || { echo "no ./bin/pocketbase — run ./scripts/dev.sh once to fetch it"; exit 2; }

rm -rf "$TMP"; mkdir -p "$TMP/pb_data" "$TMP/workers"
PIDS=()
stop() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done; }
trap stop EXIT

./bin/pocketbase migrate up --dir="$TMP/pb_data" --migrationsDir=./pb_migrations >/dev/null 2>&1
./bin/pocketbase superuser upsert test@cxi.local test-superuser-pass --dir="$TMP/pb_data" >/dev/null 2>&1
# Two Desk owners, one with odd casing: the gate must read the list and ignore case.
CXI_DESK_OWNERS="desk@test.local, Second.Owner@Test.local" \
./bin/pocketbase serve --http="127.0.0.1:$PORT" --dir="$TMP/pb_data" --migrationsDir=./pb_migrations --hooksDir=./pb_hooks --publicDir=./public >"$TMP/pb.log" 2>&1 &
PIDS+=($!)
for i in $(seq 1 30); do curl -sf "$CXI_TEST_URL/api/health" >/dev/null && break; sleep 0.3; done
curl -sf "$CXI_TEST_URL/api/health" >/dev/null || { echo "spine did not start"; cat "$TMP/pb.log"; exit 1; }

want="${1:-all}"
need_workers=0; case "$want" in all|workers|corpus) need_workers=1;; esac
if [ "$need_workers" = 1 ]; then
  "$PY" tests/fake_embed.py 11435 >"$TMP/fake.log" 2>&1 & PIDS+=($!)
  # workers keep their generated passwords and caches next to themselves; point them at the temp folder
  cp workers/*.py workers/*.md "$TMP/workers/"
  ( cd "$TMP/workers" && CXI_HOMEI_POLL=0.5 "$PY" homei.py >"$TMP/homei.log" 2>&1 ) & PIDS+=($!)
  ( cd "$TMP/workers" && CXI_HANDI_POLL=0.5 CXI_HANDI_MODEL=0 CXI_EMBED_MODEL=fake-embed \
      CXI_SUPERUSER_EMAIL=test@cxi.local CXI_SUPERUSER_PASSWORD=test-superuser-pass "$PY" handi.py >"$TMP/handi.log" 2>&1 ) & PIDS+=($!)
  sleep 2
fi

status=0
run() { echo; echo "== $1 =="; shift; "$@" || status=1; }
case "$want" in
  all)      run rules node tests/rules.js; run register "$PY" tests/register.py; run corpus "$PY" tests/corpus.py
            run workers node tests/workers.js; run backup "$PY" tests/backup.py; run bates "$PY" tests/bates.py
            run board "$PY" tests/board.py; run browser node tests/browser.js ;;
  rules)    run rules node tests/rules.js ;;
  workers)  run workers node tests/workers.js ;;
  register) run register "$PY" tests/register.py ;;
  corpus)   run corpus "$PY" tests/corpus.py ;;
  backup)   run backup "$PY" tests/backup.py ;;
  bates)    run bates "$PY" tests/bates.py ;;
  board)    run board "$PY" tests/board.py ;;
  browser)  run browser node tests/browser.js ;;
  signup)   : ;;
  startstop) : ;;
  *) echo "unknown suite: $want"; status=2 ;;
esac
if [ "$want" = all ] || [ "$want" = startstop ]; then
  echo; echo "== start / stop =="
  bash tests/startstop.sh || status=1
fi

# The sign-up code needs a spine started with the variable set: a second, short-lived one.
if [ "$want" = all ] || [ "$want" = signup ]; then
  echo; echo "== signup code =="
  CODE_PORT=$((PORT + 1))
  mkdir -p "$TMP/pb_code"
  ./bin/pocketbase migrate up --dir="$TMP/pb_code" --migrationsDir=./pb_migrations >/dev/null 2>&1
  ./bin/pocketbase superuser upsert test@cxi.local test-superuser-pass --dir="$TMP/pb_code" >/dev/null 2>&1
  CXI_SIGNUP_CODE=open-sesame-test ./bin/pocketbase serve --http="127.0.0.1:$CODE_PORT" --dir="$TMP/pb_code" \
    --migrationsDir=./pb_migrations --hooksDir=./pb_hooks --publicDir=./public >"$TMP/pb_code.log" 2>&1 &
  PIDS+=($!)
  for i in $(seq 1 30); do curl -sf "http://127.0.0.1:$CODE_PORT/api/health" >/dev/null && break; sleep 0.3; done
  CXI_TEST_URL="http://127.0.0.1:$CODE_PORT" node tests/signup_code.js || status=1
fi

echo; [ "$status" = 0 ] && echo "ALL GREEN" || echo "SOMETHING FAILED (logs in tests/.tmp)"
exit $status
