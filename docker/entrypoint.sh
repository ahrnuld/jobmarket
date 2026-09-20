#!/bin/sh
# Worker start-up: seed empty volumes, build the site from the current data, then run the
# scheduler (daily by default; or exit if SCHEDULER=off, e.g. with Coolify's Scheduled Tasks).
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

# Re-derive everything this release computes from the stored vacancies, then republish: a
# volume written by an older release holds classifications and aggregates from the old rules,
# and can miss files this version expects. No source is contacted here, so it costs no API
# calls. A rejected publish keeps the previous snapshot (NFR-07).
jobmarket init-db || true
jobmarket process || echo "[entrypoint] process failed (see the error above)"
# Months this database cannot compute itself (it holds fewer vacancies of them than the history
# in the image was computed from) are taken from that history: a release can add a breakdown or
# correct a mapping, and the figures of such a month change without this database changing.
jobmarket history repair --source /app/seed/aggregates || true
jobmarket aggregate || echo "[entrypoint] aggregate failed (see the error above)"
jobmarket publish || echo "[entrypoint] publish failed (see the error above)"

# If the volume still lacks files this release needs, the snapshot in it is older than the code.
# Replace it as a whole with the one shipped in the image, so the site never misses a page.
missing=""
for f in meta.json stats.json map.json; do
  [ -f "/app/site/public/data/$f" ] || missing="$missing $f"
done
if [ -n "$missing" ]; then
  echo "[entrypoint] published snapshot misses:$missing -> restoring the snapshot from the image"
  cp -a /app/seed/published/. /app/site/public/data/
fi

# Every (re)deploy rebuilds the site from the latest published data with the new code.
/app/docker/build-site.sh

if [ "${RUN_ON_START:-no}" = "yes" ]; then
  echo "[entrypoint] RUN_ON_START=yes: running the pipeline job now"
  /app/docker/weekly.sh || echo "[entrypoint] job failed; the site keeps its last snapshot"
fi

if [ "${SCHEDULER:-on}" = "off" ]; then
  echo "[entrypoint] SCHEDULER=off: not scheduling; keeping the container alive for exec/tasks"
  exec tail -f /dev/null
fi
exec python -m jobmarket.scheduler
