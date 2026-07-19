"""Path resolution for dev checkouts vs the frozen (installed) app.

Dev run: writable data lives in ./data, resources are repo-relative.
Frozen (PyInstaller): writable data goes to the per-user OS location
(%LOCALAPPDATA%\\JobEngine on Windows, ~/Library/Application Support/JobEngine
on macOS) and read-only bundled resources resolve inside the bundle.
JOBS_DATA_DIR overrides the data location everywhere.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "JobEngine"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    override = os.environ.get("JOBS_DATA_DIR")
    if override:
        return Path(override)
    if is_frozen():
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
        return base / APP_NAME
    return Path("data")


def resource_path(rel: str) -> Path:
    """Locate a bundled read-only resource (companies.yml, templates, assets)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / rel
    return Path(__file__).resolve().parents[1] / rel
