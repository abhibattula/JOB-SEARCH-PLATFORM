"""018 US3 — the page-answer index.

Through v1.7.0 the on-page panel was fed by `drafter.answers_for_page`, which
reads `drafter._records`. That table only ever holds questions routed to the AI
drafter. Everything resolved from the profile, the answer bank or a direct tag
map — name, email, phone, location, work authorization, self-ID — never
reached the page at all. The applicant could not confirm from the page what
had been put in the fields they were about to submit.

Worse, no entry carried a field identifier, so the panel's Insert and Show me
buttons were gated on `item.je_idx` and therefore never rendered. Every answer
offered Copy and nothing else.

This module assembles the real thing, in `ext_backend._handle_fields`, where
every decision passes and `je_idx` is already in hand.
"""
from __future__ import annotations

from engine.autofill import page_answers


def entry(**kw):
    """A decision as `_handle_fields` records it."""
    base = {
        "key": "label:question",
        "je_idx": "1",
        "question": "Question?",
        "answer": "",
        "action": "fill",
        "ai_draft": False,
        "secret": False,
        "tag": "",
    }
    base.update(kw)
    return base


class TestGrouping:
    def test_a_profile_fill_is_its_own_group(self):
        items = page_answers.build([
            entry(key="k1", je_idx="7", question="Email", answer="a@b.com",
                  tag="email"),
        ])
        assert len(items) == 1
        assert items[0]["group"] == "profile"
        assert items[0]["state"] == "filled"
        assert items[0]["answer"] == "a@b.com"
        assert items[0]["je_idx"] == "7"

    def test_an_ai_draft_is_marked_as_one(self):
        items = page_answers.build([
            entry(key="k1", question="Why us?", answer="Because…",
                  ai_draft=True),
        ])
        assert items[0]["group"] == "draft"
        assert items[0]["state"] == "drafted"

    def test_a_refused_question_needs_the_applicant(self):
        items = page_answers.build(
            [entry(key="k1", question="When does it expire?", action="skip")],
            {"when does it expire?": {
                "question": "When does it expire?", "state": "failed",
                "reason": "profile_fact_missing", "answer": ""}},
        )
        assert items[0]["group"] == "needs_you"
        assert items[0]["reason"] == "profile_fact_missing"
        assert items[0]["askable"] is True

    def test_a_binding_acknowledgement_is_refused_not_merely_pending(self):
        items = page_answers.build(
            [entry(key="k1", question="Is this your top preference?",
                   action="skip")],
            {"is this your top preference?": {
                "question": "Is this your top preference?", "state": "failed",
                "reason": "binding_commitment", "answer": ""}},
        )
        assert items[0]["group"] == "needs_you"
        assert items[0]["state"] == "refused"
        assert items[0]["askable"] is True

    def test_a_draft_still_in_flight_shows_as_drafting(self):
        items = page_answers.build(
            [entry(key="k1", question="Why us?", action="skip")],
            {"why us?": {"question": "Why us?", "state": "pending",
                         "reason": None, "answer": ""}},
        )
        assert items[0]["state"] == "drafting"
        assert items[0]["askable"] is False

    def test_a_skip_with_no_record_is_not_listed(self):
        """A field we deliberately ignored is not an unanswered question —
        listing it would bury the ones that genuinely need an answer."""
        items = page_answers.build([entry(key="k1", action="skip")])
        assert items == []


class TestOrdering:
    def test_needs_you_comes_first_then_drafts_then_profile(self):
        items = page_answers.build(
            [
                entry(key="p", question="Email", answer="a@b.com"),
                entry(key="d", question="Why us?", answer="Because…",
                      ai_draft=True),
                entry(key="n", question="Expiry?", action="skip"),
            ],
            {"expiry?": {"question": "Expiry?", "state": "failed",
                         "reason": "profile_fact_missing", "answer": ""}},
        )
        assert [i["group"] for i in items] == ["needs_you", "draft", "profile"]

    def test_document_order_is_kept_within_a_group(self):
        items = page_answers.build([
            entry(key="a", question="First", answer="1"),
            entry(key="b", question="Second", answer="2"),
            entry(key="c", question="Third", answer="3"),
        ])
        assert [i["question"] for i in items] == ["First", "Second", "Third"]


class TestSecretsNeverReachThePage:
    def test_a_secret_field_is_excluded_entirely(self):
        """FR-037. A password or pairing value is fill-and-forget: it is
        typed into the field and never rendered, logged or transmitted back."""
        items = page_answers.build([
            entry(key="k1", question="Password", answer="hunter2", secret=True),
            entry(key="k2", question="Email", answer="a@b.com"),
        ])
        assert [i["question"] for i in items] == ["Email"]
        assert "hunter2" not in str(items)


class TestFieldIdentity:
    def test_every_item_carries_its_key_and_field(self):
        """R4: without `je_idx` the panel cannot offer Insert or Show me —
        which is why neither button rendered even once in v1.7.0."""
        items = page_answers.build([
            entry(key="k1", je_idx="12", question="Email", answer="a@b.com"),
        ])
        assert items[0]["key"] == "k1"
        assert items[0]["je_idx"] == "12"

    def test_a_missing_field_id_is_tolerated(self):
        """A merged group whose member vanished still has an answer worth
        reading — it just cannot be inserted."""
        items = page_answers.build([
            entry(key="k1", je_idx="", question="Pronouns", answer="They/them"),
        ])
        assert items[0]["je_idx"] == ""


class TestDigest:
    def test_identical_input_gives_an_identical_digest(self):
        a = page_answers.build([entry(key="k1", answer="x")])
        b = page_answers.build([entry(key="k1", answer="x")])
        assert page_answers.digest(a) == page_answers.digest(b)

    def test_a_changed_answer_changes_the_digest(self):
        a = page_answers.build([entry(key="k1", answer="x")])
        b = page_answers.build([entry(key="k1", answer="y")])
        assert page_answers.digest(a) != page_answers.digest(b)

    def test_a_changed_group_changes_the_digest(self):
        a = page_answers.build([entry(key="k1", answer="x")])
        b = page_answers.build([entry(key="k1", answer="x", ai_draft=True)])
        assert page_answers.digest(a) != page_answers.digest(b)

    def test_order_matters(self):
        a = page_answers.build([entry(key="a", question="One", answer="1"),
                                entry(key="b", question="Two", answer="2")])
        b = page_answers.build([entry(key="b", question="Two", answer="2"),
                                entry(key="a", question="One", answer="1")])
        assert page_answers.digest(a) != page_answers.digest(b)

    def test_an_empty_feed_has_a_stable_digest(self):
        assert page_answers.digest([]) == page_answers.digest([])


class TestDeduplication:
    def test_the_same_field_seen_twice_is_listed_once(self):
        """Scans repeat; the index is keyed, so a re-scan updates rather than
        appends. This is the difference between a review list and the 170-row
        flood 017 had to clean up."""
        items = page_answers.build([
            entry(key="k1", question="Email", answer="old@b.com"),
            entry(key="k1", question="Email", answer="new@b.com"),
        ])
        assert len(items) == 1
        assert items[0]["answer"] == "new@b.com"
