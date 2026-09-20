from __future__ import annotations

from datetime import date

import pytest

from jobmarket.aggregate import compute, coverage_start
from jobmarket.budget import Budget, Limits
from jobmarket.db import connect, init_schema
from jobmarket.ingest import ingest
from jobmarket.models import VacancyRecord
from jobmarket.sources.adzuna import AdzunaClient, AdzunaConfig

TODAY = date(2026, 9, 20)


@pytest.fixture
def db():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _budget(conn, **limits):
    return Budget(conn, "adzuna", Limits(**limits), today=TODAY)


def test_counts_survive_the_run_that_spent_them(db):
    first = _budget(db, per_day=10)
    first.spend(4)
    first.commit()
    assert _budget(db, per_day=10).used("day") == 4
    assert _budget(db, per_day=10).remaining()["day"] == 6


def test_a_window_without_a_limit_never_blocks(db):
    budget = _budget(db)
    budget.spend(10_000)
    assert budget.allow()
    assert budget.remaining() == {"day": None, "week": None, "month": None}


def test_the_narrowest_window_stops_the_run(db):
    db.execute("INSERT INTO api_calls (source_id, day, calls) VALUES ('adzuna', '2026-09-19', 40)")
    budget = _budget(db, per_day=50, per_week=45, per_month=1000)
    assert budget.used("day") == 0  # yesterday is outside the day window
    assert budget.used("week") == 40
    budget.spend(4)
    assert budget.allow()  # 44 of the 45 the week allows
    budget.spend(1)
    assert not budget.allow()  # the week is full, even though the day is not


def test_calls_of_another_source_do_not_count(db):
    db.execute(
        "INSERT INTO api_calls (source_id, day, calls) VALUES ('other', ?, 99)",
        (TODAY.isoformat(),),
    )
    assert _budget(db, per_day=10).used("day") == 0


class FakeApi:
    """Returns one page of one result, forever: paging stops on the budget, not on the data."""

    def __init__(self):
        self.calls = 0

    def __call__(self, url):
        self.calls += 1
        return {
            "count": 10_000,
            "results": [
                {"id": f"{self.calls}", "title": "Developer", "created": "2026-09-19T10:00:00Z"}
            ],
        }


def test_client_stops_on_the_plan_limit_and_says_so(db):
    config = AdzunaConfig(
        app_id="x",
        app_key="y",
        max_calls_per_run=100,
        max_calls_per_day=3,
        queries=[{"id": "q", "params": {}}],
    )
    budget = _budget(db, per_day=3)
    client = AdzunaClient(config, http_get=FakeApi(), sleep=lambda s: None, budget=budget)
    list(client.fetch(days=3))
    assert client.stats.calls == 3
    assert client.stats.budget_exhausted
    assert "plan limit" in (client.stats.budget_note or "")
    budget.commit()
    assert _budget(db, per_day=3).remaining()["day"] == 0


def _record(ext: str, posted: str) -> VacancyRecord:
    return VacancyRecord(
        source_id="adzuna",
        external_id=ext,
        title="Java Developer",
        posted_at=posted,
        employer="ACME",
        location_raw="Alkmaar",
        area=["Nederland", "Noord-Holland", "Alkmaar"],
        description="Java, SQL.",
        source_category="it-jobs",
    )


def test_backfilled_months_stay_out_of_the_published_figures(conn, ref):
    from jobmarket.process import process

    db = conn  # this one needs the sources table filled, for the foreign key on a run
    ingest(db, "adzuna", [_record("new", "2026-09-10")], ref, covers_from="2026-09-01")
    # A backfill reaches into months the source only partly still lists.
    ingest(
        db, "adzuna", [_record("old", "2026-03-04")], ref, covers_from="2025-09-20", backfill=True
    )
    process(db, ref, [])

    assert coverage_start(db, sample=False) == "2026-09-01"
    agg = compute(db, sample=False, today=TODAY)
    assert agg.months == ["2026-09"]  # March is stored, but not counted
    assert db.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0] == 2
