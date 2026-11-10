#!/usr/bin/env bash
# Start Umami on 127.0.0.1:9477. Visit data stays in the local Postgres volume.
#
# Dashboard (SSH tunnel):
#   ssh -L 9477:127.0.0.1:9477 root@<vps>
#   open http://127.0.0.1:9477
# First login is admin / umami. Change that password before adding the site.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash umami/up.sh" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed; Umami was not started." >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin is not installed; Umami was not started." >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is not installed; Umami was not started." >&2
  exit 1
fi

ENV_FILE=/etc/kfm-umami.env
if [ ! -s "$ENV_FILE" ]; then
  umask 077
  {
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
    echo "APP_SECRET=$(openssl rand -hex 32)"
    echo "TWO_FACTOR_ENCRYPTION_KEY=$(openssl rand -hex 32)"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Wrote ${ENV_FILE} (mode 600). Keep it: it is the database password."
fi

DIR=$(cd "$(dirname "$0")" && pwd)
echo "==> umami"
docker compose --env-file "$ENV_FILE" -f "$DIR/docker-compose.yml" up -d
echo "    dashboard: http://127.0.0.1:9477  (SSH tunnel; first login admin / umami)"
echo "    then set UMAMI_WEBSITE_ID in /etc/kfm-site.env and redeploy"
