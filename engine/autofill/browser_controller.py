"""App-driven browser automation for Apply Assist (feature 005).

Owns the Playwright lifecycle on its own dedicated background thread — the
FastAPI request thread (web/routes_autofill.py) only calls these module-level
functions, never touches a Playwright object directly, matching engine/db.py's
existing rule that background and request threads never implicitly share one
stateful connection.

Hard safety rule (spec FR-008/FR-016, analyze finding C1): this module NEVER
clicks anything. It only ever fills values (fill/set_input_files/select_option/
check) into fields the classifier recognizes. The DOM query used to collect
fields (FIELD_QUERY_SELECTOR) does not even select buttons or submit-shaped
inputs, so there is structurally nothing button-like to act on — the human
always performs the actual submit/login/next-page click.

The queue advances only on an explicit advance() call (the "Done, next
application" control) — never automatic completion detection, per the
005 clarify session.
"""
from __future__ import annotations

import logging
import threading

from . import fields as fields_mod

log = logging.getLogger(__name__)

# Deliberately excludes <button> and input[type=submit|button|reset] — this
# module has nothing to click, so it collects nothing clickable in the
# first place (second layer of defense alongside _apply_field_value never
# calling .click()).
FIELD_QUERY_SELECTOR = (
    "input:not([type=submit]):not([type=button]):not([type=reset]),"
    " textarea, select"
)

_CORE_IDENTITY_TAGS = {"full_name", "first_name", "last_name", "email", "resume_upload"}

# 008 (FR-007): Apply Assist drives the user's INSTALLED branded browser via
# Playwright channels — nothing is downloaded, PLAYWRIGHT_BROWSERS_PATH is
# irrelevant. Edge ships inbox and is non-removable on US-market Windows 11;
# Chrome is the fallback for machines where it isn't.
_CHANNELS = ("msedge", "chrome")

# 008 (FR-009): reason classes that mean "complete this one manually" —
# each renders a DISTINCT message in the status panel, so a browser that
# never launched is no longer misreported as "this page couldn't be read".
FALLBACK_REASONS = ("launch_failed", "nav_failed", "scan_failed", "unrecognized")


class BrowserUnavailable(RuntimeError):
    """No supported installed browser (Edge/Chrome) could be launched."""


class _State:
    def __init__(self) -> None:
        self.job_ids: list[int] = []
        self.index: int = -1
        self.running: bool = False
        # job_id -> {"reason": FALLBACK_REASONS member, "detail": str}
        self.outcomes: dict[int, dict] = {}
        # At most one pending confirmation tracked at a time (FR-011): an
        # unrecognized/no-saved-answer question pauses for review rather
        # than being auto-filled from an unreviewed AI draft.
        self.pending: dict | None = None
        # 007 depth: per-job fill reports (passwords pre-masked at record
        # time — the secret never enters this structure), browser-closed
        # interruption flag, and the end-of-queue batch summary. All
        # session-scoped by design: an app restart clears them (spec
        # assumption).
        self.fill_reports: dict[int, list[dict]] = {}
        self.interrupted: bool = False
        self.summary: dict | None = None


_state = _State()
_lock = threading.Lock()

# Real Playwright objects — created lazily, never at import time, so unit
# tests never touch a real browser.
_playwright = None
_context = None
_page = None
_launched_channel: str | None = None


def _mark_fallback(job_id: int, reason: str, detail: str = "") -> None:
    with _lock:
        _state.outcomes[job_id] = {"reason": reason, "detail": detail[:300]}


def _should_fall_back(classified_tags: list[str]) -> bool:
    """FR-009: fall back to manual completion when none of the page's core
    identity fields (name, email, resume upload) were recognized."""
    return not any(tag in _CORE_IDENTITY_TAGS for tag in classified_tags)


def _apply_field_value(element, tag: str, field_type: str, value) -> None:
    """The only place values are written into the page. NEVER calls .click()
    — see module docstring and tests/test_browser_controller.py::
    TestNeverClicksAnything, which regression-tests this directly."""
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


