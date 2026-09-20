#!/bin/sh
# Worker start-up: seed empty volumes, build the site from the current data, then run the
# weekly scheduler (or exit if SCHEDULER=off, e.g. when Coolify's Scheduled Tasks are used).
set -eu

seed() {  # seed <volume dir> <seed dir>
  if [ -z "$(ls -A "$1" 2>/dev/null)" ]; then
    echo "[entrypoint] seeding $1 from the image"
    mkdir -p "$1"
    cp -a "$2/." "$1/"
  fi
}

seed /app/data/aggregates /app/seed/aggregates
seed /app/site/public/data /app/seed/published
mkdir -p /app/var /srv/www

# Republish from the aggregate history first: a data volume written by an older release can
# miss files this version expects. A rejected publish keeps the previous snapshot (NFR-07).
jobmarket init-db || true
jobmarket publish || echo "[entrypoint] publish failed; keeping the published snapshot"

# Every (re)deploy rebuilds the site from the latest published data with the new code.
/app/docker/build-site.sh

if [ "${RUN_ON_START:-no}" = "yes" ]; then
  echo "[entrypoint] RUN_ON_START=yes: running the weekly job now"
  /app/docker/weekly.sh || echo "[entrypoint] weekly job failed; the site keeps its last snapshot"
fi

if [ "${SCHEDULER:-on}" = "off" ]; then
  echo "[entrypoint] SCHEDULER=off: not scheduling; keeping the container alive for exec/tasks"
  exec tail -f /dev/null
fi
exec python -m jobmarket.scheduler
