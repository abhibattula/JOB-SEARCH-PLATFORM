"""005-T022/T022a: engine/autofill/browser_controller.py — queue state
machine and the never-auto-submit/login safety invariant. Playwright is
never touched for real in these tests; `_open_job` (the one function that
talks to a real browser) is monkeypatched to a no-op recorder so the pure
queue logic is tested in isolation, and the fill-application logic is
tested against a fake page/element that would raise if `.click()` were
ever called.
"""
import pytest

from engine import db
from engine.autofill import browser_controller as bc


def seed_job(url):
    # title derived from the url: same-source same-title rows would
    # otherwise collapse as reposts of one job (008 FR-017)
    db.upsert_job(
        {"title": f"SWE {url.rsplit('/', 1)[-1]}", "company": "TestCo", "url": url,
         "source": "greenhouse", "description": "desc"}
    )
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
    return next(j for j in jobs if j["url"] == url)["id"]


class TestQueueStateMachine:
    def test_start_queue_opens_first_job(self, tmp_db, monkeypatch):
        opened = []
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: opened.append(payload["job_id"]) if name == "OPEN_JOB" else None)
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")

        result = bc.start_queue([j1, j2])

        assert result["job_id"] == j1
        assert opened == [j1]

    def test_advance_moves_to_next_job(self, tmp_db, monkeypatch):
        opened = []
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: opened.append(payload["job_id"]) if name == "OPEN_JOB" else None)
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        bc.start_queue([j1, j2])

        result = bc.advance()

        assert result["job_id"] == j2
        assert opened == [j1, j2]

    def test_advance_is_user_driven_not_automatic(self, tmp_db, monkeypatch):
        """005 clarify session: the queue never advances on its own — only
        an explicit advance() call (the "Done, next application" button)
        moves it forward."""
        opened = []
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: opened.append(payload["job_id"]) if name == "OPEN_JOB" else None)
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        bc.start_queue([j1, j2])

        assert bc.current_job()["job_id"] == j1  # unchanged without advance()

    def test_advance_past_last_job_returns_none_and_empties_queue(self, tmp_db, monkeypatch):
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: None)
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])

        result = bc.advance()

        assert result is None
        assert bc.current_job() is None

    def test_stop_queue_clears_state(self, tmp_db, monkeypatch):
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: None)
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])

        bc.stop_queue()

        assert bc.current_job() is None

    def test_current_job_none_when_idle(self, tmp_db):
        assert bc.current_job() is None


class FakeElement:
    """Records every method call; used to prove the fill logic never
    invokes .click() on anything, for any classification."""

    def __init__(self):
        self.calls = []

    def fill(self, value):
        self.calls.append(("fill", value))

    def set_input_files(self, path):
        self.calls.append(("set_input_files", path))

    def select_option(self, value=None, label=None):
        # real Playwright selects by label= for option-text matching (007);
        # record whichever was used so assertions read naturally
        self.calls.append(("select_option", label if label is not None else value))

    def check(self):
        self.calls.append(("check",))

    def click(self):  # pragma: no cover - must never be reached
        raise AssertionError("browser_controller must never click any element")


class TestNeverClicksAnything:
    """005-T022a (analyze finding C1): the single most safety-critical
    invariant in this feature — regression-tested directly, not just true
    by construction."""

    @pytest.mark.parametrize("tag,field_type", [
        ("full_name", "text"),
        ("email", "email"),
        ("phone", "tel"),
        ("resume_upload", "file"),
        ("work_authorization", "text"),
        ("sponsorship_requirement", "text"),
        ("eeo_disclosure", "text"),
        ("login_email", "email"),
        ("login_password", "password"),
        ("free_text_unknown", "text"),
    ])
    def test_apply_field_value_never_clicks(self, tag, field_type):
        element = FakeElement()
        bc._apply_field_value(element, tag, field_type, "some value")
        assert all(call[0] != "click" for call in element.calls)

    def test_apply_field_value_never_clicks_even_with_none_value(self):
        # e.g. an unrecognized/unanswered field with nothing to fill yet
        element = FakeElement()
        bc._apply_field_value(element, "free_text_unknown", "text", None)
        assert all(call[0] != "click" for call in element.calls)

    def test_field_query_selector_excludes_buttons(self):
        """Second layer of defense: the DOM query used to serialize fields
        must not even collect <button>/submit-shaped elements in the first
        place, so there is nothing button-like to ever act on."""
        query = bc.FIELD_QUERY_SELECTOR
        # No standalone "button" tag selector (only an exclusion guard is allowed)
        selectors = [part.strip() for part in query.split(",")]
        assert "button" not in selectors
        # The exclusion guards themselves must be present
        assert ":not([type=submit])" in query
        assert ":not([type=button])" in query


