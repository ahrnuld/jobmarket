"""Refresh all statistics sources; each source is one logged run in ingestion_runs (FR-20).

A failing source is logged and skipped: its previously stored observations stay untouched, so
the site keeps showing the last good figures (NFR-07).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from jobmarket.db import utc_now
from jobmarket.ingest import finish_run, start_run
from jobmarket.reference import Reference
from jobmarket.stats import load_series_config, upsert
from jobmarket.stats.cbs import CbsClient
from jobmarket.stats.manual import read_file


@dataclass
class StatsResult:
    source_id: str
    status: str
    rows: int
    error: str | None = None


def refresh_cbs(
    conn: sqlite3.Connection, ref: Reference, config: dict, client: CbsClient | None = None
) -> StatsResult:
    client = client or CbsClient()
    run_id = start_run(conn, "cbs")
    total = 0
    try:
        observations = []
        for series in config.get("cbs", []):
            observations += client.fetch_series(series)
        total = upsert(conn, observations, ref.sources["cbs"].licence, utc_now())
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - logged, other sources continue
        conn.rollback()
        message = f"{type(exc).__name__}: {exc}"[:1000]
        finish_run(conn, run_id, "failed", 0, 0, message)
        return StatsResult("cbs", "failed", 0, message)
    finish_run(conn, run_id, "success", total, total)
    return StatsResult("cbs", "success", total)


def refresh_manual(
    conn: sqlite3.Connection, ref: Reference, config: dict, manual_dir: Path
) -> list[StatsResult]:
    series = {s["series_id"]: s for s in config.get("manual", [])}
    results = []
    # A manual source whose CSV was removed has no figures any more: drop its stored rows too.
    present = {p.stem for p in manual_dir.glob("*.csv")}
    placeholders = ",".join("?" * len(present)) or "''"
    conn.execute(
        f"DELETE FROM stat_observations WHERE source_id != 'cbs' "
        f"AND source_id NOT IN ({placeholders})",
        tuple(present),
    )
    conn.commit()
    for path in sorted(manual_dir.glob("*.csv")):
        source_id = path.stem
        if source_id not in ref.sources:
            results.append(StatsResult(source_id, "failed", 0, f"{path.name}: unknown source"))
            continue
        run_id = start_run(conn, source_id)
        try:
            observations = read_file(path, series, ref)
            if any(o.source_id != source_id for o in observations):
                raise ValueError(f"{path.name} may only contain rows for source {source_id}")
            # The CSV is the complete truth for this source: rows removed there are removed here.
            conn.execute("DELETE FROM stat_observations WHERE source_id = ?", (source_id,))
            n = upsert(conn, observations, ref.sources[source_id].licence, utc_now())
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            message = f"{type(exc).__name__}: {exc}"[:2000]
            finish_run(conn, run_id, "failed", 0, 0, message)
            results.append(StatsResult(source_id, "failed", 0, message))
            continue
        finish_run(conn, run_id, "success", n, n)
        results.append(StatsResult(source_id, "success", n))
    return results


def refresh_all(conn, ref, reference_dir: Path, manual_dir: Path, which: str = "all"):
    config = load_series_config(reference_dir)
    results = []
    if which in ("all", "cbs"):
        results.append(refresh_cbs(conn, ref, config))
    if which in ("all", "manual"):
        results += refresh_manual(conn, ref, config, manual_dir)
    return results
