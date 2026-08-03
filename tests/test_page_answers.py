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


def sectioned(section, index=0, **kw):
    """A decision that knows which region of the form it came from."""
    return entry(section_label=section, section_index=index, **kw)


class TestOneRowPerQuestion:
    """021 US1 (FR-004/FR-005/FR-010).

    v2.0.0 keyed rows on `field_core.key(descriptor)` = (doc, je_idx) — a
    per-ELEMENT stamp. A Workday prompt is a button with aria-haspopup=listbox
    PLUS its listbox, and FIELD_SELECTOR matches both, so every dropdown
    produced two identical rows. On the applicant's real page that was part of
    149 rows, most of them blank.
    """

    def test_two_elements_one_question_collapse_to_one_row(self):
        items = page_answers.build([
            sectioned("Address", key="a", je_idx="4", question="Country/Region",
                      action="skip", tag="location_country"),
            sectioned("Address", key="b", je_idx="5", question="Country/Region",
                      action="skip", tag="location_country"),
        ], {"Country/Region": {"state": "failed",
                               "reason": "profile_fact_missing"}})
        assert len(items) == 1

    def test_the_same_question_in_two_sections_stays_two_rows(self):
        """The guard against over-collapsing. Two employment blocks each ask
        "From" and they are two real questions — merging them would be worse
        than the flood it fixes."""
        records = {"From": {"state": "failed", "reason": "cannot_answer"}}
        items = page_answers.build([
            sectioned("Work Experience", 0, key="a", je_idx="1",
                      question="From", action="skip"),
            sectioned("Work Experience", 1, key="b", je_idx="2",
                      question="From", action="skip"),
        ], records)
        assert len(items) == 2
        assert {i["section_index"] for i in items} == {0, 1}

    def test_a_collapsed_row_keeps_every_element_behind_it(self):
        """FR-005: "Show me" must still reach each one."""
        items = page_answers.build([
            sectioned("Address", key="a", je_idx="4", question="State",
                      action="skip"),
            sectioned("Address", key="b", je_idx="5", question="State",
                      action="skip"),
            sectioned("Address", key="c", je_idx="6", question="State",
                      action="skip"),
        ], {"State": {"state": "failed", "reason": "profile_fact_missing"}})
        assert items[0]["je_idx_all"] == ["4", "5", "6"]

    def test_je_idx_stays_a_string(self):
        """analysis A3. panel.js uses `item.je_idx` as a string in five
        places (Insert, Show me, the ask input and two hidden flags) and it
        feeds the render digest. A list here breaks all of them."""
        items = page_answers.build([
            sectioned("Address", key="a", je_idx="4", question="State",
                      action="skip"),
            sectioned("Address", key="b", je_idx="5", question="State",
                      action="skip"),
        ], {"State": {"state": "failed", "reason": "profile_fact_missing"}})
        assert items[0]["je_idx"] == "4"
        assert isinstance(items[0]["je_idx"], str)

    def test_a_single_element_still_lists_itself(self):
        items = page_answers.build([
            sectioned("Address", key="a", je_idx="9", question="City",
                      action="fill", answer="Austin"),
        ])
        assert items[0]["je_idx"] == "9"
        assert items[0]["je_idx_all"] == ["9"]

    def test_a_filled_answer_outranks_a_bare_skip_for_the_same_question(self):
        """The v1.8.0 rule, preserved through de-duplication: what the
        applicant needs to review is the value we put there."""
        items = page_answers.build([
            sectioned("Address", key="a", je_idx="1", question="City",
                      action="fill", answer="Austin"),
            sectioned("Address", key="b", je_idx="2", question="City",
                      action="skip"),
        ])
        assert len(items) == 1
        assert items[0]["answer"] == "Austin"

    def test_collapsing_is_case_and_whitespace_insensitive(self):
        items = page_answers.build([
            sectioned("Address", key="a", je_idx="1", question="Country/Region",
                      action="skip"),
            sectioned("Address", key="b", je_idx="2",
                      question="  country/region  ", action="skip"),
        ], {"Country/Region": {"state": "failed",
                               "reason": "profile_fact_missing"}})
        assert len(items) == 1

    def test_an_undetermined_section_does_not_merge_unrelated_questions(self):
        """`section_label: ""` means UNDETERMINED. Two different questions
        must never merge just because neither resolved a section."""
        items = page_answers.build([
            entry(key="a", je_idx="1", question="Additional Information",
                  action="fill", answer="x"),
            entry(key="b", je_idx="2", question="Something Else",
                  action="fill", answer="y"),
        ])
        assert len(items) == 2

    def test_the_section_travels_to_the_panel(self):
        """FR-008: the panel groups by it, so it has to arrive."""
        items = page_answers.build([
            sectioned("Work Experience", 1, key="a", je_idx="1",
                      question="Company", action="fill", answer="Acme"),
        ])
        assert items[0]["section_label"] == "Work Experience"
        assert items[0]["section_index"] == 1

    def test_a_hundred_and_fifty_field_page_stays_readable(self):
        """The headline: the applicant's page, in the shape that produced
        149 rows. 12 sections x 6 questions, each served by two elements."""
        entries = []
        n = 0
        for section in range(12):
            for question in range(6):
                for _element in range(2):
                    n += 1
                    entries.append(sectioned(
                        "Work Experience", section, key=f"k{n}",
                        je_idx=str(n), question=f"Question {question}",
                        action="fill", answer="x"))
        items = page_answers.build(entries)
        assert len(entries) == 144
        assert len(items) == 72   # one row per question per section
