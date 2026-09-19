"""Processing after ingestion: normalise, locate, deduplicate, classify, purge old texts.

Everything here is recomputed from the stored vacancies on every run, so a change in the
reference data or corrections applies to all history that still has its text. Vacancies whose
text has been purged (DR-07) keep their stored classification; corrections still apply to them.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jobmarket import corrections as corr
from jobmarket.classify import CLASSIFIER_VERSION, Classification, classify
from jobmarket.clean import geo, language
from jobmarket.clean.dedupe import deduplicate
from jobmarket.clean.normalise import normalise_employer, normalise_location, normalise_title
from jobmarket.db import utc_now
from jobmarket.reference import Reference


@dataclass
class ProcessResult:
    vacancies: int
    duplicates: int
    ict: int
    purged: int


def normalise_all(conn: sqlite3.Connection, ref: Reference) -> None:
    rows = conn.execute(
        "SELECT id, title, employer, location_raw, area_json, description FROM vacancies"
    ).fetchall()
    updates = []
    for r in rows:
        place = geo.resolve(json.loads(r["area_json"] or "[]"), r["location_raw"], ref)
        lang = language.detect(r["description"]) if r["description"] is not None else None
        updates.append(
            (
                normalise_title(r["title"]),
                normalise_employer(r["employer"]),
                normalise_location(place.municipality, place.province),
                place.municipality,
                place.labour_market_region,
                place.province,
                lang,
                r["id"],
            )
        )
    conn.executemany(
        """UPDATE vacancies SET title_norm = ?, employer_norm = ?, location_norm = ?,
           municipality = ?, labour_market_region = ?, province = ?,
           language = COALESCE(?, language) WHERE id = ?""",
        updates,
    )


def _stored(conn: sqlite3.Connection, row: sqlite3.Row) -> Classification:
    programmes = {
        p["programme_id"]: p["role_family"]
        for p in conn.execute(
            "SELECT programme_id, role_family FROM vacancy_programmes WHERE vacancy_id = ?",
            (row["id"],),
        )
    }
    skills = [
        s["skill_id"]
        for s in conn.execute(
            "SELECT skill_id FROM vacancy_skills WHERE vacancy_id = ?", (row["id"],)
        )
    ]
    return Classification(bool(row["is_ict"]), row["seniority"] or "unknown", programmes, skills)


def classify_all(conn: sqlite3.Connection, ref: Reference, corrections: list) -> None:
    by_title = corr.index_by_title(corrections)
    rows = conn.execute(
        """SELECT id, title, title_norm, description, description_purged_at, source_category,
                  is_ict, seniority FROM vacancies"""
    ).fetchall()
    now = utc_now()
    for r in rows:
        if r["description_purged_at"]:
            result = _stored(conn, r)
        else:
            result = classify(
                r["title"], r["title_norm"], r["description"], r["source_category"], ref
            )
        result = corr.apply(result, by_title.get(r["title_norm"], []))
        conn.execute(
            """UPDATE vacancies SET is_ict = ?, seniority = ?, classifier_version = ?,
               classified_at = ? WHERE id = ?""",
            (int(result.is_ict), result.seniority, CLASSIFIER_VERSION, now, r["id"]),
        )
        conn.execute("DELETE FROM vacancy_programmes WHERE vacancy_id = ?", (r["id"],))
        conn.executemany(
            "INSERT INTO vacancy_programmes (vacancy_id, programme_id, role_family) "
            "VALUES (?, ?, ?)",
            [(r["id"], p, f) for p, f in result.programmes.items()],
        )
        conn.execute("DELETE FROM vacancy_skills WHERE vacancy_id = ?", (r["id"],))
        conn.executemany(
            "INSERT INTO vacancy_skills (vacancy_id, skill_id, esco_uri) VALUES (?, ?, ?)",
            [(r["id"], s, ref.skills[s].esco_uri) for s in result.skills if s in ref.skills],
        )


def purge_expired_texts(
    conn: sqlite3.Connection, ref: Reference, now: datetime | None = None
) -> int:
    """DR-07: drop description texts older than the source's retention period."""
    now = now or datetime.now(UTC)
    purged = 0
    for source in ref.sources.values():
        if source.raw_retention_days is None:
            continue
        cutoff = (
            (now - timedelta(days=source.raw_retention_days)).replace(microsecond=0).isoformat()
        )
        cur = conn.execute(
            """UPDATE vacancies SET description = NULL, description_purged_at = ?
               WHERE source_id = ? AND description_purged_at IS NULL AND retrieved_at < ?""",
            (utc_now(), source.id, cutoff),
        )
        purged += cur.rowcount
    return purged


def process(conn: sqlite3.Connection, ref: Reference, corrections: list) -> ProcessResult:
    normalise_all(conn, ref)
    duplicates = deduplicate(conn)
    # Classify before purging, so texts that expire today are classified one last time.
    classify_all(conn, ref, corrections)
    purged = purge_expired_texts(conn, ref)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
    ict = conn.execute(
        "SELECT COUNT(*) FROM vacancies WHERE is_ict = 1 AND duplicate_of IS NULL"
    ).fetchone()[0]
    return ProcessResult(total, duplicates, ict, purged)
