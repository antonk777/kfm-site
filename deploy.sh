#!/usr/bin/env bash
# Deploy KF-Maniacs site to a Caddy host and refresh Companion from GitHub.
#
# Usage (on the VPS, as root or with sudo):
#   export COMPANION_GITHUB_TOKEN=ghp_...
#   sudo -E bash deploy.sh
#
# Optional env:
#   SITE_DOMAIN=kfm.manul.lol
#   SITE_ROOT=/var/www/kfm.manul.lol
#   SITE_LOG=/var/log/caddy/kfm.manul.lol.log
#   CADDY_EMAIL=admin@manul.lol
#   SKIP_FETCH=1          # only sync static files / Caddyfile
#   INSTALL_CADDY=1       # apt-install caddy if missing
set -euo pipefail

SITE_DOMAIN="${SITE_DOMAIN:-kfm.manul.lol}"
SITE_ROOT="${SITE_ROOT:-/var/www/${SITE_DOMAIN}}"
SITE_LOG="${SITE_LOG:-/var/log/caddy/${SITE_DOMAIN}.log}"
SITE_IP="${SITE_IP:-85.192.30.108}"
CADDY_EMAIL="${CADDY_EMAIL:-admin@manul.lol}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Load secrets/paths when present (COMPANION_GITHUB_TOKEN, …).
if [ -f /etc/kfm-site.env ]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/kfm-site.env
  set +a
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root (needs write to ${SITE_ROOT} and caddy reload): sudo -E bash deploy.sh" >&2
  exit 1
fi

if [ "${INSTALL_CADDY:-0}" = "1" ] && ! command -v caddy >/dev/null 2>&1; then
  echo "==> install Caddy"
  apt-get update -y
  apt-get install -y --no-install-recommends debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -y
  apt-get install -y caddy
fi

if ! command -v caddy >/dev/null 2>&1; then
  echo "caddy not found; install it or re-run with INSTALL_CADDY=1" >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "==> install nodejs"
  apt-get update -y
  apt-get install -y --no-install-recommends nodejs
fi

echo "==> sync static files -> ${SITE_ROOT}"
mkdir -p "${SITE_ROOT}" "$(dirname "${SITE_LOG}")" /var/lib/kfm-site
# Caddy runs as user `caddy` and must own its log directory.
if id caddy >/dev/null 2>&1; then
  chown -R caddy:caddy "$(dirname "${SITE_LOG}")"
fi
install -m 644 "${SCRIPT_DIR}/index.html" "${SITE_ROOT}/index.html"
install -m 644 "${SCRIPT_DIR}/favicon.ico" "${SITE_ROOT}/favicon.ico"
install -m 644 "${SCRIPT_DIR}/kf-maniacs-logo.svg" "${SITE_ROOT}/kf-maniacs-logo.svg"

if [ "${SKIP_FETCH:-0}" != "1" ]; then
  if [ -z "${COMPANION_GITHUB_TOKEN:-}${GITHUB_TOKEN:-}" ]; then
    echo "Set COMPANION_GITHUB_TOKEN (or GITHUB_TOKEN) to fetch Companion." >&2
    exit 1
  fi
  echo "==> fetch Companion into ${SITE_ROOT}"
  SITE_ROOT="${SITE_ROOT}" \
    COMPANION_GITHUB_TOKEN="${COMPANION_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}" \
    COMPANION_REPO="${COMPANION_REPO:-antonk777/KFMLauncher}" \
    node "${SCRIPT_DIR}/fetch-companion.mjs"
fi

STATS_PORT="${STATS_PORT:-8765}"

echo "==> install Caddyfile"
install -d /etc/caddy
# Bake paths so the caddy systemd unit does not need SITE_* env.
# Overwrite the package default Caddyfile — a global { email } block must be first.
sed \
  -e "s|{\$SITE_DOMAIN:kfm.manul.lol}|${SITE_DOMAIN}|g" \
  -e "s|{\$SITE_ROOT:/var/www/kfm.manul.lol}|${SITE_ROOT}|g" \
  -e "s|{\$SITE_LOG:/var/log/caddy/kfm.manul.lol.log}|${SITE_LOG}|g" \
  -e "s|{\$CADDY_EMAIL:admin@manul.lol}|${CADDY_EMAIL}|g" \
  -e "s|{\$SITE_IP:85.192.30.108}|${SITE_IP}|g" \
  -e "s|{\$STATS_PORT:8765}|${STATS_PORT}|g" \
  "${SCRIPT_DIR}/Caddyfile" > /etc/caddy/Caddyfile
chmod 644 /etc/caddy/Caddyfile
# Keep a copy named by domain for reference / multi-site later.
cp -f /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.${SITE_DOMAIN}"

echo "==> stats API (secret /statistics/)"
install -m 644 "${SCRIPT_DIR}/systemd/kfm-stats.service" /etc/systemd/system/kfm-stats.service
systemctl daemon-reload
systemctl enable --now kfm-stats.service
systemctl restart kfm-stats.service

echo "==> validate + reload Caddy"
caddy validate --config /etc/caddy/Caddyfile
if systemctl is-active --quiet caddy; then
  systemctl reload caddy
else
  systemctl enable --now caddy
fi

echo "==> done"
echo "    site:  https://${SITE_DOMAIN}/"
echo "    ip:    http://${SITE_IP}/"
echo "    file:  ${SITE_ROOT}/release.json"
echo "    dl:    https://${SITE_DOMAIN}/download"
echo "    logs:  ${SITE_LOG}"
echo "    stats: SITE_LOG=${SITE_LOG} node ${SCRIPT_DIR}/download-stats.mjs"
echo "    charts: https://${SITE_DOMAIN}/statistics/ (unlisted)"
