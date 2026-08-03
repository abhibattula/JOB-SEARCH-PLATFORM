"""021 US4 — the app learns the answers the applicant types themselves.

Requested directly: "IF I FILL IT ON JOB APPLICATION IT SHOULD COLLECT THE
ANSWERS AND SAVE IT FOR MODEL TRAINING OR PROFILE FOR REFERENCE."

There was no capture path at all. Writes into `answer_bank` came only from
the panel's own input, the app's Apply Assist page, and the drafter. When the
applicant filled a field by hand, the next scan saw a non-empty value,
`field_core.decide` returned `settle`/`skipped_existing`, and the value was
dropped on the floor.

This module is a NEW PLACE PRIVATE DATA COULD LAND, so every refusal test
here is paired with a substance test. A refusal assertion on its own passes
happily against a function that stores nothing at all — and this project has
shipped that mistake before.
"""
from __future__ import annotations

import logging

import pytest

from engine import db
from engine.autofill import answer_bank


def stored(question: str):
    return answer_bank.lookup(question)


class TestItRefusesAnythingPrivate:
    """FR-017 / contracts/observed_answer.md. Refusal happens BEFORE the
    value is copied anywhere, including before any log statement."""

    @pytest.mark.parametrize("tag", [
        "login_password", "login_email", "login_username", "signup_password",
    ])
    def test_a_credential_is_never_recorded(self, tmp_db, tag):
        answer_bank.record_observed(
            question="Password", answer="Zq7-canary-PASSWORD", tag=tag)
        assert stored("Password") is None

    @pytest.mark.parametrize("tag", [
        "selfid_gender", "selfid_race", "selfid_veteran", "selfid_disability",
        "selfid_orientation", "eeo_disclosure", "demographics",
    ])
    def test_self_identification_is_never_recorded(self, tmp_db, tag):
        answer_bank.record_observed(
            question="Race / Ethnicity", answer="Asian", tag=tag)
        assert stored("Race / Ethnicity") is None

    @pytest.mark.parametrize("question", [
        "Social Security Number",
        "SSN",
        "National Insurance number",
        "Date of birth",
        "DOB",
        "Passport number",
        "Driver's licence number",
        "Bank account number",
        "Routing number",
        "Sort code",
        "Credit card number",
        "Government ID number",
        "Aadhaar number",
    ])
    def test_a_private_question_is_never_recorded_whatever_its_tag(
            self, tmp_db, question):
        """Matched by QUESTION TEXT as well as by tag. A field the classifier
        failed to tag is exactly the one most likely to be dangerous."""
        answer_bank.record_observed(question=question, answer="123-45-6789",
                                    tag="free_text_unknown")
        assert stored(question) is None

    def test_a_refused_answer_is_not_logged(self, tmp_db, caplog):
        caplog.set_level(logging.DEBUG)
        answer_bank.record_observed(question="SSN", answer="123-45-6789",
                                    tag="free_text_unknown")
        assert "123-45-6789" not in caplog.text

    def test_a_secret_flagged_field_is_refused_regardless(self, tmp_db):
        answer_bank.record_observed(question="Anything", answer="hunter2",
                                    tag="free_text_unknown", secret=True)
        assert stored("Anything") is None

    def test_an_empty_answer_is_not_recorded(self, tmp_db):
        answer_bank.record_observed(question="Why us?", answer="   ",
                                    tag="free_text_unknown")
        assert stored("Why us?") is None

    def test_an_empty_question_is_not_recorded(self, tmp_db):
        answer_bank.record_observed(question="  ", answer="something",
                                    tag="free_text_unknown")
        assert answer_bank.list_all() == []


