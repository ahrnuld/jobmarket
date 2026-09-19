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
)
from jobmarket.config import load_settings
from jobmarket.ingest import ingest
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
