#!/bin/sh
# The weekly job: ingest, statistics, process, aggregate, validate + publish; then rebuild the
# site, but only when a new snapshot was published. A rejected snapshot leaves the site as is.
set -u

echo "[weekly] start $(date -u +%FT%TZ)"
if jobmarket run; then
  /app/docker/build-site.sh
  echo "[weekly] done"
else
  echo "[weekly] snapshot not published (see messages above); site unchanged"
  exit 1
fi