class TestItActuallyRecordsOrdinaryAnswers:
    """The other half. Without these, every test above passes against a
    function whose body is `return`."""

    def test_an_ordinary_question_is_stored(self, tmp_db):
        answer_bank.record_observed(
            question="Why do you want to work here?",
            answer="I care about verification tooling.",
            tag="free_text_unknown")
        row = stored("Why do you want to work here?")
        assert row is not None
        assert row["answer"] == "I care about verification tooling."

    def test_it_is_marked_as_observed_not_as_confirmed(self, tmp_db):
        """FR-016: provenance is what lets the applicant tell what the app
        read off a page from what they actually told it."""
        answer_bank.record_observed(question="Notice period",
                                    answer="2 weeks", tag="notice_period")
        assert stored("Notice period")["source"] == "observed"

    def test_it_is_offered_for_the_same_question_later(self, tmp_db):
        """FR-015's whole point: each question is answered once, ever."""
        answer_bank.record_observed(question="Preferred pronouns for the team",
                                    answer="they/them",
                                    tag="free_text_unknown")
        assert answer_bank.lookup(
            "  preferred PRONOUNS for the team ")["answer"] == "they/them"

    def test_the_source_application_is_remembered(self, tmp_db):
        db.upsert_job({"title": "RTL", "company": "Intel",
                       "url": "https://x/1", "source": "workday",
                       "description": "d", "posted_date": None})
        with db._conn() as conn:
            job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
        answer_bank.record_observed(question="Why us?", answer="Because.",
                                    tag="free_text_unknown", job_id=job_id)
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT job_id, question_raw FROM application_answers"
            ).fetchall()
        assert [(r["job_id"], r["question_raw"]) for r in rows] == \
            [(job_id, "Why us?")]


class TestItNeverOverwritesWhatTheApplicantTold:
    """FR-019 / analysis A1. `save_with_provenance` upserts with an
    UNCONDITIONAL `ON CONFLICT ... DO UPDATE SET`, so delegating to it would
    have silently destroyed confirmed answers. `record_observed` writes
    through a guarded upsert instead."""

    QUESTION = "Why do you want to work here?"

    def test_a_confirmed_answer_survives(self, tmp_db):
        answer_bank.save(self.QUESTION, "The answer I wrote myself.")
        answer_bank.record_observed(question=self.QUESTION,
                                    answer="Something read off a page",
                                    tag="free_text_unknown")
        row = stored(self.QUESTION)
        assert row["answer"] == "The answer I wrote myself."
        assert row["source"] == "user"

    def test_an_auto_saved_draft_survives(self, tmp_db):
        answer_bank.save_with_provenance(self.QUESTION, "Accepted draft.",
                                         "auto_saved")
        answer_bank.record_observed(question=self.QUESTION, answer="Other",
                                    tag="free_text_unknown")
        assert stored(self.QUESTION)["answer"] == "Accepted draft."

    def test_an_earlier_observed_answer_IS_refreshed(self, tmp_db):
        """The applicant changed their mind on a later application; the
        newer answer is the one they meant."""
        answer_bank.record_observed(question=self.QUESTION, answer="First",
                                    tag="free_text_unknown")
        answer_bank.record_observed(question=self.QUESTION, answer="Second",
                                    tag="free_text_unknown")
        assert stored(self.QUESTION)["answer"] == "Second"

    def test_a_generated_answer_is_replaced_by_a_real_one(self, tmp_db):
        """A real answer beats one the model invented."""
        answer_bank.save_with_provenance(self.QUESTION, "Model prose.",
                                         "model")
        answer_bank.record_observed(question=self.QUESTION,
                                    answer="What I actually typed",
                                    tag="free_text_unknown")
        row = stored(self.QUESTION)
        assert row["answer"] == "What I actually typed"
        assert row["source"] == "observed"


class TestForgettingEverythingLearned:
    """FR-018: nothing is trapped."""

    def test_it_removes_observed_rows_only(self, tmp_db):
        answer_bank.save("Mine", "typed by me")
        answer_bank.save_with_provenance("Accepted", "draft", "auto_saved")
        answer_bank.record_observed(question="Learned", answer="read",
                                    tag="free_text_unknown")

        removed = answer_bank.forget_observed()

        assert removed == 1
        assert stored("Mine") is not None
        assert stored("Accepted") is not None
        assert stored("Learned") is None

    def test_forgetting_nothing_is_not_an_error(self, tmp_db):
        assert answer_bank.forget_observed() == 0


