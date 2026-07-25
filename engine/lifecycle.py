"""015 (FR-005): unclean-exit detection via a running marker.

A native fault in a bundled library (the recorded ggml-cpu.dll access
violation) kills the process instantly — no traceback, no crash.marker, the
window just vanishes. The honest signal is a marker file: written when a
session starts, removed only by a clean shutdown. Present at the NEXT startup
⇒ the previous session died abnormally, so the app says so instead of
pretending nothing happened (banner in web/templates/base.html, record in
the UNCLEAN_EXIT_AT settings key until dismissed).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_MARKER_NAME = "running.marker"


def _marker() -> Path:
    from . import paths

    return paths.data_dir() / _MARKER_NAME


def startup_check_and_mark() -> bool:
    """Call once at app startup (after db init). Returns True when the
    previous session ended without a clean shutdown; always (re)writes the
    marker for the session now starting."""
    marker = _marker()
    unclean = marker.exists()
    if unclean:
        try:
            from . import settings

            settings.set(
                "UNCLEAN_EXIT_AT",
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            )
        except Exception:  # recording must never block startup
            log.warning("could not record unclean exit", exc_info=True)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("", encoding="utf-8")
    except Exception:
        log.warning("could not write running marker", exc_info=True)
    return unclean


def clear_running() -> None:
    """Call on every deliberate shutdown path — a surviving marker is the
    'died abnormally' signal, so clean exits must remove it."""
    try:
        _marker().unlink(missing_ok=True)
    except Exception:
        log.debug("could not clear running marker", exc_info=True)