def _profile_dir():
    """Dedicated persistent profile for Apply Assist — the launched browser
    is the user's installed Edge/Chrome BINARY, but never their personal
    browsing profile (005 clarify session; 008 FR-007)."""
    from .. import paths

    path = paths.data_dir() / "browser-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_context():
    """Lazily launches a headed session of the user's installed browser via
    Playwright channels (msedge → chrome). Raises BrowserUnavailable with
    per-channel detail when neither can start (008 FR-007/FR-009)."""
    global _playwright, _context, _launched_channel
    if _context is not None:
        return _context
    from playwright.sync_api import sync_playwright

    _playwright = sync_playwright().start()
    errors = []
    for channel in _CHANNELS:
        try:
            _context = _playwright.chromium.launch_persistent_context(
                user_data_dir=str(_profile_dir()), channel=channel, headless=False
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
    """Cheap launchability probe (FR-010): can an installed browser actually
    start? Runs before any queue; never touches an already-live session."""
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


def _job_url(job_id: int) -> str | None:
    from .. import db

    job = db.get_job(job_id)
    return job["url"] if job else None


def _serialize_fields(page) -> list[dict]:
    """Real-DOM field extraction — the only function that reaches into a
    live page; browser_controller is the sole caller of fields.classify()
    with real serialized data (fields.py itself stays pure/fixture-testable).
    007: also captures the current value (idempotency, FR-007) and select
    option texts (structured-input matching, FR-006)."""
    return page.eval_on_selector_all(
        FIELD_QUERY_SELECTOR,
        """(elements) => elements.map(el => ({
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            name: el.name || '',
            id: el.id || '',
            label_text: (el.labels && el.labels[0] ? el.labels[0].innerText : '')
                || el.getAttribute('aria-label') || '',
            placeholder: el.placeholder || '',
            aria_label: el.getAttribute('aria-label') || '',
            autocomplete: el.autocomplete || '',
            value: (el.type === 'checkbox' || el.type === 'radio')
                ? (el.checked ? 'on' : '')
                : (el.value || ''),
            options: el.tagName === 'SELECT'
                ? Array.from(el.options).map(o => o.text)
                : null,
        }))""",
    )


def _is_closed_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "targetclosed" in text or "has been closed" in text


def _mark_interrupted() -> None:
    """The dedicated browser window was closed under us (FR-008): keep the
    queue and its position, drop the dead Playwright objects, and let
    resume_queue() relaunch at the current job."""
    global _playwright, _context, _page
    with _lock:
        _state.interrupted = True
    _page = None
    _context = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None


def _open_job(job_id: int) -> None:
    """Real Playwright work for one job: open its application page, wire
    same-tab page-change rescans, and run the fill pass. Monkeypatched
    entirely in unit tests (TestQueueStateMachine and friends)."""
    global _page

    url = _job_url(job_id)
    if not url:
        return
    try:
        context = _ensure_context()
        _page = context.new_page()
    except Exception as exc:
        if _is_closed_error(exc):
            _mark_interrupted()
        else:
            log.warning("browser launch failed", exc_info=True)
            _mark_fallback(job_id, "launch_failed", str(exc))
        return
    _wire_page_change(_page, job_id)
    try:
        _page.goto(url, timeout=30_000)
    except Exception as exc:
        if _is_closed_error(exc):
            _mark_interrupted()
            return
        log.warning("failed to load %s", url, exc_info=True)
        _mark_fallback(job_id, "nav_failed", str(exc))
        return

    try:
        raw_fields = _serialize_fields(_page)
    except Exception as exc:
        log.warning("field serialization failed for %s", url, exc_info=True)
        _mark_fallback(job_id, "scan_failed", str(exc))
        return

    classified = [fields_mod.classify(f) for f in raw_fields]
    if _should_fall_back(classified):
        _mark_fallback(
            job_id, "unrecognized",
            "no core identity fields (name/email/resume) recognized on this page",
        )
        return

    _fill_page(job_id)


def _wire_page_change(page, job_id: int) -> None:
    """FR-003: when the human clicks the site's own Next/Continue and the
    same tab navigates, re-run the fill pass on the settled new page. The
    app itself never navigates — this only ever REACTS to navigation the
    user performed. Best-effort: SPA re-renders that never navigate are
    covered by the manual rescan button (POST /api/autofill/rescan)."""
    def _on_navigated(frame) -> None:
        try:
            if frame != page.main_frame:
                return
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            _fill_page(job_id)
        except Exception as exc:
            if _is_closed_error(exc):
                _mark_interrupted()
            else:
                log.debug("page-change fill pass failed", exc_info=True)

    try:
        page.on("framenavigated", _on_navigated)
    except Exception:
        log.debug("could not wire page-change listener", exc_info=True)


def _resume_file_for_job(job_id: int, profile: dict) -> str | None:
    """FR-001/FR-002: the job's tailored PDF when available and the
    preference (default on) allows it; otherwise the stored original."""
    from .. import settings

    if settings.get("AUTOFILL_USE_TAILORED_PDF") != "0":
        try:
            from .. import resume_pdf

            return str(resume_pdf.tailored_resume_path(job_id))
        except Exception:
            # no sections yet / render failure -> the original upload
            log.debug("tailored PDF unavailable — using original resume", exc_info=True)
    return profile.get("resume_file_path") or None


def _fill_page(job_id: int) -> int:
    """One idempotent fill pass over the current page (FR-005/006/007).
    Safe to run repeatedly: non-empty fields (user-typed or previously
    filled) are never overwritten. Returns the number of fields filled.
    Every action lands in the job's fill report; a filled password is
    recorded pre-masked — the secret never enters controller state."""
    from .. import db

    page = _page
    if page is None:
        return 0
    try:
        raw_fields = _serialize_fields(page)
    except Exception as exc:
        if _is_closed_error(exc):
            _mark_interrupted()
        return 0

    profile = db.get_profile() or {}
    with _lock:
        report = _state.fill_reports.setdefault(job_id, [])
    filled_count = 0

    def record(raw: dict, tag: str, value_preview: str, outcome: str) -> None:
        label = (raw.get("label_text") or raw.get("placeholder")
                 or raw.get("aria_label") or raw.get("name") or "")
        with _lock:
            report.append({
                "label": label[:120],
                "tag": tag,
                "value_preview": value_preview[:60],
                "outcome": outcome,
            })

    for raw in raw_fields:
        tag = fields_mod.classify(raw)

        # FR-007: a value already present is sacred — never overwritten,
        # never duplicated, for text inputs and file inputs alike.
        if (raw.get("value") or "").strip():
            if tag != "free_text_unknown":
                record(raw, tag, "", "skipped_existing")
            continue

        selector = f"#{raw['id']}" if raw.get("id") else f"[name='{raw.get('name')}']"

        if tag == "resume_upload":
            path = _resume_file_for_job(job_id, profile)
            if not path:
                continue
            try:
                handle = page.query_selector(selector)
                if handle is None:
                    continue
                handle.set_input_files(path)
                record(raw, tag, path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1], "filled")
                filled_count += 1
            except Exception as exc:
                if _is_closed_error(exc):
                    _mark_interrupted()
                    return filled_count
                # Spec edge case: custom widgets rejecting programmatic
                # attachment are reported, never fatal — queue continues.
                record(raw, tag, "", "needs_manual")
            continue

        pending_before = _state.pending
        value = _value_for_tag(tag, raw, profile, job_id)
        if value is None:
            if _state.pending is not None and _state.pending is not pending_before:
                record(raw, tag, "", "paused")
            continue

        try:
            handle = page.query_selector(selector)
            if handle is None:
                continue
            if raw.get("options"):
                # FR-006: structured inputs answer by option-text match —
                # below confidence the input is left untouched, never guessed.
                matched = fields_mod.match_option(str(value), raw["options"])
                if matched is None:
                    record(raw, tag, "", "no_match")
                    continue
                handle.select_option(label=matched)
                record(raw, tag, matched, "filled")
            else:
                _apply_field_value(handle, tag, raw.get("type", ""), value)
                preview = "•••" if tag == "login_password" else str(value)
                record(raw, tag, preview, "filled")
            filled_count += 1
        except Exception as exc:
            if _is_closed_error(exc):
                _mark_interrupted()
                return filled_count
            log.debug("could not fill field %s", raw, exc_info=True)
    return filled_count


