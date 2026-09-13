#!/usr/bin/env bash
# start.sh brings the spine and both seats up; stop.sh takes them down. Alternate port, real pb_data untouched.
set -uo pipefail
cd "$(dirname "$0")/.."
TMP="$(pwd)/tests/.tmp/startstop"; rm -rf "$TMP"; mkdir -p "$TMP"
fails=0
check() { if [ "$2" = 0 ]; then echo "  ok   $1"; else echo "  FAIL $1"; fails=$((fails+1)); fi; }
# run from a copy so pb_data, .run and logs land in the temp folder
cp -r scripts pb_migrations pb_hooks public workers "$TMP/"; mkdir -p "$TMP/bin"; ln -s "$(pwd)/bin/pocketbase" "$TMP/bin/pocketbase"
rm -rf "$TMP/workers/log" "$TMP/workers/.homei-password" "$TMP/workers/.handi-password"
( cd "$TMP" && PB_PORT=8097 CXI_OLLAMA_HOST=http://127.0.0.1:11435 ./scripts/start.sh >"$TMP/start.out" 2>&1 ); check "start.sh exits 0" $?
grep -q "spine     http://127.0.0.1:8097" "$TMP/start.out"; check "reports the spine address" $?
curl -sf http://127.0.0.1:8097/api/health >/dev/null; check "spine answers" $?
sleep 2
kill -0 "$(cat "$TMP/.run/homei.pid")" 2>/dev/null; check "homei running" $?
kill -0 "$(cat "$TMP/.run/handi.pid")" 2>/dev/null; check "handi running" $?
grep -q "signed in as Homei" "$TMP/workers/log/homei.log"; check "homei signed in (log)" $?
( cd "$TMP" && PB_PORT=8097 ./scripts/start.sh >"$TMP/start2.out" 2>&1 ); grep -q "already running" "$TMP/start2.out"; check "second start says already running" $?
( cd "$TMP" && ./scripts/stop.sh >"$TMP/stop.out" 2>&1 ); check "stop.sh exits 0" $?
sleep 1
! curl -sf http://127.0.0.1:8097/api/health >/dev/null 2>&1; check "spine gone after stop" $?
[ ! -f "$TMP/.run/spine.pid" ]; check "pid files cleared" $?
( cd "$TMP" && ./scripts/stop.sh >"$TMP/stop2.out" 2>&1 ); grep -q "nothing running\|was not running" "$TMP/stop2.out"; check "second stop is harmless" $?
[ "$fails" = 0 ] && echo "startstop: all passed" || echo "startstop: $fails FAILED"
exit $fails
