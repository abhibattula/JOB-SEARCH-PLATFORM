"""Headless pipeline runner (Constitution IV: same engine, no web layer).

Usage:
    python cli.py refresh [--force]
    python cli.py load-sponsorship [--uscis DIR] [--dol DIR]
"""
import argparse
import logging

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def cmd_refresh(args) -> int:
    from engine import pipeline

    summary = pipeline.run_refresh(trigger="cli", force=args.force)
    if not summary["started"]:
        print(f"Refresh not started: {summary['reason']}")
        return 1
    print(f"Refresh run {summary['run_id']} complete:")
    for name, info in sorted(summary["sources"].items()):
        state = info.get("state", "?")
        line = f"  {name:12} {state:8} found={info.get('found', 0):4}  new={info.get('added', 0):4}"
        if info.get("error"):
            line += f"  error={info['error'][:80]}"
        print(line)
    return 0


def cmd_load_sponsorship(args) -> int:
    from engine import db, sponsorship

    db.init_db()
    stats = sponsorship.load_all(uscis_dir=args.uscis, dol_dir=args.dol)
    print(
        f"Loaded {stats['employers']} employers "
        f"({stats['uscis_files']} USCIS files, {stats['dol_files']} DOL files); "
        f"matched {stats['companies_matched']} seed companies."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="job-engine")
    sub = parser.add_subparsers(dest="command", required=True)

    refresh = sub.add_parser("refresh", help="run the full ingest/classify/score pipeline")
    refresh.add_argument("--force", action="store_true", help="bypass the 30-min cooldown")
    refresh.set_defaults(func=cmd_refresh)

    from engine import paths

    load = sub.add_parser("load-sponsorship", help="load USCIS/DOL data into the DB")
    load.add_argument(
        "--uscis", default=str(paths.data_dir() / "uscis"),
        help="dir with USCIS Data Hub CSVs",
    )
    load.add_argument(
        "--dol", default=str(paths.data_dir() / "dol"),
        help="dir with DOL LCA disclosure files",
    )
    load.set_defaults(func=cmd_load_sponsorship)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