class TestUnknownQuestions016:
    """016 (T005/T006, FR-003): unknown questions go to the background
    drafter — decide never blocks, never parks, and both questions on a
    form draft concurrently (no single-pending gate)."""

    @pytest.fixture(autouse=True)
    def _drafter(self):
        from engine.autofill import drafter

        drafter.reset_for_tests(backoff_base_s=0.1, backoff_cap_s=0.5)
        yield drafter
        drafter.reset_for_tests()

    def _raw(self, name="hh", label="How did you hear about us?"):
        return {"tag": "input", "type": "text", "name": name, "id": name,
                "label_text": label, "placeholder": "", "aria_label": "",
                "autocomplete": "", "options": [], "maxlength": None}

    def test_unknown_question_schedules_draft_and_returns_none(self, tmp_db):
        from engine.autofill import drafter

        drafter.set_generator_for_tests(lambda q, c, p: "Drafted answer")
        value = bc._value_for_tag("how_heard", self._raw(),
                                  {"resume_text": "..."}, job_id=1)
        assert value is None  # this pass skips; the draft lands via push
        record = drafter.get(1, "How did you hear about us?")
        assert record is not None and record["state"] in ("drafting", "done")

    def test_all_unknowns_draft_concurrently_no_single_gate(self, tmp_db):
        from engine.autofill import drafter

        drafter.set_generator_for_tests(lambda q, c, p: "ans")
        bc._value_for_tag("how_heard", self._raw("q1", "Question one?"), {}, job_id=1)
        bc._value_for_tag("how_heard", self._raw("q2", "Question two?"), {}, job_id=1)
        assert drafter.get(1, "Question one?") is not None
        assert drafter.get(1, "Question two?") is not None

    def test_existing_answer_bank_entry_wins_without_drafting(self, tmp_db):
        from engine.autofill import answer_bank, drafter

        answer_bank.save("Known question?", "Known answer", category="how_heard")
        value = bc._value_for_tag(
            "how_heard", self._raw("q", "Known question?"), {}, job_id=1)
        assert value == "Known answer"
        assert drafter.get(1, "Known question?") is None

    def test_cached_draft_served_as_flagged_draft(self, tmp_db):
        import time

        from engine.autofill import drafter, field_core

        drafter.set_generator_for_tests(lambda q, c, p: "Because I build tools.")
        bc._value_for_tag("how_heard", self._raw(), {}, job_id=1)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and \
                not drafter.answer_for(1, "How did you hear about us?"):
            time.sleep(0.01)
        value = bc._value_for_tag("how_heard", self._raw(), {}, job_id=1)
        assert value == "Because I build tools."
        assert isinstance(value, field_core.Draft)  # fills + ai_draft flag


class TestProfileFacts016:
    """016 (FR-012): work-auth/sponsorship questions answer from the
    profile — never from a model; not derivable → left for the human."""

    @pytest.fixture(autouse=True)
    def _drafter(self, monkeypatch):
        from engine.autofill import drafter

        drafter.reset_for_tests()

        def boom(*a, **k):
            raise AssertionError("profile facts must never reach a model")

        from engine import matcher, qa
        from engine.autofill import answer_bank

        monkeypatch.setattr(matcher, "_chat", boom)
        monkeypatch.setattr(qa, "draft", boom)
        monkeypatch.setattr(answer_bank, "suggest", boom)
        yield drafter
        drafter.reset_for_tests()

    def _raw(self, label):
        return {"tag": "select", "type": "", "name": "wa", "id": "wa",
                "label_text": label, "placeholder": "", "aria_label": "",
                "autocomplete": "", "options": ["Yes", "No"], "maxlength": None}

    def test_sponsorship_requirement_from_profile(self, tmp_db):
        profile = {"authorized_without_sponsorship": "yes"}
        value = bc._value_for_tag(
            "sponsorship_requirement",
            self._raw("Will you now or in the future require sponsorship?"),
            profile, job_id=1)
        assert value == "No"

    def test_sponsorship_requirement_inverse(self, tmp_db):
        profile = {"authorized_without_sponsorship": "no"}
        value = bc._value_for_tag(
            "sponsorship_requirement",
            self._raw("Will you require sponsorship?"), profile, job_id=1)
        assert value == "Yes"

    def test_work_authorization_yes_when_authorized(self, tmp_db):
        profile = {"authorized_without_sponsorship": "yes"}
        value = bc._value_for_tag(
            "work_authorization",
            self._raw("Are you legally authorized to work in the US?"),
            profile, job_id=1)
        assert value == "Yes"

    def test_unknown_fact_stays_unfilled_and_flagged(self, tmp_db):
        from engine.autofill import drafter

        value = bc._value_for_tag(
            "work_authorization",
            self._raw("Are you legally authorized to work in the US?"),
            {}, job_id=1)
        assert value is None
        record = drafter.get(1, "Are you legally authorized to work in the US?")
        assert record is not None
        assert record["state"] == "failed"
        assert record["reason"] == "profile_fact_missing"


