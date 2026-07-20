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
    db.upsert_job(
        {"title": "SWE", "company": "TestCo", "url": url,
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

    def select_option(self, value):
        self.calls.append(("select_option", value))

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
