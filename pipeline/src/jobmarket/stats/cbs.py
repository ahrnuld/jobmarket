"""CBS StatLine OData client (https://opendata.cbs.nl/, licence CC BY 4.0).

Dimension keys in StatLine are padded with spaces ('391600  '), so filters are built from the
exact keys as listed by the API rather than from the configured values.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable

from jobmarket.stats import Observation

API_BASE = "https://opendata.cbs.nl/ODataApi/odata"
STATLINE_URL = "https://opendata.cbs.nl/#/CBS/nl/dataset"  # human-readable table page (TR-01)
PERIOD = re.compile(r"^(\d{4})(KW|JJ|MM)(\d{2})$")

Fetch = Callable[[str], dict]


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def parse_period(key: str) -> tuple[str, str, str] | None:
    """'2025KW03' -> ('2025Q3', '2025-07-01', 'quarter'); '2024JJ00' -> ('2024', ..., 'year')."""
    m = PERIOD.match(key.strip())
    if not m:
        return None
    year, kind, n = m.group(1), m.group(2), int(m.group(3))
    if kind == "KW":
        return f"{year}Q{n}", f"{year}-{3 * (n - 1) + 1:02d}-01", "quarter"
    if kind == "MM":
        return f"{year}-{n:02d}", f"{year}-{n:02d}-01", "month"
    return year, f"{year}-01-01", "year"


class CbsClient:
    def __init__(self, fetch: Fetch = http_get_json):
        self._fetch = fetch

    def _get(self, table: str, path: str, **params) -> list[dict]:
        query = urllib.parse.urlencode({"$format": "json", **params}, quote_via=urllib.parse.quote)
        url = f"{API_BASE}/{table}/{path}?{query}"
        rows: list[dict] = []
        while url:  # the API pages large results with odata.nextLink
            data = self._fetch(url)
            rows.extend(data.get("value", []))
            url = data.get("odata.nextLink")
        return rows

    def table_modified(self, table: str) -> str:
        return self._get(table, "TableInfos")[0]["Modified"][:10]

    def dimension_keys(self, table: str, dimension: str) -> dict[str, str]:
        """Map stripped key -> exact key as used in the data."""
        return {v["Key"].strip(): v["Key"] for v in self._get(table, dimension)}

    def provisional_periods(self, table: str) -> set[str]:
        return {
            v["Key"].strip()
            for v in self._get(table, "Perioden")
            if (v.get("Status") or "").lower().startswith("voorlopig")
        }

    def fetch_series(self, cfg: dict) -> list[Observation]:
        table = cfg["table"]
        clauses = []
        pinned = dict(cfg.get("filters", {}))
        choices = {}
        if cfg.get("region_dimension"):
            choices[cfg["region_dimension"]] = cfg["regions"]
        if cfg.get("breakdown_dimension"):
            choices[cfg["breakdown_dimension"]] = cfg["breakdowns"]
        for dim, key in pinned.items():
            exact = self.dimension_keys(table, dim)
            if str(key) not in exact:
                raise ValueError(f"{cfg['series_id']}: key {key!r} not found in {table}.{dim}")
            clauses.append(f"{dim} eq '{exact[str(key)]}'")
        for dim, mapping in choices.items():
            exact = self.dimension_keys(table, dim)
            missing = [k for k in mapping if k not in exact]
            if missing:
                raise ValueError(f"{cfg['series_id']}: keys {missing} not found in {table}.{dim}")
            clauses.append("(" + " or ".join(f"{dim} eq '{exact[k]}'" for k in mapping) + ")")

        rows = self._get(table, "TypedDataSet", **{"$filter": " and ".join(clauses)})
        provisional = self.provisional_periods(table)
        modified = self.table_modified(table)
        multiplier = float(cfg.get("multiplier", 1))
        observations = []
        for row in rows:
            parsed = parse_period(row["Perioden"])
            if parsed is None or parsed[2] != cfg["frequency"]:
                continue
            period, start, _ = parsed
            raw = row.get(cfg["measure"])
            region = "NL"
            if cfg.get("region_dimension"):
                region = cfg["regions"][row[cfg["region_dimension"]].strip()]
            breakdown = ""
            if cfg.get("breakdown_dimension"):
                breakdown = cfg["breakdowns"][row[cfg["breakdown_dimension"]].strip()]
            observations.append(
                Observation(
                    source_id="cbs",
                    series_id=cfg["series_id"],
                    period=period,
                    period_start=start,
                    value=None if raw is None else round(float(raw) * multiplier, 3),
                    unit=cfg["unit"],
                    region=region,
                    breakdown=breakdown,
                    published_at=modified,
                    source_url=f"{STATLINE_URL}/{table}/table",
                    note="voorlopig" if row["Perioden"].strip() in provisional else None,
                )
            )
        return observations
