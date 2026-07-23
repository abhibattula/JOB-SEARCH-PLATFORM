"""Thread-safe facade over the Apply Assist live fill engine (feature 009).

Division of labor:
- THIS module owns the queue state machine (start/advance/stop/interrupt/
  resume/summary — semantics unchanged since 005-008) and the value
  resolution (profile, credentials, answer bank, tailored-PDF preference).
  Public functions mutate shared state under `_lock` and enqueue commands;
  they NEVER perform browser work on the caller's thread (FR-001).
- engine/autofill/worker.py owns the ONE thread that may touch Playwright.
- engine/autofill/watcher.py performs each ~2s watch tick: serialize+stamp
  every frame, classify (adapters → generic), idempotently fill.

Hard safety rule (unchanged since 005): this engine NEVER clicks anything.
It only fills values into recognized fields — the field query selector
(fields.FIELD_QUERY_SELECTOR) collects nothing clickable, and no fill path
contains a click call. The human always performs every submit/login/next/
apply click. The queue advances only on an explicit advance() call.

There is deliberately NO terminal "couldn't read this page" state: while a
job is current the watcher keeps watching (FR-003) — late-rendering forms,
forms the user reveals by clicking the site's own Apply button, and every
page of a multi-step application fill when their fields appear.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from . import fields as fields_mod
from . import watcher

log = logging.getLogger(__name__)

# Re-exported for callers/tests that referenced it here historically; the
# definition lives in fields.py so every serializer shares it.
FIELD_QUERY_SELECTOR = fields_mod.FIELD_QUERY_SELECTOR

# 008 (FR-007): Apply Assist drives the user's INSTALLED branded browser via
# Playwright channels — nothing is downloaded. Edge ships inbox on
# US-market Windows 11; Chrome is the fallback.
_CHANNELS = ("msedge", "chrome")

# Reason classes that mean "complete this one manually". 009: `unrecognized`
# is gone — an unreadable-looking page just keeps being watched.
FALLBACK_REASONS = ("launch_failed", "nav_failed", "scan_failed")

# Scan trouble must persist this many consecutive ticks before it is
# surfaced as scan_failed (and a single healthy tick clears it again).
SCAN_FAILURE_LIMIT = 3

# The bundled practice application queues like a job but has no DB row.
PRACTICE_JOB_ID = -1


class BrowserUnavailable(RuntimeError):
    """No supported installed browser (Edge/Chrome) could be launched."""


def _fresh_activity() -> dict:
    return {
        "phase": "idle", "fields_seen": 0, "fields_filled": 0,
        "message": "", "last_scan_at": None, "url": None,
    }


class _State:
    def __init__(self) -> None:
        self.job_ids: list[int] = []
        self.index: int = -1
        self.running: bool = False
        self.practice: bool = False
        self.practice_url: str | None = None
        # job_id -> {"reason": FALLBACK_REASONS member, "detail": str}
        self.outcomes: dict[int, dict] = {}
        # job_id -> {(doc, je_idx): outcome} — the watcher's idempotency
        # ledger (which elements are settled for this job)
        self.handled: dict[int, dict] = {}
        # consecutive all-frames-unreadable ticks for the current job
        self.scan_failures: int = 0
        # At most one pending confirmation at a time (005 FR-011): an
        # unrecognized/no-saved-answer question pauses for review rather
        # than being auto-filled from an unreviewed AI draft.
        self.pending: dict | None = None
        # per-job fill reports (passwords pre-masked at record time — the
        # secret never enters this structure)
        self.fill_reports: dict[int, list[dict]] = {}
        self.interrupted: bool = False
        self.summary: dict | None = None
        self.activity: dict = _fresh_activity()
        # 010: which fill path this queue runs on. Chosen at start_queue,
        # sticky for the run: "extension" (companion in the user's Chrome)
        # or "playwright" (assistant window). None while idle.
        self.backend: str | None = None


_state = _State()
_lock = threading.Lock()

# Real Playwright objects — owned EXCLUSIVELY by the worker thread; created
# lazily, never at import time, so unit tests never touch a real browser.
_playwright = None
_context = None
_page = None
_launched_channel: str | None = None


def _dispatch(name: str, payload: dict | None = None, wait: float | None = None):
    """The one seam between the facade and the worker thread (tests
    monkeypatch exactly this)."""
    from . import worker

    return worker.dispatch(name, payload, wait)


def _choose_backend() -> str:
    """Pick the fill path at queue start. AUTOFILL_BACKEND forces it;
    otherwise the companion wins when a live socket exists, else the
    assistant window. Chosen once, then sticky for the run (010 FR-005)."""
    import os

    forced = os.environ.get("AUTOFILL_BACKEND", "auto")
    if forced in ("extension", "playwright"):
        return forced
    from . import ext_backend

    return "extension" if ext_backend.is_live() else "playwright"


def _open_job_on_backend(job_id: int) -> None:
    """Route OPEN_JOB to the active backend."""
    if _state.backend == "extension":
        from .. import db
        from . import apply_urls, ext_backend

        job = db.get_job(job_id)
        url = apply_urls.resolve(job) if job else None
        if url:
            ext_backend.open_job(job_id, url)
    else:
        _dispatch("OPEN_JOB", {"job_id": job_id})


def _close_on_backend() -> None:
    if _state.backend == "extension":
        from . import ext_backend

        ext_backend.close_current()
    else:
        _dispatch("CLOSE_PAGE")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _set_activity(**updates) -> None:
    with _lock:
        _state.activity.update(updates)


def _mark_fallback(job_id: int, reason: str, detail: str = "") -> None:
    with _lock:
        _state.outcomes[job_id] = {"reason": reason, "detail": detail[:300]}


def _clear_fallback(job_id: int, reason: str) -> None:
    with _lock:
        outcome = _state.outcomes.get(job_id)
        if outcome and outcome["reason"] == reason:
            del _state.outcomes[job_id]


def _apply_field_value(element, tag: str, field_type: str, value) -> None:
    """The only kind of write ever made into a page. NEVER calls .click()
    — regression-tested directly (TestNeverClicksAnything)."""
    if value is None:
        return
    if tag == "resume_upload":
        element.set_input_files(value)
    elif field_type == "checkbox":
        if value:
            element.check()
    elif field_type == "select" or field_type == "select-one":
        element.select_option(value)
    else:
        element.fill(str(value))


# --- browser launch (008, unchanged) ----------------------------------------


def _profile_dir():
    """Dedicated persistent profile — the user's installed Edge/Chrome
    BINARY, never their personal browsing profile (005 clarify; 008)."""
    from .. import paths

    path = paths.data_dir() / "browser-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _headless() -> bool:
    import os

    return os.environ.get("AUTOFILL_HEADLESS") == "1"


def _ensure_context():
    """Lazily launches a headed session of the user's installed browser via
    Playwright channels (msedge → chrome). Raises BrowserUnavailable with
    per-channel detail when neither can start. Worker thread only."""
    global _playwright, _context, _launched_channel
    if _context is not None:
        return _context
    from playwright.sync_api import sync_playwright

    _playwright = sync_playwright().start()
    errors = []
    for channel in _CHANNELS:
        try:
            _context = _playwright.chromium.launch_persistent_context(
                user_data_dir=str(_profile_dir()),
                channel=channel,
                headless=_headless(),
            )
            _launched_channel = channel
            return _context
        except Exception as exc:
            errors.append(f"{channel}: {str(exc).splitlines()[0][:200]}")
    try:
        _playwright.stop()
    finally:
        _playwright = None
    raise BrowserUnavailable("; ".join(errors))


def preflight() -> dict:
    """Cheap launchability probe: can an installed browser actually start?
    Never touches a live session."""
    if _context is not None:
        return {"ok": True, "channel": _launched_channel, "error": None}
    from playwright.sync_api import sync_playwright

    errors = []
    try:
        with sync_playwright() as p:
            for channel in _CHANNELS:
                try:
                    probe = p.chromium.launch(channel=channel, headless=True)
                    probe.close()
                    return {"ok": True, "channel": channel, "error": None}
                except Exception as exc:
                    errors.append(f"{channel}: {str(exc).splitlines()[0][:200]}")
    except Exception as exc:
        errors.append(str(exc).splitlines()[0][:200])
    return {"ok": False, "channel": None, "error": "; ".join(errors) or "unknown"}


def chromium_selftest() -> bool:
    """Diagnostics/smoke hook: raises with detail when the browser layer
    can't start."""
    result = preflight()
    if not result["ok"]:
        raise RuntimeError(result["error"])
    return True


