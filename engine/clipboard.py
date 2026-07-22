"""Host-side clipboard writes (feature 008, FR-002).

navigator.clipboard is permission-gated inside the WebView2 shell and fails
silently there, so the UI's copyText() helper falls back to POST
/api/clipboard, which lands here — a real OS clipboard write on the machine
the server runs on (always the user's own machine; this app is local-only).
"""
from __future__ import annotations

import subprocess
import sys


def copy_text(text: str) -> None:
    """Writes text to the OS clipboard. Raises RuntimeError when no
    mechanism works — callers surface that honestly (never fake success)."""
    if sys.platform == "win32":
        _copy_windows(text)
        return
    if sys.platform == "darwin":
        _pipe(["pbcopy"], text)
        return
    for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        try:
            _pipe(cmd, text)
            return
        except (OSError, RuntimeError):
            continue
    raise RuntimeError("no clipboard mechanism available on this platform")


def _pipe(cmd: list[str], text: str) -> None:
    proc = subprocess.run(cmd, input=text.encode("utf-8"), timeout=5)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} exited {proc.returncode}")


def _copy_windows(text: str) -> None:
    """CF_UNICODETEXT via ctypes — no subprocess console flash, full
    Unicode, zero dependencies. restype/argtypes set explicitly: the
    defaults truncate 64-bit handles/pointers."""
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)

    if not user32.OpenClipboard(None):
        raise RuntimeError("could not open the Windows clipboard")
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise RuntimeError("GlobalAlloc failed")
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise RuntimeError("GlobalLock failed")
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise RuntimeError("SetClipboardData failed")
        # ownership transferred to the clipboard on success — do not free
    finally:
        user32.CloseClipboard()
