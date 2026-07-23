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


# --- watch session (extension analogue of the worker's current page) --------

# tab/job the companion is watching; pending open_tab correlations
_watch: dict = {"tab_id": None, "job_id": None, "pending_open": {}}
# (tab_id, frame_id, je_idx) -> (descriptor_raw, tag, preview) for fills
# whose result has not come back — prevents double-fill on overlapping scans
_inflight: dict[tuple, tuple] = {}
# per-frame seen counts for the watched tab (overlay + activity aggregation)
_frame_seen: dict[int, int] = {}
# detected submissions awaiting user confirmation (FR-020; consumed by the
# next-actions surface — never advances status by itself)
_pending_submissions: list[dict] = []


def _outbound(type_: str, **payload) -> dict:
    from . import ext_protocol

    return ext_protocol.outbound(type_, **payload)


def open_job(job_id: int, url: str) -> None:
    """OPEN_JOB translated for the companion: open a tab, then watch it."""
    req_id = _secrets.token_hex(8)
    with _lock:
        _watch["pending_open"][req_id] = job_id
    send(_outbound("open_tab", req_id=req_id, job_id=job_id, url=url))


def open_practice(url: str) -> None:
    """OPEN_PRACTICE for the companion — the bundled practice application
    watched as a job-less session (PRACTICE_JOB_ID)."""
    from . import browser_controller as bc

    req_id = _secrets.token_hex(8)
    with _lock:
        _watch["pending_open"][req_id] = bc.PRACTICE_JOB_ID
    send(_outbound("open_tab", req_id=req_id, job_id=bc.PRACTICE_JOB_ID, url=url))


def close_current() -> None:
    with _lock:
        tab_id = _watch["tab_id"]
        _watch.update(tab_id=None, job_id=None)
        _watch["pending_open"].clear()
        _inflight.clear()
        _frame_seen.clear()
    if tab_id is not None:
        send(_outbound("close_tab", tab_id=tab_id))


def pending_submissions() -> list[dict]:
    with _lock:
        return list(_pending_submissions)


def clear_submission(job_id: int) -> None:
    with _lock:
        _pending_submissions[:] = [
            s for s in _pending_submissions if s["job_id"] != job_id
        ]


def handle_message(msg) -> None:
    """Process one validated inbound message (called off the event loop)."""
    from . import ext_protocol

    touch()
    if isinstance(msg, ext_protocol.TabOpened):
        _handle_tab_opened(msg)
    elif isinstance(msg, ext_protocol.Fields):
        _handle_fields(msg)
    elif isinstance(msg, ext_protocol.FillResult):
        _handle_fill_result(msg)
    elif isinstance(msg, ext_protocol.PageEvent):
        _handle_page_event(msg)
    elif isinstance(msg, ext_protocol.FillHere):
        _handle_fill_here(msg)
    # Pong: heartbeat only (touch() above)


def _handle_tab_opened(msg) -> None:
    with _lock:
        job_id = _watch["pending_open"].pop(msg.req_id, None)
        if job_id is None:
            return
        _watch.update(tab_id=msg.tab_id, job_id=job_id)
        _inflight.clear()
        _frame_seen.clear()
    send(_outbound("watch_start", tab_id=msg.tab_id, job_id=job_id))


def _frame_domain(url: str) -> str | None:
    from urllib.parse import urlparse

    return urlparse(url).netloc or None


