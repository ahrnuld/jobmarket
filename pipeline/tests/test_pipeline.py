"""End-to-end tests of ingest -> process on synthetic data."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from jobmarket import corrections as corr
from jobmarket.ingest import ingest
from jobmarket.models import VacancyRecord
from jobmarket.process import process, purge_expired_texts
from jobmarket.sources import fixtures


def rec(i, title="Junior Java Developer", posted="2026-09-01", employer="Voorbeeld BV", **kw):
    return VacancyRecord(
        source_id="adzuna",
        external_id=str(i),
        title=title,
        posted_at=posted,
        employer=employer,
        area=["Nederland", "Noord-Holland", "Haarlem"],
        description=kw.pop("description", "Je werkt met Java en SQL in een Scrum-team."),
        source_category="it-jobs",
        **kw,
    )


def test_ingest_is_idempotent_and_scrubs_pii(conn, ref):
    records = [rec(1, description="Bel Sanne de Vries op 06-12345678 of mail sanne@x.nl.")]
    first = ingest(conn, "adzuna", records, ref)
    second = ingest(conn, "adzuna", records, ref)
    assert (first.new, second.new) == (1, 0)
    text = conn.execute("SELECT description FROM vacancies").fetchone()[0]
    assert "Sanne" not in text and "12345678" not in text and "sanne@x.nl" not in text
    row = conn.execute("SELECT licence, retrieved_at FROM vacancies").fetchone()
    assert row["licence"] and row["retrieved_at"]  # DR-01


def test_failed_source_leaves_no_partial_data(conn, ref):
    def broken():
        yield rec(1)
        raise RuntimeError("API down")

    result = ingest(conn, "adzuna", broken(), ref)
    assert result.status == "failed"
    assert conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0] == 0
    run = conn.execute("SELECT status, error FROM ingestion_runs").fetchone()
    assert run["status"] == "failed" and "API down" in run["error"]


def test_deduplication_window(conn, ref):
    ingest(
        conn,
        "adzuna",
        [
            rec(1, posted="2026-06-01"),
            rec(2, title="Junior Java Developer (m/v/x)", posted="2026-06-20"),  # repost: duplicate
            rec(3, posted="2026-07-15"),  # 44 days after original: counts again
            rec(4, posted="2026-06-05", employer="Ander Bedrijf BV"),  # other employer
        ],
        ref,
    )
    result = process(conn, ref, [])
    assert result.duplicates == 1
    dup = conn.execute(
        "SELECT external_id FROM vacancies WHERE duplicate_of IS NOT NULL"
    ).fetchall()
    assert [r[0] for r in dup] == ["2"]


def test_classification_is_stored(conn, ref):
    ingest(conn, "adzuna", [rec(1), rec(2, title="Werkvoorbereider", description="Excel.")], ref)
    process(conn, ref, [])
    rows = {r["external_id"]: r for r in conn.execute("SELECT * FROM vacancies")}
    assert rows["1"]["is_ict"] == 1 and rows["1"]["seniority"] == "junior"
    assert rows["1"]["province"] == "noord-holland" and rows["1"]["language"] == "nl"
    assert rows["2"]["is_ict"] == 0
    skills = {
        r[0]
        for r in conn.execute(
            "SELECT skill_id FROM vacancy_skills WHERE vacancy_id = ?", (rows["1"]["id"],)
        )
    }
    assert {"java", "sql", "agile-scrum"} <= skills


def test_corrections_override_rules(conn, ref, tmp_path):
    path = tmp_path / "corrections.yaml"
    path.write_text("corrections: []\n", encoding="utf-8")
    corr.append_correction(
        path,
        ref,
        {
            "author": "admin",
            "type": "seniority",
            "match": "Junior Java Developer",
            "value": "medior",
            "reason": "test",
        },
    )
    corr.append_correction(
        path,
        ref,
        {
            "author": "admin",
            "type": "programme",
            "match": "junior java developer",
            "value": ["informatica", "technische-informatica"],
            "reason": "test",
        },
    )
    loaded = corr.load_corrections(path, ref)
    assert len(loaded) == 2
    ingest(conn, "adzuna", [rec(1)], ref)
    process(conn, ref, loaded)
    assert conn.execute("SELECT seniority FROM vacancies").fetchone()[0] == "medior"
    progs = {r[0] for r in conn.execute("SELECT programme_id FROM vacancy_programmes")}
    assert progs == {"informatica", "technische-informatica"}


def test_invalid_correction_is_rejected(ref, tmp_path):
    path = tmp_path / "corrections.yaml"
    with pytest.raises(corr.CorrectionError):
        corr.append_correction(
            path,
            ref,
            {"author": "a", "type": "seniority", "match": "x", "value": "expert", "reason": "r"},
        )


def test_retention_purges_text_but_keeps_classification(conn, ref):
    ingest(conn, "adzuna", [rec(1)], ref)
    process(conn, ref, [])
    later = datetime.now(UTC) + timedelta(days=ref.sources["adzuna"].raw_retention_days + 1)
    assert purge_expired_texts(conn, ref, now=later) == 1
    process(conn, ref, [])  # reprocessing a purged vacancy keeps its skills
    row = conn.execute("SELECT description, seniority FROM vacancies").fetchone()
    assert row["description"] is None and row["seniority"] == "junior"
    assert conn.execute("SELECT COUNT(*) FROM vacancy_skills").fetchone()[0] >= 2


def test_fixture_run_end_to_end(conn, ref):
    records = list(fixtures.generate(n=1500, months=24, end=date(2026, 9, 19)))
    assert all(r.is_sample for r in records)
    ingest(conn, "fixture", records, ref)
    result = process(conn, ref, [])
    assert result.vacancies == 1500
    assert 0.03 < result.duplicates / 1500 < 0.12
    levels = dict(
        conn.execute(
            "SELECT seniority, COUNT(*) FROM vacancies WHERE is_ict = 1 GROUP BY seniority"
        ).fetchall()
    )
    assert set(levels) == {"internship", "junior", "medior", "senior", "unknown"}
    noise = conn.execute(
        "SELECT COUNT(*) FROM vacancies WHERE title = 'Werkvoorbereider' AND is_ict = 1"
    ).fetchone()[0]
    assert noise == 0
    leaked = conn.execute(
        "SELECT COUNT(*) FROM vacancies WHERE description LIKE '%06-12345678%' "
        "OR description LIKE '%@voorbeeld.invalid%' OR description LIKE '%Sanne de Vries%'"
    ).fetchone()[0]
    assert leaked == 0


def test_spray_postings_count_once_and_only_nationally(conn, ref):
    """An agency posts one role in many villages on one day: one vacancy, no region."""
    from jobmarket.aggregate import compute

    villages = [
        ["Nederland", "Noord-Brabant", "Vught", "Cromvoirt"],
        ["Nederland", "Noord-Holland", "Drechterland", "Westwoud"],
        ["Nederland", "Zuid-Holland", "Schiedam"],
        ["Nederland", "Groningen", "Groningen"],
    ]
    spray = [
        VacancyRecord(
            source_id="adzuna",
            external_id=f"s{i}",
            title="Junior Monitoring Engineer",
            posted_at="2026-09-19",
            employer="Hallo",
            area=a,
            description="Linux",
            source_category="it-jobs",
        )
        for i, a in enumerate(villages)
    ]
    two_offices = [
        rec(10, employer="Echt Bedrijf BV", posted="2026-09-10"),
        VacancyRecord(
            **{
                **rec(11, employer="Echt Bedrijf BV", posted="2026-09-10").__dict__,
                "area": ["Nederland", "Utrecht", "Utrecht"],
            }
        ),
    ]
    ingest(conn, "adzuna", spray + two_offices, ref)
    process(conn, ref, [])
    rows = conn.execute(
        "SELECT employer, COUNT(*), SUM(multi_location) FROM vacancies "
        "WHERE duplicate_of IS NULL GROUP BY employer ORDER BY employer"
    ).fetchall()
    assert [tuple(r) for r in rows] == [("Echt Bedrijf BV", 2, 0), ("Hallo", 1, 1)]
    agg = compute(conn, sample=False, today=date(2026, 9, 20))
    geos = {r["geo"] for r in agg.rows["vacancies"] if r["seniority"] == "junior"}
    # The two real offices count in their regions; the spray posting only nationally.
    junior_by_geo = {
        r["geo"]: r["n"]
        for r in agg.rows["vacancies"]
        if r["seniority"] == "junior" and r["programme"] == "all"
    }
    assert junior_by_geo["nl"] == 3
    assert "p:groningen" not in geos and "p:noord-brabant" not in geos