# --- value resolution (005-008 logic, preserved) -----------------------------


def _is_closed_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "targetclosed" in text or "has been closed" in text


def _mark_interrupted() -> None:
    """The dedicated browser window was closed under us: keep the queue and
    its position, drop the dead Playwright objects, let resume_queue()
    relaunch at the current job. Worker thread only (except via tests)."""
    global _playwright, _context, _page
    with _lock:
        _state.interrupted = True
        _state.activity.update(phase="interrupted",
                               message="the browser window was closed — resume when ready")
    _page = None
    _context = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None


def _resume_file_for_job(job_id: int, profile: dict) -> str | None:
    """The job's tailored PDF when available and the preference (default
    on) allows it; otherwise the stored original upload."""
    from .. import settings

    if settings.get("AUTOFILL_USE_TAILORED_PDF") != "0":
        try:
            from .. import resume_pdf

            return str(resume_pdf.tailored_resume_path(job_id))
        except Exception:
            log.debug("tailored PDF unavailable — using original resume", exc_info=True)
    return profile.get("resume_file_path") or None


def _domain_for_job(job_id: int) -> str | None:
    from urllib.parse import urlparse

    from .. import db

    job = db.get_job(job_id)
    if not job or not job.get("url"):
        return None
    return urlparse(job["url"]).netloc or None


