# Worker: runs the weekly pipeline and builds the static site into a shared volume.
# Python for the pipeline, Node for the Astro build.

FROM node:24-bookworm-slim AS node

FROM python:3.12-slim-bookworm

# Node + npm from the official Node image (no extra package sources needed)
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JOBMARKET_ROOT=/app \
    ASTRO_TELEMETRY_DISABLED=1

WORKDIR /app

# Dependencies first, for layer caching
COPY site/package.json site/package-lock.json site/
RUN cd site && npm ci --no-audit --no-fund

COPY pipeline/pyproject.toml pipeline/
COPY pipeline/src pipeline/src
RUN pip install -e ./pipeline

# Everything else: reference data, manual statistics, corrections, changelog, site source
COPY . .

# Seed copies of the committed history and published data. On first start the entrypoint copies
# them into the (empty) volumes; after that the volumes are the source of truth.
RUN mkdir -p /app/seed \
 && cp -a /app/data/aggregates /app/seed/aggregates \
 && cp -a /app/site/public/data /app/seed/published \
 && chmod +x /app/docker/*.sh

VOLUME ["/app/var", "/app/data/aggregates", "/app/site/public/data", "/srv/www"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD test -f /srv/www/current/nl/index.html || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
