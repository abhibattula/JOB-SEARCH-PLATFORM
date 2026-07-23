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
        monkeypatch.setattr(bc, "_open_job", lambda job_id: opened.append(job_id))
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")

        result = bc.start_queue([j1, j2])

        assert result["job_id"] == j1
        assert opened == [j1]

    def test_advance_moves_to_next_job(self, tmp_db, monkeypatch):
        opened = []
        monkeypatch.setattr(bc, "_open_job", lambda job_id: opened.append(job_id))
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
        monkeypatch.setattr(bc, "_open_job", lambda job_id: opened.append(job_id))
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        bc.start_queue([j1, j2])

        assert bc.current_job()["job_id"] == j1  # unchanged without advance()

    def test_advance_past_last_job_returns_none_and_empties_queue(self, tmp_db, monkeypatch):
        monkeypatch.setattr(bc, "_open_job", lambda job_id: None)
        j1 = seed_job("https://x.example/1")
        bc.start_queue([j1])

        result = bc.advance()

        assert result is None
        assert bc.current_job() is None

    def test_stop_queue_clears_state(self, tmp_db, monkeypatch):
        monkeypatch.setattr(bc, "_open_job", lambda job_id: None)
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

        monkeypatch.setattr(matcher, "_chat", lambda messages: "Drafted answer")
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

        monkeypatch.setattr(matcher, "_chat", lambda messages: "First draft")
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
    def test_resolve_pending_fills_live_field_and_clears_state(self, monkeypatch):
        bc._state.pending = {"job_id": 1, "question_raw": "Q?", "category": "how_heard",
                              "drafted_answer": "draft", "field_id": "hh", "field_name": "how_heard"}
        element = FakeElement()

        class FakePage:
            def query_selector(self, selector):
                assert selector == "#hh"
                return element

        bc._page = FakePage()

        bc.resolve_pending("Confirmed answer")

        assert element.calls == [("fill", "Confirmed answer")]
        assert bc._state.pending is None
        bc._page = None

    def test_resolve_pending_is_noop_when_nothing_pending(self):
        bc._state.pending = None
        bc._page = None
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


class TestGracefulFallback:
    def test_no_core_identity_fields_triggers_fallback(self):
        classified_tags = ["how_heard", "salary_expectation", "free_text_unknown"]
        assert bc._should_fall_back(classified_tags) is True

    def test_email_alone_is_sufficient_to_avoid_fallback(self):
        assert bc._should_fall_back(["email"]) is False

    def test_resume_upload_alone_is_sufficient_to_avoid_fallback(self):
        assert bc._should_fall_back(["resume_upload"]) is False

    def test_empty_field_list_triggers_fallback(self):
        assert bc._should_fall_back([]) is True


# ---------------------------------------------------------------------------
# 007-T023: Apply Assist depth — file attachment, idempotency, fill report,
# structured inputs, page-change rescan, interruption recovery, batch summary
# ---------------------------------------------------------------------------


def descriptor(**overrides):
    base = {
        "tag": "input", "type": "text", "name": "", "id": "",
        "label_text": "", "placeholder": "", "aria_label": "",
        "autocomplete": "", "value": "", "options": None,
    }
    base.update(overrides)
    return base


class FailingFileElement(FakeElement):
    def set_input_files(self, path):
        raise RuntimeError("custom widget rejects programmatic upload")


