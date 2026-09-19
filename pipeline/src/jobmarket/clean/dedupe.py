"""Deduplication (DR-02): same normalised title, employer and location within 30 days.

Vacancies are processed in posting order. The first posting of a (title, employer, location) key
becomes the original; a later posting with the same key within WINDOW_DAYS of that original is
marked duplicate_of it. A posting more than WINDOW_DAYS after the original starts a new original,
because a vacancy that is still open after a month counts again in the next month's figures.

Postings without an employer are only compared with other postings without an employer.
Sample (fixture) and real records are never compared with each other.
"""

from __future__ import annotations

import sqlite3
from datetime import date

WINDOW_DAYS = 30


def deduplicate(conn: sqlite3.Connection) -> int:
    """Recompute duplicate_of for all vacancies. Returns the number of duplicates."""
    rows = conn.execute(
        """
        SELECT id, title_norm, employer_norm, location_norm, posted_at, is_sample
        FROM vacancies
        ORDER BY posted_at, id
        """
    ).fetchall()
    originals: dict[tuple, tuple[int, date]] = {}
    updates: list[tuple[int | None, int]] = []
    duplicates = 0
    for r in rows:
        key = (r["is_sample"], r["title_norm"], r["employer_norm"], r["location_norm"])
        posted = date.fromisoformat(r["posted_at"])
        original = originals.get(key)
        if original and (posted - original[1]).days <= WINDOW_DAYS:
            updates.append((original[0], r["id"]))
            duplicates += 1
        else:
            originals[key] = (r["id"], posted)
            updates.append((None, r["id"]))
    conn.executemany("UPDATE vacancies SET duplicate_of = ? WHERE id = ?", updates)
    return duplicates
