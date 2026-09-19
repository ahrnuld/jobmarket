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

## Status

Built step by step:

1. [x] Repository skeleton, data model, reference data (programmes, seniority, skills + ESCO, regions)
2. [ ] Vacancy pipeline: Adzuna client and fixtures, PII scrubbing, deduplication, classification
3. [ ] Statistics: CBS API, HBO-Monitor / ROA / UWV manual tables
4. [ ] Aggregation, validation, publishing, and the static site (FR-01 to FR-07)
5. [ ] Trends, programme comparison, NL/EN, CSV downloads (FR-08 to FR-11)
6. [ ] Admin tooling, accuracy measurement, scheduling, handover guide