def _value_for_tag(tag: str, raw: dict, profile: dict, job_id: int):
    from . import answer_bank

    if tag in ("login_email", "login_password"):
        from .. import credentials

        domain = _domain_for_job(job_id)
        if not domain:
            return None
        saved = credentials.get(domain)
        if not saved:
            return None
        return saved["email"] if tag == "login_email" else saved["password"]
    if tag == "full_name":
        first = profile.get("first_name") or ""
        last = profile.get("last_name") or ""
        combined = f"{first} {last}".strip()
        return combined or None
    if tag == "first_name":
        return profile.get("first_name")
    if tag == "last_name":
        return profile.get("last_name")
    if tag == "email":
        return profile.get("email")
    if tag == "phone":
        return profile.get("phone")
    if tag == "resume_upload":
        return _resume_file_for_job(job_id, profile)
    if tag in ("linkedin_url",):
        return profile.get("linkedin_url")
    if tag in ("portfolio_url",):
        return profile.get("portfolio_url")
    # Everything else (work_authorization, sponsorship_requirement,
    # eeo_disclosure, years_experience, salary_expectation, how_heard,
    # cover_letter, free_text_unknown) goes through the answer bank —
    # unrecognized/unconfirmed questions are surfaced for review, never
    # auto-filled from an unreviewed draft (005 FR-011/FR-012).
    question = raw.get("label_text") or raw.get("placeholder") or raw.get("aria_label") or ""
    if not question:
        return None
    existing = answer_bank.lookup(question)
    if existing:
        return existing["answer"]
    with _lock:
        if _state.pending is None:
            draft = answer_bank.suggest(question, tag, profile)
            _state.pending = {
                "job_id": job_id,
                "question_raw": question,
                "category": tag,
                "drafted_answer": draft,
                "field_id": raw.get("id"),
                "field_name": raw.get("name"),
            }
    return None


# --- queue state machine (public facade) -------------------------------------


def start_queue(job_ids: list[int]) -> dict | None:
    with _lock:
        _state.job_ids = list(job_ids)
        _state.index = 0 if job_ids else -1
        _state.running = bool(job_ids)
        _state.practice = False
        _state.practice_url = None
        _state.outcomes = {}
        _state.handled = {}
        _state.scan_failures = 0
        _state.pending = None
        _state.fill_reports = {}
        _state.interrupted = False
        _state.summary = None
        _state.activity = _fresh_activity()
        _state.backend = _choose_backend() if job_ids else None
        if job_ids:
            _state.activity.update(phase="opening",
                                   message="opening the application page…")
    if job_ids:
        _open_job_on_backend(job_ids[0])
    return current_job()


