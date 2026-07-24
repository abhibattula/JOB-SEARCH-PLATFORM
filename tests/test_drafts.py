"""010 T017: AI-draft lifecycle — the ai_drafts ledger, answer-bank
provenance, and the field_core flag flowing through the fill decision."""
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