class TestTheCapturePredicate:
    """FR-015 / contracts/observed_answer.md, through the real decision loop.

    The rule that separates "the applicant answered this" from "the employer
    prefilled it": the field must have been seen EMPTY on an earlier scan of
    the same document, and the app must not have filled it. A value present
    on first sight is the employer's own data or the browser's password
    manager — not an answer to learn.
    """

    @pytest.fixture()
    def session(self, tmp_db, monkeypatch):
        from engine.autofill import browser_controller as bc
        from engine.autofill import ext_backend, ext_protocol
        from engine import matcher

        messages: list[dict] = []
        ext_backend.register(messages.append, lambda code: None, "1.0.0")
        monkeypatch.setattr(bc, "_dispatch", lambda *a, **k: None)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        db.save_profile(first_name="Abhinav", email="a@example.com")
        db.upsert_job({"title": "RTL", "company": "Intel",
                       "url": "https://intel.wd1.myworkdayjobs.com/j/1",
                       "source": "workday", "description": "d",
                       "posted_date": None})
        with db._conn() as conn:
            job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
        bc.start_queue([job_id])
        with bc._lock:
            bc._state.backend = "extension"
        ext_backend.open_job(job_id, "https://intel.wd1.myworkdayjobs.com/j/1")
        req_id = next(m["req_id"] for m in reversed(messages)
                      if m["type"] == "open_tab")
        ext_backend.handle_message(
            ext_protocol.TabOpened(req_id=req_id, tab_id=40))
        yield {"job_id": job_id, "sent": messages}
        ext_backend.reset_for_tests()

    def scan(self, value="", **kw):
        from engine.autofill import ext_backend, ext_protocol

        base = {"je_idx": "1", "doc": "docA", "tag": "textarea",
                "type": "", "name": "why", "id": "why",
                "label_text": "Why do you want to work here?",
                "value": value, "visible": True}
        base.update(kw)
        ext_backend.handle_message(ext_protocol.Fields(
            tab_id=40, frame_id=0, doc=base["doc"],
            url="https://intel.wd1.myworkdayjobs.com/j/1",
            descriptors=[ext_protocol.Descriptor(**base)]))

    def test_empty_then_filled_by_hand_is_learned(self, session):
        self.scan(value="")
        self.scan(value="Because I like verification.")
        assert stored("Why do you want to work here?")["answer"] == \
            "Because I like verification."

    def test_a_value_present_on_first_sight_is_NOT_learned(self, session):
        """The employer's own prefill, or the browser's password manager."""
        self.scan(value="Something that was already there")
        assert stored("Why do you want to work here?") is None

    def test_an_unclassified_free_text_field_is_learned(self, session):
        """analysis A6 — the one that would have been missed.

        `field_core.decide` returns a plain `skip` (NOT `settle`) when
        tag == "free_text_unknown", so a predicate keyed only on the settle
        path would drop every essay answer — the class the applicant most
        wants learned.
        """
        self.scan(value="", label_text="Describe a project you are proud of")
        self.scan(value="I built a RISC-V testbench.",
                  label_text="Describe a project you are proud of")
        assert stored("Describe a project you are proud of")["answer"] == \
            "I built a RISC-V testbench."

    def test_a_classified_field_is_also_learned(self, session):
        """The paired half: the settle path must work too."""
        self.scan(value="", label_text="Notice period", name="notice",
                  id="notice")
        self.scan(value="2 weeks", label_text="Notice period", name="notice",
                  id="notice")
        assert stored("Notice period")["answer"] == "2 weeks"

    def test_a_placeholder_choice_is_not_an_answer(self, session):
        """"Select…" DISPLAYS text but the applicant has chosen nothing —
        the 019 trap, which would otherwise be learned as a real answer."""
        self.scan(value="", tag="select", widget="native_select",
                  label_text="Country/Region")
        self.scan(value="Select…", tag="select", widget="native_select",
                  label_text="Country/Region")
        assert stored("Country/Region") is None

    def test_a_password_typed_by_hand_is_never_learned(self, session):
        self.scan(value="", type="password", name="password", id="password",
                  label_text="Password")
        self.scan(value="Zq7-canary-PASSWORD", type="password",
                  name="password", id="password", label_text="Password")
        assert stored("Password") is None
        assert all("Zq7-canary" not in str(row)
                   for row in answer_bank.list_all())