def start_practice(url: str) -> dict | None:
    """Queue the bundled practice application (FR-009) through the normal
    engine — same watcher, same fills, the user's real data. Refused while
    a queue is active."""
    with _lock:
        if _state.running:
            return None
        _state.job_ids = [PRACTICE_JOB_ID]
        _state.index = 0
        _state.running = True
        _state.practice = True
        _state.practice_url = url
        _state.outcomes = {}
        _state.handled = {}
        _state.scan_failures = 0
        _state.pending = None
        _state.fill_reports = {}
        _state.interrupted = False
        _state.summary = None
        _state.activity = _fresh_activity()
        _state.activity.update(phase="opening",
                               message="opening the practice application…")
        # Practice fills in the user's own Chrome when the companion is
        # live (they watch it work where they'll actually apply); else the
        # assistant window.
        _state.backend = _choose_backend()
    if _state.backend == "extension":
        from . import ext_backend

        ext_backend.open_practice(url)
    else:
        _dispatch("OPEN_PRACTICE", {"url": url})
    return current_job()


def current_job() -> dict | None:
    with _lock:
        if not _state.running or not (0 <= _state.index < len(_state.job_ids)):
            return None
        job_id = _state.job_ids[_state.index]
        remaining = len(_state.job_ids) - _state.index - 1
        pending = None
        if _state.pending is not None:
            pending = {
                "question_raw": _state.pending["question_raw"],
                "category": _state.pending["category"],
                "drafted_answer": _state.pending["drafted_answer"],
            }
        outcome = _state.outcomes.get(job_id)
        return {
            "job_id": job_id,
            "remaining": remaining,
            "fell_back": bool(outcome and outcome["reason"] in FALLBACK_REASONS),
            "pending": pending,
        }


def resolve_pending(answer: str) -> None:
    """Called after the user confirms/edits a drafted answer (the route has
    already saved it to the answer bank). 009: no element bookkeeping —
    clear the pending slot, unlock any no_match verdicts (the confirmed
    answer may now match), and force a fill pass; the watcher fills it via
    the normal answer-bank lookup on the worker thread."""
    with _lock:
        pending = _state.pending
        _state.pending = None
        if pending is None:
            return
        active = _state.running and 0 <= _state.index < len(_state.job_ids)
        if active:
            job_id = _state.job_ids[_state.index]
            ledger = _state.handled.get(job_id)
            if ledger:
                for key in [k for k, v in ledger.items() if v == "no_match"]:
                    del ledger[key]
        backend = _state.backend
    if active and backend != "extension":
        _dispatch("FORCE_TICK", wait=0.5)


def _job_outcome(job_id: int) -> str:
    """Per-job outcome for the batch summary. Caller holds _lock."""
    outcome = _state.outcomes.get(job_id)
    if outcome and outcome["reason"] in FALLBACK_REASONS:
        return "manual"
    entries = _state.fill_reports.get(job_id) or []
    if any(entry["outcome"] == "filled" for entry in entries):
        return "filled"
    return "skipped"


def advance() -> dict | None:
    """User-driven only ("Done, next application") — never automatic
    completion detection (005 clarify session)."""
    with _lock:
        if not _state.running:
            return None
        _state.index += 1
        _state.pending = None  # a pending confirmation belongs to the job just left
        _state.scan_failures = 0
        if _state.index >= len(_state.job_ids):
            _state.running = False
            per_job = [
                {"job_id": job_id, "outcome": _job_outcome(job_id)}
                for job_id in _state.job_ids
            ]
            _state.summary = {
                "filled": sum(1 for e in per_job if e["outcome"] == "filled"),
                "manual": sum(1 for e in per_job if e["outcome"] == "manual"),
                "skipped": sum(1 for e in per_job if e["outcome"] == "skipped"),
                "per_job": per_job,
            }
            _state.activity = _fresh_activity()
            finished = True
            next_job_id = None
        else:
            finished = False
            next_job_id = _state.job_ids[_state.index]
            _state.activity = _fresh_activity()
            _state.activity.update(phase="opening",
                                   message="opening the application page…")
    _close_on_backend()
    if finished:
        return None
    _open_job_on_backend(next_job_id)
    return current_job()


