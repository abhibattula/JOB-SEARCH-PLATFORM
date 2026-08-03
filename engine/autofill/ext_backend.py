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
    "browser": None,   # 015: "chrome" | "edge" | "" from Hello.browser
    "last_seen": None,  # time.monotonic() of the last inbound frame
}

# 015 (T009/FR-014): rejected connection attempts by kind, for this process's
# lifetime — lets the doctor distinguish "nothing is knocking" (wrong folder /
# not installed) from "knocking but rejected" (stale pairing vs old protocol).
_rejects: dict = {"auth": 0, "protocol": 0, "last_kind": None, "last_at": None}


def record_reject(kind: str) -> None:
    """Called by the web layer when it closes a companion socket with 4401
    ("auth") or 4426 ("protocol")."""
    if kind not in ("auth", "protocol"):
        return
    with _lock:
        _rejects[kind] += 1
        _rejects["last_kind"] = kind
        _rejects["last_at"] = time.monotonic()


def reject_stats() -> dict:
    with _lock:
        age = (time.monotonic() - _rejects["last_at"]
               if _rejects["last_at"] is not None else None)
        return {
            "auth": _rejects["auth"],
            "protocol": _rejects["protocol"],
            "last_kind": _rejects["last_kind"],
            "last_age_s": round(age, 1) if age is not None else None,
        }

FILE_TOKEN_TTL = 60.0
_file_tokens: dict[str, tuple[str, float]] = {}  # token -> (path, issued_at)


def register(send, close, version: str, browser: str = ""):
    """Install a new companion session. Returns the PREVIOUS session's
    close callable when one existed (caller closes it with 4409).

    A reconnect usually means the MV3 service worker was terminated and
    restarted, which wipes the extension's in-memory tab bookkeeping. Tab IDs
    themselves survive, so re-send watch_start for the tab we were watching —
    otherwise the content scripts are never told to scan again and filling
    silently stops mid-queue (v1.0.0 bug)."""
    with _lock:
        old_close = _session["close"]
        _session.update(send=send, close=close, version=version,
                        browser=browser or "", last_seen=time.monotonic())
        tab_id = _watch["tab_id"]
        job_id = _watch["job_id"]
    if tab_id is not None:
        send(_outbound("watch_start", tab_id=tab_id, job_id=job_id))
    return old_close


def unregister(send) -> None:
    """Tear down the session — but only if `send` is still the current
    one (a superseded socket must not clear its successor)."""
    with _lock:
        if _session["send"] is send:
            _session.update(send=None, close=None, version=None,
                            browser=None, last_seen=None)


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
            "browser": _session["browser"] or "" if connected else "",
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
    """Expiring — the resume-file endpoint's whole auth. 019 (FR-005): a
    token stays redeemable for its TTL instead of dying on first use, so a
    transient fetch failure doesn't turn the retry into http_404 →
    needs_manual. The map dies with the session (close_current /
    reset_for_tests), and the TTL bounds the exposure window."""
    with _lock:
        entry = _file_tokens.get(token)
        if entry is None:
            return None
        path, issued_at = entry
        if time.monotonic() - issued_at > FILE_TOKEN_TTL:
            del _file_tokens[token]
            return None
        return path


# --- watch session (extension analogue of the worker's current page) --------

# tab/job the companion is watching; pending open_tab correlations —
# 016 (T008): req_id -> {job_id, url, deadline, retried}; expired entries
# get ONE retry, then a visible launch_failed (never a silent hang).
_watch: dict = {"tab_id": None, "job_id": None, "pending_open": {}}
OPEN_TAB_ACK_S = 5.0

# 016 (T008/T010): doctor tripwires — silently-dropped traffic is counted.
# 019 (FR-002): version_mismatch_fills counts fills withheld from a stale
# companion — each one is ALSO visible on the page as needs-you.
_counters: dict = {"dropped_fields": 0, "scan_errors": 0,
                   "version_mismatch_fills": 0,
                   # 021 (analysis A8): fields the page-entry cap refused.
                   # Silent truncation on a review surface reads as "that is
                   # everything" — the failure 018/019 were spent removing.
                   "page_entries_truncated": 0}


def counters() -> dict:
    with _lock:
        return dict(_counters)


def version_ok() -> bool:
    """019 (FR-035): exact app/companion version match. The escort consults
    this and never arms across a mismatch; the UI renders the amber state."""
    from .. import APP_VERSION

    with _lock:
        return _session["version"] == APP_VERSION
# (tab_id, frame_id, je_idx) -> (descriptor_raw, tag, preview, ai_draft,
# sent_at) for fills whose result has not come back — prevents double-fill
# on overlapping scans. 016 (T007): entries EXPIRE — a lost fill_result
# must not block its field for the life of the document.
_inflight: dict[tuple, tuple] = {}
INFLIGHT_TTL_S = 20.0
# per-frame seen counts for the watched tab (overlay + activity aggregation).
# 021 (FR-009): frame_id -> (count, monotonic of the scan that reported it).
# This was frame_id -> count, cleared only at session start — so an iframe
# that navigated away or was removed left its count in the sum FOREVER, and
# "Seen 156" could be several dead frames added together. PageEvent carries no
# frame_id (and defaulting one to 0 would wrongly clear the TOP frame), so
# staleness is judged by time instead: a frame stops counting once it has gone
# quiet for longer than any live frame's scan cadence.
_frame_seen: dict[int, tuple[int, float]] = {}
FRAME_STALE_S = 30.0


def _total_seen_locked() -> int:
    """Fields across every frame still reporting. Caller holds `_lock`."""
    now = time.monotonic()
    return sum(count for count, at in _frame_seen.values()
               if now - at <= FRAME_STALE_S)

# 018 (US3): the page-answer index — every decision this session made, keyed by
# the stable ledger key, in the order the fields were first seen. This is what
# lets the on-page companion show the WHOLE application rather than only the
# questions the AI drafter touched, and it is where `je_idx` finally travels
# with the answer so Insert and Show me can exist.
_page_entries: dict[int, dict[str, dict]] = {}
# 021 (FR-009): how many scans of each (job, document) have been processed,
# and how many consecutive misses evict a page-answer entry. THREE, not one:
# a single missed scan is a re-render, and evicting on the first miss would
# make live fields flicker out of the review list exactly when the page is
# busiest.
_scan_counts: dict[tuple, int] = {}
PRUNE_AFTER_SCANS = 3
# 021 (FR-001): the SHAPE of the last scan of each frame — every descriptor,
# including the ones `_page_entries` deliberately drops (no question, ignored).
# A field the app cannot name is precisely what needs diagnosing, so the report
# must see more than the review feed does. job_id -> frame_id -> [records]
_page_shape: dict[int, dict[int, list[dict]]] = {}
# The digest of the last `answers` payload pushed per tab. An unchanged scan
# sends nothing at all (FR-027) — this payload used to go out every ~2s and
# every push rebuilt the panel, destroying half-typed answers.
_answers_digest: dict[int, str] = {}
# Tabs whose next scan must push regardless of the digest: the applicant just
# did something and deserves to see it land.
_answers_force: set[int] = set()
# A wizard accumulates fields across steps; this bounds the index so a long
# multi-page application cannot grow it without limit.
MAX_PAGE_ENTRIES = 200
# detected submissions awaiting user confirmation (FR-020; consumed by the
# next-actions surface — never advances status by itself)
_pending_submissions: list[dict] = []


