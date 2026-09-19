"""Build the published data set for the static site, validate it, and swap it in (NFR-07).

Output layout (site/public/data/; read by the site build and fetched by the browser for filters):
    meta.json            sources, reference data, months, changelog, validation warnings
    stats.json           CBS / HBO-Monitor / ROA / UWV observations with provenance
    geo/<geo>/<kind>.json  monthly aggregates for one geography (nl, p-<province>, r-<region>);
                         kind = vacancies, skills, families, titles, salaries
    csv/*.csv            the aggregate history as downloadable CSV (FR-11)

Only aggregates are published, never vacancy texts or bulk vacancy records (LR-02).
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from jobmarket.aggregate import TABLES, read_history
from jobmarket.classify import CLASSIFIER_VERSION
from jobmarket.config import Settings
from jobmarket.reference import Reference
from jobmarket.stats import load_series_config
from jobmarket.validate import Report, validate

MIN_SAMPLE_SIZE = 30  # TR-02
MIN_TITLE_COUNT = 3  # typical titles must occur at least this often in a geography
VACANCY_SOURCES = {"real": "adzuna", "sample": "fixture"}


@dataclass
class PublishResult:
    snapshot_id: str
    published: bool
    report: Report
    staging_dir: Path


def geo_filename(geo_id: str) -> str:
    return geo_id.replace(":", "-")


def _geo_list(ref: Reference) -> list[dict]:
    geos = [
        {
            "id": "nl",
            "level": "country",
            "name": {"nl": "Nederland", "en": "Netherlands"},
            "parent": None,
        }
    ]
    for p in ref.provinces.values():
        geos.append(
            {
                "id": f"p:{p.id}",
                "level": "province",
                "name": {"nl": p.name, "en": p.name},
                "parent": "nl",
            }
        )
    for r in ref.regions.values():
        geos.append(
            {
                "id": f"r:{r.id}",
                "level": "region",
                "name": {"nl": r.name, "en": r.name},
                "parent": f"p:{r.province}",
            }
        )
    return geos


def _source_status(conn: sqlite3.Connection, ref: Reference, used: set[str]) -> list[dict]:
    out = []
    for s in ref.sources.values():
        last = conn.execute(
            "SELECT status, finished_at, records_fetched, error FROM ingestion_runs "
            "WHERE source_id = ? ORDER BY id DESC LIMIT 1",
            (s.id,),
        ).fetchone()
        ok = conn.execute(
            "SELECT finished_at FROM ingestion_runs WHERE source_id = ? AND status = 'success' "
            "ORDER BY id DESC LIMIT 1",
            (s.id,),
        ).fetchone()
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "url": s.url,
                "licence": s.licence,
                "licence_url": s.licence_url,
                "attribution": s.attribution,
                "terms_checked_on": s.terms_checked_on,
                "used": s.id in used,
                "last_success_at": ok["finished_at"] if ok else None,
                "last_run_status": last["status"] if last else None,
                "last_error": last["error"] if last else None,
            }
        )
    return out


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}


def build(
    conn: sqlite3.Connection,
    ref: Reference,
    settings: Settings,
    history_dir: Path,
    dataset: str,
    snapshot_id: str,
) -> tuple[dict, dict[str, dict], dict]:
    history = {name: read_history(history_dir, name) for name in TABLES}
    month_rows = sorted(history["months"], key=lambda r: r["month"])
    months = [{"month": r["month"], "partial": r["partial"] == "1"} for r in month_rows]
    index = {m["month"]: i for i, m in enumerate(months)}

    # Titles: keep only those seen at least MIN_TITLE_COUNT times in a geography (drops one-off
    # and employer-specific titles).
    title_totals: dict[tuple, int] = defaultdict(int)
    for r in history["titles"]:
        title_totals[(r["geo"], r["programme"], r["title"])] += int(r["n"])

    geo_files: dict[str, dict] = defaultdict(
        lambda: {"vacancies": [], "skills": [], "families": [], "titles": [], "salaries": []}
    )
    for r in history["vacancies"]:
        geo_files[r["geo"]]["vacancies"].append(
            [index[r["month"]], r["programme"], r["seniority"], int(r["n"])]
        )
    for r in history["skills"]:
        geo_files[r["geo"]]["skills"].append(
            [index[r["month"]], r["programme"], r["seniority"], r["skill"], int(r["n"])]
        )
    for r in history["families"]:
        geo_files[r["geo"]]["families"].append(
            [index[r["month"]], r["programme"], r["family"], int(r["n"])]
        )
    for r in history["titles"]:
        if title_totals[(r["geo"], r["programme"], r["title"])] >= MIN_TITLE_COUNT:
            geo_files[r["geo"]]["titles"].append(
                [index[r["month"]], r["programme"], r["title"], int(r["n"])]
            )
    for r in history["salaries"]:
        geo_files[r["geo"]]["salaries"].append(
            [index[r["month"]], r["programme"], r["seniority"], int(r["bucket"]), int(r["n"])]
        )

    config = load_series_config(settings.reference_dir)
    series_meta = {}
    for s in config.get("cbs", []):
        series_meta[s["series_id"]] = {
            "source": "cbs",
            "unit": s["unit"],
            "title": s["title"],
            "note": s.get("note"),
            "frequency": s["frequency"],
            "table": s["table"],
        }
    for s in config.get("manual", []):
        series_meta[s["series_id"]] = {
            "source": s["source_id"],
            "unit": s["unit"],
            "title": s["title"],
            "note": s.get("note"),
        }
    observations = [
        {
            "series": r["series_id"],
            "source": r["source_id"],
            "period": r["period"],
            "start": r["period_start"],
            "region": r["region"],
            "breakdown": r["breakdown"],
            "value": r["value"],
            "label": r["value_label"],
            "n": r["sample_size"],
            "published": r["published_at"],
            "retrieved": r["retrieved_at"],
            "url": r["source_url"],
            "sample": bool(r["is_sample"]),
            "note": r["note"],
        }
        for r in conn.execute("SELECT * FROM stat_observations ORDER BY series_id, period_start")
    ]
    stats = {"series": series_meta, "observations": observations}

    esco_links = _load_yaml(settings.reference_dir / "esco_links.yaml").get("links", {}) or {}
    changelog = _load_yaml(settings.changelog_file).get("entries", []) or []
    accuracy_file = settings.labels_dir / "accuracy.json"
    accuracy = json.loads(accuracy_file.read_text("utf-8")) if accuracy_file.is_file() else None

    used = {VACANCY_SOURCES[dataset], "esco"} | {o["source"] for o in observations}
    posted = [r["first_posted"] for r in month_rows] + [r["last_posted"] for r in month_rows]
    meta = {
        "snapshot_id": snapshot_id,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "production": os.environ.get("JOBMARKET_ENV") == "production",
        "dataset": dataset,
        "classifier_version": CLASSIFIER_VERSION,
        "min_sample_size": MIN_SAMPLE_SIZE,
        "vacancy_source": VACANCY_SOURCES[dataset],
        "vacancies": {
            "months": months,
            "first_posted": min(posted) if posted else None,
            "last_posted": max(posted) if posted else None,
        },
        "sources": _source_status(conn, ref, used),
        "programmes": [
            {"id": p.id, "name": p.name, "summary": p.summary, "locations": p.locations}
            for p in ref.programmes.values()
        ],
        "role_families": [
            {"id": f.id, "name": f.name, "programmes": f.programmes} for f in ref.role_families
        ],
        "skills": [
            {
                "id": s.id,
                "label": s.label,
                "category": s.category,
                "esco_uri": s.esco_uri,
                "esco_label": s.esco_label,
                "esco_checked": bool((esco_links.get(s.id) or {}).get("checked")),
            }
            for s in ref.skills.values()
        ],
        "geos": [g for g in _geo_list(ref) if g["id"] in geo_files],
        "changelog": changelog,
        "accuracy": accuracy,
    }
    return meta, dict(geo_files), stats


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def publish(
    conn: sqlite3.Connection,
    ref: Reference,
    settings: Settings,
    dataset: str = "real",
    history_dir: Path | None = None,
    today: date | None = None,
) -> PublishResult:
    history_dir = history_dir or settings.history_dir
    snapshot_id = base_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = 1
    while conn.execute("SELECT 1 FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone():
        suffix += 1
        snapshot_id = f"{base_id}-{suffix}"
    production = os.environ.get("JOBMARKET_ENV") == "production"
    meta, geo_files, stats = build(conn, ref, settings, history_dir, dataset, snapshot_id)
    report = validate(meta, geo_files, stats, production=production, today=today)
    meta["validation"] = report.as_dict()

    staging = settings.snapshots_dir / snapshot_id
    if staging.exists():
        shutil.rmtree(staging)
    _write_json(staging / "meta.json", meta)
    _write_json(staging / "stats.json", stats)
    # One file per geography and kind, so a page downloads only what it shows (NFR-02).
    for geo_id, data in geo_files.items():
        for kind, rows in data.items():
            _write_json(staging / "geo" / geo_filename(geo_id) / f"{kind}.json", rows)
    _write_csv_downloads(staging / "csv", history_dir)

    conn.execute(
        "INSERT INTO snapshots (id, created_at, status, validation_report) VALUES (?, ?, ?, ?)",
        (
            snapshot_id,
            meta["generated_at"],
            "published" if report.ok else "rejected",
            json.dumps(report.as_dict()),
        ),
    )
    conn.commit()
    if report.ok:
        _swap_in(staging, settings.publish_dir)
    return PublishResult(snapshot_id, report.ok, report, staging)


def _write_csv_downloads(target: Path, history_dir: Path) -> None:
    """FR-11: the aggregate history as CSV, with the same title threshold as the site."""
    target.mkdir(parents=True, exist_ok=True)
    for name, cols in TABLES.items():
        rows = read_history(history_dir, name)
        if name == "titles":
            totals: dict[tuple, int] = defaultdict(int)
            for r in rows:
                totals[(r["geo"], r["programme"], r["title"])] += int(r["n"])
            rows = [
                r for r in rows if totals[(r["geo"], r["programme"], r["title"])] >= MIN_TITLE_COUNT
            ]
        with (target / f"{name}.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def _swap_in(staging: Path, publish_dir: Path) -> None:
    """Replace publish_dir with a copy of staging; the staged snapshot stays as a record."""
    publish_dir.parent.mkdir(parents=True, exist_ok=True)
    incoming = publish_dir.with_name(publish_dir.name + ".incoming")
    old = publish_dir.with_name(publish_dir.name + ".old")
    for p in (incoming, old):
        if p.exists():
            shutil.rmtree(p)
    shutil.copytree(staging, incoming)
    if publish_dir.exists():
        publish_dir.rename(old)
    incoming.rename(publish_dir)
    if old.exists():
        shutil.rmtree(old)


def prune_snapshots(snapshots_dir: Path, keep: int = 10) -> None:
    dirs = sorted(p for p in snapshots_dir.glob("*T*Z*") if p.is_dir())
    for p in dirs[:-keep]:
        shutil.rmtree(p)