def rescan() -> dict | None:
    """009: 'Re-scan' = force an immediate fill pass (the watcher already
    re-scans every ~2s). None when no active session."""
    with _lock:
        if not _state.running or not (0 <= _state.index < len(_state.job_ids)):
            return None
        backend = _state.backend
    # The companion scans continuously on its own (MutationObserver + poll),
    # so there is no tick to force; the Playwright watcher needs the nudge.
    if backend != "extension":
        _dispatch("FORCE_TICK")
    return {"forced": True}


def resume_queue() -> dict | None:
    """Relaunch the browser at the current queue position after the window
    was closed. None when there is nothing to resume."""
    with _lock:
        if not _state.interrupted or not _state.running:
            return None
        if not (0 <= _state.index < len(_state.job_ids)):
            return None
        _state.interrupted = False
        _state.scan_failures = 0
        practice = _state.practice
        practice_url = _state.practice_url
        job_id = _state.job_ids[_state.index]
        _state.activity.update(phase="opening",
                               message="reopening the application page…")
    if _state.backend == "extension":
        from . import ext_backend

        if practice and practice_url:
            ext_backend.open_practice(practice_url)
        else:
            _open_job_on_backend(job_id)
    elif practice and practice_url:
        _dispatch("OPEN_PRACTICE", {"url": practice_url})
    else:
        _dispatch("OPEN_JOB", {"job_id": job_id})
    return current_job()


def stop_queue() -> None:
    global _page
    with _lock:
        backend = _state.backend
        had_pw_session = _page is not None or _context is not None
        _state.running = False
        _state.job_ids = []
        _state.index = -1
        _state.practice = False
        _state.practice_url = None
        _state.outcomes = {}
        _state.handled = {}
        _state.scan_failures = 0
        _state.pending = None
        _state.fill_reports = {}
        _state.interrupted = False
        _state.summary = None
        _state.activity = _fresh_activity()
        _state.backend = None
    if backend == "extension":
        from . import ext_backend

        ext_backend.close_current()
    elif had_pw_session:
        _dispatch("CLOSE_PAGE")


def queue_snapshot() -> dict:
    """Everything the mission-control panel needs: queue with per-job state
    and titles, progress, current fill report, interruption flag, summary,
    reason-class outcomes, and the live watch activity (009)."""
    from .. import db

    with _lock:
        job_ids = list(_state.job_ids)
        index = _state.index
        running = _state.running
        interrupted = _state.interrupted
        summary = _state.summary
        activity = dict(_state.activity)
        outcomes = [
            {"job_id": job_id, **entry}
            for job_id, entry in _state.outcomes.items()
        ]
        current_report = []
        if 0 <= index < len(job_ids):
            current_report = list(_state.fill_reports.get(job_ids[index]) or [])

    queue = []
    for i, job_id in enumerate(job_ids):
        if job_id == PRACTICE_JOB_ID:
            title, company = "Practice application", "Job Engine"
        else:
            job = db.get_job(job_id) or {}
            title = job.get("title") or f"#{job_id}"
            company = job.get("company") or ""
        if running:
            state = "done" if i < index else ("current" if i == index else "pending")
        else:
            state = "done"
        queue.append({
            "job_id": job_id, "title": title, "company": company, "state": state,
        })
    done = index if running else len(job_ids)
    from . import ext_backend

    ext_status = ext_backend.status()
    with _lock:
        backend = _state.backend
    return {
        "queue": queue,
        "progress": {"done": done, "total": len(job_ids)},
        "fill_report": current_report,
        "interrupted": interrupted,
        "summary": summary,
        "outcomes": outcomes,
        "activity": activity,
        # 010: which fill path this run uses, and the live companion state
        # (rendered as "filling in your Chrome" vs the assistant window)
        "backend": backend,
        "extension": {
            "connected": ext_status["connected"],
            "version": ext_status["version"],
            "last_seen_age_s": ext_status["last_seen_age_s"],
        },
    }


# --- worker-side (the ONLY functions that touch Playwright) ------------------


def _worker_open_job(job_id: int) -> None:
    from .. import db
    from . import apply_urls

    job = db.get_job(job_id)
    url = apply_urls.resolve(job) if job else None
    _worker_open_url(job_id, url)


def _worker_open_practice(url: str) -> None:
    _worker_open_url(PRACTICE_JOB_ID, url)