class TestFillFirstResponsiveness016:
    """016 (T005/T006, SC-002): decide stays fast and every status surface
    answers while a slow draft generates in the background — the chronic-
    freeze regression guard, restated for the fill-first model. Also the
    push: a completed draft nudges the active backend by itself."""

    @pytest.fixture(autouse=True)
    def _drafter(self):
        from engine.autofill import drafter

        drafter.reset_for_tests(backoff_base_s=0.1, backoff_cap_s=0.5)
        yield drafter
        drafter.reset_for_tests()

    def _raw(self):
        return {"tag": "input", "type": "text", "name": "q", "id": "q",
                "label_text": "Why us?", "placeholder": "", "aria_label": "",
                "autocomplete": "", "options": [], "maxlength": None}

    def test_decide_and_status_fast_while_draft_generates(self, tmp_db):
        import threading
        import time

        from engine.autofill import drafter

        release = threading.Event()
        drafter.set_generator_for_tests(
            lambda q, c, p: (release.wait(timeout=10), "Drafted later")[1])
        bc._state.running = True
        bc._state.job_ids = [1]
        bc._state.index = 0

        start = time.monotonic()
        value = bc._value_for_tag("how_heard", self._raw(), {}, job_id=1)
        assert value is None
        assert time.monotonic() - start < 1.0  # scheduled, not generated inline

        start = time.monotonic()
        snapshot = bc.queue_snapshot()
        current = bc.current_job()
        assert time.monotonic() - start < 1.0
        assert snapshot["queue"]
        drafting = [e for e in current["activity"] if e["state"] == "drafting"]
        assert drafting and drafting[0]["question"] == "Why us?"

        release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and \
                not drafter.answer_for(1, "Why us?"):
            time.sleep(0.01)
        assert drafter.answer_for(1, "Why us?") == "Drafted later"
        current = bc.current_job()
        drafted = [e for e in current["activity"] if e["state"] == "drafted"]
        assert drafted and drafted[0]["answer_preview"].startswith("Drafted")

    def test_draft_completion_nudges_assistant_backend(self, tmp_db, monkeypatch):
        import time

        from engine.autofill import drafter

        dispatched = []
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None: dispatched.append(name))
        drafter.set_generator_for_tests(lambda q, c, p: "ans")
        bc._state.running = True
        bc._state.job_ids = [1]
        bc._state.index = 0
        bc._state.backend = "playwright"

        bc._value_for_tag("how_heard", self._raw(), {}, job_id=1)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "FORCE_TICK" not in dispatched:
            time.sleep(0.01)
        assert "FORCE_TICK" in dispatched


class TestRescanNudge016:
    """016 (FR-008): the app's Re-scan works in companion mode — it sends
    the rescan message instead of silently doing nothing."""

    def test_rescan_nudges_extension_backend(self, tmp_db):
        from engine.autofill import ext_backend

        sent: list[dict] = []
        ext_backend.register(sent.append, lambda code: None, "1.6.0")
        bc._state.running = True
        bc._state.job_ids = [1]
        bc._state.index = 0
        bc._state.backend = "extension"

        result = bc.rescan()
        assert result == {"forced": True, "nudged": True}
        assert any(m["type"] == "rescan" for m in sent)

    def test_rescan_still_ticks_playwright_backend(self, tmp_db, monkeypatch):
        dispatched = []
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None: dispatched.append(name))
        bc._state.running = True
        bc._state.job_ids = [1]
        bc._state.index = 0
        bc._state.backend = "playwright"

        result = bc.rescan()
        assert result is not None and result["forced"] is True
        assert "FORCE_TICK" in dispatched

    def test_the_park_gate_is_gone(self):
        """016 (FR-019): the blocking approval gate is removed for good —
        no pending slot, no resolve_pending API."""
        assert not hasattr(bc, "resolve_pending")
        assert not hasattr(bc._state, "pending")


