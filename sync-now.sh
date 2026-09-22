#!/usr/bin/env bash
# Invoked by the release deploy key (forced SSH command) or manually.
set -euo pipefail
set -a
# shellcheck disable=SC1091
. /etc/kfm-site.env
set +a
exec /usr/bin/node /opt/kfm-site/fetch-companion.mjs
