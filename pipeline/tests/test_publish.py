from __future__ import annotations

import dataclasses
import json
from datetime import date

import pytest

from jobmarket.aggregate import (
    annual_salary,
    compute,
    display_title,
    merge_into_history,
    read_history,
    repair_from_seed,
    salary_bucket,
)
from jobmarket.config import load_settings
from jobmarket.ingest import ingest
from jobmarket.models import VacancyRecord
from jobmarket.process import process
from jobmarket.publish import publish
from jobmarket.sources import fixtures
from jobmarket.validate import validate

TODAY = date(2026, 9, 19)


@pytest.mark.parametrize(
    "lo, hi, predicted, expected",
    [
        (40000, 50000, 0, 45000),
        (3000, 3500, 0, 39000),  # monthly -> annual
        (300, 300, 0, None),  # day or hour rate: unit unknown
        (40000, 50000, 1, None),  # estimated by source
        (None, None, None, None),
        (600000, 600000, 0, None),
    ],
)
def test_annual_salary(lo, hi, predicted, expected):
    assert annual_salary(lo, hi, predicted) == expected


@pytest.mark.parametrize(
    "lo, hi, expected",
    [
        (500, 500, 6000),  # monthly allowance (stored as annual, like every salary)
        (300, 600, 5400),
        (1800, 2000, 22800),
        (15, 15, None),  # hourly rate
        (3000, 3500, None),  # a junior salary on a posting classified as internship
        (6000, 6000, None),  # no annual allowances: internships last months
        (40000, 45000, None),
    ],
)
def test_internship_allowance(lo, hi, expected):
    assert annual_salary(lo, hi, 0, seniority="internship") == expected


def test_salary_buckets():
    assert salary_bucket(6000) == 6000  # 600-wide below 30,000
    assert salary_bucket(6250) == 6000
    assert salary_bucket(41000) == 40000  # 2,500-wide above
    assert salary_bucket(30100) == 30000


def test_display_title_drops_levels():
    assert display_title("senior java developer") == "java developer"


@pytest.fixture
def loaded(conn, ref):
    ingest(conn, "fixture", fixtures.generate(n=2500, months=12, end=TODAY), ref)
    process(conn, ref, [])
    return conn


@pytest.fixture
def settings(tmp_path):
    s = load_settings()
    return dataclasses.replace(
        s,
        history_dir=tmp_path / "aggregates",
        publish_dir=tmp_path / "site" / "published",
        snapshots_dir=tmp_path / "snapshots",
    )


def test_aggregate_counts_are_consistent(loaded):
    agg = compute(loaded, sample=True, today=TODAY)
    total = sum(
        r["n"]
        for r in agg.rows["vacancies"]
        if r["geo"] == "nl" and r["programme"] == "all" and r["seniority"] == "all"
    )
    unique_ict = loaded.execute(
        "SELECT COUNT(*) FROM vacancies WHERE is_ict = 1 AND duplicate_of IS NULL"
    ).fetchone()[0]
    assert total == unique_ict
    entry = sum(
        r["n"]
        for r in agg.rows["vacancies"]
        if r["geo"] == "nl" and r["programme"] == "all" and r["seniority"] == "entry"
    )
    parts = sum(
        r["n"]
        for r in agg.rows["vacancies"]
        if r["geo"] == "nl"
        and r["programme"] == "all"
        and r["seniority"] in ("internship", "junior")
    )
    assert entry == parts
    months = {r["month"]: r["partial"] for r in agg.rows["months"]}
    assert months["2026-09"] == 1  # current month is partial
    assert compute(loaded, sample=False, today=TODAY).months == []  # real and sample never mix


def test_internship_allowances_stay_out_of_salary_totals(loaded):
    rows = compute(loaded, sample=True, today=TODAY).rows["salaries"]
    nl = [r for r in rows if r["geo"] == "nl" and r["programme"] == "all"]
    intern = [r for r in nl if r["seniority"] == "internship"]
    assert intern, "fixture internships state an allowance"
    assert all(r["bucket"] < 12_000 for r in intern)  # 300-750 a month
    # 'all' and 'entry' contain real salaries only
    assert all(r["bucket"] >= 12_000 for r in nl if r["seniority"] in ("all", "junior"))
    assert not [r for r in nl if r["seniority"] == "entry"]