def _outbound(type_: str, **payload) -> dict:
    from . import ext_protocol

    return ext_protocol.outbound(type_, **payload)


def _queue_open(job_id: int, url: str, retried: bool = False) -> None:
    req_id = _secrets.token_hex(8)
    with _lock:
        _watch["pending_open"][req_id] = {
            "job_id": job_id, "url": url, "retried": retried,
            "deadline": time.monotonic() + OPEN_TAB_ACK_S,
        }
    send(_outbound("open_tab", req_id=req_id, job_id=job_id, url=url))


def open_job(job_id: int, url: str) -> None:
    """OPEN_JOB translated for the companion: open a tab, then watch it."""
    _queue_open(job_id, url)


def adopt_tab(tab_id: int, job_id: int) -> None:
    """019 (FR-003): watch the tab the user is ALREADY on — no open_tab, no
    duplicate. Clearing pending_open guarantees a late tab_opened from an
    earlier queued open can never steal this watch (the v1.8.0 bug)."""
    with _lock:
        _watch.update(tab_id=tab_id, job_id=job_id)
        _watch["pending_open"].clear()
        _inflight.clear()
        _frame_seen.clear()
        _start_answer_feed(tab_id, job_id)
    send(_outbound("watch_start", tab_id=tab_id, job_id=job_id))


def open_practice(url: str) -> None:
    """OPEN_PRACTICE for the companion — the bundled practice application
    watched as a job-less session (PRACTICE_JOB_ID)."""
    from . import browser_controller as bc

    _queue_open(bc.PRACTICE_JOB_ID, url)


def check_pending_open() -> None:
    """016 (T008): called from the worker's ~2 s tick while the extension
    backend is active — expire unacknowledged open_tab requests: one
    retry, then a visible launch_failed so the queue never hangs."""
    now = time.monotonic()
    to_retry: list[dict] = []
    failed: list[dict] = []
    with _lock:
        for req_id, entry in list(_watch["pending_open"].items()):
            if now < entry["deadline"]:
                continue
            del _watch["pending_open"][req_id]
            (failed if entry["retried"] else to_retry).append(entry)
    for entry in to_retry:
        _queue_open(entry["job_id"], entry["url"], retried=True)
    if failed:
        from . import browser_controller as bc

        for entry in failed:
            bc._mark_fallback(entry["job_id"], "launch_failed",
                              "the companion never opened the tab "
                              "(retried once)")
        bc._set_activity(
            phase="error",
            message="couldn't open the application tab — check the "
                    "companion, then Resume or press Next",
        )


def close_current() -> None:
    with _lock:
        tab_id = _watch["tab_id"]
        _watch.update(tab_id=None, job_id=None)
        _watch["pending_open"].clear()
        _inflight.clear()
        _frame_seen.clear()
        _file_tokens.clear()  # 019 (FR-005): tokens die with the session
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
    elif isinstance(msg, ext_protocol.ScoreRequest):
        _handle_score_request(msg)
    elif isinstance(msg, ext_protocol.SaveJob):
        _handle_save_job(msg)
    elif isinstance(msg, ext_protocol.ChildTab):
        _handle_child_tab(msg)
    elif isinstance(msg, ext_protocol.ScanError):
        _handle_scan_error(msg)
    elif isinstance(msg, ext_protocol.FillAgain):
        _handle_fill_again(msg)
    elif isinstance(msg, ext_protocol.AnswerQuestion):
        _handle_answer_question(msg)
    elif isinstance(msg, ext_protocol.ApplyHere):
        _handle_apply_here(msg)
    elif isinstance(msg, ext_protocol.SessionControl):
        _handle_session_control(msg)
    elif isinstance(msg, ext_protocol.AdvanceResult):
        _handle_advance_result(msg)
    elif isinstance(msg, ext_protocol.CredentialSave):
        _handle_credential_save(msg)
    elif isinstance(msg, ext_protocol.PageReport):
        _handle_page_report(msg)
    # Pong: heartbeat only (touch() above)


# 019 (FR-031): every automated progression click, in order — the session's
# activity trail. `open_apply` comes from the opener, `sign_in`/`next` from
# the advancer; one shape for all three so the record is complete.
_progression_clicks: list[dict] = []
MAX_PROGRESSION_CLICKS = 200


def progression_clicks() -> list[dict]:
    with _lock:
        return list(_progression_clicks)


def _handle_advance_result(msg) -> None:
    from . import browser_controller as bc, escort as escort_mod

    # 019 (FR-030): the advancer looked for a way forward and every
    # candidate was final-class (or there was none at all) on a step we had
    # judged complete. That is the door: everything fillable is in, and the
    # Submit is the applicant's.
    if msg.kind == "next" and msg.status in ("refused", "not_found"):
        if msg.selector_kind in ("final_class", "") :
            with _lock:
                tab_id = _watch["tab_id"]
            if tab_id is not None:
                send(_outbound("overlay_state", tab_id=tab_id, summary={
                    "session": escort_mod.STATE_READY,
                    "message": "Review & submit — your turn",
                }))

    with _lock:
        job_id = _watch["job_id"]
        if len(_progression_clicks) < MAX_PROGRESSION_CLICKS:
            _progression_clicks.append({
                "kind": msg.kind,
                "status": msg.status,
                "selector_kind": msg.selector_kind,
                "control_hash": msg.control_hash,
                "job_id": job_id,
                "at": bc._utcnow_iso(),
            })
    log.info("companion progression click: %s %s (%s)",
             msg.kind, msg.status, msg.selector_kind)


def _handle_answer_question(msg) -> None:
    """017 (D7, FR-045/FR-046): the applicant answered, in the panel, a
    question we declined to answer.

    Stored as THEIR answer — source 'user', never 'ai' — so it fills this
    field now, fills every future application that asks the same thing, and
    survives a purge of model-written answers. Stored verbatim: the app does
    not rewrite, expand or "improve" what they typed.
    """
    from . import answer_bank, browser_controller as bc, drafter

    question = (msg.question or "").strip()
    answer = (msg.answer or "").strip()
    if not question or not answer:
        return
    with _lock:
        if msg.tab_id != _watch["tab_id"]:
            return
        job_id = _watch["job_id"]
    try:
        answer_bank.save(question, answer)
    except Exception:  # noqa: BLE001 — never lose the fill over a bank write
        log.warning("answer capture failed to save", exc_info=True)
    if job_id is not None:
        # Drop the refusal record and re-open the field so the next scan
        # fills it from the bank.
        drafter.clear(job_id, question)
        with bc._lock:
            ledger = bc._state.handled.get(job_id) or {}
            for lkey in [k for k, v in list(ledger.items())
                         if (v[0] if isinstance(v, tuple) else v)
                         != "skipped_existing"]:
                del ledger[lkey]
    # 018 (FR-027): the digest must not suppress the one push that shows their
    # typed answer landing.
    with _lock:
        _answers_force.add(msg.tab_id)
    send(_outbound("rescan", reason="user_rescan"))