class TestNameFields:
    """006-A regression: full_name/first_name/last_name were either reading
    a profile column that never existed (full_name) or not handled at all
    (first_name/last_name — they'd silently fall through to the answer-bank
    Q&A path, incorrectly pausing the queue to "confirm an answer" to your
    own name)."""

    def test_full_name_combines_first_and_last(self):
        raw = {"tag": "input", "type": "text", "name": "name", "id": "name",
               "label_text": "Full Name", "placeholder": "", "aria_label": "", "autocomplete": ""}
        value = bc._value_for_tag("full_name", raw, {"first_name": "Ada", "last_name": "Lovelace"}, job_id=1)
        assert value == "Ada Lovelace"

    def test_full_name_none_when_neither_set(self):
        raw = {"tag": "input", "type": "text", "name": "name", "id": "name",
               "label_text": "Full Name", "placeholder": "", "aria_label": "", "autocomplete": ""}
        assert bc._value_for_tag("full_name", raw, {}, job_id=1) is None

    def test_first_name_fills_directly_not_via_answer_bank(self):
        raw = {"tag": "input", "type": "text", "name": "fname", "id": "fname",
               "label_text": "First Name", "placeholder": "", "aria_label": "", "autocomplete": ""}
        bc._state.pending = None
        value = bc._value_for_tag("first_name", raw, {"first_name": "Ada"}, job_id=1)
        assert value == "Ada"
        assert bc._state.pending is None  # must not treat a name field as a Q&A question

    def test_last_name_fills_directly_not_via_answer_bank(self):
        raw = {"tag": "input", "type": "text", "name": "lname", "id": "lname",
               "label_text": "Last Name", "placeholder": "", "aria_label": "", "autocomplete": ""}
        bc._state.pending = None
        value = bc._value_for_tag("last_name", raw, {"last_name": "Lovelace"}, job_id=1)
        assert value == "Lovelace"
        assert bc._state.pending is None


class TestLoginFieldCredentials:
    """005-T041: recognized login fields fill from a saved credential,
    matched by the current job's domain — never auto-submitted (that
    invariant is covered by TestNeverClicksAnything)."""

    def test_login_email_fills_from_saved_credential(self, tmp_db, monkeypatch):
        from engine import credentials

        job_id = seed_job("https://jobs.example.com/apply/123")
        monkeypatch.setattr(
            credentials, "get",
            lambda domain: {"email": "me@example.com", "password": "hunter2"}
            if domain == "jobs.example.com" else None,
        )
        raw = {"tag": "input", "type": "email", "name": "email", "id": "email",
               "label_text": "Email", "placeholder": "", "aria_label": "", "autocomplete": ""}

        value = bc._value_for_tag("login_email", raw, {}, job_id)

        assert value == "me@example.com"

    def test_login_password_fills_from_saved_credential(self, tmp_db, monkeypatch):
        from engine import credentials

        job_id = seed_job("https://jobs.example.com/apply/123")
        monkeypatch.setattr(
            credentials, "get",
            lambda domain: {"email": "me@example.com", "password": "hunter2"}
            if domain == "jobs.example.com" else None,
        )
        raw = {"tag": "input", "type": "password", "name": "password", "id": "password",
               "label_text": "Password", "placeholder": "", "aria_label": "", "autocomplete": ""}

        value = bc._value_for_tag("login_password", raw, {}, job_id)

        assert value == "hunter2"

    def test_login_fields_return_none_without_saved_credential(self, tmp_db, monkeypatch):
        from engine import credentials

        job_id = seed_job("https://unknown.example.com/apply/1")
        monkeypatch.setattr(credentials, "get", lambda domain: None)
        raw = {"tag": "input", "type": "email", "name": "email", "id": "email",
               "label_text": "Email", "placeholder": "", "aria_label": "", "autocomplete": ""}

        assert bc._value_for_tag("login_email", raw, {}, job_id) is None