def test_history_keeps_months_no_longer_in_database(loaded, tmp_path):
    history = tmp_path / "agg"
    merge_into_history(history, compute(loaded, sample=True, today=TODAY))
    before = {r["month"] for r in read_history(history, "vacancies")}
    loaded.execute("DELETE FROM vacancy_programmes")
    loaded.execute("DELETE FROM vacancy_skills")
    loaded.execute("UPDATE vacancies SET duplicate_of = NULL")
    loaded.execute("DELETE FROM vacancies WHERE posted_at < '2026-06-01'")
    merge_into_history(history, compute(loaded, sample=True, today=TODAY))
    after = {r["month"] for r in read_history(history, "vacancies")}
    assert before == after


def test_fresh_database_does_not_overwrite_complete_history(conn, ref, tmp_path):
    """New server: the history has all of September, the new database only its last week."""
    history = tmp_path / "agg"

    def rec(i, posted):
        return VacancyRecord(
            source_id="adzuna",
            external_id=str(i),
            title="Java Developer",
            posted_at=posted,
            employer=f"E{i}",
            area=["Nederland"],
            description="Java",
            source_category="it-jobs",
        )

    # Old setup: a full month, fetched with coverage from 1 September
    ingest(
        conn,
        "adzuna",
        [rec(i, f"2026-09-{d:02d}") for i, d in enumerate(range(1, 31))],
        ref,
        covers_from="2026-09-01",
    )
    process(conn, ref, [])
    merge_into_history(history, compute(conn, sample=False, today=date(2026, 10, 5)))
    full = [
        r
        for r in read_history(history, "vacancies")
        if r["geo"] == "nl" and r["programme"] == "all" and r["seniority"] == "all"
    ]
    assert [(r["month"], r["n"]) for r in full] == [("2026-09", "30")]

    # New server: empty database, first run covers 22 September onwards
    conn.execute("DELETE FROM vacancy_programmes")
    conn.execute("DELETE FROM vacancy_skills")
    conn.execute("DELETE FROM vacancies")
    conn.execute("DELETE FROM ingestion_runs")
    ingest(
        conn,
        "adzuna",
        [rec(100 + d, f"2026-09-{d:02d}") for d in range(22, 31)]
        + [rec(200 + d, f"2026-10-0{d}") for d in range(1, 5)],
        ref,
        covers_from="2026-09-22",
    )
    process(conn, ref, [])
    result = merge_into_history(history, compute(conn, sample=False, today=date(2026, 10, 5)))
    assert result.protected == ["2026-09"]
    after = {
        r["month"]: r["n"]
        for r in read_history(history, "vacancies")
        if r["geo"] == "nl" and r["programme"] == "all" and r["seniority"] == "all"
    }
    assert after == {"2026-09": "30", "2026-10": "4"}  # September kept, October added


def test_publish_writes_snapshot(loaded, ref, settings):
    merge_into_history(settings.history_dir, compute(loaded, sample=True, today=TODAY))
    result = publish(
        loaded, ref, settings, dataset="sample", history_dir=settings.history_dir, today=TODAY
    )
    assert result.published, result.report.errors
    meta = json.loads((settings.publish_dir / "meta.json").read_text("utf-8"))
    assert meta["dataset"] == "sample"
    assert any("synthetic" in w for w in meta["validation"]["warnings"])
    assert (settings.publish_dir / "geo" / "nl" / "vacancies.json").is_file()
    assert (settings.publish_dir / "csv" / "skills.csv").is_file()
    stats_csv = settings.publish_dir / "csv" / "statistics.csv"
    assert stats_csv.read_text("utf-8").startswith("series,")


