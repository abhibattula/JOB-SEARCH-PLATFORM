"""Refresh orchestration: run all sources concurrently, isolate failures,
record per-source progress, then run post-ingest stages (classification and
scoring are wired in by later phases).

Concurrency model: the web layer calls trigger_refresh() which makes the
start/blocked decision synchronously (so the HTTP response is truthful) and
executes the run on a daemon thread. The CLI and tests call run_refresh()
which executes inline. REFRESH_SYNC=1 forces inline execution everywhere.
"""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from . import db

log = logging.getLogger(__name__)


def load_companies() -> list[dict]:
    override = os.environ.get("COMPANIES_PATH")
    if override:
        path = Path(override)
    else:
        from . import paths

        path = paths.resource_path("companies.yml")
    if not path.exists():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc.get("companies") or []


def _source_names() -> list[str]:
    from .ingest import SOURCE_ORDER

    return list(SOURCE_ORDER)


def _get_source(name: str):
    from .ingest import get_source

    return get_source(name)


# 008 (FR-012): date-bearing rows older than this never enter the DB —
# "latest postings" is enforced at ingest, not just at display.
INGEST_MAX_AGE_DAYS = 14

# 008 (FR-013): sources that fetch ENTIRE boards, where absence from a
# successful fetch authoritatively means the posting is gone.
FULL_BOARD_SOURCES = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters")

# 008: scraped-board rows can't be board-diffed; their apply URLs get a
# bounded HEAD liveness check instead.
SCRAPED_SOURCES = ("jobspy",)
LIVENESS_CHECKS_PER_RUN = 20


def _ingest_cutoff() -> str:
    from datetime import datetime, timedelta, timezone

    return (
        datetime.now(timezone.utc) - timedelta(days=INGEST_MAX_AGE_DAYS)
    ).strftime("%Y-%m-%d")


def _run_source(run_id: int, name: str, entries: list[dict]) -> None:
    db.update_run_source(run_id, name, state="running", found=0, added=0)
    found = added = 0
    cutoff = _ingest_cutoff()
    try:
        module = _get_source(name)
        for job in module.fetch_jobs(entries):
            found += 1
            payload = job.to_dict()
            posted = payload.get("posted_date")
            if posted and posted[:10] < cutoff:
                continue  # older than the freshness window (FR-012)
            if db.upsert_job(payload) == "inserted":
                added += 1
            if found % 50 == 0:
                db.update_run_source(run_id, name, found=found, added=added)
        db.update_run_source(run_id, name, state="done", found=found, added=added)
    except Exception as exc:  # per-source isolation (FR-013)
        log.warning("source %s failed", name, exc_info=True)
        db.update_run_source(
            run_id, name, state="failed", found=found, added=added, error=str(exc)
        )


def delist_missing(run_id: int) -> int:
    """Board-diff delisting (FR-013): after the sources finish, mark rows of
    full-board sources that a SUCCESSFUL board fetch no longer contains."""
    status = db.get_run_status()
    if status.get("run_id") != run_id or not status.get("started_at"):
        return 0
    run_start = status["started_at"]
    total = 0
    for source, info in (status.get("sources") or {}).items():
        if source in FULL_BOARD_SOURCES and info.get("state") == "done":
            total += db.delist_missing_for_source(source, run_start)
    if total:
        log.info("delisted %d postings no longer on their boards", total)
    return total


def _check_scraped_liveness(limit: int = LIVENESS_CHECKS_PER_RUN) -> int:
    """Bounded HEAD checks on scraped-board apply URLs (FR-013): 404/410 or
    a redirect to the site root means the posting is dead. Network errors
    change NOTHING — a job is never delisted on uncertainty. Uses the same
    polite per-domain rate limit as ingestion."""
    from urllib.parse import urlparse

    from .ingest import base

    dead = 0
    for row in db.jobs_for_liveness_check(SCRAPED_SOURCES, limit):
        try:
            resp = base.polite_head(row["url"])
        except Exception:
            continue
        final_path = urlparse(str(resp.url)).path
        bounced_home = str(resp.url) != row["url"] and final_path in ("", "/")
        if resp.status_code in (404, 410) or bounced_home:
            db.mark_job_delisted(row["id"])
            dead += 1
        elif resp.status_code < 400:
            db.touch_job_seen(row["id"])
    if dead:
        log.info("liveness check delisted %d dead scraped postings", dead)
    return dead


