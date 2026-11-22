#!/usr/bin/env bash
# First-time setup of Pack It Up on a Linux server (Ubuntu 24.04 or Debian 12 or later; needs Python 3.11+).
# Run as root:  sudo bash deploy/setup.sh            (from a checkout, or download this file alone)
#               sudo bash deploy/setup.sh --cloudflared   also installs cloudflared from Cloudflare's apt repo
# Safe to run again: it skips what is already done. It never overwrites .env.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pack-it-up}"
APP_USER="${APP_USER:-packitup}"
REPO_URL="${REPO_URL:-https://github.com/TallGibbs/Pack-It-Up.git}"
BRANCH="${BRANCH:-main}"
INSTALL_CLOUDFLARED=0
[ "${1:-}" = "--cloudflared" ] && INSTALL_CLOUDFLARED=1

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }

echo "== Packages"
apt-get update -q
apt-get install -y -q git python3 python3-venv curl ca-certificates
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "Python 3.11 or later is needed (the code uses tomllib)." >&2; exit 1; }

echo "== Service user $APP_USER"
id -u "$APP_USER" >/dev/null 2>&1 \
  || useradd --system --home-dir "$APP_DIR" --no-create-home --shell /usr/sbin/nologin "$APP_USER"

echo "== Code in $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
  sudo -u "$APP_USER" git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  echo "   checkout exists; use deploy/update.sh to pull new code"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "== Python packages"
[ -x "$APP_DIR/.venv/bin/python" ] || sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "== .env"
if [ ! -f "$APP_DIR/.env" ]; then
  install -m 600 -o "$APP_USER" -g "$APP_USER" "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "   created $APP_DIR/.env from .env.example: add GEMINI_API_KEY, then: systemctl restart packitup"
else
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"; chmod 600 "$APP_DIR/.env"
fi

echo "== systemd units"
for unit in packitup.service packitup-cleanup.service packitup-cleanup.timer; do
  sed "s#/opt/pack-it-up#$APP_DIR#g; s#^User=packitup#User=$APP_USER#; s#^Group=packitup#Group=$APP_USER#" \
    "$APP_DIR/deploy/$unit" > "/etc/systemd/system/$unit"
done
chmod +x "$APP_DIR/deploy/"*.sh
systemctl daemon-reload
systemctl enable --now packitup.service packitup-cleanup.timer
systemctl restart packitup.service

echo "== Health check"
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then echo "   API answers on 127.0.0.1:8000"; break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8000/health >/dev/null || { echo "API did not start: journalctl -u packitup -n 50" >&2; exit 1; }

if [ "$INSTALL_CLOUDFLARED" -eq 1 ] && ! command -v cloudflared >/dev/null; then
  echo "== cloudflared"
  install -d -m 0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
    > /etc/apt/sources.list.d/cloudflared.list
  apt-get update -q && apt-get install -y -q cloudflared
  echo "   installed; set up the tunnel as in DEPLOY.md, step 5"
fi

grep -q '^GEMINI_API_KEY=.\+' "$APP_DIR/.env" || echo "NOTE: GEMINI_API_KEY is empty in $APP_DIR/.env; model calls will fail until it is set."
echo "Done."
