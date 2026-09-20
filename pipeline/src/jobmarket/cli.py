"""Command-line entry point: `jobmarket <command>`. Run `jobmarket --help` for the list."""

from __future__ import annotations

import argparse
import sys

from jobmarket.config import load_settings
from jobmarket.db import open_db
from jobmarket.reference import ReferenceError, load_reference, sync_sources


def cmd_init_db(args: argparse.Namespace) -> int:
    settings = load_settings()
    ref = load_reference(settings.reference_dir)
    with open_db(settings.db_path) as conn:
        sync_sources(conn, ref)
    print(f"Database ready at {settings.db_path}")
    return 0


def cmd_reference_check(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        ref = load_reference(settings.reference_dir)
    except ReferenceError as exc:
        print(f"Reference data invalid: {exc}", file=sys.stderr)
        return 1
    unlinked = [s.id for s in ref.skills.values() if not s.esco_uri]
    unchecked = [s.id for s in ref.sources.values() if not s.terms_checked_on]
    print(
        f"OK: {len(ref.sources)} sources, {len(ref.programmes)} programmes, "
        f"{len(ref.role_families)} role families, {len(ref.skills)} skills, "
        f"{len(ref.regions)} labour market regions"
    )
    if unlinked:
        print(f"Skills without ESCO link ({len(unlinked)}): {', '.join(unlinked)}")
    if unchecked:
        print(f"Sources with unchecked licence terms: {', '.join(unchecked)}")
    return 0


def cmd_update_regions(args: argparse.Namespace) -> int:
    """Rebuild data/reference/municipalities.csv from the CBS area classifications."""
    from jobmarket.reference_geo import (
        build,
        fetch_nuts3,
        normalise_name,
        write_csv,
        write_nuts3_csv,
    )

    settings = load_settings()
    rows = build()
    path = settings.reference_dir / "municipalities.csv"
    write_csv(path, rows)
    corops = {r.corop for r in rows}
    print(f"Wrote {len(rows)} municipality names and {len(corops)} COROP areas to {path}")

    # The Dutch NUTS 3 regions are those same COROP areas; EURES locates a vacancy by NUTS 3.
    codes = {normalise_name(r.corop): r.corop_code for r in rows}
    nuts3_path = settings.reference_dir / "nuts3.csv"
    written = write_nuts3_csv(nuts3_path, fetch_nuts3(), codes)
    print(f"Wrote {written} NUTS 3 codes to {nuts3_path}")
    return 0


def cmd_update_occupations(args: argparse.Namespace) -> int:
    """Rebuild the list of ESCO occupations that count as ICT (used to ask EURES)."""
    from jobmarket.occupations import ISCO_GROUPS, fetch_ict_occupations, write_yaml

    settings = load_settings()
    path = settings.reference_dir / "esco_occupations.yaml"
    n = write_yaml(path, fetch_ict_occupations())
    print(f"Wrote {n} ESCO occupations from ISCO groups {', '.join(ISCO_GROUPS)} to {path}")
    return 0


def cmd_resolve_esco(args: argparse.Namespace) -> int:
    from jobmarket.esco import resolve_links

    settings = load_settings()
    ref = load_reference(settings.reference_dir)
    resolved, not_found = resolve_links(
        ref.skills, settings.reference_dir / "esco_links.yaml", refresh=args.refresh
    )
    print(f"Resolved {resolved} ESCO links; review data/reference/esco_links.yaml")
    if not_found:
        print(f"No ESCO match for: {', '.join(not_found)}")
    return 0


def _adzuna_budget(conn, config):
    from jobmarket.budget import Budget, Limits

    return Budget(
        conn,
        "adzuna",
        Limits(config.max_calls_per_day, config.max_calls_per_week, config.max_calls_per_month),
    )


def _records_for(source: str, args: argparse.Namespace, settings, conn):
    if source == "fixture":
        from jobmarket.sources import fixtures

        return fixtures.generate(n=args.count, months=args.months), None
    if source == "adzuna":
        import yaml

        from jobmarket.sources.adzuna import AdzunaClient, AdzunaConfig

        cfg = yaml.safe_load((settings.reference_dir / "ingestion.yaml").read_text("utf-8"))
        config = AdzunaConfig.from_settings(settings, cfg)
        client = AdzunaClient(config, budget=_adzuna_budget(conn, config))
        return client.fetch(days=args.days), client
    if source == "eures":
        import yaml

        from jobmarket.occupations import load_occupation_uris
        from jobmarket.sources.eures import EuresClient, EuresConfig

        cfg = yaml.safe_load((settings.reference_dir / "ingestion.yaml").read_text("utf-8"))
        uris = load_occupation_uris(settings.reference_dir / "esco_occupations.yaml")
        client = EuresClient(EuresConfig.from_settings(cfg, uris))
        # Vacancies we already have cost no detail call.
        known = {
            r[0]
            for r in conn.execute("SELECT external_id FROM vacancies WHERE source_id = 'eures'")
        }
        return client.fetch(days=args.days, known=known), client
    raise SystemExit(f"Unknown source {source!r}")


def cmd_ingest(args: argparse.Namespace) -> int:
    from jobmarket.ingest import ingest

    settings = load_settings()
    ref = load_reference(settings.reference_dir)
    with open_db(settings.db_path) as conn:
        sync_sources(conn, ref)
        records, client = _records_for(args.source, args, settings, conn)
        covers_from = None
        if client is not None:
            from datetime import date, timedelta

            days = args.days or client.config.default_days
            covers_from = (date.today() - timedelta(days=days)).isoformat()
        result = ingest(
            conn, args.source, records, ref, covers_from=covers_from, backfill=args.backfill
        )
        budget_used = None
        budget = getattr(client, "budget", None)
        if budget is not None:
            budget.commit()  # also count the calls of a failed run
            budget_used = budget.describe()  # while the database is still open
        if client is not None and client.stats.budget_exhausted:
            # Results come newest first: the oldest days are missing, so claim no coverage.
            conn.execute(
                "UPDATE ingestion_runs SET covers_from = NULL WHERE id = ?", (result.run_id,)
            )
    print(f"Run {result.run_id} [{result.status}]: fetched {result.fetched}, new {result.new}")
    if client is not None:
        s = client.stats
        detail = (
            f"per query: {s.per_query}"
            if hasattr(s, "per_query")
            else f"listed {s.listed}, details fetched {s.details}"
        )
        print(f"API calls: {s.calls}; {detail}")
        if budget_used:
            print(f"Call budget used — {budget_used}")
        if s.budget_exhausted:
            print(
                f"Stopped on the call budget ({s.budget_note}): not everything was fetched. "
                "Run again later to continue."
            )
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        return 1
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    from jobmarket.corrections import load_corrections
    from jobmarket.process import process

    settings = load_settings()
    ref = load_reference(settings.reference_dir)
    corrections = load_corrections(settings.corrections_file, ref)
    with open_db(settings.db_path) as conn:
        sync_sources(conn, ref)
        r = process(conn, ref, corrections)
    print(
        f"Processed {r.vacancies} vacancies: {r.duplicates} duplicates, "
        f"{r.ict} unique ICT vacancies, {r.purged} texts purged (retention)"
    )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from jobmarket.stats.run import refresh_all

    settings = load_settings()
    ref = load_reference(settings.reference_dir)
    with open_db(settings.db_path) as conn:
        sync_sources(conn, ref)
        results = refresh_all(
            conn, ref, settings.reference_dir, settings.manual_dir, which=args.source
        )
    failed = 0
    for r in results:
        print(f"{r.source_id:12} [{r.status}] {r.rows} observations")
        if r.error:
            failed += 1
            print(f"  {r.error}", file=sys.stderr)
    return 1 if failed else 0


def _history_dir(settings, dataset: str):
    # Sample (fixture) aggregates never mix with, or end up next to, the real history.
    return (
        settings.history_dir
        if dataset == "real"
        else settings.repo_root / "var" / "sample" / "aggregates"
    )


def cmd_aggregate(args: argparse.Namespace) -> int:
    from jobmarket.aggregate import compute, merge_into_history

    settings = load_settings()
    with open_db(settings.db_path) as conn:
        agg = compute(conn, sample=args.dataset == "sample")
    result = merge_into_history(_history_dir(settings, args.dataset), agg, force=args.force)
    print(
        f"Aggregated months {agg.months[0] if agg.months else '-'} .. "
        f"{agg.months[-1] if agg.months else '-'}; rows: {result.written}"
    )
    if result.protected:
        print(
            f"warning: kept the existing history for {', '.join(result.protected)}: the database "
            f"only covers the source from {agg.coverage_start}, and the history has earlier "
            "postings for these months. Set JOBMARKET_INGEST_DAYS for one run, or restore the "
            "database, to close the gap."
        )
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    from jobmarket.publish import prune_snapshots, publish

    settings = load_settings()
    ref = load_reference(settings.reference_dir)
    with open_db(settings.db_path) as conn:
        sync_sources(conn, ref)
        result = publish(
            conn,
            ref,
            settings,
            dataset=args.dataset,
            history_dir=_history_dir(settings, args.dataset),
        )
    prune_snapshots(settings.snapshots_dir)
    for w in result.report.warnings:
        print(f"warning: {w}")
    for e in result.report.errors:
        print(f"ERROR: {e}", file=sys.stderr)
    if result.published:
        print(f"Published snapshot {result.snapshot_id} to {settings.publish_dir}")
        return 0
    print(
        f"Snapshot {result.snapshot_id} rejected; the previous snapshot stays online. "
        f"Staged files: {result.staging_dir}",
        file=sys.stderr,
    )
    return 1


def cmd_budget(args: argparse.Namespace) -> int:
    """What is left of the source's call limits."""
    import yaml

    from jobmarket.sources.adzuna import AdzunaConfig

    settings = load_settings()
    cfg = yaml.safe_load((settings.reference_dir / "ingestion.yaml").read_text("utf-8"))
    config = AdzunaConfig.from_settings(settings, cfg)
    with open_db(settings.db_path) as conn:
        budget = _adzuna_budget(conn, config)
        print(f"adzuna calls used — {budget.describe()}")
        for window, left in budget.remaining().items():
            if left is not None:
                print(f"  {window:<6} {left:>6} calls left (about {left * 50:,} vacancies)")
    return 0


def cmd_history_repair(args: argparse.Namespace) -> int:
    """Take months from a shipped history where the working history holds less detail."""
    from pathlib import Path

    from jobmarket.aggregate import repair_from_seed, stored_per_month

    settings = load_settings()
    seed = Path(args.source)
    if not seed.is_dir():
        print(f"No history to repair from: {seed} does not exist", file=sys.stderr)
        return 1
    with open_db(settings.db_path) as conn:
        stored = stored_per_month(conn, sample=args.dataset == "sample")
    replaced = repair_from_seed(seed, _history_dir(settings, args.dataset), stored)
    if replaced:
        print(
            "Replaced months from "
            + str(seed)
            + ": "
            + ", ".join(f"{n} in {name}.csv" for name, n in sorted(replaced.items()))
        )
    else:
        print(f"Nothing to repair: the history is at least as complete as {seed}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """What the working store and the aggregate history hold right now (FR-20)."""
    from jobmarket.aggregate import coverage_start, read_history

    settings = load_settings()
    print(f"database     {settings.db_path}")
    with open_db(settings.db_path) as conn:
        counts = conn.execute(
            """SELECT COUNT(*), SUM(is_ict = 1 AND duplicate_of IS NULL),
                      SUM(is_ict = 1 AND duplicate_of IS NULL AND corop IS NOT NULL),
                      MIN(posted_at), MAX(posted_at)
               FROM vacancies WHERE is_sample = 0"""
        ).fetchone()
        total, ict, located, first, last = (c or 0 for c in counts)
        print(f"vacancies    {total} stored, {ict} unique ICT, {located} of those in a COROP area")
        print(f"posted       {first or '-'} .. {last or '-'}")
        print(f"coverage     from {coverage_start(conn, sample=False) or '-'}")
        print("runs")
        for r in conn.execute(
            """SELECT source_id, started_at, status, records_fetched, records_new, backfill, error
               FROM ingestion_runs ORDER BY id DESC LIMIT 5"""
        ):
            note = " (backfill)" if r["backfill"] else ""
            error = f" — {r['error'][:60]}" if r["error"] else ""
            print(
                f"  {r['started_at']} {r['source_id']:<14} {r['status']:<8} "
                f"fetched {r['records_fetched']:>5} new {r['records_new']:>5}{note}{error}"
            )

    print(f"history      {settings.history_dir}")
    rows = read_history(settings.history_dir, "vacancies")
    months = sorted({r["month"] for r in rows})
    corop_rows = sum(1 for r in rows if r["geo"].startswith("c:"))
    print(
        f"  {len(rows)} rows over {len(months)} months "
        f"({months[0] if months else '-'} .. {months[-1] if months else '-'})"
    )
    print(f"  {corop_rows} rows per COROP area (0 means the map has nothing to show)")

    published = settings.publish_dir
    print(f"published    {published}")
    for name in ("meta.json", "stats.json", "map.json"):
        path = published / name
        print(
            f"  {name:<12} {'present' if path.is_file() else 'MISSING'}"
            + (f", {path.stat().st_size:,} bytes" if path.is_file() else "")
        )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """The scheduled job: ingest, statistics, process, aggregate, publish."""
    import os

    days = os.environ.get("JOBMARKET_INGEST_DAYS")
    if args.dataset == "real":
        # e.g. 30 for the first run on a new server, to close the gap since the last run
        extra = ["--days", days] if days else []
        ingest_steps = [
            ["ingest", "--source", "adzuna", *extra],
            ["ingest", "--source", "eures", *extra],
        ]
    else:
        ingest_steps = [["ingest", "--source", "fixture"]]
    steps = [
        *ingest_steps,
        ["stats"],
        ["process"],
        ["aggregate", "--dataset", args.dataset],
        ["publish", "--dataset", args.dataset],
    ]
    status = 0
    for step in steps:
        print(f"== jobmarket {' '.join(step)}")
        code = main(step)
        # A failed source is logged and the run continues on the last good data (NFR-07);
        # only publish decides whether the site changes.
        if code and step[0] == "publish":
            status = code
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobmarket", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="create or upgrade the working database")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("ingest", help="fetch vacancies from a source into the database")
    p.add_argument("--source", choices=["adzuna", "eures", "fixture"], required=True)
    p.add_argument(
        "--days", type=int, help="adzuna/eures: days of history (default from ingestion.yaml)"
    )
    p.add_argument("--count", type=int, default=6000, help="fixture: number of vacancies")
    p.add_argument("--months", type=int, default=24, help="fixture: months of history")
    p.add_argument(
        "--backfill",
        action="store_true",
        help="reach into the past (with --days): the source only still lists a fraction of what "
        "was posted then, so these vacancies are stored but stay out of the published figures",
    )
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("budget", help="show how many API calls the plan limits still allow")
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser("status", help="what the database, the history and the snapshot hold")
    p.set_defaults(func=cmd_status)

    history = sub.add_parser("history", help="aggregate history tools").add_subparsers(
        dest="history_command", required=True
    )
    p = history.add_parser(
        "repair", help="take months from a shipped history that hold more detail than ours"
    )
    p.add_argument("--source", required=True, help="directory with the history to compare against")
    p.add_argument("--dataset", choices=["real", "sample"], default="real")
    p.set_defaults(func=cmd_history_repair)

    p = sub.add_parser("process", help="normalise, deduplicate and classify stored vacancies")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("stats", help="refresh CBS and manual (HBO-Monitor, ROA, UWV) statistics")
    p.add_argument("--source", choices=["all", "cbs", "manual"], default="all")
    p.set_defaults(func=cmd_stats)

    for name, func, help_text in [
        ("aggregate", cmd_aggregate, "update the monthly aggregate history (data/aggregates)"),
        ("publish", cmd_publish, "build, validate and publish the site data"),
        ("run", cmd_run, "full scheduled run: ingest, stats, process, aggregate, publish"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument(
            "--dataset",
            choices=["real", "sample"],
            default="real",
            help="real = collected vacancies; sample = synthetic fixture vacancies",
        )
        if name == "aggregate":
            p.add_argument(
                "--force",
                action="store_true",
                help="recompute months the history protects; for a deliberate change of the "
                "rules, after which the old figures are no longer the ones we stand behind",
            )
        p.set_defaults(func=func)

    ref = sub.add_parser("reference", help="reference data tools").add_subparsers(
        dest="ref_command", required=True
    )
    p = ref.add_parser("check", help="validate data/reference/*.yaml")
    p.set_defaults(func=cmd_reference_check)
    p = ref.add_parser(
        "update-regions", help="rebuild municipalities.csv from the CBS area classifications"
    )
    p.set_defaults(func=cmd_update_regions)
    p = ref.add_parser(
        "update-occupations", help="rebuild the ESCO occupations that count as ICT (for EURES)"
    )
    p.set_defaults(func=cmd_update_occupations)
    p = ref.add_parser("resolve-esco", help="look up ESCO links for skills")
    p.add_argument("--refresh", action="store_true", help="re-resolve unchecked links")
    p.set_defaults(func=cmd_resolve_esco)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