def test_map_data_is_published_per_corop_area(loaded, ref, settings):
    merge_into_history(settings.history_dir, compute(loaded, sample=True, today=TODAY))
    result = publish(
        loaded, ref, settings, dataset="sample", history_dir=settings.history_dir, today=TODAY
    )
    assert result.published, result.report.errors
    data = json.loads((settings.publish_dir / "map.json").read_text("utf-8"))
    assert len(data["corops"]) == len(ref.corops)
    assert {c["code"] for c in data["corops"]} == {c.code for c in ref.corops.values()}
    known = {c["id"] for c in data["corops"]}
    assert data["rows"] and all(r[1] in known for r in data["rows"])
    # A COROP area is map detail, not a geography the visitor can filter on, and it gets no
    # files of its own.
    meta = json.loads((settings.publish_dir / "meta.json").read_text("utf-8"))
    assert not [g for g in meta["geos"] if g["id"].startswith("c:")]
    assert not list((settings.publish_dir / "geo").glob("c-*"))
    # The map never counts more vacancies than the country as a whole.
    nl = json.loads((settings.publish_dir / "geo" / "nl" / "vacancies.json").read_text("utf-8"))
    national = sum(n for _mi, p, s, n in nl if p == "all" and s == "all")
    on_map = sum(r[4] for r in data["rows"] if r[2] == "all" and r[3] == "all")
    assert 0 < on_map <= national


def test_publishes_into_a_directory_that_cannot_be_replaced(loaded, ref, settings, monkeypatch):
    """On a server the published directory is a mounted volume: renaming it raises EBUSY."""
    import errno
    from pathlib import Path

    merge_into_history(settings.history_dir, compute(loaded, sample=True, today=TODAY))
    settings.publish_dir.mkdir(parents=True, exist_ok=True)
    (settings.publish_dir / "stale.json").write_text("{}", encoding="utf-8")
    real_rename = Path.rename

    def rename(self, target):
        if self == settings.publish_dir:
            raise OSError(errno.EBUSY, "Device or resource busy")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    result = publish(
        loaded, ref, settings, dataset="sample", history_dir=settings.history_dir, today=TODAY
    )
    assert result.published, result.report.errors
    assert (settings.publish_dir / "map.json").is_file()
    assert (settings.publish_dir / "geo" / "nl" / "vacancies.json").is_file()
    assert not (settings.publish_dir / "stale.json").exists()  # files of the old snapshot go


def test_production_refuses_sample_data_and_keeps_old_snapshot(loaded, ref, settings, monkeypatch):
    merge_into_history(settings.history_dir, compute(loaded, sample=True, today=TODAY))
    first = publish(
        loaded, ref, settings, dataset="sample", history_dir=settings.history_dir, today=TODAY
    )
    assert first.published
    monkeypatch.setenv("JOBMARKET_ENV", "production")
    second = publish(
        loaded, ref, settings, dataset="sample", history_dir=settings.history_dir, today=TODAY
    )
    assert not second.published
    assert any("synthetic" in e for e in second.report.errors)
    meta = json.loads((settings.publish_dir / "meta.json").read_text("utf-8"))
    assert meta["snapshot_id"] == first.snapshot_id  # NFR-07: last good snapshot stays


def test_sync_tree_replaces_and_removes_files(tmp_path):
    from jobmarket.publish import _sync_tree

    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "geo" / "nl").mkdir(parents=True)
    (src / "meta.json").write_text("new", "utf-8")
    (src / "geo" / "nl" / "a.json").write_text("a", "utf-8")
    (dst / "geo" / "old").mkdir(parents=True)
    (dst / "meta.json").write_text("old", "utf-8")
    (dst / "geo" / "old" / "stale.json").write_text("x", "utf-8")
    _sync_tree(src, dst)
    assert (dst / "meta.json").read_text("utf-8") == "new"
    assert (dst / "geo" / "nl" / "a.json").is_file()
    assert not (dst / "geo" / "old").exists()


