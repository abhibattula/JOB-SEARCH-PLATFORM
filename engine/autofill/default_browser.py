"""013 (Refinements): resolve the OS default browser to a Playwright channel
order, so Apply Assist's assistant window opens the user's *default* browser
(e.g. Chrome) instead of a hardcoded Edge-first order.

Pure, engine-only. Windows reads the registered https handler; other platforms
fall back to a sensible order. Windows-only APIs (`winreg`) are imported LAZILY
inside a platform branch so this module imports cleanly on macOS/Linux/CI
(constitution IV — the engine runs headless/cross-platform).
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

# The browsers Playwright can drive via installed channels (no download).
AUTOMATABLE = ("chrome", "msedge")
_DEFAULT_ORDER = ("chrome", "msedge")

# Windows UserChoice ProgId → Playwright channel. Chromium-family browsers that
# aren't a distinct Playwright channel (Brave/Vivaldi/Opera) drive as "chrome".
_PROGID_CHANNEL = {
    "ChromeHTML": "chrome",
    "MSEdgeHTM": "msedge",
    "MSEdgeDHTML": "msedge",
    "BraveHTML": "chrome",
    "VivaldiHTM": "chrome",
    "OperaStable": "chrome",
}


def _read_progid_windows() -> str | None:
    """Read HKCU UserChoice ProgId for https. Windows only; imports winreg
    lazily so this file is import-safe on every platform."""
    try:
        import winreg  # noqa: PLC0415 — Windows-only, intentionally lazy
    except Exception:
        return None
    key = (r"Software\Microsoft\Windows\Shell\Associations"
           r"\UrlAssociations\https\UserChoice")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            value, _ = winreg.QueryValueEx(k, "ProgId")
            return value or None
    except OSError:
        return None
    except Exception:
        log.debug("default-browser ProgId read failed", exc_info=True)
        return None


def default_channel_order(read_progid=None) -> tuple[str, ...]:
    """Return automatable Playwright channels, the OS default browser first.

    `read_progid` is an injectable callable returning the OS handler id (used by
    tests); when omitted, the real OS reader is used on Windows and a sensible
    fixed order elsewhere. The result always contains every automatable channel
    (deduped) so a fallback exists even when the default can't be driven."""
    if read_progid is None:
        read_progid = _read_progid_windows if sys.platform == "win32" else (lambda: None)

    try:
        progid = read_progid()
    except Exception:
        progid = None

    preferred = _PROGID_CHANNEL.get(progid or "")
    order: list[str] = []
    if preferred:
        order.append(preferred)
    for ch in _DEFAULT_ORDER:
        if ch not in order:
            order.append(ch)
    return tuple(order)
