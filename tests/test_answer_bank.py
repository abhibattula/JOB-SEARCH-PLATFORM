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
