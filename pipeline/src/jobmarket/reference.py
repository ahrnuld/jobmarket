"""Load and validate the reference data in data/reference/*.yaml.

Everything the classifiers depend on is in these files, so methodology changes show up as
reviewable diffs rather than code changes.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SENIORITY_LEVELS = ("internship", "junior", "medior", "senior", "unknown")


class ReferenceError(ValueError):
    """Raised when a reference file is missing fields or contains an invalid pattern."""


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    licence: str
    licence_url: str | None
    attribution: str | None
    raw_retention_days: int | None
    terms_checked_on: str | None
    release: str


@dataclass(frozen=True)
class Programme:
    id: str
    name: dict[str, str]
    locations: list[str]
    summary: dict[str, str]


@dataclass(frozen=True)
class RoleFamily:
    id: str
    name: dict[str, str]
    programmes: list[str]
    title_patterns: list[re.Pattern[str]]


@dataclass(frozen=True)
class Skill:
    id: str
    label: str
    category: str
    patterns: list[re.Pattern[str]]
    esco_query: str | None
    esco_uri: str | None
    esco_label: str | None
    ict_signal: bool = True  # False for generic skills that don't make a vacancy ICT on their own


@dataclass(frozen=True)
class SeniorityLevel:
    id: str
    title_patterns: list[re.Pattern[str]]
    description_patterns: list[re.Pattern[str]]


@dataclass(frozen=True)
class LabourMarketRegion:
    id: str
    name: str
    province: str
    municipalities: list[str]


@dataclass(frozen=True)
class Province:
    id: str
    name: str
    aliases: list[str]


@dataclass
class Reference:
    sources: dict[str, Source]
    programmes: dict[str, Programme]
    role_families: list[RoleFamily]
    exclude_title_patterns: list[re.Pattern[str]]
    skills: dict[str, Skill]
    seniority_levels: list[SeniorityLevel]
    junior_max_years: int
    medior_max_years: int
    provinces: dict[str, Province]
    regions: dict[str, LabourMarketRegion]
    # lookup tables built after loading
    municipality_index: dict[str, str] = field(default_factory=dict)  # lower name -> region id
    province_index: dict[str, str] = field(default_factory=dict)  # lower name/alias -> province id


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ReferenceError(f"Missing reference file: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ReferenceError(f"{path.name}: expected a mapping at top level")
    return data


def _require(item: dict, keys: list[str], where: str) -> None:
    missing = [k for k in keys if k not in item]
    if missing:
        raise ReferenceError(f"{where}: missing field(s) {', '.join(missing)}")


def _compile(patterns: list[str] | None, where: str) -> list[re.Pattern[str]]:
    compiled = []
    for p in patterns or []:
        try:
            compiled.append(re.compile(p, re.IGNORECASE))
        except re.error as exc:
            raise ReferenceError(f"{where}: invalid pattern {p!r}: {exc}") from exc
    return compiled


def load_reference(reference_dir: Path) -> Reference:
    src = _read_yaml(reference_dir / "sources.yaml")
    sources = {}
    for s in src["sources"]:
        _require(s, ["id", "name", "url", "licence", "release"], f"sources.yaml:{s.get('id')}")
        sources[s["id"]] = Source(
            id=s["id"],
            name=s["name"],
            url=s["url"],
            licence=s["licence"],
            licence_url=s.get("licence_url"),
            attribution=s.get("attribution"),
            raw_retention_days=s.get("raw_retention_days"),
            terms_checked_on=str(s["terms_checked_on"]) if s.get("terms_checked_on") else None,
            release=s["release"],
        )

    prog = _read_yaml(reference_dir / "programmes.yaml")
    programmes = {}
    for p in prog["programmes"]:
        _require(p, ["id", "name", "summary"], f"programmes.yaml:{p.get('id')}")
        programmes[p["id"]] = Programme(p["id"], p["name"], p.get("locations", []), p["summary"])
    role_families = []
    seen_families = set()
    for rf in prog["role_families"]:
        where = f"programmes.yaml:role_family {rf.get('id')}"
        _require(rf, ["id", "name", "programmes", "title_patterns"], where)
        if rf["id"] in seen_families:
            raise ReferenceError(f"{where}: duplicate id")
        seen_families.add(rf["id"])
        unknown = set(rf["programmes"]) - programmes.keys()
        if unknown:
            raise ReferenceError(f"{where}: unknown programme(s) {sorted(unknown)}")
        role_families.append(
            RoleFamily(
                rf["id"], rf["name"], rf["programmes"], _compile(rf["title_patterns"], where)
            )
        )

    sk = _read_yaml(reference_dir / "skills.yaml")
    links_path = reference_dir / "esco_links.yaml"
    esco_links = (_read_yaml(links_path).get("links") or {}) if links_path.is_file() else {}
    skills = {}
    for s in sk["skills"]:
        where = f"skills.yaml:{s.get('id')}"
        _require(s, ["id", "label", "category", "patterns"], where)
        if s["id"] in skills:
            raise ReferenceError(f"{where}: duplicate id")
        link = esco_links.get(s["id"]) or {}
        skills[s["id"]] = Skill(
            id=s["id"],
            label=s["label"],
            category=s["category"],
            patterns=_compile(s["patterns"], where),
            esco_query=s.get("esco_query"),
            esco_uri=link.get("uri"),
            esco_label=link.get("label"),
            ict_signal=bool(s.get("ict_signal", True)),
        )

    sen = _read_yaml(reference_dir / "seniority.yaml")
    levels = []
    for lvl in sen["levels"]:
        where = f"seniority.yaml:{lvl.get('id')}"
        _require(lvl, ["id", "title_patterns"], where)
        if lvl["id"] not in SENIORITY_LEVELS or lvl["id"] == "unknown":
            raise ReferenceError(f"{where}: level must be one of {SENIORITY_LEVELS[:-1]}")
        levels.append(
            SeniorityLevel(
                lvl["id"],
                _compile(lvl["title_patterns"], where),
                _compile(lvl.get("description_patterns"), where),
            )
        )
    years = sen.get("experience_years", {})

    reg = _read_yaml(reference_dir / "regions.yaml")
    provinces = {
        p["id"]: Province(p["id"], p["name"], p.get("aliases", [])) for p in reg["provinces"]
    }
    regions = {}
    for r in reg["labour_market_regions"]:
        where = f"regions.yaml:{r.get('id')}"
        _require(r, ["id", "name", "province", "municipalities"], where)
        if r["province"] not in provinces:
            raise ReferenceError(f"{where}: unknown province {r['province']!r}")
        regions[r["id"]] = LabourMarketRegion(
            r["id"], r["name"], r["province"], r["municipalities"]
        )

    ref = Reference(
        sources=sources,
        programmes=programmes,
        role_families=role_families,
        exclude_title_patterns=_compile(
            prog.get("exclude_title_patterns"), "programmes.yaml:exclude_title_patterns"
        ),
        skills=skills,
        seniority_levels=levels,
        junior_max_years=int(years.get("junior_max", 2)),
        medior_max_years=int(years.get("medior_max", 5)),
        provinces=provinces,
        regions=regions,
    )
    for region in regions.values():
        for m in region.municipalities:
            key = m.lower()
            if key in ref.municipality_index and ref.municipality_index[key] != region.id:
                raise ReferenceError(f"regions.yaml: municipality {m!r} is in two regions")
            ref.municipality_index[key] = region.id
    for p in provinces.values():
        for name in [p.name, *p.aliases]:
            ref.province_index[name.lower()] = p.id
    return ref


def sync_sources(conn: sqlite3.Connection, ref: Reference) -> None:
    """Mirror sources.yaml into the database so every run records the licence terms it used."""
    for s in ref.sources.values():
        conn.execute(
            """
            INSERT INTO sources (id, name, url, licence, licence_url, attribution,
                                 raw_retention_days, terms_checked_on, release)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, url=excluded.url, licence=excluded.licence,
                licence_url=excluded.licence_url, attribution=excluded.attribution,
                raw_retention_days=excluded.raw_retention_days,
                terms_checked_on=excluded.terms_checked_on, release=excluded.release
            """,
            (
                s.id,
                s.name,
                s.url,
                s.licence,
                s.licence_url,
                s.attribution,
                s.raw_retention_days,
                s.terms_checked_on,
                s.release,
            ),
        )