class FakePage:
    """Serialized-fixture page: never a live DOM. Raises on click — the
    never-click invariant holds through every depth feature (FR-004/g)."""

    def __init__(self, field_list, elements):
        self._fields = field_list
        self.elements = elements

    def eval_on_selector_all(self, selector, js):
        return self._fields

    def query_selector(self, selector):
        return self.elements.get(selector)

    def click(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("browser_controller must never click the page")


def start_with_fake_page(monkeypatch, job_id, page):
    """Start a queue with _open_job stubbed, then point the module at the
    fake page so _fill_page runs the real fill pass against fixtures."""
    monkeypatch.setattr(bc, "_open_job", lambda jid: None)
    bc.start_queue([job_id])
    bc._page = page


class TestResumeAttachment:
    def _profile_with_file(self, tmp_path):
        resume = tmp_path / "resume.pdf"
        resume.write_bytes(b"%PDF-fake")
        db.save_profile(first_name="Ada", resume_file_path=str(resume))
        return str(resume)

    def test_resume_field_attaches_stored_file(self, tmp_db, tmp_path, monkeypatch):
        stored = self._profile_with_file(tmp_path)
        job_id = seed_job("https://x.example/1")
        element = FakeElement()
        page = FakePage(
            [descriptor(type="file", id="resume", label_text="Resume/CV")],
            {"#resume": element},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)

        assert ("set_input_files", stored) in element.calls

    def test_resume_field_prefers_tailored_pdf(self, tmp_db, tmp_path, monkeypatch):
        from engine import resume_pdf

        self._profile_with_file(tmp_path)
        job_id = seed_job("https://x.example/1")
        tailored = tmp_path / "tailored.pdf"
        tailored.write_bytes(b"%PDF-tailored")
        monkeypatch.setattr(resume_pdf, "tailored_resume_path", lambda jid: tailored)
        element = FakeElement()
        page = FakePage(
            [descriptor(type="file", id="resume", label_text="Resume/CV")],
            {"#resume": element},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)

        assert ("set_input_files", str(tailored)) in element.calls

    def test_tailored_toggle_off_uses_original(self, tmp_db, tmp_path, monkeypatch):
        from engine import resume_pdf, settings

        stored = self._profile_with_file(tmp_path)
        job_id = seed_job("https://x.example/1")
        settings.set("AUTOFILL_USE_TAILORED_PDF", "0")
        monkeypatch.setattr(
            resume_pdf, "tailored_resume_path",
            lambda jid: (_ for _ in ()).throw(AssertionError("must not render")),
        )
        element = FakeElement()
        page = FakePage(
            [descriptor(type="file", id="resume", label_text="Resume/CV")],
            {"#resume": element},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)

        assert ("set_input_files", stored) in element.calls

    def test_file_attach_failure_records_needs_manual(self, tmp_db, tmp_path, monkeypatch):
        """Spec edge case: a custom widget rejecting set_input_files is
        reported, never fatal — the queue continues."""
        self._profile_with_file(tmp_path)
        job_id = seed_job("https://x.example/1")
        page = FakePage(
            [descriptor(type="file", id="resume", label_text="Resume/CV")],
            {"#resume": FailingFileElement()},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)  # must not raise

        report = bc.queue_snapshot()["fill_report"]
        assert any(e["outcome"] == "needs_manual" for e in report)


class TestFillIdempotency:
    def test_nonempty_field_is_never_overwritten(self, tmp_db, monkeypatch):
        """FR-007: a value already present (user-typed or previously
        filled) is sacred — skipped and reported, never replaced."""
        db.save_profile(first_name="Ada", last_name="Lovelace", email="ada@example.com")
        job_id = seed_job("https://x.example/1")
        element = FakeElement()
        page = FakePage(
            [descriptor(type="email", id="email", label_text="Email",
                        value="user@typed.example")],
            {"#email": element},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)

        assert element.calls == []
        report = bc.queue_snapshot()["fill_report"]
        assert any(e["outcome"] == "skipped_existing" for e in report)

    def test_repeat_fill_pass_is_idempotent(self, tmp_db, monkeypatch):
        """Running the pass twice (SPA re-render) must not duplicate: the
        second pass sees the first pass's value and skips."""
        db.save_profile(email="ada@example.com")
        job_id = seed_job("https://x.example/1")

        class StatefulElement(FakeElement):
            def __init__(self):
                super().__init__()
                self.value = ""

            def fill(self, value):
                super().fill(value)
                self.value = value

        element = StatefulElement()
        field = descriptor(type="email", id="email", label_text="Email")
        page = FakePage([field], {"#email": element})
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)
        field["value"] = element.value  # what a real re-serialization would see
        bc._fill_page(job_id)

        assert element.calls.count(("fill", "ada@example.com")) == 1


class TestFillReport:
    def test_report_records_filled_fields(self, tmp_db, monkeypatch):
        db.save_profile(first_name="Ada", last_name="Lovelace", email="ada@example.com")
        job_id = seed_job("https://x.example/1")
        page = FakePage(
            [descriptor(type="email", id="email", label_text="Email")],
            {"#email": FakeElement()},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)

        report = bc.queue_snapshot()["fill_report"]
        assert any(
            e["label"] == "Email" and e["tag"] == "email"
            and e["outcome"] == "filled" and "ada@example.com" in e["value_preview"]
            for e in report
        )

    def test_password_is_masked_at_record_time(self, tmp_db, monkeypatch):
        """FR-005 clarification: the secret never enters the report —
        the mask is written when the entry is recorded, not at display."""
        from engine import credentials

        job_id = seed_job("https://jobs.example.com/apply/1")
        monkeypatch.setattr(
            credentials, "get",
            lambda domain: {"email": "me@example.com", "password": "hunter2"},
        )
        element = FakeElement()
        page = FakePage(
            [descriptor(type="password", id="pw", label_text="Password")],
            {"#pw": element},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)

        assert ("fill", "hunter2") in element.calls  # really filled
        report = bc.queue_snapshot()["fill_report"]
        password_entries = [e for e in report if e["tag"] == "login_password"]
        assert password_entries and password_entries[0]["value_preview"] == "•••"
        assert all("hunter2" not in str(e) for e in report)