def _handle_fields(msg) -> None:
    from . import adapters, browser_controller as bc, field_core

    with _lock:
        if msg.tab_id != _watch["tab_id"]:
            return
        job_id = _watch["job_id"]
    if job_id is None:
        return

    from .. import db

    profile = db.get_profile() or {}
    with bc._lock:
        ledger = bc._state.handled.setdefault(job_id, {})

    frame_domain = _frame_domain(msg.url)

    def get_value(tag, raw):
        # Credentials are gated by the SENDING FRAME's domain — the frame
        # is where the secret would land, and it may not be the job's own
        # host (Greenhouse iframes, SSO pages). Everything else reuses the
        # facade's value resolution unchanged.
        if tag in ("login_email", "login_password"):
            from .. import credentials

            if not frame_domain:
                return None
            saved = credentials.get(frame_domain)
            if not saved:
                return None
            return saved["email"] if tag == "login_email" else saved["password"]
        return bc._value_for_tag(tag, raw, profile, job_id)

    ats = adapters.ats_from_url(msg.url)
    items: list[dict] = []
    seen = 0
    for desc in msg.descriptors:
        raw = desc.as_watcher_dict()
        fkey = (msg.tab_id, msg.frame_id, raw["je_idx"])
        if fkey in _inflight:
            seen += 1
            continue
        decision = field_core.decide(ats, raw, ledger, get_value)
        if decision.action == "ignore":
            continue
        seen += 1
        lkey = field_core.key(raw)
        if decision.action == "skip":
            continue
        if decision.action == "settle":
            bc._record(job_id, raw, decision.tag, "", decision.outcome)
            with bc._lock:
                ledger[lkey] = decision.outcome
            continue
        # action == "fill"
        item: dict = {"je_idx": raw["je_idx"], "flag": None}
        if decision.kind == "file":
            token = issue_file_token(str(decision.value))
            item.update(kind="file", value="",
                        file_url=f"/api/bridge/file/{token}")
        elif decision.secret:
            item.update(kind="secret", value=str(decision.value))
        elif decision.kind == "select":
            item.update(kind="select", value=str(decision.value),
                        option_label=decision.option_label)
        elif decision.kind == "checkbox":
            item.update(kind="checkbox", value="on")
        else:
            item.update(kind="text", value=str(decision.value))
        with _lock:
            _inflight[fkey] = (raw, decision.tag, decision.preview)
        items.append(item)

    with _lock:
        _frame_seen[msg.frame_id] = seen
        total_seen = sum(_frame_seen.values())

    if items:
        send(_outbound("fill", tab_id=msg.tab_id, frame_id=msg.frame_id,
                       items=items))

    with bc._lock:
        filled_total = bc._state.activity.get("fields_filled", 0)
    bc._set_activity(
        phase="watching" if total_seen else "waiting_for_form",
        fields_seen=total_seen,
        last_scan_at=bc._utcnow_iso(),
        url=msg.url if msg.frame_id == 0 else bc._state.activity.get("url"),
        message=(
            f"watching page — {total_seen} fields seen · "
            f"{filled_total} filled · you click the actual apply/submit"
            if total_seen else
            "no form fields visible yet — click the site's own Apply "
            "button; fields fill the moment the form appears"
        ),
    )
    send(_outbound("overlay_state", tab_id=msg.tab_id, summary={
        "seen": total_seen, "filled": filled_total, "drafts": 0,
        "message": "you click the actual apply/submit",
    }))


def _handle_fill_result(msg) -> None:
    from . import browser_controller as bc, field_core

    with _lock:
        if msg.tab_id != _watch["tab_id"]:
            return
        job_id = _watch["job_id"]
    if job_id is None:
        return
    filled_now = 0
    for item in msg.items:
        fkey = (msg.tab_id, msg.frame_id, item.je_idx)
        with _lock:
            info = _inflight.pop(fkey, None)
        if info is None:
            continue
        raw, tag, preview = info
        lkey = field_core.key(raw)
        if item.outcome == "filled":
            bc._record(job_id, raw, tag, preview, "filled")
            with bc._lock:
                bc._state.handled.setdefault(job_id, {})[lkey] = "filled"
            filled_now += 1
        elif item.outcome == "needs_manual":
            bc._record(job_id, raw, tag, "", "needs_manual")
            with bc._lock:
                bc._state.handled.setdefault(job_id, {})[lkey] = "needs_manual"
        # focused / not_found: retryable — no record, next scan re-decides
    if filled_now:
        with bc._lock:
            bc._state.activity["fields_filled"] = (
                bc._state.activity.get("fields_filled", 0) + filled_now
            )


def _handle_page_event(msg) -> None:
    from . import browser_controller as bc

    with _lock:
        watched = msg.tab_id == _watch["tab_id"]
        job_id = _watch["job_id"]
    if not watched:
        return
    if msg.kind == "tab_closed":
        with _lock:
            _inflight.clear()
            _frame_seen.clear()
        with bc._lock:
            if bc._state.running:
                bc._state.interrupted = True
                bc._state.activity.update(
                    phase="interrupted",
                    message="the application tab was closed — Resume "
                            "reopens it",
                )
    elif msg.kind == "nav":
        # document changed: in-flight fills for the tab are void; the new
        # page's scans re-decide everything (doc token changes)
        with _lock:
            for key in [k for k in _inflight if k[0] == msg.tab_id]:
                del _inflight[key]
            _frame_seen.clear()
    elif msg.kind == "frame_gone":
        # harmless: ledger keys die with their doc token
        with _lock:
            for key in [k for k in _inflight if k[0] == msg.tab_id]:
                del _inflight[key]
    elif msg.kind == "submit_detected":
        with _lock:
            _pending_submissions.append({
                "job_id": job_id, "tab_id": msg.tab_id,
                "url": msg.url, "at": time.time(),
            })


def _handle_fill_here(msg) -> None:
    """Ad-hoc 'Fill this page' — wired fully in T012."""
    log.info("fill_here received for tab %s (%s)", msg.tab_id, msg.url)


def reset_for_tests() -> None:
    with _lock:
        _session.update(send=None, close=None, version=None, last_seen=None)
        _file_tokens.clear()
        _watch.update(tab_id=None, job_id=None)
        _watch["pending_open"].clear()
        _inflight.clear()
        _frame_seen.clear()
        _pending_submissions.clear()