class TestInterruptionRecovery:
    def test_closed_browser_marks_interrupted_and_resumes(self, tmp_db, monkeypatch):
        """FR-008: a closed browser window preserves the queue position;
        resume_queue() relaunches at the current job."""
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        opened = []
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: opened.append(payload["job_id"]) if name == "OPEN_JOB" else None)
        bc.start_queue([j1, j2])
        bc.advance()
        assert opened == [j1, j2]

        bc._mark_interrupted()
        assert bc.queue_snapshot()["interrupted"] is True
        assert bc.current_job()["job_id"] == j2  # position preserved

        result = bc.resume_queue()

        assert result["job_id"] == j2
        assert opened == [j1, j2, j2]  # reopened current, not restarted
        assert bc.queue_snapshot()["interrupted"] is False

    def test_resume_queue_without_interruption_returns_none(self, tmp_db, monkeypatch):
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: None)
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])
        assert bc.resume_queue() is None

    def test_open_job_failure_from_closed_target_marks_interrupted(self, tmp_db, monkeypatch):
        j1 = seed_job("https://x.example/1")
        monkeypatch.setattr(
            bc, "_ensure_context",
            lambda: (_ for _ in ()).throw(
                RuntimeError("Target page, context or browser has been closed")
            ),
        )
        # dispatch executes inline so the real worker-side open runs here
        from engine.autofill import worker

        monkeypatch.setattr(worker, "_assert_worker_thread", lambda: None)
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None:
                bc._worker_open_job(payload["job_id"]) if name == "OPEN_JOB" else None,
        )
        bc.start_queue([j1])
        assert bc.queue_snapshot()["interrupted"] is True


class TestBatchSummary:
    def test_summary_computed_at_queue_end(self, tmp_db, monkeypatch):
        """FR-009: per-job outcomes surface as a summary when the queue
        finishes."""
        db.save_profile(email="ada@example.com")
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: None)
        bc.start_queue([j1, j2])
        with bc._lock:  # the watcher recorded one filled field on j1
            bc._state.fill_reports[j1] = [
                {"label": "Email", "tag": "email",
                 "value_preview": "ada@example.com", "outcome": "filled"},
            ]
        bc.advance()
        with bc._lock:  # j2's browser never launched
            bc._state.outcomes[j2] = {"reason": "launch_failed", "detail": "no browser"}
        bc.advance()  # past the end -> queue finishes

        summary = bc.queue_snapshot()["summary"]
        assert summary is not None
        assert summary["filled"] == 1
        assert summary["manual"] == 1
        outcomes = {e["job_id"]: e["outcome"] for e in summary["per_job"]}
        assert outcomes[j1] == "filled"
        assert outcomes[j2] == "manual"


class TestQueueSnapshot:
    def test_snapshot_lists_queue_with_titles_and_progress(self, tmp_db, monkeypatch):
        """FR-026: the mission-control panel needs the whole queue with
        per-job state and the current job's title+company — not raw ids."""
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: None)
        bc.start_queue([j1, j2])
        bc.advance()

        snapshot = bc.queue_snapshot()

        states = {entry["job_id"]: entry["state"] for entry in snapshot["queue"]}
        assert states[j1] == "done"
        assert states[j2] == "current"
        assert snapshot["progress"] == {"done": 1, "total": 2}
        current_entry = next(e for e in snapshot["queue"] if e["state"] == "current")
        assert current_entry["title"] == "SWE 2"  # j2 is current after advance()
        assert current_entry["company"] == "TestCo"


