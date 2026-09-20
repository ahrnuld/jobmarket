"""Build the municipality table from CBS "Gebieden in Nederland" (one table per year).

Vacancy sources use the municipality names of the moment a location was recorded, so they also
contain names that no longer exist (Naarden, Veghel, Bussum). CBS publishes the classification
per year, and an old municipality carries its own COROP, labour market region and province in
the year it existed. Reading several years therefore resolves old names without merge rules.

Written to data/reference/municipalities.csv by `jobmarket reference update-regions`; that file
is committed, so a build never depends on the CBS API being up.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API = "https://opendata.cbs.nl/ODataApi/odata"
# Table id per classification year; the oldest year only needs to cover the vacancy history.
TABLES = {
    2010: "80397ned",
    2011: "81008ned",
    2012: "81498ned",
    2013: "82000NED",
    2014: "82496NED",
    2015: "82949NED",
    2016: "83287NED",
    2017: "83553NED",
    2018: "83859NED",
    2019: "84378NED",
    2020: "84721NED",
    2021: "84929NED",
    2022: "85067NED",
    2023: "85385NED",
    2024: "85755NED",
    2025: "86059NED",
    2026: "86247NED",
}
COLUMNS = [
    "name",
    "code",
    "year",
    "corop_code",
    "corop",
    "region_code",
    "region",
    "province_code",
    "province",
]


def normalise_name(name: str) -> str:
    """Key for matching source names: lowercase, no accents, no punctuation."""
    text = unicodedata.normalize("NFKD", name.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in text).split())


@dataclass(frozen=True)
class MunicipalityRow:
    name: str
    code: str
    year: int
    corop_code: str
    corop: str
    region_code: str
    region: str
    province_code: str
    province: str


def _get(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=120) as resp:
        return json.load(resp)["value"]


def _pair_keys(row: dict, prefix: str) -> tuple[str, str] | None:
    """Find the Code_x/Naam_y pair whose code starts with `prefix` (CR, AM, PV)."""
    for key, value in row.items():
        if key.startswith("Code_") and isinstance(value, str) and value.strip().startswith(prefix):
            index = int(key.split("_")[1])
            name_key = f"Naam_{index + 1}"
            if name_key in row:
                return key, name_key
    return None


def _pair_keys_by_names(rows: list[dict], known: set[str]) -> tuple[str, str] | None:
    """Find the Code_x/Naam_y pair whose names are mostly in `known`.

    Tables up to 2012 use plain numbers as codes ("07" for a COROP), so the column cannot be
    recognised by its code. The names are stable, so they identify the column instead.
    """
    sample = rows[:60]
    for key in rows[0]:
        if not key.startswith("Naam_"):
            continue
        values = {str(r.get(key, "") or "").strip() for r in sample}
        values.discard("")
        if values and len(values & known) / len(values) > 0.8:
            return f"Code_{int(key.split('_')[1]) - 1}", key
    return None


# Older tables use the NUTS names and codes, or the Dutch name of Fryslân.
PROVINCE_RENAMES = {
    "Friesland (NL)": ("Fryslân", "PV21"),
    "Friesland": ("Fryslân", "PV21"),
    "Limburg (NL)": ("Limburg", "PV31"),
}


def _with_prefix(code: str, prefix: str) -> str:
    """Tables up to 2012 write codes as plain numbers ("7"); make them CR07, AM01, GM0363."""
    if not code or not code.isdigit():
        return code
    width = 4 if prefix == "GM" else 2
    return f"{prefix}{int(code):0{width}d}"


def fetch_year(
    year: int,
    table: str,
    known_corop: set[str] | None = None,
    known_province: set[str] | None = None,
) -> list[MunicipalityRow]:
    rows = _get(f"{API}/{table}/TypedDataSet?$format=json")
    municipalities = [r for r in rows if str(r.get("Code_1", "")).strip().startswith("GM")]
    if not municipalities:
        # Up to 2012 municipality rows have a plain number as code; they are the rows whose
        # name column is filled and whose code is numeric.
        municipalities = [r for r in rows if str(r.get("Code_1", "")).strip().isdigit()]
    if not municipalities:
        return []
    first = municipalities[0]
    keys = {p: _pair_keys(first, p) for p in ("CR", "AM", "PV")}
    if not keys["CR"] and known_corop:
        keys["CR"] = _pair_keys_by_names(municipalities, known_corop)
    if not keys["PV"] and known_province:
        keys["PV"] = _pair_keys_by_names(municipalities, known_province)
    if not keys["CR"] or not keys["PV"]:
        raise ValueError(f"{table}: no COROP or province columns found")
    out = []
    for r in municipalities:

        def field(prefix: str, which: int, r: dict = r) -> str:
            pair = keys[prefix]
            value = str(r.get(pair[which], "") or "").strip() if pair else ""
            return _with_prefix(value, prefix) if which == 0 else value

        province = field("PV", 1)
        province_code = field("PV", 0)
        if province in PROVINCE_RENAMES:
            province, province_code = PROVINCE_RENAMES[province]
        out.append(
            MunicipalityRow(
                name=str(r["Naam_2"]).strip(),
                code=_with_prefix(str(r["Code_1"]).strip(), "GM"),
                year=year,
                corop_code=field("CR", 0),
                corop=field("CR", 1),
                region_code=field("AM", 0),
                region=field("AM", 1),
                province_code=province_code,
                province=province,
            )
        )
    return out


def build(years: list[int] | None = None) -> list[MunicipalityRow]:
    """One row per municipality name; the most recent year a name existed wins."""
    wanted = sorted(years or TABLES)
    # The newest year gives the COROP and province names that identify the columns of the
    # older tables, which have no code prefixes.
    newest = fetch_year(max(wanted), TABLES[max(wanted)])
    known_corop = {r.corop for r in newest}
    known_province = {r.province for r in newest}
    by_name: dict[str, MunicipalityRow] = {}
    for year in wanted:
        rows = (
            newest
            if year == max(wanted)
            else fetch_year(year, TABLES[year], known_corop, known_province)
        )
        for row in rows:
            if row.corop:  # later years overwrite earlier ones
                by_name[normalise_name(row.name)] = row
    return [by_name[k] for k in sorted(by_name)]


def write_csv(path: Path, rows: list[MunicipalityRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow(
                [
                    r.name,
                    r.code,
                    r.year,
                    r.corop_code,
                    r.corop,
                    r.region_code,
                    r.region,
                    r.province_code,
                    r.province,
                ]
            )


def slug(name: str) -> str:
    """Id from a region name: 'Zuid-Kennemerland en IJmond' -> 'zuid-kennemerland-en-ijmond'."""
    return re.sub(r"[^a-z0-9]+", "-", normalise_name(name)).strip("-")
