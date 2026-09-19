from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from jobmarket.scheduler import next_run, parse_schedule

AMS = ZoneInfo("Europe/Amsterdam")


def test_parse():
    assert parse_schedule("mon 05:00") == (0, 5, 0)
    assert parse_schedule("Sun 23:30") == (6, 23, 30)
    assert parse_schedule("daily 04:15") == (-1, 4, 15)
    with pytest.raises(ValueError):
        parse_schedule("someday 05:00")
    with pytest.raises(ValueError):
        parse_schedule("mon 25:00")


def test_next_weekly_run():
    sat = datetime(2026, 9, 19, 17, 0, tzinfo=AMS)  # a Saturday
    assert next_run(sat, 0, 5, 0) == datetime(2026, 9, 21, 5, 0, tzinfo=AMS)
    mon_early = datetime(2026, 9, 21, 4, 59, tzinfo=AMS)
    assert next_run(mon_early, 0, 5, 0) == datetime(2026, 9, 21, 5, 0, tzinfo=AMS)
    mon_late = datetime(2026, 9, 21, 5, 0, tzinfo=AMS)
    assert next_run(mon_late, 0, 5, 0) == datetime(2026, 9, 28, 5, 0, tzinfo=AMS)


def test_next_daily_run():
    now = datetime(2026, 9, 19, 17, 0, tzinfo=AMS)
    assert next_run(now, -1, 4, 0) == datetime(2026, 9, 20, 4, 0, tzinfo=AMS)