def _post_ingest(run_id: int) -> None:
    """Post-ingest stages: delisting, sponsorship matching, classification,
    scoring, liveness, prune, then fresh-match alerts."""
    delist_missing(run_id)
    _classify_new_jobs()
    _score_new_jobs()
    try:
        _check_scraped_liveness()
    except Exception:
        log.warning("liveness check failed", exc_info=True)
    removed = db.prune_old_jobs()
    if removed:
        log.info("pruned %d stale untouched jobs", removed)
    from . import alerts

    status = db.get_run_status()
    if status.get("run_id") == run_id and status.get("started_at"):
        count = alerts.process(since=status["started_at"])
        if count:
            db.update_run_source(run_id, "_alerts", state="done", found=count)


def _classify_new_jobs() -> None:
    from . import filters, sponsorship

    # New companies (from HN/jobspy) get matched against stored H-1B records.
    sponsorship.apply_to_companies()
    for job in db.jobs_needing_classification():
        description = job.get("description") or ""
        entry = filters.classify_entry_level(job["title"], description)
        jd_flag, phrase = filters.scan_sponsorship(description)
        rating, evidence = filters.rate_sponsorship(
            job.get("h1b_approvals") or 0, jd_flag
        )
        if phrase:
            evidence["phrase"] = phrase
        db.set_classification(job["id"], entry, rating, evidence)


def _analyze(resume_text: str, title: str, company: str, description: str):
    from . import matcher

    return matcher.analyze_match(resume_text, title, company, description)


def _score_new_jobs() -> None:
    """Score unscored entry-level jobs against the resume (FR-012).

    Three-tier precedence (005): cloud LLM key > bundled local model > the
    deterministic basic matcher. Cloud/local calls are throttled + capped
    for the free tier; basic is unlimited (no external cost). Whichever tier
    just became available also upgrades jobs scored by a lower tier
    (db.jobs_needing_score's upgrade_methods). Failures leave jobs visible
    and unscored.
    """
    import json

    from . import basic_match, matcher, settings

    profile = db.get_profile()
    if not profile or not profile.get("resume_text"):
        return
    resume_text = profile["resume_text"]
    # 006-E: the user's explicit Profile skills list boosts basic-tier
    # matching alongside whatever regex extraction finds in the raw resume
    # text — matters most for no-cloud-key users.
    profile_skills = set(profile.get("skills") or [])
    tier = matcher.scoring_tier()  # "cloud" | "local" | "basic"
    upgrade_methods = {"cloud": ("basic", "local"), "local": ("basic",), "basic": ()}[tier]
    cap = int(settings.get("MAX_SCORE_PER_RUN") or "150") if tier != "basic" else 2000
    for job in db.jobs_needing_score(limit=cap, upgrade_methods=upgrade_methods):
        description = job.get("description") or ""
        if tier in ("cloud", "local"):
            analysis = _analyze(resume_text, job["title"], job["company"], description)
            if analysis is None:
                continue
            method = "llm" if tier == "cloud" else "local"
        else:
            analysis = basic_match.score(
                resume_text, job["title"], description, extra_skills=profile_skills
            )
            method = "basic"
        payload = analysis.model_dump()
        payload["method"] = method
        db.set_match(job["id"], analysis.match_score, json.dumps(payload))


def _execute(run_id: int) -> dict:
    companies = load_companies()
    names = _source_names()
    by_source: dict[str, list[dict]] = {name: [] for name in names}
    for entry in companies:
        ats = entry.get("ats")
        if ats in by_source:
            by_source[ats].append(entry)
    for name in names:
        db.update_run_source(run_id, name, state="queued")
    if names:
        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            for name in names:
                pool.submit(_run_source, run_id, name, by_source.get(name, []))
    try:
        _post_ingest(run_id)
    except Exception:
        log.warning("post-ingest stage failed", exc_info=True)
    db.finish_run(run_id)
    status = db.get_run_status()
    return {"started": True, "run_id": run_id, "sources": status["sources"]}


def _blocked_reply() -> dict:
    status = db.get_run_status()
    reason = "running" if status["active"] else "cooldown"
    return {"started": False, "reason": reason}


def run_refresh(trigger: str, force: bool = False) -> dict:
    """Synchronous full refresh (CLI, tests, REFRESH_SYNC mode)."""
    db.init_db()
    run_id = db.start_run(trigger, force=force)
    if run_id is None:
        return _blocked_reply()
    return _execute(run_id)


def trigger_refresh(trigger: str, force: bool = False) -> dict:
    """Start a refresh for the web layer; returns immediately."""
    if os.environ.get("REFRESH_SYNC") == "1":
        return run_refresh(trigger, force=force)
    db.init_db()
    run_id = db.start_run(trigger, force=force)
    if run_id is None:
        return _blocked_reply()
    thread = threading.Thread(target=_execute, args=(run_id,), daemon=True)
    thread.start()
    return {"started": True, "run_id": run_id}
