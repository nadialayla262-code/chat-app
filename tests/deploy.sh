#!/usr/bin/env bash
# The box setup: syntax, a dry run that changes nothing, and rendered files that say what they must.
set -uo pipefail
cd "$(dirname "$0")/.."
ok=0; fail() { echo "FAIL: $*"; ok=1; }

bash -n deploy/install.sh || fail "install.sh does not parse"
for f in deploy/units/*.service deploy/units/*.timer deploy/Caddyfile deploy/env.example deploy/README.md; do [ -s "$f" ] || fail "missing $f"; done

# usage errors
./deploy/install.sh --dry-run >/dev/null 2>&1 && fail "no arguments should be refused"
./deploy/install.sh --dry-run only-domain >/dev/null 2>&1 && fail "one argument should be refused"

# dry run: every step printed, nothing written
out="$(./deploy/install.sh --dry-run cxi.test.local owner@test.local --with-ollama 2>&1)" || fail "dry run exited non-zero"
for want in "useradd" "apt-get install" "rsync" "/etc/cxi/env" "cxi-spine.service" "cxi-backup.timer" "Caddyfile for cxi.test.local" "ufw allow 443" "ollama"; do
  echo "$out" | grep -q -- "$want" || fail "dry run did not mention: $want"
done
[ -e /etc/cxi ] && [ "$(id -u)" != 0 ] && fail "dry run wrote to /etc/cxi"
echo "$out" | grep -q "rules applied" || fail "no rules line"

# the units point at real files in this repository, with the same flags the dev script uses
for u in cxi-spine cxi-homei cxi-handi cxi-backup; do
  grep -q "^EnvironmentFile=/etc/cxi/env" "deploy/units/$u.service" || fail "$u has no EnvironmentFile"
  grep -q "^User=cxi" "deploy/units/$u.service" || fail "$u does not run as cxi"
done
grep -q -- "--hooksDir=/opt/cxi/app/pb_hooks" deploy/units/cxi-spine.service || fail "spine unit misses hooksDir"
grep -q -- "--migrationsDir=/opt/cxi/app/pb_migrations" deploy/units/cxi-spine.service || fail "spine unit misses migrationsDir"
grep -q "homei.py" deploy/units/cxi-homei.service || fail "homei unit"
grep -q "handi.py" deploy/units/cxi-handi.service || fail "handi unit"
grep -q "backup.py /opt/cxi/backups" deploy/units/cxi-backup.service || fail "backup unit"
grep -q "OnCalendar=" deploy/units/cxi-backup.timer || fail "timer has no schedule"
grep -q "reverse_proxy 127.0.0.1:8090" deploy/Caddyfile || fail "Caddyfile does not proxy the spine"
for v in CXI_PB_URL CXI_DESK_OWNERS CXI_SIGNUP_CODE CXI_SUPERUSER_EMAIL CXI_SUPERUSER_PASSWORD CXI_OLLAMA_HOST; do
  grep -q "^$v=" deploy/env.example || fail "env.example lacks $v"
done
# the language rule
# (the one fixed systemd command name that carries the word is not ours to rename)
grep -rniE "\b(kill|spawn|child|parent|orphan|daemon)\b" deploy/ | grep -v "systemctl daemon-reload" | grep -q . && fail "forbidden word in deploy/"

[ "$ok" = 0 ] && echo "deploy: OK"
exit $ok