def _domain_for_job(job_id: int) -> str | None:
    from urllib.parse import urlparse

    url = _job_url(job_id)
    if not url:
        return None
    return urlparse(url).netloc or None


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
        # handled directly in _fill_page (007: _resume_file_for_job — the
        # tailored-preferred file attachment path), never through here
        return None
    if tag in ("linkedin_url",):
        return profile.get("linkedin_url")
    if tag in ("portfolio_url",):
        return profile.get("portfolio_url")
    # Everything else (work_authorization, sponsorship_requirement,
    # eeo_disclosure, years_experience, salary_expectation, how_heard,
    # cover_letter, free_text_unknown) goes through the answer bank —
    # unrecognized/unconfirmed questions are surfaced for review, never
    # auto-filled from an unreviewed draft (FR-011/FR-012).
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


def start_queue(job_ids: list[int]) -> dict | None:
    with _lock:
        _state.job_ids = list(job_ids)
        _state.index = 0 if job_ids else -1
        _state.running = bool(job_ids)
        _state.outcomes = {}
        _state.pending = None
        _state.fill_reports = {}
        _state.interrupted = False
        _state.summary = None
    if job_ids:
        _open_job(job_ids[0])
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
    """Called after the user confirms/edits a drafted answer (the caller —
    web/routes_autofill.py's confirm route — has already saved it to
    answer_bank). Fills the actual paused field on the still-open live
    page, if any, and clears the pending state."""
    global _page
    with _lock:
        pending = _state.pending
        _state.pending = None
    if pending is None or _page is None:
        return
    try:
        selector = (
            f"#{pending['field_id']}" if pending.get("field_id")
            else f"[name='{pending.get('field_name')}']"
        )
        handle = _page.query_selector(selector)
        if handle is not None:
            _apply_field_value(handle, "free_text_unknown", "text", answer)
    except Exception:
        log.debug("could not fill resolved pending field", exc_info=True)


