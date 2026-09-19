#!/bin/sh
# Build the static site from site/public/data into a new release directory and switch the
# `current` symlink to it atomically. nginx serves /srv/www/current. A failed build leaves the
# previous release online (NFR-07).
set -eu

WWW=/srv/www
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RELEASE="$WWW/releases/$STAMP"

cd /app/site
echo "[build-site] building into $RELEASE"
rm -rf dist
npm run build --silent
mkdir -p "$WWW/releases"
cp -a dist "$RELEASE"

# Atomic switch: create the new link next to the old one, then rename over it.
ln -sfn "releases/$STAMP" "$WWW/current.tmp"
mv -T "$WWW/current.tmp" "$WWW/current"
echo "[build-site] now serving $STAMP"

# Keep the three most recent releases.
ls -1d "$WWW"/releases/*/ 2>/dev/null | sort | head -n -3 | while read -r old; do
  rm -rf "$old"
done
