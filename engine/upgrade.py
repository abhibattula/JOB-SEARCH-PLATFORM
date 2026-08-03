"""020 (US2/US3): the background AI assessment pass.

Scoring is two tiers with very different costs. RANKING — the deterministic
keyword matcher — covers every eligible job during the refresh at 0.0044 s a
job. ASSESSMENT — a full model-generated analysis — costs ~67 s a job on the
applicant's laptop, and that is the whole reason this module exists.

Feature 019 and earlier ran assessment INLINE inside the refresh run. At the
150-job cap that held the run open for 2 h 47 m, which is longer than
db.STALE_RUN_MINUTES — so a feed page load thirty minutes later declared the
live run crashed and started a second scoring loop beside the first. Both read
the same unscored set and re-scored the same jobs through one serialized
inference worker. The applicant's database converged to 310 of 937 eligible
jobs scored and stayed there (see specs/020-every-job-ranked/baseline.txt).

So the pass lives here instead: outside the run, single-flight, resumable, and
standing down completely whenever an application is being filled. Contract:
specs/020-every-job-ranked/contracts/upgrade-api.md.

Deliberately stores NOTHING. Every pass rebuilds its candidate list from the
database, which is what makes resumability free — an interrupted pass loses at
most the one job in flight, and restarting can never double-score, because an
assessed job no longer matches upgrade_methods=("basic",).

This module is pure engine (Principle IV): it imports nothing from web/, and
pipeline imports IT — never the other way round.
"""
from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger(__name__)

# How many jobs one pass assesses. Read from settings; this is the fallback.
# 40 rather than the pre-020 cap of 150 because a unit of work here costs
# ~67 s on the applicant's laptop — 40 is roughly 45 minutes of background
# work, which is a pass that actually finishes.
DEFAULT_LIMIT = 40

# 008 (FR-029): embeddings order the pass. Inherited unchanged from the stage
# this module replaces, including its per-pass cap.
EMBED_LIMIT = 300

# FR-013: how the pass yields to an application fill session. It polls rather
# than exiting immediately so a short session (open a form, fill it, submit)
# does not cost a whole pass; past the cap it gives up and lets the next
# trigger start a fresh one, which is free because passes are resumable.
PAUSE_POLL_S = 2.0
MAX_PAUSE_S = 300.0

_lock = threading.Lock()
_thread: threading.Thread | None = None


def _blank() -> dict:
    return {"running": False, "done": 0, "total": 0,
            "failed": 0, "paused_for_session": False}


_state: dict = _blank()


def progress() -> dict:
    """Read-only snapshot for the status endpoint (FR-011).

    Always the complete shape, even before the first pass — the feed asks on
    every page load, including the first one after install, and the template
    reads every key unconditionally. Returns a COPY so a caller cannot mutate
    pass state, and never blocks on the pass itself.
    """
    with _lock:
        return dict(_state)


def reset_for_tests() -> None:
    """Mirrors the reset_for_tests convention in inference/ext_backend/
    browser_controller so each test starts from a clean pass. Joins a live
    pass first — one leaking into the next test would assess against a
    database that no longer holds those job ids."""
    global _state, _interactive
    join_for_tests(timeout=15)
    with _lock:
        _state = _blank()
        # 021: a leaked interactive claim would make every later pass stand
        # down forever, which reads as "the AI stopped working".
        _interactive = 0


def join_for_tests(timeout: float = 30.0) -> None:
    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)


def _limit() -> int:
    from . import settings

    raw = settings.get("MAX_SCORE_PER_RUN")
    try:
        value = int(raw) if raw else DEFAULT_LIMIT
    except (TypeError, ValueError):
        value = DEFAULT_LIMIT
    return max(0, value)


def start(reason: str = "refresh") -> bool:
    """Begin one assessment pass on a daemon thread.

    Returns True if a pass was started, False if one is already running —
    NEVER a queued second pass (FR-009). This is the direct fix for the defect
    in research R2: pre-020 the scoring loop lived inside the refresh run, and
    because a full pass outlasted db.STALE_RUN_MINUTES, a feed page load thirty
    minutes later superseded the run and started a SECOND loop beside the
    first. Both drew from the same unscored set.

    JOBS_DISABLE_UPGRADE=1 suppresses the auto-start (tests set it; run_once
    remains available and explicit).
    """
    global _thread

    if os.environ.get("JOBS_DISABLE_UPGRADE") == "1":
        return False
    with _lock:
        if _state["running"]:
            return False
        _state.update(_blank())
        _state["running"] = True
    _thread = threading.Thread(target=_guarded_pass, args=(None, reason),
                               name="je-assessment", daemon=True)
    _thread.start()
    return True


def run_once(limit: int | None = None) -> dict:
    """Synchronous single pass — the CLI and test seam, mirroring how
    pipeline.run_refresh mirrors trigger_refresh. Honours every guarantee
    except threading, and ignores JOBS_DISABLE_UPGRADE because calling it is
    already explicit."""
    with _lock:
        if _state["running"]:
            return dict(_state)
        _state.update(_blank())
        _state["running"] = True
    _guarded_pass(limit, "run_once")
    return progress()


def _guarded_pass(limit: int | None, reason: str) -> None:
    try:
        _pass(limit if limit is not None else _limit())
    except Exception:  # noqa: BLE001 — a pass must never take the app down
        log.warning("assessment pass (%s) failed", reason, exc_info=True)
    finally:
        with _lock:
            _state["running"] = False
            # paused_for_session is deliberately NOT cleared here. A finished
            # pass that stopped because the applicant was filling a form is
            # exactly what the feed needs to say, and the next pass resets it
            # via _blank(). Clearing it on the way out erased the only record
            # that the stand-down happened.


