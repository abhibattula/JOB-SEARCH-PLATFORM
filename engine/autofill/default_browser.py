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
import subprocess
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


# --- 015 (D3): the user's explicit browser preference ------------------------

_EXE_NAMES = {"chrome": "chrome.exe", "msedge": "msedge.exe"}
_MAC_APP_NAMES = {"chrome": "Google Chrome", "msedge": "Microsoft Edge"}


def _preference() -> str:
    from .. import settings

    value = settings.get("PREFERRED_BROWSER") or "chrome"
    return value if value in ("chrome", "msedge", "auto") else "chrome"


def effective_channel_order(read_progid=None) -> tuple[str, ...]:
    """The 013 detected order with the 015 preference applied first (D3):
    an explicit preference leads; `auto` means follow the OS default. The
    result still contains every automatable channel as fallback."""
    detected = default_channel_order(read_progid=read_progid)
    pref = _preference()
    if pref == "auto":
        return detected
    return tuple([pref] + [ch for ch in detected if ch != pref])


def _browser_exe(channel: str) -> str | None:
    """Resolve a browser's executable via the Windows App Paths registry —
    the canonical, install-location-independent lookup. None off-Windows or
    when not installed."""
    if sys.platform != "win32":
        return None
    try:
        import winreg  # noqa: PLC0415 — Windows-only, intentionally lazy
    except Exception:
        return None
    exe = _EXE_NAMES.get(channel)
    if not exe:
        return None
    key_path = (r"SOFTWARE\Microsoft\Windows\CurrentVersion"
                rf"\App Paths\{exe}")
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "")
                if value:
                    return value
        except OSError:
            continue
    return None


def _open_with_os_default(url: str) -> None:
    import os

    if sys.platform == "win32" and hasattr(os, "startfile"):
        try:
            os.startfile(url)  # noqa: S606 — caller validated http/https
            return
        except OSError:
            log.debug("os.startfile failed for %s", url, exc_info=True)
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", url])
            return
        except Exception:
            log.debug("mac open failed", exc_info=True)
    import webbrowser

    webbrowser.open(url)


def open_url(url: str) -> str:
    """Open a (pre-validated http/https) url honoring PREFERRED_BROWSER
    (FR-017). Returns what actually opened it — "chrome" | "msedge" |
    "os-default" — so the UI can note a substitution, never silently."""
    pref = _preference()
    if pref != "auto":
        exe = _browser_exe(pref)
        if exe:
            try:
                subprocess.Popen([exe, url])
                return pref
            except Exception:
                log.warning("preferred browser launch failed — falling back",
                            exc_info=True)
        elif sys.platform == "darwin":
            try:
                subprocess.Popen(["open", "-a", _MAC_APP_NAMES[pref], url])
                return pref
            except Exception:
                log.debug("mac open -a failed — falling back", exc_info=True)
    _open_with_os_default(url)
    return "os-default"
