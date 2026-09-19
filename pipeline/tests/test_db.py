from __future__ import annotations

import sqlite3

import pytest

from jobmarket.db import init_schema


def test_schema_is_idempotent(conn):
    init_schema(conn)
    init_schema(conn)
    assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1


def test_sources_are_mirrored(conn):
    row = conn.execute("SELECT licence, attribution FROM sources WHERE id = 'adzuna'").fetchone()
    assert row["attribution"] == "Jobs by Adzuna"


def test_vacancy_requires_provenance_fields(conn):
    # DR-01: source, retrieval timestamp and licence are NOT NULL
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO vacancies (source_id, external_id, title, posted_at) "
            "VALUES ('adzuna', '1', 'Developer', '2026-09-01')"
        )


def test_seniority_is_constrained(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO vacancies (source_id, external_id, retrieved_at, licence, title, "
            "posted_at, seniority) VALUES ('adzuna', '1', '2026-09-01', 'x', 'Dev', "
            "'2026-09-01', 'expert')"
        )
