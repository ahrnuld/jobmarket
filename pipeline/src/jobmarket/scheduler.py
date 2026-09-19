"""Minimal weekly scheduler for the container (no cron daemon needed).

Runs JOB_COMMAND at the time given by SCHEDULE (e.g. "mon 05:00") in SCHEDULE_TZ, forever.
Output of the job goes to the container log. A failed job is logged and retried at the next
scheduled time; the site keeps its last good snapshot in the meantime (NFR-07).

    python -m jobmarket.scheduler
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_schedule(text: str) -> tuple[int, int, int]:
    """'mon 05:00' -> (0, 5, 0). Also accepts 'daily 05:00' as weekday -1."""
    day, _, hm = text.strip().lower().partition(" ")
    hour, minute = (int(x) for x in hm.split(":"))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"Invalid time in schedule {text!r}")
    if day == "daily":
        return -1, hour, minute
    if day not in DAYS:
        raise ValueError(f"Schedule {text!r} must start with one of {DAYS} or 'daily'")
    return DAYS.index(day), hour, minute


def next_run(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    """First moment after `now` (timezone-aware) matching the schedule."""
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if weekday >= 0:
        candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
    while candidate <= now:
        candidate += timedelta(days=7 if weekday >= 0 else 1)
    return candidate


def log(message: str) -> None:
    print(f"[scheduler {datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def main() -> int:
    schedule = os.environ.get("SCHEDULE", "mon 05:00")
    tz = ZoneInfo(os.environ.get("SCHEDULE_TZ", "Europe/Amsterdam"))
    command = os.environ.get("JOB_COMMAND", "/app/docker/weekly.sh")
    weekday, hour, minute = parse_schedule(schedule)
    log(f"schedule '{schedule}' ({tz.key}), job: {command}")
    while True:
        now = datetime.now(tz)
        due = next_run(now, weekday, hour, minute)
        log(f"next run at {due.isoformat()}")
        # Sleep in chunks so clock changes (DST, suspend) are picked up.
        while (remaining := (due - datetime.now(tz)).total_seconds()) > 0:
            time.sleep(min(remaining, 300))
        log("starting job")
        result = subprocess.run(command, shell=True)  # noqa: S602 - command comes from our own env
        log(f"job finished with exit code {result.returncode}")


if __name__ == "__main__":
    sys.exit(main())