class TestResumeFileSelection:
    """Ported from 007's TestResumeAttachment: the FILE CHOICE logic —
    tailored-PDF preference, toggle, fallback — lives in
    _resume_file_for_job; the attach mechanics live in test_watcher.py."""

    def test_tailored_pdf_preferred_when_available(self, tmp_db, monkeypatch):
        from engine import resume_pdf

        monkeypatch.setattr(
            resume_pdf, "tailored_resume_path", lambda job_id: "C:/t/tailored-7.pdf"
        )
        path = bc._resume_file_for_job(7, {"resume_file_path": "C:/r/original.pdf"})
        assert path == "C:/t/tailored-7.pdf"

    def test_toggle_off_uses_original_upload(self, tmp_db, monkeypatch):
        from engine import db as edb

        edb.set_setting("AUTOFILL_USE_TAILORED_PDF", "0")
        path = bc._resume_file_for_job(7, {"resume_file_path": "C:/r/original.pdf"})
        assert path == "C:/r/original.pdf"

    def test_tailored_failure_falls_back_to_original(self, tmp_db, monkeypatch):
        from engine import resume_pdf

        def boom(job_id):
            raise ValueError("no sections yet")

        monkeypatch.setattr(resume_pdf, "tailored_resume_path", boom)
        path = bc._resume_file_for_job(7, {"resume_file_path": "C:/r/original.pdf"})
        assert path == "C:/r/original.pdf"

    def test_no_resume_at_all_returns_none(self, tmp_db, monkeypatch):
        from engine import resume_pdf

        def boom(job_id):
            raise ValueError("no sections")

        monkeypatch.setattr(resume_pdf, "tailored_resume_path", boom)
        assert bc._resume_file_for_job(7, {}) is None


class TestFacade009:
    """009: the facade's new surface — activity, forced rescan, practice."""

    def test_queue_snapshot_exposes_activity(self, tmp_db, monkeypatch):
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: None)
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])
        activity = bc.queue_snapshot()["activity"]
        assert activity["phase"] == "opening"
        assert set(activity) >= {"phase", "fields_seen", "fields_filled",
                                 "message", "last_scan_at", "url"}

    def test_rescan_forces_a_tick(self, tmp_db, monkeypatch):
        dispatched = []
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None: dispatched.append(name),
        )
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])
        assert bc.rescan() == {"forced": True, "nudged": True}
        assert "FORCE_TICK" in dispatched

    def test_rescan_without_session_returns_none(self, tmp_db):
        assert bc.rescan() is None

    def test_start_practice_queues_the_practice_page(self, tmp_db, monkeypatch):
        dispatched = []
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None: dispatched.append((name, payload)),
        )
        result = bc.start_practice("http://127.0.0.1:8000/practice/apply")
        assert result is not None
        assert ("OPEN_PRACTICE", {"url": "http://127.0.0.1:8000/practice/apply"}) in dispatched
        snapshot = bc.queue_snapshot()
        assert snapshot["queue"][0]["title"] == "Practice application"
        assert bc.current_job()["job_id"] == bc.PRACTICE_JOB_ID

    def test_start_practice_refused_while_queue_active(self, tmp_db, monkeypatch):
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: None)
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])
        assert bc.start_practice("http://x/practice") is None

    def test_stop_queue_without_session_never_dispatches(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None: (_ for _ in ()).throw(
                AssertionError("idle stop_queue must not touch the worker")
            ),
        )
        bc.stop_queue()  # conftest calls this around every test — must be free


