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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobmarket", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="create or upgrade the working database")
    p.set_defaults(func=cmd_init_db)

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
