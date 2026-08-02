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


def load_seed_companies() -> list[dict]:
    """The bundled companies.yml — a one-time SEED source only (008). The
    runtime source of monitored boards is the watchlist table."""
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


def load_companies() -> list[dict]:
    """008 (FR-015): DB-backed watchlist — seeded from YAML on first call,
    user-editable from Settings, edits survive updates."""
    from . import watchlist

    watchlist.ensure_seeded()
    return watchlist.load_active()


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
    """Post-ingest stages: delisting, classification, RANKING, liveness,
    prune, then fresh-match alerts.

    020: every stage here is now fast and deterministic, so the run reaches
    db.finish_run() in seconds. The AI assessment that used to sit between
    ranking and liveness — holding the run open for 2 h 47 m and delaying
    these alerts by the same amount — moved to engine/upgrade.py, which starts
    only AFTER the run is closed (see _execute).
    """
    delist_missing(run_id)
    _classify_new_jobs()
    _rank_new_jobs()
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
    # 020 (FR-022): row counts just changed, and idx_jobs_sort_date is inert
    # without current statistics — the index alone left the query plan
    # completely unchanged when measured. ~31 ms over 22k rows, which is noise
    # next to a refresh.
    db.refresh_statistics()


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


# 020: ranking reads candidates in chunks so a large backlog never loads the
# whole jobs table into memory at once. Sized well above a typical refresh's
# intake and far below the applicant's 937-job eligible pool.
_RANK_BATCH = 500


def _rank_new_jobs() -> None:
    """020 (FR-001/FR-002): give EVERY eligible unscored job a score, now.

    Uses ONLY engine/basic_match.py — no cloud call, no on-device inference,
    no cap. Measured at 0.0044 s a job, so the applicant's entire 627-job
    backlog ranks in under three seconds.

    This replaces the pre-020 stage that picked ONE tier for the whole run and
    scored a capped slice with it. When the bundled model was present that tier
    was "local" at ~67 s a job, so a 150-job cap held the refresh open for
    2 h 47 m — longer than db.STALE_RUN_MINUTES, which meant the next feed page
    load declared the run crashed and started a second scoring loop beside it.
    Neither ever finished. The applicant's database sat at 310 of 937 eligible
    jobs scored (specs/020-every-job-ranked/baseline.txt).

    Full AI assessment still happens — it just happens in engine/upgrade.py,
    outside the run, best-first, and only for jobs worth spending a minute on.

    Embedding deliberately does NOT happen here. It costs 0.6 s a job and
    exists to ORDER the assessment pass, so it belongs to that pass; running
    its 300-job cap inline would add three minutes to every refresh.
    """
    import json

    from . import basic_match

    profile = db.get_profile()
    if not profile or not profile.get("resume_text"):
        return
    resume_text = profile["resume_text"]
    # 006-E: the user's explicit Profile skills list boosts matching alongside
    # whatever regex extraction finds in the raw resume text.
    profile_skills = set(profile.get("skills") or [])

    ranked = 0
    while True:
        candidates = db.jobs_needing_score(limit=_RANK_BATCH)
        if not candidates:
            break
        writes: list[tuple[int, float, str]] = []
        for job in candidates:
            try:
                analysis = basic_match.score(
                    resume_text, job["title"], job.get("description") or "",
                    extra_skills=profile_skills,
                )
            except Exception:  # noqa: BLE001 — one bad posting cannot stall the feed
                log.warning("could not rank job %s", job["id"], exc_info=True)
                continue
            payload = analysis.model_dump()
            payload["method"] = "basic"
            writes.append((job["id"], analysis.match_score, json.dumps(payload)))
        db.set_matches(writes)  # one transaction per chunk, not per job
        ranked += len(writes)
        if not writes:
            # every job in this chunk failed to rank; another pass would fetch
            # the same rows forever
            log.warning("ranking made no progress on %d candidates; stopping",
                        len(candidates))
            break
    if ranked:
        log.info("ranked %d job(s) with the keyword matcher", ranked)


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
    # 020 (guarantee L3): the AI assessment pass starts only once the run is
    # CLOSED. Started any earlier, a slow or failing pass could hold the run
    # open again — which is precisely the defect this feature removes. It is
    # single-flight, so a second refresh cannot stack a second pass.
    from . import upgrade

    upgrade.start("refresh")
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
