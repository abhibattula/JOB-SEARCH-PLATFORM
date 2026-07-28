"""005-T023: engine/autofill/answer_bank.py — lookup/save/suggest.

save() must only ever be reachable via explicit user confirmation (FR-011);
suggest() reuses the matcher._chat tier dispatcher (cloud -> local ->
placeholder) rather than calling any LLM tier directly.
"""
import pytest

from engine.autofill import answer_bank


class TestTimestamps:
    def test_utcnow_has_microsecond_resolution(self):
        """v0.6.1: same millisecond-truncation fix as engine/db.py —
        updated_at ordering (list_all, fuzzy-match recency) must not
        collide for back-to-back saves on a fast machine."""
        fractional = answer_bank._utcnow().rsplit(".", 1)[1]
        assert len(fractional) == 6


class TestSaveAndLookup:
    def test_save_then_exact_lookup(self, tmp_db):
        answer_bank.save(
            "Are you authorized to work in the US?", "Yes",
            category="work_authorization",
        )
        result = answer_bank.lookup("Are you authorized to work in the US?")
        assert result is not None
        assert result["answer"] == "Yes"
        assert result["category"] == "work_authorization"

    def test_lookup_miss_returns_none(self, tmp_db):
        assert answer_bank.lookup("Some question never asked before") is None

    def test_save_is_idempotent_on_same_normalized_question(self, tmp_db):
        answer_bank.save("Do you require sponsorship?", "No", category="sponsorship_requirement")
        answer_bank.save("Do you require sponsorship?", "No, I do not", category="sponsorship_requirement")
        result = answer_bank.lookup("Do you require sponsorship?")
        assert result["answer"] == "No, I do not"

    def test_fuzzy_lookup_matches_near_identical_phrasing(self, tmp_db):
        """005 edge case: near-identical wording across different job sites
        reuses the saved answer."""
        answer_bank.save(
            "Are you legally authorized to work in the United States?",
            "Yes", category="work_authorization",
        )
        result = answer_bank.lookup("Are you legally authorized to work in the US?")
        assert result is not None
        assert result["answer"] == "Yes"

    def test_fuzzy_lookup_does_not_collapse_genuinely_different_questions(self, tmp_db):
        """005 edge case: work-authorization and sponsorship-requirement are
        related but distinct — must not silently share an answer."""
        answer_bank.save(
            "Are you legally authorized to work in the United States?",
            "Yes", category="work_authorization",
        )
        result = answer_bank.lookup(
            "Do you require visa sponsorship now or in the future?"
        )
        assert result is None


class TestSuggest:
    def test_suggest_uses_chat_dispatcher(self, tmp_db, monkeypatch):
        from engine import matcher

        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: "Suggested answer text")
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        draft = answer_bank.suggest(
            "How did you hear about us?", category="how_heard", profile={"resume_text": "..."}
        )
        assert draft == "Suggested answer text"

    def test_suggest_falls_back_to_placeholder_when_no_tier_available(self, tmp_db, monkeypatch):
        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        draft = answer_bank.suggest(
            "How did you hear about us?", category="how_heard", profile={"resume_text": "..."}
        )
        assert draft == ""  # never fabricate — caller shows an empty/manual state

    def test_suggest_never_writes_to_answer_bank(self, tmp_db, monkeypatch):
        """FR-011: a drafted suggestion is never saved until the user
        explicitly confirms it — suggest() alone must not create a row."""
        from engine import matcher

        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: "Suggested answer text")
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        answer_bank.suggest("Novel question", category="free_text_unknown", profile={})
        assert answer_bank.lookup("Novel question") is None