class TestFacade010Backend:
    """010: start_queue picks extension vs Playwright; status reports it."""

    def _live_extension(self, monkeypatch):
        from engine.autofill import ext_backend
        opened = []
        monkeypatch.setattr(ext_backend, "is_live", lambda max_age_s=10.0: True)
        monkeypatch.setattr(ext_backend, "open_job",
                            lambda job_id, url: opened.append(("open_job", job_id)))
        monkeypatch.setattr(ext_backend, "close_current",
                            lambda: opened.append(("close", None)))
        monkeypatch.setattr(ext_backend, "status",
                            lambda: {"connected": True, "version": "1.0.0",
                                     "last_seen_age_s": 1.0})
        return opened

    def test_extension_backend_chosen_when_live(self, tmp_db, monkeypatch):
        opened = self._live_extension(monkeypatch)
        # the Playwright dispatch must NOT be used for opening
        monkeypatch.setattr(bc, "_dispatch",
                            lambda name, payload=None, wait=None:
                            opened.append(("dispatch", name)))
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])
        assert ("open_job", j1) in opened
        assert not any(o[0] == "dispatch" and o[1] == "OPEN_JOB" for o in opened)
        assert bc.queue_snapshot()["backend"] == "extension"

    def test_playwright_backend_when_extension_absent(self, tmp_db, monkeypatch):
        from engine.autofill import ext_backend
        monkeypatch.setattr(ext_backend, "is_live", lambda max_age_s=10.0: False)
        dispatched = []
        monkeypatch.setattr(bc, "_dispatch",
                            lambda name, payload=None, wait=None:
                            dispatched.append(name))
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])
        assert "OPEN_JOB" in dispatched
        assert bc.queue_snapshot()["backend"] == "playwright"

    def test_backend_sticky_across_advance(self, tmp_db, monkeypatch):
        opened = self._live_extension(monkeypatch)
        monkeypatch.setattr(bc, "_dispatch", lambda *a, **k: None)
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        bc.start_queue([j1, j2])
        # even if the socket dropped mid-queue, advance stays on extension
        from engine.autofill import ext_backend
        monkeypatch.setattr(ext_backend, "is_live", lambda max_age_s=10.0: False)
        bc.advance()
        assert ("open_job", j2) in opened

    def test_forced_override_to_playwright(self, tmp_db, monkeypatch):
        self._live_extension(monkeypatch)
        monkeypatch.setenv("AUTOFILL_BACKEND", "playwright")
        dispatched = []
        monkeypatch.setattr(bc, "_dispatch",
                            lambda name, payload=None, wait=None:
                            dispatched.append(name))
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])
        assert "OPEN_JOB" in dispatched
        assert bc.queue_snapshot()["backend"] == "playwright"

    def test_status_reports_extension_block(self, tmp_db, monkeypatch):
        self._live_extension(monkeypatch)
        snap = bc.queue_snapshot()
        assert snap["extension"]["connected"] is True
        assert snap["extension"]["version"] == "1.0.0"


class TestBrowserRouting013:
    """013: the assistant window opens the OS DEFAULT browser first (fixing the
    Edge-first bug), and the companion is still preferred when connected."""

    def test_channel_order_comes_from_default_browser(self, monkeypatch):
        # 015 (D3): the order now flows through effective_channel_order —
        # preference first, then the detected default (the injected reader
        # keeps this deterministic on any machine).
        from engine.autofill import default_browser
        monkeypatch.setattr(default_browser, "effective_channel_order",
                            lambda read_progid=None: ("chrome", "msedge"))
        assert bc._channel_order() == ("chrome", "msedge")

    def test_ensure_context_tries_default_browser_first(self, monkeypatch):
        monkeypatch.setattr(bc, "_context", None, raising=False)
        monkeypatch.setattr(bc, "_channel_order", lambda: ("chrome", "msedge"))
        tried = []

        class FakeChromium:
            def launch_persistent_context(self, **kw):
                tried.append(kw["channel"])
                raise RuntimeError("no browser")

        class FakePW:
            chromium = FakeChromium()

            def stop(self):
                pass

        class FakeSync:
            def start(self):
                return FakePW()

        import playwright.sync_api as psa
        monkeypatch.setattr(psa, "sync_playwright", lambda: FakeSync())
        with pytest.raises(bc.BrowserUnavailable):
            bc._ensure_context()
        assert tried == ["chrome", "msedge"], "default browser must be tried first"

    def test_choose_backend_prefers_live_companion(self, monkeypatch):
        from engine.autofill import ext_backend
        monkeypatch.delenv("AUTOFILL_BACKEND", raising=False)
        seen = {}

        def fake_is_live(max_age_s=10.0):
            seen["age"] = max_age_s
            return True

        monkeypatch.setattr(ext_backend, "is_live", fake_is_live)
        assert bc._choose_backend() == "extension"
        # a brief heartbeat gap should still keep the companion (widened window)
        assert seen["age"] >= 30

    def test_choose_backend_falls_back_when_no_companion(self, monkeypatch):
        from engine.autofill import ext_backend
        monkeypatch.delenv("AUTOFILL_BACKEND", raising=False)
        monkeypatch.setattr(ext_backend, "is_live", lambda max_age_s=10.0: False)
        assert bc._choose_backend() == "playwright"


class TestSnapshotBrowser015:
    def test_queue_snapshot_extension_includes_browser(self, tmp_db):
        """015 (T014): the snapshot carries the companion's browser so the
        path banner can say 'your Chrome', not just 'your browser'."""
        from engine.autofill import ext_backend

        ext_backend.register(lambda m: None, lambda code: None, "1.5.0",
                             browser="chrome")
        snapshot = bc.queue_snapshot()
        assert snapshot["extension"]["browser"] == "chrome"
        ext_backend.reset_for_tests()