class TestStructuredInputs:
    def test_select_matches_option_text(self, tmp_db, monkeypatch):
        """FR-006: a confirmed answer selects the best-matching option."""
        from engine.autofill import answer_bank

        db.save_profile(first_name="Ada", email="ada@example.com")
        answer_bank.save("Are you authorized to work in the US?", "Yes",
                         category="work_authorization")
        job_id = seed_job("https://x.example/1")
        element = FakeElement()
        page = FakePage(
            [
                descriptor(type="email", id="email", label_text="Email"),
                descriptor(tag="select", type="select-one", id="auth",
                           label_text="Are you authorized to work in the US?",
                           options=["Yes, I am authorized", "No, I am not authorized"]),
            ],
            {"#email": FakeElement(), "#auth": element},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)

        assert ("select_option", "Yes, I am authorized") in element.calls

    def test_select_without_confident_match_left_untouched(self, tmp_db, monkeypatch):
        from engine.autofill import answer_bank

        db.save_profile(email="ada@example.com")
        answer_bank.save("How did you hear about us?", "A friend told me",
                         category="how_heard")
        job_id = seed_job("https://x.example/1")
        element = FakeElement()
        page = FakePage(
            [descriptor(tag="select", type="select-one", id="heard",
                        label_text="How did you hear about us?",
                        options=["LinkedIn", "Indeed", "Company website"])],
            {"#heard": element},
        )
        start_with_fake_page(monkeypatch, job_id, page)

        bc._fill_page(job_id)

        assert element.calls == []
        report = bc.queue_snapshot()["fill_report"]
        assert any(e["outcome"] == "no_match" for e in report)


class TestPageChangeRescan:
    def test_rescan_fills_new_page_and_keeps_confirmation_gates(self, tmp_db, monkeypatch):
        """FR-003: page 2 of the same application fills on rescan, and a
        sensitive question with no confirmed answer still pauses."""
        from engine.autofill import answer_bank

        # never a real LLM call from a unit test — the draft content is
        # irrelevant here, only the pause behavior is under test
        monkeypatch.setattr(answer_bank, "suggest", lambda q, tag, profile: "drafted")
        db.save_profile(first_name="Ada", last_name="Lovelace", email="ada@example.com")
        job_id = seed_job("https://x.example/1")
        page1 = FakePage([descriptor(type="email", id="email", label_text="Email")],
                         {"#email": FakeElement()})
        start_with_fake_page(monkeypatch, job_id, page1)
        bc._fill_page(job_id)

        sponsor_element = FakeElement()
        page2 = FakePage(
            [
                descriptor(type="text", id="name", label_text="Full Name"),
                descriptor(type="text", id="sponsor",
                           label_text="Will you require sponsorship?"),
            ],
            {"#name": FakeElement(), "#sponsor": sponsor_element},
        )
        bc._page = page2

        result = bc.rescan()

        assert result["rescanned"] is True
        assert result["filled"] >= 1
        assert sponsor_element.calls == []  # paused, not auto-filled
        assert bc.current_job()["pending"] is not None

    def test_rescan_without_session_returns_none(self, tmp_db):
        assert bc.rescan() is None


class TestInterruptionRecovery:
    def test_closed_browser_marks_interrupted_and_resumes(self, tmp_db, monkeypatch):
        """FR-008: a closed browser window preserves the queue position;
        resume_queue() relaunches at the current job."""
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        opened = []
        monkeypatch.setattr(bc, "_open_job", lambda jid: opened.append(jid))
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
        monkeypatch.setattr(bc, "_open_job", lambda jid: None)
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
        bc.start_queue([j1])
        assert bc.queue_snapshot()["interrupted"] is True


class TestBatchSummary:
    def test_summary_computed_at_queue_end(self, tmp_db, monkeypatch):
        """FR-009: per-job outcomes surface as a summary when the queue
        finishes."""
        db.save_profile(email="ada@example.com")
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        monkeypatch.setattr(bc, "_open_job", lambda jid: None)
        bc.start_queue([j1, j2])
        page = FakePage([descriptor(type="email", id="email", label_text="Email")],
                        {"#email": FakeElement()})
        bc._page = page
        bc._fill_page(j1)
        bc.advance()
        with bc._lock:
            bc._state.outcomes[j2] = {"reason": "unrecognized", "detail": ""}
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
        monkeypatch.setattr(bc, "_open_job", lambda jid: None)
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
