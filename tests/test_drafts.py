"""010 T017: AI-draft lifecycle — the ai_drafts ledger, answer-bank
provenance, and the field_core flag flowing through the fill decision."""
import time

from engine import db
from engine.autofill import answer_bank, drafts, field_core


class TestDraftLedger:
    def test_record_and_list(self, tmp_db):
        did = drafts.record(5, "Why us?", "Because UVM.", "local")
        rows = drafts.list_for_job(5)
        assert len(rows) == 1 and rows[0]["id"] == did
        assert rows[0]["status"] == "drafted"

    def test_confirm_saves_answer_with_provenance(self, tmp_db):
        did = drafts.record(5, "Why us?", "Draft text.", "local")
        drafts.confirm(did, text="Edited final answer.")
        assert drafts.get(did)["status"] == "confirmed"
        saved = answer_bank.lookup("Why us?")
        assert saved["answer"] == "Edited final answer."
        assert saved["source"] == "confirmed"
        # confirmed drafts no longer appear in the review list
        assert drafts.list_for_job(5) == []

    def test_confirm_without_edit_uses_draft_text(self, tmp_db):
        did = drafts.record(5, "Q?", "The draft.", "local")
        drafts.confirm(did)
        assert answer_bank.lookup("Q?")["answer"] == "The draft."

    def test_discard_removes_from_review(self, tmp_db):
        did = drafts.record(5, "Q?", "x", "local")
        drafts.discard(did)
        assert drafts.list_for_job(5) == []
        assert answer_bank.lookup("Q?") is None

    def test_auto_save_on_submission_persists_final_text(self, tmp_db):
        drafts.record(7, "Why?", "Original draft.", "local")
        n = drafts.auto_save_for_job(7, {"Why?": "What I actually submitted."})
        assert n == 1
        saved = answer_bank.lookup("Why?")
        assert saved["answer"] == "What I actually submitted."
        assert saved["source"] == "auto_saved"

    def test_auto_save_falls_back_to_draft_when_no_final(self, tmp_db):
        drafts.record(7, "Why?", "The draft stands.", "local")
        drafts.auto_save_for_job(7, {})
        assert answer_bank.lookup("Why?")["answer"] == "The draft stands."

    def test_prune_leaves_recent(self, tmp_db):
        drafts.record(1, "recent", "x", "local")
        drafts.prune_stale(max_age_days=30)
        assert len(drafts.list_for_job(1)) == 1


class TestDraftFlagInDecision:
    def _desc(self, **o):
        d = {"doc": "d", "je_idx": "1", "tag": "textarea", "type": "",
             "name": "why", "id": "why", "label_text": "Why do you want this?",
             "placeholder": "", "aria_label": "", "autocomplete": "",
             "value": "", "options": None, "focused": False, "visible": True}
        d.update(o)
        return d

    def test_plain_value_not_flagged(self, tmp_db):
        d = field_core.decide(None, self._desc(name="first_name",
                                               label_text="First name"),
                              {}, lambda tag, desc: "Abhinav")
        assert d.action == "fill" and d.ai_draft is False

    def test_draft_value_is_flagged(self, tmp_db):
        d = field_core.decide(None, self._desc(), {},
                              lambda tag, desc: field_core.Draft("A drafted answer."))
        assert d.action == "fill" and d.ai_draft is True
        assert d.value == "A drafted answer."


