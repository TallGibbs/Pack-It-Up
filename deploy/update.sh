#!/usr/bin/env bash
# Pull new code and restart the API. Run as root:  sudo bash /opt/pack-it-up/deploy/update.sh [--force]
# A restart stops any move still being processed, so by default this waits until no move
# has changed for 90 seconds (the same rule the team used on the demo laptop). --force skips the wait.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pack-it-up}"
APP_USER="${APP_USER:-packitup}"
QUIET_SECONDS="${QUIET_SECONDS:-90}"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
cd "$APP_DIR"

before=$(sudo -u "$APP_USER" git rev-parse --short HEAD)
sudo -u "$APP_USER" git pull --ff-only
after=$(sudo -u "$APP_USER" git rev-parse --short HEAD)
echo "Code: $before -> $after"
sudo -u "$APP_USER" .venv/bin/pip install -q -r requirements.txt

# Unit files may have changed too.
for unit in packitup.service packitup-cleanup.service packitup-cleanup.timer; do
  sed "s#/opt/pack-it-up#$APP_DIR#g; s#^User=packitup#User=$APP_USER#; s#^Group=packitup#Group=$APP_USER#" \
    "deploy/$unit" > "/etc/systemd/system/$unit"
done
systemctl daemon-reload

if [ "$FORCE" -eq 0 ] && [ -d runs ]; then
  for _ in $(seq 1 40); do
    busy=$(find runs -mindepth 2 -maxdepth 2 -name status.json -newermt "-$QUIET_SECONDS seconds" | head -1)
    [ -z "$busy" ] && break
    echo "Waiting: $(dirname "$busy") changed in the last $QUIET_SECONDS s"
    sleep 15
  done
  [ -z "$busy" ] || { echo "Moves are still busy; run again later or use --force." >&2; exit 1; }
fi

systemctl restart packitup.service
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && { echo "API restarted on $after"; exit 0; }
  sleep 1
done
echo "API did not come back: journalctl -u packitup -n 50" >&2
exit 1
