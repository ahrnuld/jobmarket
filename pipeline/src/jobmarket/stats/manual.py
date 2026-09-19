"""Load hand-filled statistics from data/manual/*.csv (HBO-Monitor, ROA, UWV).

Every row is validated; a file with any invalid row is rejected as a whole, so a typo never
reaches the site. The column layout is documented in data/manual/README.md.
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

from jobmarket.reference import Reference
from jobmarket.stats import Observation

COLUMNS = [
    "source_id",
    "series_id",
    "period",
    "region",
    "breakdown",
    "value",
    "value_label",
    "unit",
    "sample_size",
    "published_at",
    "source_url",
    "is_sample",
    "note",
]
# Breakdown value for the national average of all hbo bachelors (programme series).
NATIONAL_AVG = "hbo-bachelor"
# '2025' (a year), '2025Q3' (a quarter), '2025-2030' (a forecast horizon)
PERIOD = re.compile(r"^(\d{4})(?:Q([1-4])|-(\d{4}))?$")


class ManualDataError(ValueError):
    pass


def _period_start(period: str) -> str | None:
    m = PERIOD.match(period)
    if not m:
        return None
    year, quarter = m.group(1), m.group(2)
    month = 3 * (int(quarter) - 1) + 1 if quarter else 1
    return f"{year}-{month:02d}-01"


def read_file(path: Path, series: dict[str, dict], ref: Reference) -> list[Observation]:
    """`series`: manual series config by id (from statistics.yaml)."""
    errors: list[str] = []
    observations: list[Observation] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ManualDataError(f"{path.name}: missing columns {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            row = {k: (v or "").strip() for k, v in row.items()}
            if not any(row.values()) or row["source_id"].startswith("#"):
                continue
            where = f"{path.name} line {line}"
            cfg = series.get(row["series_id"])
            if cfg is None:
                errors.append(f"{where}: series {row['series_id']!r} not in statistics.yaml")
                continue
            if row["source_id"] != cfg["source_id"]:
                errors.append(f"{where}: series {row['series_id']} belongs to {cfg['source_id']}")
            if row["unit"] != cfg["unit"]:
                errors.append(f"{where}: unit must be {cfg['unit']!r}")
            start = _period_start(row["period"])
            if start is None:
                errors.append(
                    f"{where}: period {row['period']!r} must look like 2025, 2025Q3 or 2025-2030"
                )
            region = row["region"] or "NL"
            if region != "NL" and region not in ref.provinces and region not in ref.regions:
                errors.append(f"{where}: unknown region {region!r}")
            kind = cfg.get("breakdown")
            if kind == "programme" and row["breakdown"] not in (*ref.programmes, NATIONAL_AVG):
                errors.append(
                    f"{where}: breakdown must be a programme id or {NATIONAL_AVG!r}, "
                    f"got {row['breakdown']!r}"
                )
            if kind == "programme_item":
                programme, _, item = row["breakdown"].partition("/")
                if programme not in ref.programmes or not item.strip():
                    errors.append(
                        f"{where}: breakdown must look like '<programme id>/<item>', "
                        f"got {row['breakdown']!r}"
                    )
            value = None
            if cfg["unit"] == "label":
                if not row["value_label"]:
                    errors.append(f"{where}: value_label is required for unit 'label'")
            else:
                try:
                    value = float(row["value"].replace(",", "."))
                except ValueError:
                    errors.append(f"{where}: value {row['value']!r} is not a number")
            sample_size = None
            if row["sample_size"]:
                if not row["sample_size"].isdigit():
                    errors.append(f"{where}: sample_size must be a whole number")
                else:
                    sample_size = int(row["sample_size"])
            try:
                date.fromisoformat(row["published_at"])
            except ValueError:
                errors.append(f"{where}: published_at must be a date (YYYY-MM-DD)")
            if not row["source_url"].startswith("http"):
                errors.append(f"{where}: source_url is required (TR-01)")
            if row["is_sample"] not in ("0", "1"):
                errors.append(f"{where}: is_sample must be 0 or 1")
            if errors:
                continue
            observations.append(
                Observation(
                    source_id=row["source_id"],
                    series_id=row["series_id"],
                    period=row["period"],
                    period_start=start,
                    value=value,
                    unit=row["unit"],
                    region=region,
                    breakdown=row["breakdown"],
                    value_label=row["value_label"] or None,
                    sample_size=sample_size,
                    published_at=row["published_at"],
                    source_url=row["source_url"],
                    is_sample=row["is_sample"] == "1",
                    note=row["note"] or None,
                )
            )
    if errors:
        raise ManualDataError("\n".join(errors))
    return observations
