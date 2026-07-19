"""Fresh best-match alerts: after a refresh, notify about newly discovered
eligible entry-level jobs scoring at or above the threshold. Speed-to-apply is
the biggest response-rate lever, so the latest strong matches come to the user
instead of waiting to be noticed.
"""
from __future__ import annotations

import logging

from . import db, settings

log = logging.getLogger(__name__)

ALERT_MIN_SCORE = 70.0
MAX_LISTED = 4


def new_best_matches(since: str) -> list[dict]:
    """Eligible entry-level jobs first seen after `since` scoring >= threshold."""
    jobs, _ = db.query_jobs(
        window=None,
        seen_since=since,
        entry_level=True,
        min_score=ALERT_MIN_SCORE,
        sort="score",
        limit=50,
    )
    return jobs


def _send(title: str, message: str) -> None:
    from plyer import notification

    notification.notify(title=title, message=message, app_name="Job Engine", timeout=10)


def process(since: str) -> int:
    """Compute fresh best matches and fire one desktop notification.

    Never raises: alerting is best-effort decoration on the refresh.
    Returns the number of matches found (for logging/verification).
    """
    try:
        if settings.get("ALERTS_ENABLED") == "0":
            return 0
        matches = new_best_matches(since)
        if not matches:
            return 0
        listed = ", ".join(
            f"{job['company']} — {job['title'][:40]}" for job in matches[:MAX_LISTED]
        )
        extra = f" (+{len(matches) - MAX_LISTED} more)" if len(matches) > MAX_LISTED else ""
        title = f"{len(matches)} new strong match{'es' if len(matches) != 1 else ''}"
        try:
            _send(title, f"{listed}{extra}")
        except Exception:
            log.info("desktop notification unavailable", exc_info=True)
        return len(matches)
    except Exception:
        log.warning("alert processing failed", exc_info=True)
        return 0