class TestListAllAndDelete:
    """006-B: Profile page lets the user pre-populate and manage the answer
    bank directly, rather than only building it up reactively during a live
    Apply Assist pause."""

    def test_list_all_returns_saved_entries(self, tmp_db):
        answer_bank.save("Question one?", "Answer one", category="how_heard")
        answer_bank.save("Question two?", "Answer two", category="years_experience")

        entries = answer_bank.list_all()

        questions = {e["question_raw"] for e in entries}
        assert questions == {"Question one?", "Question two?"}

    def test_list_all_empty_by_default(self, tmp_db):
        assert answer_bank.list_all() == []

    def test_delete_removes_entry(self, tmp_db):
        bank_id = answer_bank.save("Question?", "Answer", category="how_heard")

        answer_bank.delete(bank_id)

        assert answer_bank.list_all() == []
        assert answer_bank.lookup("Question?") is None

    def test_delete_nonexistent_id_is_a_noop(self, tmp_db):
        answer_bank.delete(99999)  # must not raise


class TestRecordApplicationAnswer:
    def test_record_creates_snapshot_row(self, tmp_db):
        from engine import db

        db.upsert_job(
            {"title": "SWE", "company": "TestCo", "url": "https://x.example/1",
             "source": "greenhouse", "description": "desc"}
        )
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
        job_id = jobs[0]["id"]
        bank_id = answer_bank.save("Question?", "Answer", category="how_heard")
        answer_bank.record_application_answer(job_id, "Question?", bank_id, "Answer")

        with db._conn() as conn:
            row = conn.execute(
                "SELECT * FROM application_answers WHERE job_id = ?", (job_id,)
            ).fetchone()
        assert row["answer_used"] == "Answer"
        assert row["answer_bank_id"] == bank_id

    def test_record_snapshot_unaffected_by_later_edit(self, tmp_db):
        """005-T031: application_answers is a snapshot, not a live reference —
        editing the answer bank later must not retroactively change history."""
        from engine import db

        db.upsert_job(
            {"title": "SWE", "company": "TestCo", "url": "https://x.example/2",
             "source": "greenhouse", "description": "desc"}
        )
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
        job_id = jobs[0]["id"]
        bank_id = answer_bank.save("Q?", "Original answer", category="how_heard")
        answer_bank.record_application_answer(job_id, "Q?", bank_id, "Original answer")

        answer_bank.save("Q?", "Edited answer", category="how_heard")

        with db._conn() as conn:
            row = conn.execute(
                "SELECT * FROM application_answers WHERE job_id = ?", (job_id,)
            ).fetchone()
        assert row["answer_used"] == "Original answer"


class TestAutoSave016:
    """016 (T004): the drafter's auto-save path — reusable facts land in
    the bank as source='ai' (never clobbering a human entry); job-specific
    prose is recorded per-application only and never enters the reusable
    bank; practice/ad-hoc sentinel job ids never touch the database."""

    @staticmethod
    def _make_job():
        from engine import db

        db.upsert_job(
            {"title": "SWE", "company": "ScopeCo", "url": "https://x.example/9",
             "source": "greenhouse", "description": "desc"}
        )
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
        return jobs[0]["id"]

    def test_fact_saves_to_bank_as_ai(self, tmp_db):
        bank_id = answer_bank.save_auto(
            question="What is your notice period?", answer="Two weeks",
            tag="notice_period", origin="ai", job_id=None)
        row = answer_bank.lookup("What is your notice period?")
        assert row is not None and row["answer"] == "Two weeks"
        assert row["source"] == "ai"
        assert bank_id == row["id"]

    def test_ai_save_never_overwrites_user_entry(self, tmp_db):
        answer_bank.save("What is your notice period?", "One month",
                         category="notice_period")
        answer_bank.save_auto(
            question="What is your notice period?", answer="Two weeks",
            tag="notice_period", origin="ai", job_id=None)
        row = answer_bank.lookup("What is your notice period?")
        assert row["answer"] == "One month"
        assert row["source"] == "user"

    def test_ai_save_updates_prior_ai_entry(self, tmp_db):
        answer_bank.save_auto(question="Notice period?", answer="Two weeks",
                              tag="notice_period", origin="ai", job_id=None)
        answer_bank.save_auto(question="Notice period?", answer="Immediately",
                              tag="notice_period", origin="ai", job_id=None)
        assert answer_bank.lookup("Notice period?")["answer"] == "Immediately"

    def test_job_scoped_prose_never_enters_the_reusable_bank(self, tmp_db):
        from engine import db

        job_id = self._make_job()
        answer_bank.save_auto(
            question="Why do you want to work at ScopeCo?",
            answer="Because of the mission.", tag="cover_letter",
            origin="ai", job_id=job_id)
        assert answer_bank.lookup("Why do you want to work at ScopeCo?") is None
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM application_answers WHERE job_id = ?",
                (job_id,)).fetchall()
        assert len(rows) == 1
        assert rows[0]["answer_used"] == "Because of the mission."

    def test_sentinel_job_id_skips_persist_without_error(self, tmp_db):
        from engine import db

        answer_bank.save_auto(question="Why us?", answer="Because",
                              tag="cover_letter", origin="ai", job_id=0)
        assert answer_bank.lookup("Why us?") is None
        with db._conn() as conn:
            n = conn.execute(
                "SELECT COUNT(1) AS n FROM application_answers").fetchone()["n"]
        assert n == 0


