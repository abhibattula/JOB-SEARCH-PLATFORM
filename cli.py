"""Headless pipeline runner (Constitution IV: same engine, no web layer).

Usage:
    python cli.py refresh [--force] [--assess]
    python cli.py assess [--limit N]
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


def cmd_assess(args) -> int:
    """020: run one background-style AI assessment pass, synchronously.

    Every eligible job already has a keyword score from the refresh; this is
    the slower tier that upgrades the best candidates to a full analysis.
    Roughly a minute a job on a laptop CPU, so it is bounded by --limit (or
    the MAX_SCORE_PER_RUN setting).
    """
    from engine import db, upgrade

    db.init_db()
    result = upgrade.run_once(limit=args.limit)
    if not result["total"]:
        print("Nothing to assess (no candidates, no resume, or no AI tier).")
        return 0
    print(f"Assessed {result['done']}/{result['total']} job(s); "
          f"{result['failed']} failed.")
    if result["paused_for_session"]:
        print("Stopped early: an application was being filled — "
              "applying always takes priority.")
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

    refresh = sub.add_parser("refresh", help="run the full ingest/classify/rank pipeline")
    refresh.add_argument("--force", action="store_true", help="bypass the 30-min cooldown")
    refresh.set_defaults(func=cmd_refresh)

    assess = sub.add_parser(
        "assess",
        help="upgrade the best keyword-scored jobs to a full AI assessment")
    assess.add_argument("--limit", type=int, default=None,
                        help="how many jobs to assess (default: the "
                             "MAX_SCORE_PER_RUN setting)")
    assess.set_defaults(func=cmd_assess)

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
    # 015 (R2): multiprocessing spawn under PyInstaller needs this before
    # any work — the frozen exe re-executes itself for the isolated AI child.
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