def _job_outcome(job_id: int) -> str:
    """Per-job outcome for the batch summary (FR-009). Caller holds _lock."""
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
            return None
        next_job_id = _state.job_ids[_state.index]
    _open_job(next_job_id)
    return current_job()


def rescan() -> dict | None:
    """Manual re-classify-and-fill of the current page (FR-003 fallback
    for SPA re-renders that never navigate). None when no active session."""
    with _lock:
        if not _state.running or not (0 <= _state.index < len(_state.job_ids)):
            return None
        job_id = _state.job_ids[_state.index]
    if _page is None:
        return None
    filled = _fill_page(job_id)
    return {"rescanned": True, "filled": filled}


def resume_queue() -> dict | None:
    """Relaunch the browser at the current queue position after the window
    was closed (FR-008). Same-app-session only — an app restart clears the
    queue entirely (spec assumption). None when there is nothing to resume."""
    with _lock:
        if not _state.interrupted or not _state.running:
            return None
        if not (0 <= _state.index < len(_state.job_ids)):
            return None
        _state.interrupted = False
        job_id = _state.job_ids[_state.index]
    _open_job(job_id)
    return current_job()


def queue_snapshot() -> dict:
    """Everything the mission-control panel needs (FR-026): the whole
    queue with per-job state and titles, progress, the current job's fill
    report, the interruption flag, and the end-of-queue summary."""
    from .. import db

    with _lock:
        job_ids = list(_state.job_ids)
        index = _state.index
        running = _state.running
        interrupted = _state.interrupted
        summary = _state.summary
        outcomes = [
            {"job_id": job_id, **entry}
            for job_id, entry in _state.outcomes.items()
        ]
        current_report = []
        if 0 <= index < len(job_ids):
            current_report = list(_state.fill_reports.get(job_ids[index]) or [])

    queue = []
    for i, job_id in enumerate(job_ids):
        job = db.get_job(job_id) or {}
        if running:
            state = "done" if i < index else ("current" if i == index else "pending")
        else:
            state = "done"
        queue.append({
            "job_id": job_id,
            "title": job.get("title") or f"#{job_id}",
            "company": job.get("company") or "",
            "state": state,
        })
    done = index if running else len(job_ids)
    return {
        "queue": queue,
        "progress": {"done": done, "total": len(job_ids)},
        "fill_report": current_report,
        "interrupted": interrupted,
        "summary": summary,
        "outcomes": outcomes,
    }


def chromium_selftest() -> bool:
    """Can the browser layer actually start? Used by GET /api/diagnostics/
    chromium-launch-selftest and packaging/smoke_test.py to catch a
    silently-dropped Playwright driver (the tls_client-shaped risk).
    008: channel-based — probes the user's installed Edge/Chrome."""
    result = preflight()
    if not result["ok"]:
        raise RuntimeError(result["error"])
    return True


def stop_queue() -> None:
    global _page
    with _lock:
        _state.running = False
        _state.job_ids = []
        _state.index = -1
        _state.outcomes = {}
        _state.pending = None
        _state.fill_reports = {}
        _state.interrupted = False
        _state.summary = None
    _page = None
