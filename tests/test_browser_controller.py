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


@pytest.fixture(autouse=True)
def _reset_state():
    bc.stop_queue()
    yield
    bc.stop_queue()


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
