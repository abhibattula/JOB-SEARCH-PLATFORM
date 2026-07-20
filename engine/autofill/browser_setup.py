"""First-use Chromium install for Apply Assist (feature 005).

Chromium (~150-280MB) is downloaded on first use of Apply Assist rather
than bundled in the base installer — this feature is opt-in, unlike the
local LLM (used by the core scoring feature nearly every user touches),
so this keeps the *unconditional* installer-size hit to the model alone
(research.md §4). Progress is tracked via the same DB-backed settings KV
pattern as everything else in engine/settings.py, not by parsing
Playwright's internal directory layout.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

log = logging.getLogger(__name__)

_STATUS_KEY = "autofill_chromium_status"


def _browsers_path():
    from .. import paths

    return paths.data_dir() / "browsers"


def status() -> str:
    from .. import db

    return db.get_setting(_STATUS_KEY) or "not_installed"


def is_installed() -> bool:
    return status() == "installed"


def _set_status(value: str) -> None:
    from .. import db

    db.set_setting(_STATUS_KEY, value)


def _run_install() -> None:
    _set_status("installing")
    path = _browsers_path()
    path.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(path)}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            env=env,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        log.warning("Chromium install failed", exc_info=True)
        _set_status(f"failed: {exc}")
        return
    if result.returncode != 0:
        log.warning("Chromium install exited %d: %s", result.returncode, result.stderr)
        _set_status(f"failed: {(result.stderr or '').strip()[:300]}")
        return
    _set_status("installed")


def start_install(background: bool = True) -> bool:
    """Kicks off the one-time Chromium download. Returns False (no-op) if
    already installed. `background=False` runs synchronously (used by tests
    and by the CI smoke test's own setup step)."""
    if is_installed():
        return False
    if background:
        threading.Thread(target=_run_install, daemon=True).start()
    else:
        _run_install()
    return True
