"""API call budget, kept across runs (Adzuna's plan limits are per day, week and month).

The client asks `Budget.allow()` before every call and reports it with `spend()`. Counts live in
the database, so a run started an hour after the previous one still knows what was used. When a
window is exhausted the fetch stops cleanly and the run says so, instead of running into the
source's 429s.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

WINDOWS = {"day": 1, "week": 7, "month": 30}


@dataclass
class Limits:
    per_day: int | None = None
    per_week: int | None = None
    per_month: int | None = None

    def get(self, window: str) -> int | None:
        return getattr(self, f"per_{window}")


class Budget:
    """Rolling call counter per source. Windows are the last 1, 7 and 30 days (UTC).

    A rolling window is stricter than the provider's own reset moments, which we cannot see;
    staying under it therefore keeps us under theirs as well.
    """

    def __init__(
        self, conn: sqlite3.Connection, source_id: str, limits: Limits, today: date | None = None
    ):
        self.conn = conn
        self.source_id = source_id
        self.limits = limits
        self.today = today or datetime.now(UTC).date()
        self._pending = 0

    def used(self, window: str) -> int:
        since = (self.today - timedelta(days=WINDOWS[window] - 1)).isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(calls), 0) FROM api_calls WHERE source_id = ? AND day >= ?",
            (self.source_id, since),
        ).fetchone()
        return int(row[0]) + self._pending

    def remaining(self) -> dict[str, int | None]:
        return {
            w: None if (limit := self.limits.get(w)) is None else limit - self.used(w)
            for w in WINDOWS
        }

    def allow(self) -> bool:
        """True while every window with a limit still has room for one more call."""
        return all(left is None or left > 0 for left in self.remaining().values())

    def spend(self, calls: int = 1) -> None:
        self._pending += calls

    def commit(self) -> None:
        """Write the calls of this run to the database (also after a failure)."""
        if not self._pending:
            return
        self.conn.execute(
            "INSERT INTO api_calls (source_id, day, calls) VALUES (?, ?, ?) "
            "ON CONFLICT (source_id, day) DO UPDATE SET calls = calls + excluded.calls",
            (self.source_id, self.today.isoformat(), self._pending),
        )
        self.conn.commit()
        self._pending = 0

    def describe(self) -> str:
        parts = []
        for window in WINDOWS:
            limit = self.limits.get(window)
            if limit is not None:
                parts.append(f"{window}: {self.used(window)}/{limit}")
        return ", ".join(parts) or "no limits configured"