def _handle_session_control(msg) -> None:
    """018 (FR-030/FR-032): Stop and Next, from the page.

    Both already existed — this is the same `stop_queue()` / `advance()` the
    app's own Apply Assist page calls. What changes is that stopping a run no
    longer means abandoning the application you are filling to go and find the
    app window. Nothing here touches the page.
    """
    from . import browser_controller as bc

    with _lock:
        if msg.tab_id != _watch["tab_id"]:
            return
    action = (msg.action or "").strip().lower()
    if action == "stop":
        bc.stop_queue()
        send(_outbound("overlay_state", tab_id=msg.tab_id, summary={
            "seen": 0, "filled": 0, "needs_you": 0, "drafts": 0,
            "needs_you_idx": [], "attention": [], "session": "stopped",
            "message": "stopped — nothing was submitted",
        }))
        return
    # 019 (FR-034): pause/resume the ESCORT only — filling continues either
    # way. This is the rollback lever a behaviour change this size needs.
    if action in ("pause_escort", "resume_escort"):
        escort = _get_escort()
        if action == "pause_escort":
            escort.enabled = False
        else:
            escort.enabled = True
            escort.resume()   # the applicant looked; the cap starts over
        send(_outbound("overlay_state", tab_id=msg.tab_id, summary={
            "session": "filling",
            "message": ("escort paused — you advance the pages"
                        if action == "pause_escort"
                        else "escort on — I'll advance completed steps"),
        }))
        return
    if action == "next":
        try:
            current = bc.advance()
        except Exception as exc:  # noqa: BLE001 — surface, never crash
            log.warning("session_control next failed", exc_info=True)
            send(_outbound("error", code="advance_failed",
                           message=str(exc)[:200]))
            return
        if current is None:
            send(_outbound("overlay_state", tab_id=msg.tab_id, summary={
                "seen": 0, "filled": 0, "needs_you": 0, "drafts": 0,
                "needs_you_idx": [], "attention": [], "session": "done",
                "message": "that was the last one",
            }))
        return
    send(_outbound("error", code="bad_action",
                   message=f"unknown session action: {action[:40]}"))


def _handle_fill_again(msg) -> None:
    """016 (T016, R10): the panel's Fill again — clear retryable ledger
    entries (user-typed values stay sacred via the write-time guards),
    re-arm failed drafts once, then nudge a rescan."""
    from . import browser_controller as bc, drafter

    with _lock:
        if msg.tab_id != _watch["tab_id"]:
            return
        job_id = _watch["job_id"]
        _inflight.clear()
    if job_id is None:
        return
    with bc._lock:
        ledger = bc._state.handled.get(job_id) or {}
        for lkey in [k for k, v in list(ledger.items())
                     if (v[0] if isinstance(v, tuple) else v)
                     != "skipped_existing"]:
            del ledger[lkey]
    drafter.reset_backoff_for_job(job_id)
    with _lock:
        _answers_force.add(msg.tab_id)
    send(_outbound("rescan", reason="fill_again"))


def _member_je_idx(raw: dict, label: str | None) -> str | None:
    """017: the je_idx of the group member carrying `label`, or None."""
    from . import drafter

    wanted = drafter.normalize_question(label or "")
    for member in raw.get("members") or []:
        if drafter.normalize_question(member.get("label") or "") == wanted:
            return member.get("je_idx")
    return None


def _handle_scan_error(msg) -> None:
    """016 (T010): a content-script scan exception, counted for the doctor
    (it used to be swallowed, leaving the tab permanently silent)."""
    with _lock:
        _counters["scan_errors"] += 1
    log.warning("companion scan error on tab %s: %s", msg.tab_id,
                (msg.message or "")[:200])


def _handle_tab_opened(msg) -> None:
    with _lock:
        entry = _watch["pending_open"].pop(msg.req_id, None)
        if entry is None:
            return
        job_id = entry["job_id"]
        _watch.update(tab_id=msg.tab_id, job_id=job_id)
        _inflight.clear()
        _frame_seen.clear()
        _start_answer_feed(msg.tab_id, job_id)
    send(_outbound("watch_start", tab_id=msg.tab_id, job_id=job_id))


def _handle_child_tab(msg) -> None:
    """016 (T008, R4): the watch TRANSFERS to a tab opened from the watched
    tab (embedded boards open the real form in a child tab). Singular
    target — the old tab's fields intentionally stop."""
    with _lock:
        if _watch["tab_id"] is None or msg.opener_tab_id != _watch["tab_id"]:
            return
        job_id = _watch["job_id"]
        _watch["tab_id"] = msg.tab_id
        _inflight.clear()
        _frame_seen.clear()
    send(_outbound("watch_start", tab_id=msg.tab_id, job_id=job_id))


def _frame_domain(url: str) -> str | None:
    from urllib.parse import urlparse

    return urlparse(url).netloc or None


# 019 (T046, FR-016): sign-in arming state, per (tab, frame, doc token).
#   `pending`  — credential fills this engine issued, awaiting their result
#   `armed`    — every one of them landed; the click may go out ONCE
#   `fired`    — it went out; a re-render of the same document never repeats
# The state is what makes the click legal under constitution v1.2.0: it is
# permitted only "immediately after a credential fill the engine itself
# issued for that exact frame", never inferred from a button's text.
_CREDENTIAL_TAGS = ("login_email", "login_username", "login_password")
_signin: dict[tuple, dict] = {}

# 019 (T060): the escort for the current session, plus per-(tab,frame) quiet
# clocks. A step that is still rendering is not a step that is complete.
_escort = None
_quiet_since: dict[tuple, tuple] = {}   # (tab, frame) -> (fieldset_hash, at)
# Hosts where we fill but never click (FR-033). The account at risk is the
# applicant's, so this is a domain rule, not a heuristic.
_NO_CLICK_HOSTS = ("linkedin.com",)


def _get_escort():
    global _escort
    from . import escort as escort_mod

    with _lock:
        if _escort is None:
            from .. import db

            enabled = (db.get_setting("escort_enabled") or "1") != "0"
            _escort = escort_mod.Escort(enabled=enabled)
        return _escort


def _clickable_host(url: str) -> bool:
    # netloc carries userinfo and an explicit port; a host rule that can be
    # defeated by ":443" is not a rule. Strip both before comparing.
    host = (_frame_domain(url) or "").lower()
    host = host.rsplit("@", 1)[-1].split(":", 1)[0]
    return not any(host == h or host.endswith("." + h)
                   for h in _NO_CLICK_HOSTS)


def _signin_key(tab_id: int, frame_id: int, doc: str) -> tuple:
    return (tab_id, frame_id, doc)


def _signin_note_issued(key: tuple, je_idx: str, *, satisfied: bool) -> None:
    entry = _signin.setdefault(key, {"pending": set(), "landed": set(),
                                     "fired": False})
    if entry["fired"]:
        return
    entry["pending"].add(je_idx)
    if satisfied:
        entry["landed"].add(je_idx)


def _signin_note_landed(tab_id: int, frame_id: int, je_idx: str) -> None:
    for (t, f, _doc), entry in _signin.items():
        if t == tab_id and f == frame_id and je_idx in entry["pending"]:
            entry["landed"].add(je_idx)


def _signin_ready(key: tuple) -> bool:
    entry = _signin.get(key)
    if not entry or entry["fired"]:
        return False
    # Both halves of a credential must have landed — clicking Sign in with
    # only the email filled submits an empty login form.
    return len(entry["pending"]) >= 2 and entry["landed"] >= entry["pending"]


def _maybe_sign_in(tab_id: int, frame_id: int, doc: str) -> None:
    """Fire the one permitted sign-in click for this rendered document."""
    key = _signin_key(tab_id, frame_id, doc)
    with _lock:
        if not _signin_ready(key):
            return
        if not version_ok():
            return  # FR-035: never arm across a version mismatch
        _signin[key]["fired"] = True
    send(_outbound("advance_step", tab_id=tab_id, frame_id=frame_id,
                   kind="sign_in", step_key=f"{doc}::signin"))