def _meta(months, last_posted="2026-09-18", **extra):
    return {
        "snapshot_id": "20260919T120000Z",
        "dataset": "real",
        "sources": [],
        "skills": [],
        "accuracy": {"n": 200},
        "vacancies": {"months": months, "last_posted": last_posted},
        **extra,
    }


def test_validate_detects_volume_collapse():
    months = [{"month": f"2026-0{i}", "partial": False} for i in range(1, 6)]
    vac = [[i, "all", "all", 1000] for i in range(4)] + [[4, "all", "all", 100]]
    geo = {"nl": {"vacancies": vac, "titles": []}}
    report = validate(_meta(months), geo, {"observations": []}, production=False, today=TODAY)
    assert any("dropped" in e for e in report.errors)


def test_validate_detects_pii_in_titles_and_stale_data():
    months = [{"month": "2026-06", "partial": False}]
    geo = {
        "nl": {
            "vacancies": [[0, "all", "all", 10]],
            "titles": [[0, "all", "developer bel 06 12345678", 5]],
        }
    }
    report = validate(
        _meta(months, last_posted="2026-06-30"),
        geo,
        {"observations": []},
        production=False,
        today=TODAY,
    )
    assert any("personal data" in e for e in report.errors)
    assert any("days ago" in w for w in report.warnings)


def test_example_statistics_are_never_published(loaded, ref, settings):
    loaded.execute(
        "INSERT INTO stat_observations (source_id, series_id, period, period_start, breakdown, "
        "value, unit, retrieved_at, licence, is_sample) VALUES "
        "('studiekeuze123', 'sk_starting_salary', '2026', '2026-01-01', 'informatica', 3000, "
        "'eur_month_gross', '2026-09-19', 'x', 1), "
        "('studiekeuze123', 'sk_starting_salary', '2026', '2026-01-01', 'business-it-management', "
        "3312, 'eur_month_gross', '2026-09-19', 'x', 0)"
    )
    merge_into_history(settings.history_dir, compute(loaded, sample=True, today=TODAY))
    publish(loaded, ref, settings, dataset="sample", history_dir=settings.history_dir, today=TODAY)
    stats = json.loads((settings.publish_dir / "stats.json").read_text("utf-8"))
    assert [(o["breakdown"], o["value"]) for o in stats["observations"]] == [
        ("business-it-management", 3312.0)
    ]
    assert stats["series"]["sk_starting_salary"]["origin"] == "CBS Microdata"


HEADER_VACANCIES = "month,geo,programme,seniority,n\n"


def _write(path, rows: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER_VACANCIES + rows, encoding="utf-8")


def test_repair_takes_the_richer_month_from_the_shipped_history(tmp_path):
    """A release that adds a breakdown: the history in the volume predates it."""
    seed, history = tmp_path / "seed", tmp_path / "history"
    _write(seed / "vacancies.csv",
           "2026-08,nl,all,all,10\n2026-08,c:groot-amsterdam,all,all,4\n2026-09,nl,all,all,1\n")
    _write(history / "vacancies.csv",
           "2026-08,nl,all,all,10\n2026-09,nl,all,all,20\n2026-09,p:utrecht,all,all,5\n")

    replaced = repair_from_seed(seed, history)

    assert replaced == {"vacancies": 1}  # August only
    rows = read_history(history, "vacancies")
    august = [r for r in rows if r["month"] == "2026-08"]
    assert any(r["geo"] == "c:groot-amsterdam" for r in august)
    # September has more rows in the volume than in the image: the server's own version stays.
    september = [r for r in rows if r["month"] == "2026-09"]
    assert {r["geo"] for r in september} == {"nl", "p:utrecht"}


def test_repair_leaves_a_complete_history_alone(tmp_path):
    seed, history = tmp_path / "seed", tmp_path / "history"
    _write(seed / "vacancies.csv", "2026-08,nl,all,all,10\n")
    _write(history / "vacancies.csv", "2026-08,nl,all,all,10\n2026-08,c:utrecht,all,all,3\n")
    assert repair_from_seed(seed, history) == {}
    assert len(read_history(history, "vacancies")) == 2