def _worker_open_url(job_id: int, url: str | None) -> None:
    from . import worker

    worker._assert_worker_thread()
    global _page
    if not url:
        return
    _set_activity(phase="opening", url=url,
                  message="opening the application page…")
    try:
        context = _ensure_context()
        if _page is not None:
            try:
                _page.close()
            except Exception:
                pass
        _page = context.new_page()
    except Exception as exc:
        if _is_closed_error(exc):
            _mark_interrupted()
        else:
            log.warning("browser launch failed", exc_info=True)
            _mark_fallback(job_id, "launch_failed", str(exc))
            _set_activity(phase="error",
                          message="the browser couldn't start — see the reason above")
        return
    try:
        _page.goto(url, timeout=30_000)
    except Exception as exc:
        if _is_closed_error(exc):
            _mark_interrupted()
            return
        log.warning("failed to load %s", url, exc_info=True)
        _mark_fallback(job_id, "nav_failed", str(exc))
        _set_activity(phase="error",
                      message="the page failed to load — Re-scan retries it")
        return
    _tick_if_active(force=True)


def _worker_close_page() -> None:
    from . import worker

    worker._assert_worker_thread()
    global _page
    if _page is not None:
        try:
            _page.close()
        except Exception:
            pass
        _page = None


def _worker_shutdown_context() -> None:
    from . import worker

    worker._assert_worker_thread()
    global _playwright, _context, _page
    _worker_close_page()
    if _context is not None:
        try:
            _context.close()
        except Exception:
            pass
        _context = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None


def _worker_resolve_pending(payload: dict) -> None:
    _tick_if_active(force=True)


def _tick_if_active(force: bool = False) -> None:
    """One watch tick when a job is current. Called by the worker on its
    ~2s idle timeout and on FORCE_TICK."""
    from .. import db

    with _lock:
        active = (
            _state.running
            and not _state.interrupted
            and 0 <= _state.index < len(_state.job_ids)
        )
        job_id = _state.job_ids[_state.index] if active else None
    page = _page
    if not active or page is None:
        return

    with _lock:
        ledger = _state.handled.setdefault(job_id, {})
    profile = db.get_profile() or {}

    def get_value(tag, descriptor):
        before = _state.pending
        value = _value_for_tag(tag, descriptor, profile, job_id)
        if value is None and _state.pending is not None and _state.pending is not before:
            _record(job_id, descriptor, tag, "", "paused")
        return value

    def record(descriptor, tag, preview, outcome):
        _record(job_id, descriptor, tag, preview, outcome)

    try:
        result = watcher.tick(page, get_value=get_value, record=record, handled=ledger)
    except Exception as exc:
        if _is_closed_error(exc):
            _mark_interrupted()
            return
        log.warning("watch tick failed", exc_info=True)
        return

    filled_total = sum(1 for outcome in ledger.values() if outcome == "filled")
    if result.scan_error:
        with _lock:
            _state.scan_failures += 1
            failures = _state.scan_failures
        if failures >= SCAN_FAILURE_LIMIT:
            _mark_fallback(job_id, "scan_failed", result.scan_error)
    else:
        with _lock:
            _state.scan_failures = 0
        _clear_fallback(job_id, "scan_failed")

    if result.fields_seen > 0:
        phase = "watching"
        message = (
            f"watching page — {result.fields_seen} fields seen · "
            f"{filled_total} filled · you click the actual apply/submit"
        )
    else:
        phase = "waiting_for_form"
        message = (
            "no form fields visible yet — click the site's own Apply "
            "button; fields fill the moment the form appears"
        )
    _set_activity(
        phase=phase,
        fields_seen=result.fields_seen,
        fields_filled=filled_total,
        message=message,
        last_scan_at=_utcnow_iso(),
    )


def _record(job_id: int, descriptor: dict, tag: str, preview: str, outcome: str) -> None:
    label = (descriptor.get("label_text") or descriptor.get("placeholder")
             or descriptor.get("aria_label") or descriptor.get("name") or "")
    with _lock:
        _state.fill_reports.setdefault(job_id, []).append({
            "label": label[:120],
            "tag": tag,
            "value_preview": (preview or "")[:60],
            "outcome": outcome,
        })
