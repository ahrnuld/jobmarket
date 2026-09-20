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
    from jobmarket.reference_geo import build, write_csv

    settings = load_settings()
    rows = build()
    path = settings.reference_dir / "municipalities.csv"
    write_csv(path, rows)
    corops = {r.corop for r in rows}
    print(f"Wrote {len(rows)} municipality names and {len(corops)} COROP areas to {path}")
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
        if client is not None and client.budget is not None:
            client.budget.commit()  # also count the calls of a failed run
            budget_used = client.budget.describe()  # while the database is still open
        if client is not None and client.stats.budget_exhausted:
            # Results come newest first: the oldest days are missing, so claim no coverage.
            conn.execute(
                "UPDATE ingestion_runs SET covers_from = NULL WHERE id = ?", (result.run_id,)
            )
    print(f"Run {result.run_id} [{result.status}]: fetched {result.fetched}, new {result.new}")
    if client is not None:
        s = client.stats
        print(f"API calls: {s.calls}; per query: {s.per_query}")
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
    result = merge_into_history(_history_dir(settings, args.dataset), agg)
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


def cmd_run(args: argparse.Namespace) -> int:
    """The scheduled job: ingest, statistics, process, aggregate, publish."""
    import os

    ingest_step = ["ingest", "--source", "adzuna" if args.dataset == "real" else "fixture"]
    if args.dataset == "real" and os.environ.get("JOBMARKET_INGEST_DAYS"):
        # e.g. 30 for the first run on a new server, to close the gap since the last run
        ingest_step += ["--days", os.environ["JOBMARKET_INGEST_DAYS"]]
    steps = [
        ingest_step,
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
    p.add_argument("--source", choices=["adzuna", "fixture"], required=True)
    p.add_argument("--days", type=int, help="adzuna: days of history (default from ingestion.yaml)")
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
            help="real = Adzuna vacancies; sample = synthetic fixture vacancies",
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
    p = ref.add_parser("resolve-esco", help="look up ESCO links for skills")
    p.add_argument("--refresh", action="store_true", help="re-resolve unchecked links")
    p.set_defaults(func=cmd_resolve_esco)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