class TestConstrainedSuggest016:
    """016 (T012, R7): the suggester is descriptor-aware — option fields
    demand exactly one of the real options, comboboxes demand a short
    literal label, prose obeys the field's length limit."""

    def _capture(self, monkeypatch, reply):
        from engine import matcher

        captured = {}

        def fake_chat(messages, **kw):
            captured["messages"] = messages
            return reply

        monkeypatch.setattr(matcher, "_chat", fake_chat)
        monkeypatch.setattr(matcher, "llm_available", lambda: True)
        return captured

    def test_option_field_prompt_lists_options_and_demands_one(
            self, tmp_db, monkeypatch):
        captured = self._capture(monkeypatch, "Yes")
        out = answer_bank.suggest(
            "Are you authorized?", "work_authorization",
            {"resume_text": "resume"},
            descriptor_ctx={"options": ["Yes", "No"], "widget": "",
                            "maxlength": None, "type": "select",
                            "tag": "work_authorization"})
        text = " ".join(m["content"] for m in captured["messages"])
        assert "Yes" in text and "No" in text
        assert "exactly one" in text.lower()
        assert out == "Yes"

    def test_combobox_prompt_demands_short_label(self, tmp_db, monkeypatch):
        captured = self._capture(monkeypatch, "LinkedIn")
        answer_bank.suggest(
            "How did you hear about us?", "how_heard", {"resume_text": "r"},
            descriptor_ctx={"options": [], "widget": "custom_combobox",
                            "maxlength": None, "type": "",
                            "tag": "how_heard"})
        text = " ".join(m["content"] for m in captured["messages"])
        assert "4 words" in text

    def test_prose_prompt_carries_maxlength(self, tmp_db, monkeypatch):
        captured = self._capture(monkeypatch, "Short answer.")
        answer_bank.suggest(
            "Why us?", "free_text_unknown", {"resume_text": "r"},
            descriptor_ctx={"options": [], "widget": "", "maxlength": 120,
                            "type": "text", "tag": "free_text_unknown"})
        text = " ".join(m["content"] for m in captured["messages"])
        assert "120" in text

    def test_legacy_call_without_ctx_still_works(self, tmp_db, monkeypatch):
        self._capture(monkeypatch, "An answer.")
        assert answer_bank.suggest("Q?", None, {"resume_text": "r"}) \
            == "An answer."