def _handle_credential_save(msg) -> None:
    """019 (T048, FR-017): a login saved from the on-page panel.

    The password goes to the OS keychain and nowhere else — not the ack, not
    the log line, not the answers feed. Saving re-arms the wall so the
    applicant does not have to hunt for a Retry button.
    """
    from .. import credentials

    try:
        credentials.save(msg.domain, msg.email, msg.password)
    except Exception:  # noqa: BLE001 — surface, never crash the bridge
        log.warning("credential save failed for %s", msg.domain, exc_info=True)
        send(_outbound("error", code="credential_save_failed", tab_id=msg.tab_id,
                       message="Couldn't save that login to your OS keychain."))
        return
    log.info("saved a login for %s", msg.domain)  # domain only, never the pair
    with _lock:
        # The wall gets one more chance now that a credential exists.
        for key in [k for k in _signin if k[0] == msg.tab_id]:
            _signin.pop(key, None)
        _answers_force.add(msg.tab_id)
    send(_outbound("credential_saved", tab_id=msg.tab_id, domain=msg.domain))
    send(_outbound("rescan", reason="credential_saved"))


# 021 (FR-015): fields a scan has seen EMPTY, keyed (doc, je_idx). This is
# what separates "the applicant answered this" from "the employer prefilled
# it" — a value present on FIRST sight is the employer's own data or the
# browser's password manager, and is never the applicant's answer to learn.
_seen_empty: set[tuple] = set()


def _learn_if_the_applicant_typed_it(raw: dict, decision, ledger: dict,
                                     job_id: int, question: str) -> None:
    """021 (FR-015/FR-017, contracts/observed_answer.md).

    Called for EVERY decided field, before the action dispatch, because the
    two branches that matter look different: a classified field with a value
    returns `settle`/`skipped_existing`, but an UNCLASSIFIED one returns a
    plain `skip` (`field_core.decide`, tag == "free_text_unknown"). Keying
    only on the settle path would silently miss every essay answer — the
    class the applicant most wants learned (analysis A6).
    """
    from . import answer_bank, field_core

    lkey = field_core.key(raw)
    value = field_core.displayed_value(raw)
    if not value:
        _seen_empty.add(lkey)
        return
    if lkey not in _seen_empty:
        return  # already answered when we first saw it — not ours to learn
    entry = ledger.get(lkey)
    outcome = entry[0] if isinstance(entry, tuple) else entry
    if outcome == "filled" or decision.action == "fill":
        _seen_empty.discard(lkey)
        return  # WE put that there
    _seen_empty.discard(lkey)
    try:
        answer_bank.record_observed(
            question=question, answer=value, tag=decision.tag,
            job_id=job_id, secret=bool(getattr(decision, "secret", False)))
    except Exception:  # noqa: BLE001 — never let learning break a fill
        log.warning("could not record an observed answer", exc_info=True)


