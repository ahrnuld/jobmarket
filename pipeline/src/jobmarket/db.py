"""SQLite connection and schema management."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = 7

# Upgrades from version N to N+1. schema.sql always describes the latest version, and a fresh
# database is created from it directly; these only run on older databases.
# Each step is (table, column, type): the column is added if the table exists; a missing table
# is created by schema.sql afterwards, already with the column.
MIGRATIONS: dict[int, tuple[str, str, str]] = {
    1: ("stat_observations", "value_label", "TEXT"),
    2: ("ingestion_runs", "covers_from", "TEXT"),
    3: ("vacancies", "multi_location", "INTEGER NOT NULL DEFAULT 0"),
    4: ("vacancies", "corop", "TEXT"),
    5: ("ingestion_runs", "backfill", "INTEGER NOT NULL DEFAULT 0"),
    6: ("vacancies", "source_region_code", "TEXT"),
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def connect(db_path: Path | str) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    version = None
    if exists:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        version = row["version"] if row else None
    if version is not None and version < SCHEMA_VERSION:
        for v in range(version, SCHEMA_VERSION):
            table, column, col_type = MIGRATIONS[v]
            columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if columns and column not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    elif version is not None and version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is newer than this code ({SCHEMA_VERSION})."
        )
    sql = resources.files("jobmarket").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql)  # CREATE ... IF NOT EXISTS: adds tables new in this version
    if version is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


@contextmanager
def open_db(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        init_schema(conn)
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
