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


def _run_source(run_id: int, name: str, entries: list[dict]) -> None:
    db.update_run_source(run_id, name, state="running", found=0, added=0)
    found = added = 0
    try:
        module = _get_source(name)
        for job in module.fetch_jobs(entries):
            found += 1
            if db.upsert_job(job.to_dict()) == "inserted":
                added += 1
            if found % 50 == 0:
                db.update_run_source(run_id, name, found=found, added=added)
        db.update_run_source(run_id, name, state="done", found=found, added=added)
    except Exception as exc:  # per-source isolation (FR-013)
        log.warning("source %s failed", name, exc_info=True)
        db.update_run_source(
            run_id, name, state="failed", found=found, added=added, error=str(exc)
        )


def _post_ingest(run_id: int) -> None:
    """Post-ingest stages: sponsorship matching, classification, scoring, prune."""
    _classify_new_jobs()
    _score_new_jobs()
    removed = db.prune_old_jobs()
    if removed:
        log.info("pruned %d stale untouched jobs", removed)


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

    Volume is capped per run and calls are throttled inside the matcher so a
    huge first refresh cannot exhaust the free-tier daily quota. Failures
    leave jobs visible and unscored.
    """
    from . import matcher, settings

    profile = db.get_profile()
    if not profile or not profile.get("resume_text") or not matcher.llm_available():
        return
    cap = int(settings.get("MAX_SCORE_PER_RUN") or "150")
    resume_text = profile["resume_text"]
    for job in db.jobs_needing_score(limit=cap):
        analysis = _analyze(
            resume_text, job["title"], job["company"], job.get("description") or ""
        )
        if analysis is not None:
            db.set_match(job["id"], analysis.match_score, analysis.model_dump_json())


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