def _embed_pending(resume_text: str, profile: dict):
    """Embed newly ranked jobs and the resume, returning the resume vector.

    Moved here from the refresh in 020: at 0.60 s a job with a 300-job cap
    this is up to three minutes of inference, which has no business inside a
    run that promises to finish in seconds. It belongs to the pass because its
    only purpose is to ORDER the pass.
    """
    from . import db, semantic

    if not semantic.available():
        return None
    try:
        for row in db.jobs_needing_embedding(limit=EMBED_LIMIT):
            # FR-013 applies here too: embedding IS inference (0.60 s a job,
            # up to 300 of them) and goes through the same single worker as an
            # Apply Assist draft. Checking only before ASSESSMENT would leave
            # three minutes of model time that ignores a live fill session.
            if not _wait_out_any_session():
                return None
            vector = semantic.embed(
                f"{row['title']}\n{(row.get('description') or '')[:1000]}"
            )
            if vector:
                db.save_job_embedding(row["id"], semantic.pack(vector))
        resume_vec = semantic.unpack(profile.get("resume_embedding"))
        if resume_vec is None:
            vector = semantic.embed(resume_text)
            if vector:
                db.save_profile(resume_embedding=semantic.pack(vector))
                resume_vec = vector
        return resume_vec
    except Exception:  # noqa: BLE001 — degrade to the incoming order
        log.warning("semantic ordering unavailable this pass", exc_info=True)
        return None


# 021 (FR-021): applicant-initiated AI work in flight. 020 made this pass
# stand down for a FILL SESSION, which left the other thing the applicant
# waits on — pressing "Tailor for this job" — queued behind a ~67 s
# assessment in a strict-FIFO queue against its own deadline. That is one of
# the two reasons "generate a tailored resume" appeared to do nothing.
_interactive: int = 0


def begin_interactive() -> None:
    """The applicant asked for something. Background work yields to it."""
    global _interactive
    with _lock:
        _interactive += 1


def end_interactive() -> None:
    global _interactive
    with _lock:
        _interactive = max(0, _interactive - 1)


def interactive_pending() -> bool:
    with _lock:
        return _interactive > 0


class interactive:
    """`with upgrade.interactive():` around anything the applicant is
    waiting on. Re-entrant by counting, so nested callers are safe."""

    def __enter__(self):
        begin_interactive()
        return self

    def __exit__(self, *exc):
        end_interactive()
        return False


def _should_stand_down() -> bool:
    from .autofill import browser_controller as bc

    return bc.session_is_live() or interactive_pending()


def _wait_out_any_session() -> bool:
    """Stand down while the applicant is filling an application — or waiting
    on any AI request they asked for themselves.

    Returns True to continue the pass, False to end it. Polls instead of
    exiting on sight so a short session does not cost a whole pass; past
    MAX_PAUSE_S it gives up, which is free — passes are resumable, so the next
    trigger simply picks the same candidates back up.
    """
    import time

    if not _should_stand_down():
        return True

    log.info("assessment standing down: the applicant is waiting on something")
    with _lock:
        _state["paused_for_session"] = True
    waited = 0.0
    while _should_stand_down():
        if waited >= MAX_PAUSE_S:
            return False
        time.sleep(PAUSE_POLL_S)
        waited += PAUSE_POLL_S
    with _lock:
        _state["paused_for_session"] = False
    return True


def _pass(limit: int) -> None:
    import json

    from . import db, matcher, semantic

    if limit <= 0:
        return

    tier = matcher.scoring_tier()  # "cloud" | "local" | "basic"
    if tier == "basic":
        # No cloud key and no bundled model: there is nothing better to
        # upgrade a keyword score TO, so a pass would be pure waste.
        return
    method = "llm" if tier == "cloud" else "local"

    profile = db.get_profile()
    if not profile or not profile.get("resume_text"):
        return
    resume_text = profile["resume_text"]

    resume_vec = _embed_pending(resume_text, profile)

    # Over-fetch so the semantic ordering has something to choose FROM;
    # without a resume vector the incoming date order is already the answer.
    fetch = limit * 4 if resume_vec else limit
    candidates = db.jobs_needing_score(limit=fetch, upgrade_methods=("basic",))
    candidates = semantic.order_jobs(resume_vec, candidates)[:limit]

    with _lock:
        _state["total"] = len(candidates)
    if not candidates:
        return

    for job in candidates:
        # G3/FR-013: applying always beats ranking. Checked before EVERY job,
        # not once per pass, so a session that starts mid-pass is respected.
        if not _wait_out_any_session():
            return
        # G2: ONE request at a time, never a batch. The inference queue is
        # strict FIFO with no priority, so blocking on each result is what
        # keeps an Apply Assist draft waiting behind at most one assessment
        # (~67 s, inside its 180 s budget) instead of behind the whole pass.
        analysis = None
        try:
            analysis = matcher.analyze_match(
                resume_text, job["title"], job["company"],
                job.get("description") or "")
        except Exception:  # noqa: BLE001 — G4: one job cannot end the pass
            log.warning("assessment failed for job %s", job["id"],
                        exc_info=True)
        if analysis is None:
            # Keeps its keyword score; not retried within this pass. It stays
            # a candidate for a later pass because it still reads as "basic".
            with _lock:
                _state["failed"] += 1
                _state["done"] += 1
            continue
        payload = analysis.model_dump()
        payload["method"] = method
        db.set_match(job["id"], analysis.match_score, json.dumps(payload))
        with _lock:
            _state["done"] += 1
