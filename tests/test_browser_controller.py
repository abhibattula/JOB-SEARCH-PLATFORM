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


class TestPendingConfirmation:
    """005-T035: unrecognized/no-saved-answer Q&A fields draft a suggestion
    and pause for review (FR-011) rather than being auto-filled."""

    def test_unanswered_question_sets_pending_and_returns_no_value(self, tmp_db, monkeypatch):
        from engine import matcher

        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: "Drafted answer")
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        bc._state.pending = None

        raw = {"tag": "input", "type": "text", "name": "how_heard", "id": "hh",
               "label_text": "How did you hear about us?", "placeholder": "",
               "aria_label": "", "autocomplete": ""}
        value = bc._value_for_tag("how_heard", raw, {"resume_text": "..."}, job_id=1)

        assert value is None  # never auto-filled from an unreviewed draft
        assert bc._state.pending is not None
        assert bc._state.pending["question_raw"] == "How did you hear about us?"
        assert bc._state.pending["drafted_answer"] == "Drafted answer"

    def test_only_one_pending_confirmation_tracked_at_a_time(self, tmp_db, monkeypatch):
        from engine import matcher

        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: "First draft")
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        bc._state.pending = None

        raw1 = {"tag": "input", "type": "text", "name": "q1", "id": "q1",
                "label_text": "Question one?", "placeholder": "", "aria_label": "", "autocomplete": ""}
        raw2 = {"tag": "input", "type": "text", "name": "q2", "id": "q2",
                "label_text": "Question two?", "placeholder": "", "aria_label": "", "autocomplete": ""}
        bc._value_for_tag("how_heard", raw1, {}, job_id=1)
        bc._value_for_tag("how_heard", raw2, {}, job_id=1)

        assert bc._state.pending["question_raw"] == "Question one?"

    def test_existing_answer_bank_entry_does_not_set_pending(self, tmp_db, monkeypatch):
        from engine.autofill import answer_bank

        answer_bank.save("Known question?", "Known answer", category="how_heard")
        bc._state.pending = None
        raw = {"tag": "input", "type": "text", "name": "q", "id": "q",
               "label_text": "Known question?", "placeholder": "", "aria_label": "", "autocomplete": ""}

        value = bc._value_for_tag("how_heard", raw, {}, job_id=1)

        assert value == "Known answer"
        assert bc._state.pending is None


class TestResolvePending:
    def test_resolve_pending_clears_state_and_forces_a_fill_pass(self, monkeypatch):
        """009: the confirmed answer is already in the answer bank (the
        route saved it) — resolving simply clears the pending slot, unlocks
        any no_match verdicts, and forces a tick so the normal fill pass
        writes it. No element bookkeeping, no cross-thread fill."""
        dispatched = []
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None: dispatched.append(name),
        )
        bc._state.running = True
        bc._state.job_ids = [1]
        bc._state.index = 0
        bc._state.pending = {"job_id": 1, "question_raw": "Q?", "category": "how_heard",
                             "drafted_answer": "draft", "field_id": "hh",
                             "field_name": "how_heard"}
        bc._state.handled[1] = {("doc1", "3"): "no_match", ("doc1", "1"): "filled"}

        bc.resolve_pending("Confirmed answer")

        assert bc._state.pending is None
        assert "FORCE_TICK" in dispatched
        # no_match unlocked so the newly-confirmed answer can fill it;
        # filled entries stay settled
        assert bc._state.handled[1] == {("doc1", "1"): "filled"}

    def test_resolve_pending_is_noop_when_nothing_pending(self, monkeypatch):
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None: (_ for _ in ()).throw(
                AssertionError("must not dispatch with nothing pending")
            ),
        )
        bc._state.pending = None
        bc.resolve_pending("anything")  # must not raise
        assert bc._state.pending is None


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
        assert bc.rescan() == {"forced": True}
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
