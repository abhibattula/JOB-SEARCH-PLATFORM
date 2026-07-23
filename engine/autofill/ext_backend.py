"""Extension-backend session state (feature 010, T006/T007).

Holds the single companion session and the one-time file tokens. The web
layer (routes_bridge) injects the send/close callables — engine code never
imports web (constitution IV). Command translation and inbound message
processing (T007) build on this state.
"""
from __future__ import annotations

import logging
import secrets as _secrets
import threading
import time

log = logging.getLogger(__name__)

# One session at most: a newer hello supersedes the older socket (4409).
_lock = threading.RLock()
_session: dict = {
    "send": None,      # callable(dict) -> None, thread-safe, injected by web
    "close": None,     # callable(code:int) -> None, closes the socket
    "version": None,
    "last_seen": None,  # time.monotonic() of the last inbound frame
}

FILE_TOKEN_TTL = 60.0
_file_tokens: dict[str, tuple[str, float]] = {}  # token -> (path, issued_at)


def register(send, close, version: str):
    """Install a new companion session. Returns the PREVIOUS session's
    close callable when one existed (caller closes it with 4409)."""
    with _lock:
        old_close = _session["close"]
        _session.update(send=send, close=close, version=version,
                        last_seen=time.monotonic())
    return old_close


def unregister(send) -> None:
    """Tear down the session — but only if `send` is still the current
    one (a superseded socket must not clear its successor)."""
    with _lock:
        if _session["send"] is send:
            _session.update(send=None, close=None, version=None,
                            last_seen=None)


def touch() -> None:
    with _lock:
        if _session["send"] is not None:
            _session["last_seen"] = time.monotonic()


def status() -> dict:
    with _lock:
        connected = _session["send"] is not None
        age = (time.monotonic() - _session["last_seen"]
               if connected and _session["last_seen"] is not None else None)
        return {
            "connected": connected,
            "version": _session["version"],
            "last_seen_age_s": round(age, 1) if age is not None else None,
        }


def is_live(max_age_s: float = 10.0) -> bool:
    """True when a companion socket exists with a fresh heartbeat —
    the condition for choosing the extension backend at queue start."""
    snapshot = status()
    return bool(
        snapshot["connected"]
        and snapshot["last_seen_age_s"] is not None
        and snapshot["last_seen_age_s"] <= max_age_s
    )


def send(payload: dict) -> bool:
    """Send one app→extension message. False when no session."""
    with _lock:
        sender = _session["send"]
    if sender is None:
        return False
    try:
        sender(payload)
        return True
    except Exception:
        log.debug("companion send failed", exc_info=True)
        return False


def issue_file_token(path: str) -> str:
    token = _secrets.token_hex(16)
    with _lock:
        _file_tokens[token] = (path, time.monotonic())
    return token


def consume_file_token(token: str) -> str | None:
    """Single use, expiring — the resume-file endpoint's whole auth."""
    with _lock:
        entry = _file_tokens.pop(token, None)
    if entry is None:
        return None
    path, issued_at = entry
    if time.monotonic() - issued_at > FILE_TOKEN_TTL:
        return None
    return path


def handle_message(msg) -> None:
    """Process one validated inbound message. Fill/scan handling arrives
    with T007; the session heartbeat lives here."""
    touch()


def reset_for_tests() -> None:
    with _lock:
        _session.update(send=None, close=None, version=None, last_seen=None)
        _file_tokens.clear()
