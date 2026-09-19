"""Monthly aggregates of the classified vacancies: the durable trend history (DR-07, DR-09).

Counts are computed per month x geography x programme x seniority from unique ICT vacancies
(duplicates and non-ICT vacancies excluded) and merged into CSV files under the history
directory: months that still have vacancies in the database are recomputed, older months are
kept as they are. The CSVs contain no vacancy text, so they can be committed and published.

Geography ids: 'nl', 'p:<province>', 'r:<labour market region>'.
Seniority ids: the five DR-03 levels, plus 'all' and 'entry' (= internship or junior).
Programme ids: the three programmes plus 'all' (every ICT vacancy, also those without programme).
"""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jobmarket.classify import CLASSIFIER_VERSION
from jobmarket.db import utc_now

# Salaries are stored as counts per bucket of annual gross salary; medians are read from buckets.
# Below 30,000 a year (internship allowances, low salaries) buckets are 600 wide (50 a month),
# above that 2,500. 30,000 is a multiple of both, so a bucket's width follows from its value.
# The site uses the same rule (site/src/lib/model.ts, bucketWidth).
SALARY_FINE_BELOW = 30_000
SALARY_BUCKET_FINE = 600
SALARY_BUCKET = 2500
SALARY_MIN_ANNUAL = 12_000
SALARY_MAX_ANNUAL = 250_000
# Internship allowances ("stagevergoeding") are stated per month: an internship lasts a few
# months, so an annual amount does not occur.
INTERN_MONTHLY_MIN = 100
INTERN_MONTHLY_MAX = 2_000
LEVEL_WORDS = {
    "junior",
    "jr",
    "medior",
    "senior",
    "sr",
    "lead",
    "principal",
    "staff",
    "stagiair",
    "stagiaire",
    "intern",
    "trainee",
    "werkstudent",
    "ervaren",
    "experienced",
}

TABLES = {
    "vacancies": ["month", "geo", "programme", "seniority", "n"],
    "skills": ["month", "geo", "programme", "seniority", "skill", "n"],
    "families": ["month", "geo", "programme", "family", "n"],
    "titles": ["month", "geo", "programme", "title", "n"],
    "salaries": ["month", "geo", "programme", "seniority", "bucket", "n"],
    "months": [
        "month",
        "first_posted",
        "last_posted",
        "partial",
        "computed_at",
        "classifier_version",
    ],
}


def annual_salary(
    salary_min: float | None,
    salary_max: float | None,
    predicted: int | None,
    seniority: str | None = None,
) -> float | None:
    """Annual gross salary (or internship allowance) midpoint; None when absent, estimated or of
    unknown unit.

    Postings state amounts per year, month, day or hour without saying which.
    - Internships: only 100-2,000 counts, as a monthly allowance (internships last months, so
      there are no annual amounts). Anything else is dropped: hourly rates, or a real salary on
      a posting classified as an internship (more likely a misclassification than an allowance).
    - Other levels: 12,000 and up is annual, 1,000-12,000 monthly; lower values (day or hour
      rates) and values above 250,000 are dropped.
    """
    if predicted:
        return None
    values = [v for v in (salary_min, salary_max) if v]
    if not values:
        return None
    mid = sum(values) / len(values)
    if seniority == "internship":
        if INTERN_MONTHLY_MIN <= mid <= INTERN_MONTHLY_MAX:
            return mid * 12  # stored like all salaries as an annual figure; the site divides by 12
        return None
    if 1_000 <= mid < SALARY_MIN_ANNUAL:
        mid *= 12
    if not SALARY_MIN_ANNUAL <= mid <= SALARY_MAX_ANNUAL:
        return None
    return mid


