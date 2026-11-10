#!/usr/bin/env bash
# Publish or clear $SITE_ROOT/umami-website-id from $UMAMI_WEBSITE_ID.
# The Vue page loads the tracker only when that file is a UUID.
#
#   website-id.sh check   exit 0 if the file already matches, 1 if it would change
#   website-id.sh apply   write or remove the file
set -euo pipefail

mode="${1:?usage: website-id.sh check|apply}"
: "${SITE_ROOT:?SITE_ROOT is required}"
case "$SITE_ROOT" in
  /|//) echo "refusing SITE_ROOT=$SITE_ROOT" >&2; exit 2 ;;
esac

dest="${SITE_ROOT}/umami-website-id"
id="${UMAMI_WEBSITE_ID:-}"
id="${id//$'\r'/}"
id="${id#"${id%%[![:space:]]*}"}"
id="${id%"${id##*[![:space:]]}"}"

uuid='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
if [ -n "$id" ] && ! printf '%s' "$id" | grep -Eq "$uuid"; then
  echo "UMAMI_WEBSITE_ID is not a UUID; leaving the tracker file unchanged" >&2
  exit 0
fi

current=""
if [ -f "$dest" ]; then
  current=$(tr -d '\r\n' < "$dest")
fi

if [ "$mode" = "check" ]; then
  if [ "$current" = "$id" ]; then exit 0; fi
  exit 1
fi
if [ "$mode" != "apply" ]; then
  echo "usage: website-id.sh check|apply" >&2
  exit 2
fi
if [ "$current" = "$id" ]; then exit 0; fi

if [ -z "$id" ]; then
  rm -f "$dest"
else
  mkdir -p "$SITE_ROOT"
  printf '%s\n' "$id" > "$dest"
  chmod 644 "$dest"
fi
