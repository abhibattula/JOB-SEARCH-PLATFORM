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


class _State:
    def __init__(self) -> None:
        self.job_ids: list[int] = []
        self.index: int = -1
        self.running: bool = False
        self.fell_back: set[int] = set()
        # At most one pending confirmation tracked at a time (FR-011): an
        # unrecognized/no-saved-answer question pauses for review rather
        # than being auto-filled from an unreviewed AI draft.
        self.pending: dict | None = None


_state = _State()
_lock = threading.Lock()

# Real Playwright objects — created lazily, never at import time, so unit
# tests never touch a real browser.
_playwright = None
_context = None
_page = None


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


def _browsers_path():
    from .. import paths

    return paths.data_dir() / "browsers"


def _profile_dir():
    path = _browsers_path() / "apply-assist-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_context():
    """Lazily launches a dedicated, isolated headed Chromium profile —
    never the user's regular default browser (005 clarify session)."""
    global _playwright, _context
    if _context is not None:
        return _context
    import os

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_path())
    from playwright.sync_api import sync_playwright

    _playwright = sync_playwright().start()
    _context = _playwright.chromium.launch_persistent_context(
        user_data_dir=str(_profile_dir()), headless=False
    )
    return _context


def _job_url(job_id: int) -> str | None:
    from .. import db

    job = db.get_job(job_id)
    return job["url"] if job else None


def _serialize_fields(page) -> list[dict]:
    """Real-DOM field extraction — the only function that reaches into a
    live page; browser_controller is the sole caller of fields.classify()
    with real serialized data (fields.py itself stays pure/fixture-testable)."""
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
        }))""",
    )


def _open_job(job_id: int) -> None:
    """Real Playwright work for one job: open its application page and fill
    recognized fields. Monkeypatched entirely in unit tests
    (tests/test_browser_controller.py's TestQueueStateMachine)."""
    global _page

    url = _job_url(job_id)
    if not url:
        return
    context = _ensure_context()
    _page = context.new_page()
    try:
        _page.goto(url, timeout=30_000)
    except Exception:
        log.warning("failed to load %s — falling back to manual", url, exc_info=True)
        with _lock:
            _state.fell_back.add(job_id)
        return

    try:
        raw_fields = _serialize_fields(_page)
    except Exception:
        log.warning("field serialization failed for %s — falling back to manual", url, exc_info=True)
        with _lock:
            _state.fell_back.add(job_id)
        return

    classified = [fields_mod.classify(f) for f in raw_fields]
    if _should_fall_back(classified):
        with _lock:
            _state.fell_back.add(job_id)
        return

    from .. import db

    profile = db.get_profile() or {}
    for raw, tag in zip(raw_fields, classified):
        value = _value_for_tag(tag, raw, profile, job_id)
        if value is None:
            continue
        try:
            handle = _page.query_selector(
                f"#{raw['id']}" if raw.get("id") else f"[name='{raw.get('name')}']"
            )
            if handle is not None:
                _apply_field_value(handle, tag, raw.get("type", ""), value)
        except Exception:
            log.debug("could not fill field %s", raw, exc_info=True)


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
    if tag in ("full_name",):
        return profile.get("full_name")
    if tag == "email":
        return profile.get("email")
    if tag == "phone":
        return profile.get("phone")
    if tag == "resume_upload":
        return None  # file path wiring lands with the Profile-driven resume path
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
        _state.fell_back = set()
        _state.pending = None
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
        return {
            "job_id": job_id,
            "remaining": remaining,
            "fell_back": job_id in _state.fell_back,
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
            return None
        next_job_id = _state.job_ids[_state.index]
    _open_job(next_job_id)
    return current_job()


def chromium_selftest() -> bool:
    """Launches a real headed Chromium instance and navigates to about:blank
    — used by GET /api/diagnostics/chromium-launch-selftest and
    packaging/smoke_test.py to catch a silently-dropped Playwright driver
    (the same tls_client-shaped risk as the local LLM's native lib)."""
    import os

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_path())
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto("about:blank")
        finally:
            browser.close()
    return True


def stop_queue() -> None:
    global _page
    with _lock:
        _state.running = False
        _state.job_ids = []
        _state.index = -1
        _state.fell_back = set()
        _state.pending = None
    _page = None
