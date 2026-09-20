#!/usr/bin/env bash
# Bring the spine and the seats up on a box you own. One run, then it stays up.
#
#   sudo ./deploy/install.sh cxi.example.org you@example.com
#   sudo ./deploy/install.sh cxi.example.org you@example.com --with-ollama   # also the local model
#   ./deploy/install.sh --dry-run cxi.example.org you@example.com            # print, change nothing
#
# Debian 12 or Ubuntu 24.04, run as root, on a fresh machine or again later:
# every step is safe to repeat. What it does, in order:
#   1. a system account `cxi` with no shell, and /opt/cxi as its home
#   2. the packages: python3, curl, unzip, caddy (HTTPS in front of the spine)
#   3. this repository copied to /opt/cxi/app and the PocketBase binary fetched once
#   4. /etc/cxi/env from deploy/env.example (kept if it already exists; never overwritten)
#   5. systemd units: cxi-spine, cxi-homei, cxi-handi, and cxi-backup on a weekly timer
#   6. Caddy serving https://<domain> -> 127.0.0.1:8090, certificate fetched by Caddy itself
#   7. the firewall (ufw): 22, 80, 443 only
# Settings are environment variables in /etc/cxi/env, never edits. The database is
# /opt/cxi/app/pb_data. Backups land in /opt/cxi/backups (weekly, restore-tested).
#
# Nothing here reaches the Netherlands. Pick the box accordingly.
set -euo pipefail

DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
DOMAIN="${1:-}"; OWNER="${2:-}"; WITH_OLLAMA=0
[ "${3:-}" = "--with-ollama" ] && WITH_OLLAMA=1
if [ -z "$DOMAIN" ] || [ -z "$OWNER" ]; then
  echo "usage: install.sh [--dry-run] <domain> <owner-email> [--with-ollama]" >&2; exit 2
fi
if [ "$DRY" = 0 ] && [ "$(id -u)" != 0 ]; then echo "run as root (sudo)" >&2; exit 2; fi

HERE="$(cd "$(dirname "$0")/.." && pwd)"     # the repository this script lives in
APP=/opt/cxi/app; ENVF=/etc/cxi/env; BACKUPS=/opt/cxi/backups
OUT="${CXI_DEPLOY_OUT:-/}"                    # tests point this at a temp folder

run() { if [ "$DRY" = 1 ]; then echo "+ $*"; else "$@"; fi; }
put() {  # put <src> <dst-under-OUT>
  local dst="$OUT$2"
  if [ "$DRY" = 1 ]; then echo "+ install $1 -> $dst"; else install -D -m 0644 "$1" "$dst"; fi
}

echo "== 1. account"
if ! id cxi >/dev/null 2>&1; then run useradd --system --home-dir /opt/cxi --create-home --shell /usr/sbin/nologin cxi; fi

echo "== 2. packages"
run apt-get update -qq
run apt-get install -y -qq python3 curl unzip caddy ufw

echo "== 3. the app"
run mkdir -p "$APP" "$BACKUPS"
run rsync -a --delete --exclude pb_data --exclude bin --exclude .run --exclude 'workers/log' \
  --exclude 'workers/.*' --exclude 'register' --exclude 'tests/.tmp' "$HERE/" "$APP/"
if [ "$DRY" = 1 ]; then echo "+ (cd $APP && fetch PocketBase via scripts/dev.sh)"; else
  ( cd "$APP" && [ -x bin/pocketbase ] || { timeout 20 bash -c 'source ./scripts/dev.sh' >/dev/null 2>&1 || true; } )
  [ -x "$APP/bin/pocketbase" ] || { echo "PocketBase did not download; run $APP/scripts/dev.sh once by hand" >&2; exit 1; }
fi
run chown -R cxi:cxi /opt/cxi

echo "== 4. settings"
if [ -f "$OUT$ENVF" ]; then echo "keeping existing $ENVF"; else
  if [ "$DRY" = 1 ]; then echo "+ write $ENVF from deploy/env.example (owner $OWNER)"; else
    install -D -m 0640 -o root -g cxi "$HERE/deploy/env.example" "$OUT$ENVF"
    sed -i "s|^CXI_DESK_OWNERS=.*|CXI_DESK_OWNERS=$OWNER|" "$OUT$ENVF"
  fi
fi

echo "== 5. units"
for u in cxi-spine.service cxi-homei.service cxi-handi.service cxi-backup.service cxi-backup.timer; do
  put "$HERE/deploy/units/$u" "/etc/systemd/system/$u"
done
run systemctl daemon-reload
run systemctl enable --now cxi-spine.service
run systemctl enable --now cxi-homei.service cxi-handi.service
run systemctl enable --now cxi-backup.timer

echo "== 6. https"
if [ "$DRY" = 1 ]; then echo "+ write /etc/caddy/Caddyfile for $DOMAIN"; else
  sed "s|DOMAIN|$DOMAIN|" "$HERE/deploy/Caddyfile" > "$OUT/etc/caddy/Caddyfile"
fi
run systemctl enable --now caddy
run systemctl reload caddy

echo "== 7. firewall"
run ufw allow 22/tcp
run ufw allow 80/tcp
run ufw allow 443/tcp
run ufw --force enable

if [ "$WITH_OLLAMA" = 1 ]; then
  echo "== 8. the local model"
  if [ "$DRY" = 1 ]; then echo "+ install ollama; pull qwen3:4b and qwen3-embedding:0.6b"; else
    command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh
    ollama pull qwen3:4b; ollama pull qwen3-embedding:0.6b
    systemctl restart cxi-homei.service cxi-handi.service
  fi
fi

echo
echo "up: https://$DOMAIN   admin: https://$DOMAIN/_/   settings: $ENVF   data: $APP/pb_data   backups: $BACKUPS"
echo "first time: open the admin address once and create the superuser; then put its email and password in $ENVF and: systemctl restart cxi-handi"
echo "rules applied: repeat-safe; settings kept if present; database never touched by this script; nothing deleted."
