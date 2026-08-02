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
import threading

log = logging.getLogger(__name__)

_lock = threading.Lock()


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
    browser_controller so each test starts from a clean pass."""
    global _state
    with _lock:
        _state = _blank()