def _handle_page_report(msg) -> None:
    """021 (FR-001/FR-002): write a shareable description of this page.

    v2.0.0's first real Workday application reported Filled 5 / Needs you 149
    / Seen 156 with most rows blank. Three causes were readable from source.
    One was not — is 156 a single scan genuinely seeing 156 fields, or
    `_frame_seen` summing frames that no longer exist? The suite's Workday
    fixtures hold 9 and 2 fields, so nothing here could answer it and a guess
    would have been the fourth plan claim this project killed by measurement.

    So the file carries BOTH numbers: `counts` derived from the descriptors
    actually held right now, and `counts_reported` as the panel header
    computed it. A gap between them IS the accumulation, made visible.

    Never a value, never a full URL. See contracts/page_report.md.
    """
    import json as _json
    from datetime import datetime, timezone

    from .. import APP_VERSION, paths
    from . import adapters, page_report

    with _lock:
        job_id = _watch["job_id"]
        records: list[dict] = []
        for frame_records in (_page_shape.get(job_id) or {}).values():
            records.extend(frame_records)
        # BOTH numbers, deliberately: `seen` is what the panel header shows
        # (live frames only), `frames_all` counts every frame that ever
        # reported. A gap between them is stale-frame inflation, made visible
        # in the file rather than argued about.
        reported = {"seen": _total_seen_locked(),
                    "frames_live": sum(
                        1 for _c, at in _frame_seen.values()
                        if time.monotonic() - at <= FRAME_STALE_S),
                    "frames_all": len(_frame_seen),
                    "seen_all_frames": sum(c for c, _at in
                                           _frame_seen.values())}

    report = page_report.build(
        records,
        captured_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        app_version=APP_VERSION,
        ats=adapters.ats_from_url(msg.url) or "",
        url_host=page_report.safe_host(msg.url),
    )
    report["counts_reported"] = reported

    directory = paths.data_dir() / "reports"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = report["captured_at"].replace(":", "").replace("-", "")
        filename = f"page-{stamp}.json"
        (directory / filename).write_text(
            _json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        log.warning("could not write the page report", exc_info=True)
        send(_outbound("error", code="page_report_failed", tab_id=msg.tab_id,
                       message="Couldn't write the page report."))
        return
    log.info("page report written: %s (%d fields)", filename,
             len(report["fields"]))
    send(_outbound("page_report_saved", tab_id=msg.tab_id, filename=filename,
                   fields=len(report["fields"])))


def _handle_fields(msg) -> None:
    from . import adapters, browser_controller as bc, field_core

    with _lock:
        if msg.tab_id != _watch["tab_id"]:
            _counters["dropped_fields"] += 1  # doctor tripwire (T008)
            return
        job_id = _watch["job_id"]
    if job_id is None:
        return

    from .. import db

    profile = db.get_profile() or {}
    with bc._lock:
        ledger = bc._state.handled.setdefault(job_id, {})

    frame_domain = _frame_domain(msg.url)

    missing_login = {"seen": False}

    def get_value(tag, raw):
        # Credentials are gated by the SENDING FRAME's domain — the frame
        # is where the secret would land, and it may not be the job's own
        # host (Greenhouse iframes, SSO pages). Everything else reuses the
        # facade's value resolution unchanged.
        if tag in _CREDENTIAL_TAGS:
            from .. import credentials

            if not frame_domain:
                return None
            saved = credentials.get(frame_domain)
            if not saved:
                # 019 (FR-017): this used to be a silent skip — the wall sat
                # there and the applicant never learned why.
                missing_login["seen"] = True
                return None
            return (saved["password"] if tag == "login_password"
                    else saved["email"])
        # 019 (FR-021): an account the applicant is CREATING. A strong
        # password is generated and saved to the vault at fill time, so the
        # credential exists the moment the form holds it — the human still
        # presses Create account.
        if tag == "signup_password":
            from .. import credentials

            if not frame_domain:
                return None
            existing = credentials.get(frame_domain)
            if existing and existing.get("password"):
                return existing["password"]
            email = (profile or {}).get("email") or ""
            if not email:
                return None
            generated = credentials.generate_password()
            try:
                credentials.save(frame_domain, email, generated)
            except Exception:  # noqa: BLE001 — never crash the fill
                log.warning("could not save the generated login for %s",
                            frame_domain, exc_info=True)
                return None
            return generated
        return bc._value_for_tag(tag, raw, profile, job_id)

    ats = adapters.ats_from_url(msg.url)
    seen = 0
    # 019 (FR-023): visible REQUIRED fields still holding no answer. The
    # escort will not advance a step while any of these remain — that is
    # what makes "complete" mean complete rather than "we tried".
    required_pending = 0
    # 016 (T017): fields the HUMAN must answer (sensitive / missing fact /
    # no valid option) — highlighted on the page + listed in the panel.
    from . import drafter

    needs_you_idx: list[str] = []
    needs_you_labels: list[str] = []
    # 017 (FR-017): first-vs-full name is a document-level question — a
    # "Name" box sitting beside "Last name" is the FIRST name, which no
    # single-descriptor classifier can see.
    raws = [desc.as_watcher_dict() for desc in msg.descriptors]
    name_overrides = field_core.name_layout(raws, ats)

    # 021 (FR-009): a monotonic scan counter per (job, document). Pruning is
    # by "absent from the last PRUNE_AFTER_SCANS scans of THIS document" —
    # a document token is what changes on a real navigation, and a count that
    # ignored it would evict a whole page's fields the moment a second
    # document appeared.
    with _lock:
        doc_key = (job_id, msg.doc)
        _scan_seq = _scan_counts.get(doc_key, 0) + 1
        _scan_counts[doc_key] = _scan_seq

    # 021 (FR-001): every descriptor this scan saw, in document order, with
    # whatever the app decided about it. Keyed so a reason discovered later
    # (no_saved_login, version_mismatch) can patch the entry it belongs to.
    shape: dict[str, dict] = {}

    def note_shape(descriptor: dict, *, decision: str = "", tag: str = "",
                   reason: str = "") -> None:
        entry = shape.get(descriptor.get("je_idx") or "")
        if entry is None:
            shape[descriptor.get("je_idx") or ""] = {
                "descriptor": descriptor, "decision": decision,
                "tag": tag, "reason": reason,
            }
            return
        if decision:
            entry["decision"] = decision
        if tag:
            entry["tag"] = tag
        if reason:
            entry["reason"] = reason

    def question_of(descriptor: dict) -> str:
        # 021 (FR-006/FR-007): .strip() is the whole first half of this fix.
        # This was `label_text or placeholder or aria_label or ""`, and a
        # label of " " is TRUTHY in Python — so a row was created and the
        # panel rendered it visually blank. Most of the applicant's 149 rows
        # on a real Workday page were exactly that.
        for source in ("label_text", "placeholder", "aria_label"):
            text = (descriptor.get(source) or "").strip()
            if text:
                return text
        # The second half: a field the label ladder cannot name usually still
        # has a stable identity, and scanner.js has been capturing it since
        # 011 while the panel threw it away. Workday puts it in
        # data-automation-id.
        for source in ("automation_id", "name", "id"):
            humanized = field_core.humanize_identifier(
                descriptor.get(source) or "")
            if humanized:
                return humanized
        # Nothing names it. A blank row is worse than no row — it belongs in
        # the page report, which records every field regardless.
        return ""

    def note_answer(descriptor: dict, *, action: str, answer: str = "",
                    tag: str = "", ai_draft: bool = False,
                    secret: bool = False, reason: str = "") -> None:
        """018 (FR-019): remember this decision for the on-page feed.

        Recorded HERE, inside the decision loop, because this is the only
        place that sees every field AND already holds its `je_idx`. Reading it
        back out of the drafter (as v1.7.0 did) can only ever show the
        questions the drafter touched.
        """
        question = question_of(descriptor)
        # 021: the report records the field regardless — an unnameable field
        # is exactly what a diagnostic is for. The review feed still skips it.
        note_shape(descriptor, decision=action, tag=tag, reason=reason)
        if not question:
            return
        index = _page_entries.setdefault(job_id, {})
        key = field_core.key(descriptor)
        if key not in index and len(index) >= MAX_PAGE_ENTRIES:
            # 021 (analysis A8): this used to drop silently. A review surface
            # that quietly stops listing fields reads as "that is everything",
            # which is the exact failure 018 and 019 were spent eliminating.
            # The panel already has a `truncated` channel — use it.
            with _lock:
                _counters["page_entries_truncated"] += 1
            return
        # A field we filled stays in the feed once it is filled. On the NEXT
        # scan that field is no longer empty, so `decide` returns "skip" —
        # and blindly overwriting the record with that skip made every
        # successfully filled field vanish from the panel a second or two
        # after it appeared. What the applicant needs to review is precisely
        # the value we put there, so an answerless skip never displaces it.
        previous = index.get(key)
        if action == "skip" and previous and previous.get("answer"):
            # Still present on this scan, so it must not be pruned — even
            # though the record itself is left alone.
            previous["last_seen_scan"] = _scan_seq
            return
        index[key] = {
            "key": key,
            "je_idx": descriptor.get("je_idx") or "",
            # 021 (FR-004/FR-010): without these, page_answers would collapse
            # every same-named question on the page into ONE row — the
            # over-collapse that would be worse than the flood it fixes.
            "section_label": descriptor.get("section_label") or "",
            "section_index": int(descriptor.get("section_index") or 0),
            # 021 (FR-009): which scan last saw this field. A wizard step or a
            # React remount replaces the elements, and v2.0.0 never pruned —
            # so every step's fields stayed listed as outstanding forever.
            "last_seen_scan": _scan_seq,
            "question": question,
            "answer": answer,
            "action": action,
            "ai_draft": ai_draft,
            "secret": secret,
            "tag": tag,
            # 019 (FR-002/FR-017): a decision-layer reason (version_mismatch,
            # no_saved_login) makes the skip visible as needs-you without a
            # drafter record.
            "reason": reason,
        }

    for raw in raws:
        override = name_overrides.get(raw.get("je_idx"))
        if override:
            raw["tag_override"] = override
        fkey = (msg.tab_id, msg.frame_id, raw["je_idx"])
        with _lock:
            info = _inflight.get(fkey)
            if info is not None:
                if time.monotonic() - info[-1] <= INFLIGHT_TTL_S:
                    seen += 1
                    # Already dispatched this scan — keep it in the feed with
                    # the value we sent, so a field in flight does not blink
                    # out of the panel and back in.
                    note_answer(raw, action="fill", answer=info[2],
                                tag=info[1], ai_draft=info[3])
                    continue
                del _inflight[fkey]  # lost fill_result — re-decide (T007)
        decision = field_core.decide(ats, raw, ledger, get_value)
        note_shape(raw, decision=decision.action, tag=decision.tag or "")
        # 021 (FR-009): this scan SAW the field, whichever branch it takes
        # below — and `settle` takes none of them, so a field we already
        # filled would have gone three scans without a touch and been pruned.
        # That both loses the v1.8.0 guarantee that a filled field stays in
        # the review list, and changes the feed, which makes the panel rebuild
        # rows the applicant may be typing into. Caught by the browser suite.
        seen_entry = (_page_entries.get(job_id) or {}).get(
            field_core.key(raw))
        if seen_entry is not None:
            seen_entry["last_seen_scan"] = _scan_seq
        if decision.action == "ignore":
            continue
        _learn_if_the_applicant_typed_it(raw, decision, ledger, job_id,
                                         question_of(raw))
        seen += 1
        if (raw.get("required") and raw.get("visible")
                and decision.action in ("fill", "skip")
                and not (raw.get("value") or "").strip()):
            required_pending += 1
        lkey = field_core.key(raw)
        if decision.action == "skip":
            question = question_of(raw)
            # 019 (FR-017): a credential field with no saved login is a
            # question for the applicant, not a field to ignore.
            if decision.tag in _CREDENTIAL_TAGS and missing_login["seen"]:
                note_answer(raw, action="skip", tag=decision.tag,
                            reason="no_saved_login")
                needs_you_idx.append(raw["je_idx"])
                needs_you_labels.append(
                    question or f"Sign in to {frame_domain or 'this site'}")
                continue
            if question:
                note_answer(raw, action="skip", tag=decision.tag)
                record = drafter.get(job_id, question)
                if record and record["state"] == "failed" and \
                        record["reason"] in drafter._NEEDS_YOU_REASONS:
                    needs_you_idx.append(raw["je_idx"])
                    needs_you_labels.append(question)
            continue
        if decision.action == "settle":
            # 019 (FR-019): a credential the browser's own password manager
            # already filled is SATISFIED, not a dead end. It counts toward
            # arming sign-in exactly as one we filled ourselves would.
            if (decision.tag in _CREDENTIAL_TAGS
                    and decision.outcome == "skipped_existing"):
                with _lock:
                    _signin_note_issued(
                        _signin_key(msg.tab_id, msg.frame_id,
                                    raw.get("doc") or msg.doc),
                        raw["je_idx"], satisfied=True)
            bc._record(job_id, raw, decision.tag, "", decision.outcome)
            with bc._lock:
                ledger[lkey] = field_core.settle_entry(decision.outcome)
            continue
        # action == "fill"
        item: dict = {"je_idx": raw["je_idx"], "flag": None}
        if decision.kind == "file":
            token = issue_file_token(str(decision.value))
            # 017 (FR-031): send the real name and the expected type so the
            # upload arrives as the applicant's own file and the companion
            # can verify what it fetched before attaching it.
            import mimetypes
            import os

            path = str(decision.value)
            filename = os.path.basename(path.replace("\\", "/")) or "resume.pdf"
            mime = mimetypes.guess_type(filename)[0] or "application/pdf"
            item.update(kind="file", value="",
                        file_url=f"/api/bridge/file/{token}",
                        filename=filename, mime=mime)
        elif decision.secret:
            item.update(kind="secret", value=str(decision.value))
        elif decision.kind == "select":
            item.update(kind="select", value=str(decision.value),
                        option_label=decision.option_label)
        elif decision.kind == "combobox":
            # 011: custom dropdown — the filler opens it and picks the option
            item.update(kind="combobox", value=str(decision.value),
                        option_label=decision.option_label)
        elif decision.kind == "typeahead":
            # 011: type then pick the matching suggestion
            item.update(kind="typeahead", value=str(decision.value))
        elif decision.kind == "radio":
            # 016 (T013): version gate — an old companion has no radio
            # branch and would text-set the element (silent mis-fill).
            # 019 (T005, FR-002): withholding is no longer SILENT — the
            # field surfaces on the page as needs-you naming the mismatch,
            # and the doctor counts it. Still retryable: it fills the
            # moment the companion is reloaded.
            if not version_ok():
                with _lock:
                    _counters["version_mismatch_fills"] += 1
                note_answer(raw, action="skip", tag=decision.tag,
                            reason="version_mismatch")
                continue
            item.update(kind="radio", value=str(decision.value),
                        option_label=decision.option_label)
        elif decision.kind == "richtext":
            # 020 (FR-017): an editable region, not a control. Without this
            # branch the decision fell through to kind="text" and the filler
            # called a native <input> value setter on a <div> — which throws,
            # so every rich-text cover letter reported needs_manual. The
            # decision was right, the write path was right, and the answer
            # still never landed; only a real-browser test showed it.
            item.update(kind="richtext", value=str(decision.value))
        elif decision.kind == "checkbox":
            item.update(kind="checkbox", value="on")
            # 017 (C8): a merged checkbox group is one logical field but the
            # tick lands on a MEMBER. Re-address the item to that member's
            # je_idx; the kind stays the ordinary "checkbox" an older
            # companion already understands, so no version gate is needed.
            if (raw.get("type") or "") == "checkbox_group":
                member_idx = _member_je_idx(raw, decision.option_label)
                if member_idx is None:
                    continue
                item["je_idx"] = member_idx
        else:
            item.update(kind="text", value=str(decision.value))
        if decision.ai_draft:
            item["flag"] = "ai_draft"
        note_answer(raw, action="fill", answer=decision.preview,
                    tag=decision.tag, ai_draft=decision.ai_draft,
                    secret=decision.secret)
        with _lock:
            _inflight[fkey] = (raw, decision.tag, decision.preview,
                               decision.ai_draft, time.monotonic())
            # 019 (FR-016): remember that WE issued this credential fill —
            # the sign-in click is legal only because of that fact.
            if decision.tag in _CREDENTIAL_TAGS:
                _signin_note_issued(
                    _signin_key(msg.tab_id, msg.frame_id,
                                raw.get("doc") or msg.doc),
                    raw["je_idx"], satisfied=False)
        # 016 (T005/R1): incremental dispatch — a decided fill goes out
        # IMMEDIATELY. Batching until the whole form was decided is what
        # withheld name/email fills behind slow decisions (RC1).
        send(_outbound("fill", tab_id=msg.tab_id, frame_id=msg.frame_id,
                       items=[item]))

    with _lock:
        _frame_seen[msg.frame_id] = (seen, time.monotonic())
        total_seen = _total_seen_locked()
        # 021 (FR-001): replaced, never accumulated — the report describes the
        # page as it is NOW. Accumulating is what made the review feed
        # unreadable in the first place (R1.3); the diagnostic must not
        # inherit that defect or it cannot be used to measure it.
        _page_shape.setdefault(job_id, {})[msg.frame_id] = list(shape.values())
        # 021 (FR-009): forget the fields this document no longer has. v2.0.0
        # cleared this index only at session start, and its keys are
        # (doc, je_idx) — so every wizard step and every React remount added
        # fresh entries while the old ones stayed. That accumulation is a
        # large part of how a page reached 149 outstanding rows.
        entries = _page_entries.get(job_id) or {}
        stale = [k for k, entry in entries.items()
                 if k[0] == msg.doc
                 and _scan_seq - entry.get("last_seen_scan", _scan_seq)
                 >= PRUNE_AFTER_SCANS]
        for k in stale:
            del entries[k]
        if stale:
            log.debug("pruned %d field(s) no longer on the page", len(stale))

    with bc._lock:
        filled_total = bc._state.activity.get("fields_filled", 0)
    bc._set_activity(
        phase="watching" if total_seen else "waiting_for_form",
        fields_seen=total_seen,
        last_scan_at=bc._utcnow_iso(),
        url=msg.url if msg.frame_id == 0 else bc._state.activity.get("url"),
        message=(
            f"watching page — {total_seen} fields seen · "
            f"{filled_total} filled · you press the final Submit"
            if total_seen else
            "no form fields visible yet — click the site's own Apply "
            "button; fields fill the moment the form appears"
        ),
    )
    with bc._lock:
        draft_count = sum(
            1 for e in bc._state.fill_reports.get(job_id, [])
            if e.get("ai_draft") and e["outcome"] == "filled"
        )
    # 018 (FR-032): the companion also gets the session context it needs to
    # offer Stop and Next without a trip to the app.
    with bc._lock:
        remaining = max(0, len(bc._state.job_ids) - bc._state.index - 1)
        running = bc._state.running
    # 019 (T060): the escort's judgment on THIS step. Everything it needs is
    # already in hand from the scan we just did — no extra page work.
    from . import escort as escort_mod

    escort = _get_escort()
    fh = escort_mod.fieldset_hash(raws)
    qkey = (msg.tab_id, msg.frame_id)
    now = time.monotonic()
    with _lock:
        prior = _quiet_since.get(qkey)
        if prior is None or prior[0] != fh:
            _quiet_since[qkey] = (fh, now)   # the step changed; clock restarts
            quiet_for = 0.0
        else:
            quiet_for = now - prior[1]
        inflight_here = sum(1 for k in _inflight
                            if k[0] == msg.tab_id and k[1] == msg.frame_id)
    step = escort_mod.StepView(
        doc=msg.doc, fieldset_hash=fh,
        visible_required_pending=required_pending,
        inflight=inflight_here, needs_you=len(needs_you_idx),
        focused=any(r.get("focused") for r in raws),
        captcha=bool(getattr(msg, "captcha", False)),
        missing_login=missing_login["seen"],
        quiet_for=quiet_for, seen=seen)
    verdict = escort.should_advance(
        step, version_ok=version_ok(), clickable_host=_clickable_host(msg.url))
    if verdict.advance:
        escort.note_advance(step.key)
        send(_outbound("advance_step", tab_id=msg.tab_id,
                       frame_id=msg.frame_id, kind=verdict.kind,
                       step_key=step.key))
    session_state = verdict.state or ("filling" if running else "done")

    send(_outbound("overlay_state", tab_id=msg.tab_id, summary={
        "seen": total_seen, "filled": filled_total, "drafts": draft_count,
        "needs_you": len(needs_you_idx),
        "needs_you_idx": needs_you_idx,
        "attention": needs_you_labels[:5],
        "message": "you press the final Submit — never us",
        "session": session_state if running else "done",
        "current_job_id": job_id if job_id and job_id > 0 else None,
        "remaining": remaining,
        # 019 (FR-017): the panel offers its inline save form only when the
        # app actually has no login for this domain.
        "needs_login": missing_login["seen"],
    }))

    # 017 (FR-034) / 018 (FR-019, FR-020, FR-027): the FULL answer text goes
    # to the page — now for EVERY field the app decided about, not only the
    # ones the AI drafter touched, and each carrying the `je_idx` that makes
    # Insert and Show me possible.
    job_id = _watch["job_id"]
    if job_id is not None:
        _push_answers(msg.tab_id, job_id)

    # 019 (FR-016): a credential already satisfied by the browser's own
    # password manager arms sign-in without any fill_result ever arriving.
    # Keyed by the DESCRIPTOR's document token — the same identity the
    # ledger uses, so the two halves of the state machine cannot disagree.
    for doc in {r.get("doc") or msg.doc for r in raws}:
        _maybe_sign_in(msg.tab_id, msg.frame_id, doc)


def _start_answer_feed(tab_id: int, job_id: int) -> None:
    """A new session begins with an empty index and no digest history, so its
    first scan always reaches the page. Caller holds `_lock`.

    Only one fill session is live at a time and this index is per-live-session
    state, so every other job's entries are dropped here too — otherwise a long
    app session filling fifty applications keeps fifty indexes alive for no one
    to read.
    """
    _page_entries.clear()
    _page_shape.clear()
    _scan_counts.clear()
    _seen_empty.clear()
    _page_entries[job_id] = {}
    _answers_digest.clear()
    _answers_force.add(tab_id)


def _push_answers(tab_id: int, job_id: int) -> None:
    """Send the page-answer feed — but only when it actually changed.

    v1.7.0 pushed this on every scan: with a 2 s safety poll that is a payload
    of up to 400 KB every two seconds, and each one made the panel rebuild
    every row from scratch, which is what destroyed a half-typed answer before
    the applicant could press Enter.
    """
    from . import drafter, page_answers

    with _lock:
        entries = list((_page_entries.get(job_id) or {}).values())
        forced = tab_id in _answers_force
        _answers_force.discard(tab_id)
        # 021 (analysis A8): the entry cap refused fields. Say so — the panel
        # already renders this as "not every answer fits here".
        capped = _counters["page_entries_truncated"] > 0
    items = page_answers.build(entries, drafter.records_for_job(job_id))
    truncated = capped
    # Stay well inside MAX_MESSAGE_BYTES on a very large form; the app's own
    # view stays complete either way (FR-029).
    while len(items) > 1 and len(str(items)) > 400_000:
        items.pop()
        truncated = True
    fingerprint = page_answers.digest(items)
    with _lock:
        unchanged = _answers_digest.get(tab_id) == fingerprint
        if unchanged and not forced:
            return
        _answers_digest[tab_id] = fingerprint
    send(_outbound("answers", tab_id=tab_id, job_id=job_id,
                   items=items, truncated=truncated,
                   counts=page_answers.counts(items)))


def _handle_fill_result(msg) -> None:
    from . import browser_controller as bc, field_core

    with _lock:
        if msg.tab_id != _watch["tab_id"]:
            return
        job_id = _watch["job_id"]
    if job_id is None:
        return
    filled_now = 0
    docs: set[str] = set()
    for item in msg.items:
        fkey = (msg.tab_id, msg.frame_id, item.je_idx)
        with _lock:
            info = _inflight.pop(fkey, None)
        if info is None:
            continue
        raw, tag, preview, ai_draft, _sent_at = info
        lkey = field_core.key(raw)
        if item.outcome == "filled":
            bc._record(job_id, raw, tag, preview, "filled", ai_draft)
            with bc._lock:
                bc._state.handled.setdefault(job_id, {})[lkey] = "filled"
                # 019 (FR-016): this credential landed. When both halves
                # have, the one permitted sign-in click is armed.
                if tag in _CREDENTIAL_TAGS:
                    _signin_note_landed(msg.tab_id, msg.frame_id, item.je_idx)
                    docs.add(raw.get("doc") or "")
            filled_now += 1
        elif item.outcome == "needs_manual":
            bc._record(job_id, raw, tag, "", "needs_manual")
            with bc._lock:
                bc._state.handled.setdefault(job_id, {})[lkey] = \
                    field_core.settle_entry("needs_manual")
        # focused / not_found: retryable — no record, next scan re-decides
    if filled_now:
        with bc._lock:
            bc._state.activity["fields_filled"] = (
                bc._state.activity.get("fields_filled", 0) + filled_now
            )
    for doc in docs:
        _maybe_sign_in(msg.tab_id, msg.frame_id, doc)


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
        # 019 (FR-032): a wizard step POSTs its form, so an escorted advance
        # looks exactly like a submission. Attribute it: only a submit the
        # applicant themselves caused belongs in the did-you-apply queue.
        if _get_escort().attribute_submit() == "app":
            log.debug("submit on tab %s attributed to an escorted advance",
                      msg.tab_id)
            return
        with _lock:
            _pending_submissions.append({
                "job_id": job_id, "tab_id": msg.tab_id,
                "url": msg.url, "at": time.time(),
            })


ADHOC_JOB_ID = -2  # job-less ad-hoc fill session (no DB row until linked)

# tab_id -> {"url", "title", "linked_job_id"} for the current ad-hoc session
_adhoc: dict = {}


def _handle_fill_here(msg) -> None:
    """Ad-hoc 'Fill this page' (FR-004a): fill whatever application page the
    user is already viewing.

    019 (T013, FR-004): always honoured on a fillable page. A finished or
    quiet earlier session is SUPERSEDED (its tab stays open, just
    unwatched); `busy` is reported only while another tab is actively
    mid-fill — and then the refusal names that tab."""
    from . import browser_controller as bc

    with bc._lock:
        queue_active = bc._state.running and bc._state.backend == "extension"
    if queue_active:
        now = time.monotonic()
        with _lock:
            watched_tab = _watch["tab_id"]
            mid_fill = any(
                key[0] == watched_tab and now - info[-1] <= INFLIGHT_TTL_S
                for key, info in _inflight.items())
        if (mid_fill and watched_tab is not None
                and watched_tab != msg.tab_id):
            send(_outbound("error", code="busy",
                           message=f"tab {watched_tab} is mid-fill — "
                                   "finish or stop it first"))
            return
        # Supersede: release the old watch; its tab stays open. The tab
        # that LOSES the session is told why — a companion that goes quiet
        # with no explanation is the defect this feature exists to fix.
        if watched_tab is not None and watched_tab != msg.tab_id:
            send(_outbound("error", code="superseded", tab_id=watched_tab,
                           message="Filling moved to the tab you just "
                                   "pressed Fill in."))
            send(_outbound("watch_stop", tab_id=watched_tab))

    # Stand up a job-less session on the extension backend keyed to this tab.
    with bc._lock:
        bc._state.job_ids = [ADHOC_JOB_ID]
        bc._state.index = 0
        bc._state.running = True
        bc._state.practice = False
        bc._state.backend = "extension"
        bc._state.handled = {ADHOC_JOB_ID: {}}
        bc._state.fill_reports = {ADHOC_JOB_ID: []}
        bc._state.outcomes = {}
        bc._state.interrupted = False
        bc._state.summary = None
        bc._state.activity = bc._fresh_activity()
    with _lock:
        _adhoc.clear()
        _adhoc[msg.tab_id] = {"url": msg.url, "title": msg.title,
                              "linked_job_id": None}
        _watch.update(tab_id=msg.tab_id, job_id=ADHOC_JOB_ID)
        _inflight.clear()
        _frame_seen.clear()
        _start_answer_feed(msg.tab_id, ADHOC_JOB_ID)
    send(_outbound("watch_start", tab_id=msg.tab_id, job_id=ADHOC_JOB_ID))


def link_adhoc(tab_id: int) -> dict:
    """Offer to track the ad-hoc page as an application: match its URL to an
    existing job, else the caller may create one. User-confirmed (FR-004a);
    never automatic."""
    from urllib.parse import urlparse

    from .. import db

    with _lock:
        session = _adhoc.get(tab_id)
    if session is None:
        return {"job_id": None, "match": None}
    page_url = session["url"]
    page_host_path = urlparse(page_url).netloc + urlparse(page_url).path
    # strip a trailing /apply or /application so the posting URL matches
    for suffix in ("/apply", "/application"):
        if page_host_path.endswith(suffix):
            page_host_path = page_host_path[: -len(suffix)]
    match_id = None
    for job in db.list_all_jobs_minimal():
        jurl = job.get("url") or ""
        jhp = urlparse(jurl).netloc + urlparse(jurl).path
        if jhp and (jhp in page_host_path or page_host_path in jhp):
            match_id = job["id"]
            break
    with _lock:
        if session is not None:
            session["linked_job_id"] = match_id
    return {"job_id": match_id, "url": page_url, "title": session["title"]}


# --- discovery (012): score + save, independent of the fill session ---------

# Defensive cap on the description text pulled off a browsed page before it is
# scored/persisted — a page cannot overwhelm the bridge or the DB.
_DISCOVERY_DESC_MAX = 20_000


def _handle_score_request(msg) -> None:
    """012: score a posting the user is browsing and send the result back to
    the requesting tab. Reads NOTHING from the fill session (_watch/bc._state)."""
    from .. import discovery

    result = discovery.score_page(
        title=msg.title, company=msg.company,
        description=(msg.description or "")[:_DISCOVERY_DESC_MAX],
        url=msg.url,
    )
    send(_outbound("score_result", tab_id=msg.tab_id, **result))


def _handle_save_job(msg) -> None:
    """012: save the browsed posting to the feed/tracker as a manual, saved
    job — dedup-safe, never a duplicate. Independent of the fill session."""
    from .. import db

    status = db.upsert_job({
        "title": msg.title,
        "company": msg.company,
        "url": msg.url,
        "description": (msg.description or "")[:_DISCOVERY_DESC_MAX],
        "location": msg.location or None,
        "source": "manual",
        "posted_date": None,
    })
    # Resolve the row by this exact url. It resolves for inserted/updated (the
    # row now carries this url); a cross-source "skipped" dup is kept under a
    # DIFFERENT url, so get_job_by_url returns None — the posting still exists,
    # so report already=True without a status write. Never error, never dup.
    row = db.get_job_by_url(msg.url)
    job_id = None
    if row is not None:
        job_id = row["id"]
        if row.get("status") != "saved":
            db.set_status(job_id, "saved")
    already = status != "inserted"
    send(_outbound("save_result", tab_id=msg.tab_id, status=status,
                   job_id=job_id, already=already))


def _handle_apply_here(msg) -> None:
    """017 (FR-038): the floating badge's Apply with Apply Assist.

    Saves the posting the applicant is looking at, then starts a watched
    session on THAT tab with the real job id — a non-ad-hoc watch, so the
    apply-opener is armed and the session is tied to a real job rather than
    the -2 sentinel. It starts a fill session and nothing else: no control on
    the page is clicked, here or anywhere in this path.
    """
    from .. import db

    db.upsert_job({
        "title": msg.title,
        "company": msg.company,
        "url": msg.url,
        "description": (msg.description or "")[:_DISCOVERY_DESC_MAX],
        "source": "manual",
        "posted_date": None,
    })
    row = db.get_job_by_url(msg.url)
    if row is None:
        send(_outbound("error", code="unknown_job",
                       message="Couldn't save this posting — open it from the app instead."))
        return
    job_id = row["id"]
    if row.get("status") not in ("saved", "applied"):
        db.set_status(job_id, "saved")

    from . import browser_controller as bc

    # 019 (T010, FR-003): the session ADOPTS the tab the user pressed the
    # button on. start_queue(adopt_tab_id=…) never opens a tab, and
    # adopt_tab() clears pending_open so nothing can re-route the watch.
    try:
        bc.start_queue([job_id], adopt_tab_id=msg.tab_id)
    except Exception as exc:  # noqa: BLE001 — surface, never crash the bridge
        log.warning("apply_here failed to start", exc_info=True)
        send(_outbound("error", code="start_failed", message=str(exc)[:200]))
        return


def reset_for_tests() -> None:
    with _lock:
        _session.update(send=None, close=None, version=None, browser=None,
                        last_seen=None)
        _rejects.update(auth=0, protocol=0, last_kind=None, last_at=None)
        _file_tokens.clear()
        _watch.update(tab_id=None, job_id=None)
        _watch["pending_open"].clear()
        _inflight.clear()
        _frame_seen.clear()
        _pending_submissions.clear()
        _progression_clicks.clear()
        _signin.clear()
        # The doctor's tripwires belong to a session too — a count carried
        # over from a previous one is a lie about this one.
        for name in _counters:
            _counters[name] = 0
        _quiet_since.clear()
        globals()["_escort"] = None
        _page_entries.clear()
        _page_shape.clear()
        _scan_counts.clear()
        _seen_empty.clear()
        _answers_digest.clear()
        _answers_force.clear()
        _counters.update(dropped_fields=0, scan_errors=0)