class TestRefusalContract017:
    """017-T015/T017 (R4, R5 corrected, FR-006/FR-007): the live drafting
    path must be able to say it does not know.

    On the 2026-07-28 Akuna run the model asserted the applicant had interned
    at the target company, completed the company's own course, held an offer
    deadline, and lived in California — none of it in their resume. The cause
    is structural: `suggest` had no refusal branch, so it always had to
    produce text. `qa.draft` has carried a CANNOT_ANSWER token since 010; the
    path 016 actually uses never got one.
    """

    def _capture(self, monkeypatch, reply):
        from engine import matcher

        captured = {}

        def fake_chat(messages, **kw):
            captured["messages"] = messages
            return reply

        monkeypatch.setattr(matcher, "_chat", fake_chat)
        monkeypatch.setattr(matcher, "llm_available", lambda: True)
        return captured

    UNGROUNDED = [
        ("Have you ever applied to a full time or internship position with "
         "Akuna in the past?", "applied_before"),
        ("Do you have prior experience working at an options market making "
         "firm?", "prior_industry_experience"),
        ("Did you complete our online Options 101 Course?", "completed_course"),
        ("Do you have any offer deadlines that we should be aware of?",
         "offer_deadlines"),
        ("Do you live in New York or California?", "residency_state"),
    ]

    @pytest.mark.parametrize("question,category", UNGROUNDED)
    def test_every_prompt_offers_the_refusal_token(
            self, tmp_db, monkeypatch, question, category):
        captured = self._capture(monkeypatch, "Yes")
        answer_bank.suggest(question, category,
                            {"resume_text": "Embedded systems intern."})
        system = captured["messages"][0]["content"]
        assert answer_bank.REFUSAL_TOKEN in system

    def test_option_and_combobox_prompts_also_offer_it(
            self, tmp_db, monkeypatch):
        captured = self._capture(monkeypatch, "Yes")
        answer_bank.suggest("Pick one", "free_text_unknown",
                            {"resume_text": "x"},
                            descriptor_ctx={"options": ["Yes", "No"]})
        assert answer_bank.REFUSAL_TOKEN in captured["messages"][0]["content"]

        captured = self._capture(monkeypatch, "Yes")
        answer_bank.suggest("Pick one", "free_text_unknown",
                            {"resume_text": "x"},
                            descriptor_ctx={"widget": "custom_combobox"})
        assert answer_bank.REFUSAL_TOKEN in captured["messages"][0]["content"]

    def test_a_refusal_is_passed_through_verbatim(self, tmp_db, monkeypatch):
        self._capture(monkeypatch, answer_bank.REFUSAL_TOKEN)
        out = answer_bank.suggest("Do you have any offer deadlines?",
                                  "offer_deadlines", {"resume_text": "x"})
        assert out == answer_bank.REFUSAL_TOKEN

    def test_a_chatty_refusal_is_still_recognised(self, tmp_db, monkeypatch):
        self._capture(
            monkeypatch,
            "CANNOT_ANSWER — the resume does not mention any offer deadlines.")
        out = answer_bank.suggest("Do you have any offer deadlines?",
                                  "offer_deadlines", {"resume_text": "x"})
        assert answer_bank.is_refusal(out)

    def test_a_real_answer_is_not_mistaken_for_a_refusal(self):
        assert not answer_bank.is_refusal("3.2")
        assert not answer_bank.is_refusal("December 2025")
        assert not answer_bank.is_refusal("")

    def test_the_factual_prompt_carries_no_job_or_company_context(
            self, tmp_db, monkeypatch):
        """R5 (corrected): the live path already passes resume grounding only.
        This pins it, because the pre-016 flow did pass the job and produced
        exactly the 'I interned at <target company>' class of answer."""
        captured = self._capture(monkeypatch, "Yes")
        answer_bank.suggest(
            "Do you have prior experience at an options market making firm?",
            "prior_industry_experience",
            {"resume_text": "Embedded systems intern at Acme Robotics."})
        blob = " ".join(m["content"] for m in captured["messages"])
        assert "Acme Robotics" in blob            # the applicant's own facts
        assert "RESUME/PROFILE" in blob
        for leak in ("JOB DESCRIPTION", "ABOUT THE ROLE", "COMPANY:"):
            assert leak not in blob

    def test_suggest_accepts_no_job_argument(self):
        import inspect

        assert "job" not in inspect.signature(answer_bank.suggest).parameters