class TestOneRowPerQuestion017:
    """017-T021 (FR-005, R1 corrected): the draft store keeps one row per
    (job, question).

    The 2026-07-28 live run showed 170 review rows for ~30 questions — the
    same question with 10-15 differently worded answers, accumulated across
    earlier runs and app versions against the same saved job and re-rendered
    in full on every 3-second poll. That is what buried the Stop button.
    """

    def test_recording_the_same_question_twice_updates_in_place(self, tmp_db):
        drafts.record(7, "Graduation Month*", "December", tier="local")
        drafts.record(7, "Graduation Month*", "December 2025", tier="local")
        rows = drafts.list_for_job(7)
        assert len(rows) == 1
        assert rows[0]["draft_text"] == "December 2025"

    def test_question_wording_noise_does_not_create_a_second_row(self, tmp_db):
        for variant in ("Graduation Month*", "graduation month* ",
                        "  Graduation  Month*"):
            drafts.record(7, variant, "December 2025", tier="local")
        assert len(drafts.list_for_job(7)) == 1

    def test_different_jobs_keep_their_own_rows(self, tmp_db):
        drafts.record(7, "What is your GPA?*", "3.2", tier="local")
        drafts.record(8, "What is your GPA?*", "3.2", tier="local")
        assert len(drafts.list_for_job(7)) == 1
        assert len(drafts.list_for_job(8)) == 1

    def test_historical_duplicates_are_collapsed_on_init(self, tmp_db):
        """The repair that fixes an existing install: 170 rows become one per
        question, newest kept."""
        from engine import db

        with db._conn() as conn:
            for index in range(12):
                conn.execute(
                    "INSERT INTO ai_drafts (job_id, question, draft_text,"
                    " status, tier, created_at)"
                    " VALUES (?,?,?,'drafted','local',?)",
                    (7, "Graduation Month*", f"answer {index}",
                     f"2026-07-0{index % 9 + 1}T00:00:00Z"),
                )
        assert len(drafts.list_for_job(7)) == 12

        db.init_db()

        rows = drafts.list_for_job(7)
        assert len(rows) == 1
        assert rows[0]["draft_text"] == "answer 11"

    def test_the_repair_is_idempotent(self, tmp_db):
        from engine import db

        drafts.record(7, "What is your GPA?*", "3.2", tier="local")
        db.init_db()
        db.init_db()
        assert len(drafts.list_for_job(7)) == 1


class TestRestartDurability017:
    """017-T021 (FR-004): a restart must not re-draft an answered form."""

    def test_stored_answers_rehydrate_the_drafter(self, tmp_db):
        from engine.autofill import drafter

        drafter.reset_for_tests()
        try:
            drafts.record(7, "Graduation Month*", "December 2025", tier="local")
            drafts.record(7, "What is your GPA?*", "3.2", tier="local")

            calls = []
            drafter.set_generator_for_tests(
                lambda q, c, p: calls.append(q) or "regenerated")
            drafter.rehydrate_from_store(7)

            assert drafter.answer_for(7, "Graduation Month*") == "December 2025"
            assert drafter.answer_for(7, "What is your GPA?*") == "3.2"

            drafter.ensure(7, "Graduation Month*", {"tag": "free_text_unknown"},
                           {})
            assert calls == [], "an already-answered question was re-drafted"
        finally:
            drafter.reset_for_tests()

    def test_rehydration_of_an_unknown_job_is_a_no_op(self, tmp_db):
        from engine.autofill import drafter

        drafter.reset_for_tests()
        drafter.rehydrate_from_store(999)
        assert drafter.list_for_job(999) == []


class TestLiveWriter017:
    """017-T012: the review surface must reflect the CURRENT run. Until this
    lands, ai_drafts has no production writer at all — the block the user saw
    could only ever show history."""

    def test_a_completed_draft_is_recorded(self, tmp_db):
        from engine.autofill import drafter

        drafter.reset_for_tests()
        try:
            drafter.set_generator_for_tests(lambda q, c, p: "December 2025")
            drafter.ensure(7, "Graduation Month*",
                           {"tag": "free_text_unknown", "options": [],
                            "maxlength": None, "widget": ""}, {})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not drafts.list_for_job(7):
                time.sleep(0.01)
            rows = drafts.list_for_job(7)
            assert len(rows) == 1
            assert rows[0]["draft_text"] == "December 2025"
        finally:
            drafter.reset_for_tests()

    def test_a_refusal_is_never_recorded(self, tmp_db):
        from engine.autofill import answer_bank, drafter

        drafter.reset_for_tests()
        try:
            drafter.set_generator_for_tests(
                lambda q, c, p: answer_bank.REFUSAL_TOKEN)
            drafter.ensure(7, "Do you have any offer deadlines?",
                           {"tag": "free_text_unknown", "options": [],
                            "maxlength": None, "widget": ""}, {})
            time.sleep(0.3)
            assert drafts.list_for_job(7) == []
        finally:
            drafter.reset_for_tests()
