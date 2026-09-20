"""Store vacancies from a source, one logged ingestion run at a time (FR-20).

All inserts of a run happen in one transaction: a run that fails halfway leaves no partial data,
only a 'failed' row in ingestion_runs with the (redacted) error message.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from jobmarket.clean.pii import scrub
from jobmarket.db import utc_now
from jobmarket.models import VacancyRecord
from jobmarket.reference import Reference


@dataclass
class IngestResult:
    run_id: int
    status: str
    fetched: int
    new: int
    error: str | None = None


def start_run(
    conn: sqlite3.Connection, source_id: str, covers_from: str | None = None, backfill: bool = False
) -> int:
    cur = conn.execute(
        "INSERT INTO ingestion_runs (source_id, started_at, status, covers_from, backfill) "
        "VALUES (?, ?, 'running', ?, ?)",
        (source_id, utc_now(), covers_from, int(backfill)),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id, status, fetched, new, error=None) -> None:
    conn.execute(
        """UPDATE ingestion_runs SET finished_at = ?, status = ?, records_fetched = ?,
           records_new = ?, error = ? WHERE id = ?""",
        (utc_now(), status, fetched, new, error, run_id),
    )
    conn.commit()


def _insert(
    conn: sqlite3.Connection, rec: VacancyRecord, run_id: int, licence: str, retrieved_at: str
) -> bool:
    if not rec.title or not rec.posted_at:
        return False
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO vacancies (
            source_id, external_id, run_id, retrieved_at, licence, is_sample, title, employer,
            location_raw, area_json, source_region_code, description, source_category,
            posted_at, salary_min, salary_max, salary_is_predicted, contract_time, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rec.source_id,
            rec.external_id,
            run_id,
            retrieved_at,
            licence,
            int(rec.is_sample),
            scrub(rec.title),
            rec.employer,
            rec.location_raw,
            json.dumps(rec.area, ensure_ascii=False),
            rec.region_code,
            scrub(rec.description),
            rec.source_category,
            rec.posted_at,
            rec.salary_min,
            rec.salary_max,
            None if rec.salary_is_predicted is None else int(rec.salary_is_predicted),
            rec.contract_time,
            rec.url,
        ),
    )
    return cur.rowcount == 1


def ingest(
    conn: sqlite3.Connection,
    source_id: str,
    records: Iterable[VacancyRecord],
    ref: Reference,
    covers_from: str | None = None,
    backfill: bool = False,
) -> IngestResult:
    """Consume `records` into the database. Exceptions from the source are caught and logged.

    covers_from: the earliest posting date this run requested (today minus max_days_old). The
    aggregation uses it to know which months the database holds completely.
    backfill: this run reached into the past, where the source only still lists a fraction of
    what was posted. Its vacancies are stored but stay out of the published aggregates.
    """
    source = ref.sources[source_id]
    run_id = start_run(conn, source_id, covers_from, backfill)
    fetched = new = 0
    try:
        retrieved_at = utc_now()
        for rec in records:
            fetched += 1
            if _insert(conn, rec, run_id, source.licence, retrieved_at):
                new += 1
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - any source failure must be logged, not crash the run
        conn.rollback()
        message = f"{type(exc).__name__}: {exc}"[:1000]
        finish_run(conn, run_id, "failed", fetched, 0, message)
        return IngestResult(run_id, "failed", fetched, 0, message)
    finish_run(conn, run_id, "success", fetched, new)
    return IngestResult(run_id, "success", fetched, new)
