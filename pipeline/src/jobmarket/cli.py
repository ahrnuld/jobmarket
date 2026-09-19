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


def _records_for(source: str, args: argparse.Namespace, settings):
    if source == "fixture":
        from jobmarket.sources import fixtures

        return fixtures.generate(n=args.count, months=args.months), None
    if source == "adzuna":
        import yaml

        from jobmarket.sources.adzuna import AdzunaClient, AdzunaConfig

        cfg = yaml.safe_load((settings.reference_dir / "ingestion.yaml").read_text("utf-8"))
        client = AdzunaClient(AdzunaConfig.from_settings(settings, cfg))
        return client.fetch(days=args.days), client
    raise SystemExit(f"Unknown source {source!r}")


def cmd_ingest(args: argparse.Namespace) -> int:
    from jobmarket.ingest import ingest

    settings = load_settings()
    ref = load_reference(settings.reference_dir)
    with open_db(settings.db_path) as conn:
        sync_sources(conn, ref)
        records, client = _records_for(args.source, args, settings)
        result = ingest(conn, args.source, records, ref)
    print(f"Run {result.run_id} [{result.status}]: fetched {result.fetched}, new {result.new}")
    if client is not None:
        s = client.stats
        print(f"API calls: {s.calls}; per query: {s.per_query}")
        if s.budget_exhausted:
            print("Call budget (max_calls_per_run) reached: some results were not fetched.")
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
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("process", help="normalise, deduplicate and classify stored vacancies")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("stats", help="refresh CBS and manual (HBO-Monitor, ROA, UWV) statistics")
    p.add_argument("--source", choices=["all", "cbs", "manual"], default="all")
    p.set_defaults(func=cmd_stats)

    ref = sub.add_parser("reference", help="reference data tools").add_subparsers(
        dest="ref_command", required=True
    )
    p = ref.add_parser("check", help="validate data/reference/*.yaml")
    p.set_defaults(func=cmd_reference_check)
    p = ref.add_parser("resolve-esco", help="look up ESCO links for skills")
    p.add_argument("--refresh", action="store_true", help="re-resolve unchecked links")
    p.set_defaults(func=cmd_resolve_esco)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
