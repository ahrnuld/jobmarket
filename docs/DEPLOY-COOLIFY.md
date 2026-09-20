# Deploying on a VPS with Coolify

The stack is defined in [docker-compose.yml](../docker-compose.yml):

| Service | What it does | RAM |
| --- | --- | --- |
| `worker` | Weekly pipeline run (ingest, statistics, classify, aggregate, validate, publish) and static site build | ~15 MB idle, ~400 MB for ~10 s during the weekly build (limit 1 GB) |
| `web` | nginx serving the built site | ~5 MB (limit 128 MB) |

The public site never talks to the worker; nginx only serves files the worker built. Every
(re)deploy rebuilds the site from the latest published data; every weekly run rebuilds it only
if a new snapshot passed validation (NFR-07).

## 1. Create the resource

1. Push this repository to a git host Coolify can reach (GitHub, GitLab, Gitea, ...).
2. In Coolify: **New resource → Application → (your git source)**, pick the repository and branch.
3. **Build pack: Docker Compose**, compose file `docker-compose.yml` (repository root).
4. On the **`web`** service set the domain, e.g. `https://ict-arbeidsmarkt.nl` (port 80). Coolify's
   proxy handles TLS. Do not give `worker` a domain.

## 2. Environment variables

Set these in the resource's **Environment Variables** screen (mark the Adzuna keys as secret):

| Variable | Value |
| --- | --- |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Your Adzuna credentials |
| `SITE_URL` | The public URL, same as the `web` domain (for canonical/hreflang links) |
| `JOBMARKET_ENV` | Leave **empty** for now. Set to `production` once licences are checked (`terms_checked_on` in `data/reference/sources.yaml`) and the example rows in `data/manual/*.csv` are replaced; production refuses to publish otherwise |
| `SCHEDULE` | Default `daily 05:00`. Daily is what the collection assumes: a vacancy is sometimes online for only a few days. A weekday + time (`mon 05:00`) also works, but then set `JOBMARKET_INGEST_DAYS=8` |
| `SCHEDULE_TZ` | Default `Europe/Amsterdam` |
| `RUN_ON_START` | `yes` for the first deploy only (runs the pipeline job right away), then back to `no` |
| `JOBMARKET_INGEST_DAYS` | `30` for the first run (see below), then empty. Empty means the default window of 2 days |
| `SCHEDULER` | `on` (default). Use `off` if you prefer Coolify's **Scheduled Tasks**: add a daily task on the `worker` service with command `/app/docker/weekly.sh` |

## Checking the state

```bash
docker exec -it <worker> jobmarket status
```

Shows what the database holds (vacancies, how many are in a COROP area, which runs happened),
what the aggregate history holds (months, and whether it has rows per COROP area), and which
files the published snapshot has.

Every deploy brings the volumes up to date with the code before it republishes: months the
database no longer covers are taken from the history in the image where that one holds more
detail (`jobmarket history repair`), then `process` and `aggregate` recompute everything the
database does cover. None of that contacts a source, so it costs no API calls.

## Sources

Two vacancy sources run in the daily job. **Adzuna** needs the key in `ADZUNA_APP_ID` /
`ADZUNA_APP_KEY` and has plan limits (see below). **EURES** needs no key and no account: it is
the European Commission's public portal, filled for the Netherlands by UWV. Its daily run costs
about a dozen search calls plus one call per new vacancy (roughly 200), paced a second apart, so
it takes a few minutes. Both are capped per run in `data/reference/ingestion.yaml`.

## Call budget

Adzuna's plan allows 25 calls a minute, 250 a day, 1,000 a week and 2,500 a month. The worker
keeps its own ledger (`api_calls` in the database) and stops cleanly before a limit is reached,
so several runs on one day cannot together overshoot. The daily job costs about 27 calls
(~800 a month).

```bash
docker exec -it <worker> jobmarket budget
```

Reaching back in time is possible but of limited use: the source only serves vacancies that are
still listed, so about 30% of the ads from a month ago and about 5% of those from six months ago
remain. `jobmarket ingest --source adzuna --days 365 --backfill` stores what it finds without
letting it into the published figures (useful as extra material for the labelled sample), and
costs roughly 450 calls, so it stops on the daily limit and continues the next day.

## 3. First deploy: continuity with your local data

The history in `data/aggregates/` (committed) is copied into the server's volume on first start,
so the trend history continues. The working database starts empty; the pipeline protects history
months the new database only covers partly (it keeps the committed version and logs a warning).

To close the gap between your last local run and the first server run:

- **Option A (simplest):** set `JOBMARKET_INGEST_DAYS=30` and `RUN_ON_START=yes` for the first
  deploy. A 30-day fetch uses about 180 of the 250 daily Adzuna calls. Afterwards clear both.
- **Option B (no gap at all):** copy your local database into the worker's volume before the
  first run, then restart the worker:

  ```bash
  docker cp var/jobmarket.sqlite <worker-container>:/app/var/jobmarket.sqlite
  ```

  Find the container name in Coolify (or `docker ps | grep worker`) on the VPS.

## 4. Updating code, methodology or manual figures

Commit and push; Coolify redeploys (enable auto-deploy on push, or press Deploy). Reference data,
corrections, the changelog and `data/manual/*.csv` come from the repository, so edits there take
effect on the next weekly run. To apply them right away:

```bash
docker exec <worker-container> /app/docker/weekly.sh
```

The server's volumes stay the source of truth for data: a redeploy never overwrites the history,
the published snapshot or the database.

## 5. Backups

What matters is the **`jobmarket-history`** volume (the monthly aggregates; the trend history
cannot be rebuilt once vacancy texts have expired). Two options:

- Back up the Docker volume with your VPS backup tooling.
- Or download the published CSVs regularly: `https://<your domain>/data/csv/` contains the same
  history (except job titles that occur fewer than 3 times).

The `jobmarket-var` volume (database) is useful but replaceable: losing it only costs the
deduplication window and texts within the retention period.

## 6. Checking that it works

- Worker log (Coolify → worker → Logs): `[scheduler] next run at ...`, and after a run
  `Published snapshot ...` and `[build-site] now serving ...`.
- `https://<your domain>/healthz` returns `ok`.
- The footer of the site shows the date of the data.

Not tested here: the images were not built on this development machine (no Docker installed).
The scripts were syntax-checked and the pipeline and site were tested outside containers.