def salary_bucket(annual: float) -> int:
    width = SALARY_BUCKET_FINE if annual < SALARY_FINE_BELOW else SALARY_BUCKET
    return int(annual // width * width)


def display_title(title_norm: str) -> str:
    """Title without seniority words, for 'typical job titles' (FR-02)."""
    return " ".join(w for w in title_norm.split() if w not in LEVEL_WORDS)


@dataclass
class Aggregates:
    rows: dict[str, list[dict]]
    months: list[str]


def _geos(province: str | None, region: str | None) -> list[str]:
    geos = ["nl"]
    if province:
        geos.append(f"p:{province}")
    if region:
        geos.append(f"r:{region}")
    return geos


def compute(conn: sqlite3.Connection, sample: bool, today: date | None = None) -> Aggregates:
    today = today or date.today()
    vacancies = conn.execute(
        """
        SELECT id, substr(posted_at, 1, 7) AS month, posted_at, province, labour_market_region,
               seniority, title_norm, salary_min, salary_max, salary_is_predicted
        FROM vacancies
        WHERE is_ict = 1 AND duplicate_of IS NULL AND is_sample = ?
        """,
        (int(sample),),
    ).fetchall()
    programmes: dict[int, list[tuple[str, str]]] = {}
    for r in conn.execute("SELECT vacancy_id, programme_id, role_family FROM vacancy_programmes"):
        programmes.setdefault(r[0], []).append((r[1], r[2]))
    skills: dict[int, list[str]] = {}
    for r in conn.execute("SELECT vacancy_id, skill_id FROM vacancy_skills"):
        skills.setdefault(r[0], []).append(r[1])

    counts = {name: Counter() for name in TABLES if name != "months"}
    posted: dict[str, list[str]] = {}
    for v in vacancies:
        month = v["month"]
        posted.setdefault(month, []).append(v["posted_at"])
        geos = _geos(v["province"], v["labour_market_region"])
        progs = programmes.get(v["id"], [])
        prog_ids = ["all"] + [p for p, _ in progs]
        level = v["seniority"] or "unknown"
        levels = ["all", level] + (["entry"] if level in ("internship", "junior") else [])
        salary = annual_salary(
            v["salary_min"], v["salary_max"], v["salary_is_predicted"], seniority=level
        )
        # An internship allowance is not a salary: it is kept under 'internship' only, never
        # mixed into 'all' or 'entry' (which would otherwise mix allowances with junior pay).
        salary_levels = ["internship"] if level == "internship" else ["all", level]
        bucket = salary_bucket(salary) if salary is not None else None
        title = display_title(v["title_norm"] or "")
        for g in geos:
            for p in prog_ids:
                for s in levels:
                    counts["vacancies"][(month, g, p, s)] += 1
                    for sk in skills.get(v["id"], []):
                        counts["skills"][(month, g, p, s, sk)] += 1
                if bucket is not None:
                    for s in salary_levels:
                        counts["salaries"][(month, g, p, s, bucket)] += 1
                if title:
                    counts["titles"][(month, g, p, title)] += 1
            for p, family in progs:
                counts["families"][(month, g, p, family)] += 1
            for family in {f for _, f in progs}:  # a family can serve two programmes
                counts["families"][(month, g, "all", family)] += 1

    rows = {}
    for name, counter in counts.items():
        cols = TABLES[name]
        rows[name] = [dict(zip(cols, (*key, n), strict=True)) for key, n in counter.items()]

    all_posted = sorted(p for ps in posted.values() for p in ps)
    series_start = all_posted[0] if all_posted else None
    now = utc_now()
    rows["months"] = []
    for month in sorted(posted):
        first, last = min(posted[month]), max(posted[month])
        # Partial: the month the series starts in (unless it starts on the 1st) or the
        # current month, which is still running.
        partial = (month == series_start[:7] and not series_start.endswith("-01")) or (
            month == today.isoformat()[:7]
        )
        rows["months"].append(
            {
                "month": month,
                "first_posted": first,
                "last_posted": last,
                "partial": int(partial),
                "computed_at": now,
                "classifier_version": CLASSIFIER_VERSION,
            }
        )
    return Aggregates(rows=rows, months=sorted(posted))


def read_history(history_dir: Path, name: str) -> list[dict]:
    path = history_dir / f"{name}.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def merge_into_history(history_dir: Path, agg: Aggregates) -> dict[str, int]:
    """Replace the recomputed months in the history CSVs; keep all other months."""
    history_dir.mkdir(parents=True, exist_ok=True)
    recomputed = set(agg.months)
    written = {}
    for name, cols in TABLES.items():
        kept = [r for r in read_history(history_dir, name) if r["month"] not in recomputed]
        merged = kept + [{k: str(v) for k, v in r.items()} for r in agg.rows[name]]
        merged.sort(key=lambda r: tuple(r[c] for c in cols[:-1]))
        path = history_dir / f"{name}.csv"
        tmp = path.with_suffix(".csv.tmp")
        with tmp.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            writer.writeheader()
            writer.writerows(merged)
        tmp.replace(path)
        written[name] = len(merged)
    return written
