"""Published statistics: CBS via its API, HBO-Monitor / ROA / UWV from hand-filled CSV files."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Observation:
    source_id: str
    series_id: str
    period: str  # '2025Q3', '2025', '2025-2030'
    period_start: str  # ISO date
    value: float | None
    unit: str
    region: str = "NL"
    breakdown: str = ""
    value_label: str | None = None
    sample_size: int | None = None
    published_at: str | None = None
    source_url: str | None = None
    is_sample: bool = False
    note: str | None = None


def load_series_config(reference_dir: Path) -> dict:
    return yaml.safe_load((reference_dir / "statistics.yaml").read_text(encoding="utf-8"))


def upsert(
    conn: sqlite3.Connection, observations: list[Observation], licence: str, retrieved_at: str
) -> int:
    conn.executemany(
        """
        INSERT INTO stat_observations (source_id, series_id, period, period_start, region,
            breakdown, value, value_label, unit, sample_size, published_at, retrieved_at, licence,
            source_url, is_sample, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source_id, series_id, period, region, breakdown) DO UPDATE SET
            period_start = excluded.period_start, value = excluded.value,
            value_label = excluded.value_label, unit = excluded.unit,
            sample_size = excluded.sample_size, published_at = excluded.published_at,
            retrieved_at = excluded.retrieved_at, licence = excluded.licence,
            source_url = excluded.source_url, is_sample = excluded.is_sample, note = excluded.note
        """,
        [
            (
                o.source_id,
                o.series_id,
                o.period,
                o.period_start,
                o.region,
                o.breakdown,
                o.value,
                o.value_label,
                o.unit,
                o.sample_size,
                o.published_at,
                retrieved_at,
                licence,
                o.source_url,
                int(o.is_sample),
                o.note,
            )
            for o in observations
        ],
    )
    return len(observations)
