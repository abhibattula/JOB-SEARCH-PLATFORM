"""Legacy Chromium-download cleanup (feature 008, FR-008).

Features 005-007 downloaded a private Chromium (~150-280MB) into
data_dir()/browsers on first use of Apply Assist. That flow is gone —
browser_controller now launches the user's installed Edge/Chrome via
Playwright channels, so nothing is downloaded and the old directory is dead
weight. These helpers report and reclaim it; the Diagnostics page offers the
cleanup as an explicit user action (never automatic deletion of user disk
data). The old `autofill_chromium_status` settings row is simply ignored.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


def legacy_browsers_dir() -> Path:
    from .. import paths

    return paths.data_dir() / "browsers"


def legacy_size_bytes() -> int:
    root = legacy_browsers_dir()
    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def cleanup_legacy() -> int:
    """Deletes the obsolete downloaded-browser directory. Returns bytes
    freed (0 when there was nothing to clean)."""
    freed = legacy_size_bytes()
    root = legacy_browsers_dir()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
        log.info("removed legacy browser dir %s (%d bytes)", root, freed)
    return freed
