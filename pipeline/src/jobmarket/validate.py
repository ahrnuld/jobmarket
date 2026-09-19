"""Checks a staged snapshot must pass before it replaces the published one (NFR-07).

Errors block publication; the site keeps showing the previous snapshot. Warnings are published
with the snapshot and shown on the admin status page.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from jobmarket.clean.pii import EMAIL, PHONE

STALE_AFTER_DAYS = 14  # success metric: data never older than 14 days
VOLUME_DROP_LIMIT = 0.4  # last full month below 40% of the recent median -> suspicious


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def validate(
    meta: dict, geo_files: dict[str, dict], stats: dict, production: bool, today: date | None = None
) -> Report:
    today = today or date.today()
    report = Report()
    err, warn = report.errors.append, report.warnings.append

    months = meta["vacancies"]["months"]
    if not months:
        err("No vacancy data: nothing to publish.")
        return report
    nl = geo_files.get("nl")
    if nl is None:
        err("National aggregate (nl) missing.")
        return report

    # Counts are whole, non-negative, and no programme exceeds the 'all' total.
    for geo_id, data in geo_files.items():
        totals: dict[tuple, int] = {}
        for mi, prog, sen, n in data["vacancies"]:
            if not isinstance(n, int) or n < 0:
                err(f"{geo_id}: invalid count {n!r}")
            if prog == "all":
                totals[(mi, sen)] = n
        for mi, prog, sen, n in data["vacancies"]:
            if prog != "all" and n > totals.get((mi, sen), 0):
                err(f"{geo_id}: programme {prog} count exceeds total in month {months[mi]}")
                break
        for _mi, _prog, title, _n in data["titles"]:
            if EMAIL.search(title) or PHONE.search(title):
                err(f"{geo_id}: personal data in a published title: {title!r}")

    # Volume sanity: a sudden collapse usually means a broken source or classifier.
    full = [i for i, m in enumerate(months) if not m["partial"]]
    per_month = {mi: n for mi, prog, sen, n in nl["vacancies"] if prog == "all" and sen == "all"}
    if len(full) >= 2:
        last = per_month.get(full[-1], 0)
        previous = [per_month.get(i, 0) for i in full[-4:-1]]
        baseline = statistics.median(previous)
        if baseline and last < VOLUME_DROP_LIMIT * baseline:
            err(
                f"Vacancies in {months[full[-1]]['month']} ({last}) dropped below "
                f"{VOLUME_DROP_LIMIT:.0%} of the recent median ({baseline:.0f})."
            )

    last_posted = date.fromisoformat(meta["vacancies"]["last_posted"])
    if today - last_posted > timedelta(days=STALE_AFTER_DAYS):
        warn(f"Newest vacancy is from {last_posted}, more than {STALE_AFTER_DAYS} days ago.")

    for s in meta["sources"]:
        if s.get("last_run_status") == "failed":
            warn(f"Last run of source {s['id']} failed: {s.get('last_error')}")
        if s["used"] and not s["terms_checked_on"]:
            (err if production else warn)(
                f"Licence terms of source {s['id']} not checked (terms_checked_on in sources.yaml)."
            )

    if meta["dataset"] == "sample":
        (err if production else warn)("Vacancy figures are synthetic sample data.")
    sample_series = sorted({o["series"] for o in stats["observations"] if o.get("sample")})
    if sample_series:
        (err if production else warn)(
            f"Example (not real) statistics in: {', '.join(sample_series)}."
        )
    unchecked = [s["id"] for s in meta["skills"] if s.get("esco_uri") and not s.get("esco_checked")]
    if unchecked:
        warn(f"{len(unchecked)} ESCO links not yet checked by hand.")
    if meta.get("accuracy") is None:
        warn("Classification accuracy not yet measured on a labelled sample (TR-05).")

    if not re.fullmatch(r"\d{8}T\d{6}Z(-\d+)?", meta["snapshot_id"]):
        err("Invalid snapshot id.")
    return report
