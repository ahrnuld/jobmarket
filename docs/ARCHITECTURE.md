# Architecture

This follows the outline in REQUIREMENTS.md section 8: a scheduled batch pipeline feeds a static
site, and the public site never queries a database.

```
data/reference/*.yaml ─┐
Adzuna / fixtures ─────┤
CBS OData API ─────────┼─> pipeline (Python) ─> var/jobmarket.sqlite  (working store, not committed)
data/manual/*.csv ─────┘        │
                                ├─> data/aggregates/*.csv     (durable trend history, committed)
                                └─> validate ─> site/public/data/*.json  (only if valid)
                                                      │
                                                      └─> Astro build ─> static HTML ─> host
```

## Repository layout

| Path | Contents |
| --- | --- |
| `data/reference/` | Hand-maintained methodology: sources and licences, programmes and role families, seniority rules, skills vocabulary, ESCO links, provinces |
| `data/reference/municipalities.csv` | Generated from the CBS area classifications by `jobmarket reference update-regions`: every municipality name since 2010 with its COROP area, labour market region and province |
| `data/manual/` | Figures from sources without an API (HBO-Monitor, ROA, UWV), typed over from the published tables |
| `data/aggregates/` | Monthly aggregates, one CSV per metric. The durable trend history (DR-07, DR-09) |
| `data/corrections.yaml` | Admin mapping corrections, append-only log (FR-21) |
| `data/changelog.yaml` | Public methodology changelog (FR-22, TR-06) |
| `data/labels/` | Manually labelled vacancy sample for accuracy measurement (TR-05) |
| `pipeline/` | Python package `jobmarket` and its tests |
| `site/` | Astro static site |
| `var/` | Working database (vacancies, runs, API call ledger) and snapshots. Git-ignored because it holds raw vacancy text |

## Decisions

**SQLite instead of PostgreSQL.** One file, no server, no monthly cost (NFR-09, NFR-10). The
pipeline runs weekly as a batch job, so concurrency is not an issue. The schema is plain SQL and
would move to PostgreSQL with minor changes.

**The database is a working store; the aggregate history lives in the repo.** Raw vacancy texts
may be kept only as long as the licence allows (DR-07), and may not be published in bulk (LR-02),
so they stay out of git. The monthly aggregates are small, contain no vacancy text, and are what
the trend pages need, so they are committed as CSV. Losing the database therefore costs at most
the deduplication window and the texts within the retention period, never the trend history.

**Methodology as data.** Role families, seniority keywords, the skills vocabulary and regions are
YAML files. A methodology change is a reviewable diff plus a changelog entry, and someone taking
over the site can adjust mappings without reading Python.

**Publish only validated snapshots (NFR-07).** The pipeline writes the new JSON to a staging
directory, validates it, and only then swaps it into `site/public/data/`. A failed
ingestion or a failed validation leaves the previous snapshot in place.

**Admin without a public admin server.** FR-20 to FR-22 are provided as `jobmarket admin ...`
commands plus a local, non-published status page. Corrections and changelog entries are
committed to the repository, so the git history is the correction log, and write access is
guarded by the git host's account security, where the owner enables two-factor authentication
(NFR-08). There is no login surface on the public site to attack.

**Fixture data until the Adzuna key exists.** A deterministic generator produces synthetic
vacancies with source `fixture`. Every figure derived from them is marked as sample data on the
site, and production mode refuses to publish them.

**Regions come from CBS, not from a hand-written list.** `jobmarket reference update-regions`
reads the CBS "Gebieden in Nederland" tables for 2010 up to the current year and writes one row
per municipality name, with its COROP area, labour market region and province. Names of
municipalities that have since been merged away are kept, because vacancies still use them
(Naarden, Sneek, Veghel). Only the provinces, a few id spellings and a handful of aliases
("Den Haag") stay by hand, in `regions.yaml`.

**The map uses COROP areas.** The 40 COROP areas are the division CBS uses for labour market
figures: large enough that a single vacancy does not make an area light up, and complete for the
whole country. Their counts ride along in the `vacancies` aggregate under geography ids
`c:<area>`, and are published separately as `map.json`; the other aggregate tables stay out of
COROP detail to keep the history files small. The boundaries (CBS/Kadaster, CC BY 4.0) sit in
`site/src/data/corop-2026.json` and are projected into SVG paths at build time, so the browser
downloads counts only, never geometry.

**A deploy re-derives before it republishes.** Classifications and aggregates are derived
data: a volume written by an earlier release holds them in the old shape, and the database can
only recompute the months it still covers. So the worker first takes months from the history
shipped in the image where that one has more rows (a release that adds a breakdown, such as
COROP areas), then runs process and aggregate, then publishes. Nothing there contacts a source.

**Collect often, never backfill counts.** The source only serves vacancies that are still
listed, so history cannot be bought back: about 30% of the ads from a month ago are still there,
about 5% of those from six months ago (measured 2026-09-20, see ingestion.yaml). The series
therefore only grows forward, and the job runs daily with a two-day window so an ad that is
online for three days is not missed. `jobmarket ingest --backfill` does reach into the past, but
marks the run: `coverage_start` ignores backfill runs and the aggregation drops everything posted
before it, so those vacancies serve the labelled sample and rule checks without ever entering a
published figure.

**The API budget is a ledger, not a per-run cap.** Adzuna's plan limits are per day, week and
month, so a per-run cap cannot honour them. `api_calls` counts calls per source per day; before
every call the client asks the rolling windows for room, and a run that runs out stops cleanly
and says which limit it hit. `jobmarket budget` shows what is left.

**ESCO links are resolved, then reviewed.** `jobmarket reference resolve-esco` queries the ESCO
API and writes `data/reference/esco_links.yaml` with `checked: false`. ESCO has no concepts for
several current tools (Docker, Kubernetes, Kotlin, Go, Spark); those link to a broader concept
(e.g. "DevOps", "cloud technologies") or to nothing.
