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
| `data/reference/` | Hand-maintained methodology: sources and licences, programmes and role families, seniority rules, skills vocabulary, ESCO links, regions |
| `data/manual/` | Figures from sources without an API (HBO-Monitor, ROA, UWV), typed over from the published tables |
| `data/aggregates/` | Monthly aggregates, one CSV per metric. The durable trend history (DR-07, DR-09) |
| `data/corrections.yaml` | Admin mapping corrections, append-only log (FR-21) |
| `data/changelog.yaml` | Public methodology changelog (FR-22, TR-06) |
| `data/labels/` | Manually labelled vacancy sample for accuracy measurement (TR-05) |
| `pipeline/` | Python package `jobmarket` and its tests |
| `site/` | Astro static site |
| `var/` | Working database and snapshots. Git-ignored because it holds raw vacancy text |

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

**ESCO links are resolved, then reviewed.** `jobmarket reference resolve-esco` queries the ESCO
API and writes `data/reference/esco_links.yaml` with `checked: false`. ESCO has no concepts for
several current tools (Docker, Kubernetes, Kotlin, Go, Spark); those link to a broader concept
(e.g. "DevOps", "cloud technologies") or to nothing.
