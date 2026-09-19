# HBO-ICT Job Market Insights

An independent website that shows HBO bachelor ICT students in the Netherlands what the job
market asks for: vacancy volumes, in-demand skills, starting salaries and trends, per study
programme and at junior level. Requirements: [REQUIREMENTS.md](REQUIREMENTS.md).
Design and decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "pipeline[dev]"
.\.venv\Scripts\python.exe -m pytest pipeline
.\.venv\Scripts\jobmarket.exe reference check
.\.venv\Scripts\jobmarket.exe init-db
```

On macOS or Linux, use `.venv/bin/...` instead.

## Running the vacancy pipeline

Put your Adzuna credentials in `.env` (copy `.env.example`; never commit it). Then:

```powershell
.\.venv\Scripts\jobmarket.exe ingest --source adzuna            # last 8 days (weekly run)
.\.venv\Scripts\jobmarket.exe ingest --source adzuna --days 30  # backfill
.\.venv\Scripts\jobmarket.exe process                           # clean, deduplicate, classify
```

Published statistics (CBS via its API; HBO-Monitor, ROA and UWV from `data/manual/*.csv`, see
[data/manual/README.md](data/manual/README.md)):

```powershell
.\.venv\Scripts\jobmarket.exe stats
```

Without credentials, use synthetic data in a separate database:

```powershell
$env:JOBMARKET_DB = "var/demo.sqlite"
.\.venv\Scripts\jobmarket.exe ingest --source fixture
.\.venv\Scripts\jobmarket.exe process
```

## Status

Built step by step:

1. [x] Repository skeleton, data model, reference data (programmes, seniority, skills + ESCO, regions)
2. [x] Vacancy pipeline: Adzuna client and fixtures, PII scrubbing, deduplication, classification
3. [x] Statistics: CBS API, HBO-Monitor / ROA / UWV manual tables
4. [ ] Aggregation, validation, publishing, and the static site (FR-01 to FR-07)
5. [ ] Trends, programme comparison, NL/EN, CSV downloads (FR-08 to FR-11)
6. [ ] Admin tooling, accuracy measurement, scheduling, handover guide