class TestTheLearnedAnswersPage:
    """FR-018/FR-020: nothing is trapped, and nothing reaches the profile
    without a click."""

    @pytest.fixture()
    def client(self, tmp_db, monkeypatch):
        from fastapi.testclient import TestClient

        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setenv("REFRESH_SYNC", "1")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        from web.main import create_app

        return TestClient(create_app())

    def test_the_page_renders(self, client):
        html = client.get("/learned-answers").text
        assert "Learned answers" in html
        assert "Forget everything learned" in html

    def test_the_page_says_what_is_never_kept(self, client):
        """The applicant has to be able to read the deny-list, not trust it."""
        html = client.get("/learned-answers").text
        for phrase in ("passwords and logins", "self-identification",
                       "date of birth", "government ID"):
            assert phrase in html, phrase

    def test_only_observed_answers_are_listed(self, client):
        answer_bank.save("Typed in the app", "mine")
        answer_bank.record_observed(question="Read off a page", answer="learned",
                                    tag="free_text_unknown")
        questions = [e["question"] for e in
                     client.get("/api/autofill/answers/observed").json()["entries"]]
        assert questions == ["Read off a page"]

    def test_a_profile_mappable_answer_is_flagged_for_promotion(self, client):
        answer_bank.record_observed(question="Notice period", answer="2 weeks",
                                    tag="notice_period")
        entry = client.get(
            "/api/autofill/answers/observed").json()["entries"][0]
        assert entry["profile_fact"] is True

    def test_promoting_it_needs_an_explicit_call(self, client):
        answer_bank.record_observed(question="Notice period", answer="2 weeks",
                                    tag="notice_period")
        # ...and until that call, the profile is untouched.
        assert (db.get_profile() or {}).get("notice_period") in (None, "")

        entry = client.get(
            "/api/autofill/answers/observed").json()["entries"][0]
        response = client.post("/api/autofill/answers/observed/to-profile",
                               json={"id": entry["id"]})
        assert response.status_code == 200
        assert db.get_profile()["notice_period"] == "2 weeks"

    def test_an_answer_that_maps_to_nothing_is_refused_politely(self, client):
        answer_bank.record_observed(question="Why us?", answer="Because.",
                                    tag="free_text_unknown")
        entry = client.get(
            "/api/autofill/answers/observed").json()["entries"][0]
        assert entry["profile_fact"] is False
        response = client.post("/api/autofill/answers/observed/to-profile",
                               json={"id": entry["id"]})
        assert response.status_code == 409

    def test_forget_everything_leaves_the_applicants_own_answers(self, client):
        answer_bank.save("Typed in the app", "mine")
        answer_bank.record_observed(question="Read off a page", answer="learned",
                                    tag="free_text_unknown")
        assert client.post(
            "/api/autofill/answers/observed/forget").json()["removed"] == 1
        assert stored("Typed in the app") is not None
        assert stored("Read off a page") is None


class TestAnAdHocSessionDoesNotHalfWrite:
    """021 — found by the browser suite, in the log rather than the assertion.

    `application_answers.job_id` is a REAL foreign key, but an ad-hoc "Fill
    this page" or practice session carries a sentinel job id with no `jobs`
    row. Writing it raised IntegrityError AFTER the answer_bank row had
    already been inserted, so the answer was stored but the link was not —
    surfaced only as a warning nobody would read.
    """

    def test_an_unknown_job_id_still_stores_the_answer(self, tmp_db):
        assert answer_bank.record_observed(
            question="Why us?", answer="Because.", tag="free_text_unknown",
            job_id=999_999) is not None
        assert stored("Why us?")["answer"] == "Because."

    def test_an_unknown_job_id_writes_no_application_row(self, tmp_db):
        answer_bank.record_observed(question="Why us?", answer="Because.",
                                    tag="free_text_unknown", job_id=999_999)
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) c FROM application_answers").fetchone()
        assert rows["c"] == 0

    def test_a_real_job_id_still_links(self, tmp_db):
        """The paired half — the guard must not disable the feature."""
        db.upsert_job({"title": "RTL", "company": "Intel",
                       "url": "https://x/1", "source": "workday",
                       "description": "d", "posted_date": None})
        with db._conn() as conn:
            job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
        answer_bank.record_observed(question="Why us?", answer="Because.",
                                    tag="free_text_unknown", job_id=job_id)
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) c FROM application_answers").fetchone()
        assert rows["c"] == 1

    def test_it_raises_nothing(self, tmp_db, caplog):
        caplog.set_level(logging.WARNING)
        answer_bank.record_observed(question="Why us?", answer="Because.",
                                    tag="free_text_unknown", job_id=999_999)
        assert "could not record an observed answer" not in caplog.text
