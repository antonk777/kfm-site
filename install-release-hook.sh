#!/usr/bin/env bash
# Install a restricted SSH deploy key that can ONLY run sync-now.sh.
# Safe to re-run. Prints the private key once if newly created — capture it for
# the KFMLauncher secret KFM_SITE_DEPLOY_KEY (or use install from the laptop).
set -euo pipefail

SITE_DIR="${SITE_DIR:-/opt/kfm-site}"
KEY_DIR="${KEY_DIR:-/root/.ssh}"
KEY_PATH="${KEY_DIR}/kfm-site-release"
AUTH_KEYS="${KEY_DIR}/authorized_keys"
MARKER="kfm-site-release-sync"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root" >&2
  exit 1
fi

install -d -m 755 "${SITE_DIR}"
chmod 755 "${SITE_DIR}/sync-now.sh"
mkdir -p "${KEY_DIR}"
chmod 700 "${KEY_DIR}"

NEW_KEY=0
if [ ! -f "${KEY_PATH}" ]; then
  ssh-keygen -t ed25519 -N "" -C "${MARKER}" -f "${KEY_PATH}" >/dev/null
  chmod 600 "${KEY_PATH}"
  NEW_KEY=1
fi

PUB=$(cat "${KEY_PATH}.pub")
LINE="command=\"${SITE_DIR}/sync-now.sh\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ${PUB}"

touch "${AUTH_KEYS}"
chmod 600 "${AUTH_KEYS}"
if grep -qF "${MARKER}" "${AUTH_KEYS}"; then
  # Replace existing restricted line for this marker
  tmp=$(mktemp)
  grep -vF "${MARKER}" "${AUTH_KEYS}" > "${tmp}" || true
  printf '%s\n' "${LINE}" >> "${tmp}"
  mv "${tmp}" "${AUTH_KEYS}"
  chmod 600 "${AUTH_KEYS}"
else
  printf '%s\n' "${LINE}" >> "${AUTH_KEYS}"
fi

echo "OK restricted deploy key -> ${SITE_DIR}/sync-now.sh"
echo "Public: ${PUB}"
if [ "${PRINT_PRIVATE_KEY:-0}" = "1" ]; then
  echo "-----BEGIN PRIVATE KEY (set as KFMLauncher secret KFM_SITE_DEPLOY_KEY)-----"
  cat "${KEY_PATH}"
  echo "-----END PRIVATE KEY-----"
elif [ "${NEW_KEY}" = "1" ]; then
  echo "New key at ${KEY_PATH} (not printed). Set PRINT_PRIVATE_KEY=1 to show once."
fi
