"""Deduplication (DR-02): same normalised title, employer and location within 30 days.

Vacancies are processed in posting order. The first posting of a (title, employer, location) key
becomes the original; a later posting with the same key within WINDOW_DAYS of that original is
marked duplicate_of it. A posting more than WINDOW_DAYS after the original starts a new original,
because a vacancy that is still open after a month counts again in the next month's figures.

A second pass catches "spray" postings: recruitment agencies post one vacancy in many places at
once (seen in the data: the same junior role in eight villages on one day). When the same title
and employer appear in SPRAY_MIN_PLACES or more places within SPRAY_WINDOW_DAYS, the postings
count as one vacancy, flagged multi_location: its real workplace is unknown, so it counts only
in the national figures. Two places stay two vacancies (a company with two offices).

One source may name the employer where another does not (EURES carries no employer field),
so a posting without an employer also matches one with the same title and place that does have
one: the same vacancy found twice must not count twice. Sample (fixture) and real records are
never compared.
"""

from __future__ import annotations

import sqlite3
from datetime import date

WINDOW_DAYS = 30
SPRAY_WINDOW_DAYS = 7
SPRAY_MIN_PLACES = 3


def deduplicate(conn: sqlite3.Connection) -> int:
    """Recompute duplicate_of and multi_location for all vacancies. Returns the duplicates."""
    rows = conn.execute(
        """
        SELECT id, title_norm, employer_norm, location_norm, posted_at, is_sample
        FROM vacancies
        ORDER BY posted_at, id
        """
    ).fetchall()
    duplicate_of: dict[int, int | None] = {}
    originals: dict[tuple, tuple[int, date]] = {}
    for r in rows:
        key = (r["is_sample"], r["title_norm"], r["employer_norm"], r["location_norm"])
        posted = date.fromisoformat(r["posted_at"])
        original = originals.get(key)
        if original is None and not r["employer_norm"]:
            # No employer: the same title in the same place from any employer is the same
            # vacancy reaching us through a second source.
            original = next(
                (
                    o
                    for (sample, title, _employer, location), o in originals.items()
                    if (sample, title, location)
                    == (r["is_sample"], r["title_norm"], r["location_norm"])
                ),
                None,
            )
        if original and (posted - original[1]).days <= WINDOW_DAYS:
            duplicate_of[r["id"]] = original[0]
        else:
            originals[key] = (r["id"], posted)
            duplicate_of[r["id"]] = None

    # Second pass over the remaining originals: same title + employer in many places at once.
    multi: set[int] = set()
    groups: dict[tuple, list[sqlite3.Row]] = {}
    for r in rows:
        if duplicate_of[r["id"]] is None and r["employer_norm"]:
            groups.setdefault((r["is_sample"], r["title_norm"], r["employer_norm"]), []).append(r)
    for postings in groups.values():
        i = 0
        while i < len(postings):
            first = postings[i]
            start = date.fromisoformat(first["posted_at"])
            burst = [
                p
                for p in postings[i:]
                if (date.fromisoformat(p["posted_at"]) - start).days <= SPRAY_WINDOW_DAYS
            ]
            if len({p["location_norm"] for p in burst}) >= SPRAY_MIN_PLACES:
                multi.add(first["id"])
                for p in burst[1:]:
                    duplicate_of[p["id"]] = first["id"]
            i += len(burst) if len({p["location_norm"] for p in burst}) >= SPRAY_MIN_PLACES else 1

    conn.executemany(
        "UPDATE vacancies SET duplicate_of = ?, multi_location = ? WHERE id = ?",
        [(dup, int(vid in multi), vid) for vid, dup in duplicate_of.items()],
    )
    return sum(1 for d in duplicate_of.values() if d is not None)
