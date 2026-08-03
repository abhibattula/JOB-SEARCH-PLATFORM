"""021 US2 — employment and education blocks answer themselves.

The applicant's Workday application asked for employer, job title, dates,
school, degree and GPA across repeated blocks, and every one came back as
"needs you". Their resume was ALREADY parsed into structured experience[] and
education[] entries (engine/resume_extract.py) and persisted as
user_profile.resume_sections. The fill layer had never read it.

The rule that matters most here is the one 017 was spent establishing: a
missing entry yields None, which means FLAG IT FOR THE APPLICANT. Never a
guess, never a fallback to a neighbouring entry. 017 exists because "Do you
have a preferred name?" was filled with the legal full name by exactly that
kind of substitution.
"""
from __future__ import annotations

import pytest

from engine.autofill import history_answers


def sections(experience=(), education=()):
    return {"experience": list(experience), "education": list(education)}


ACME = {"title": "Verification Intern", "organization": "Acme Semiconductors",
        "start": "2024-05", "end": "2024-08", "location": "Austin, TX",
        "is_current": False, "bullets": []}
GLOBEX = {"title": "RTL Design Intern", "organization": "Globex",
          "start": "2025-01", "end": "", "location": "Remote",
          "is_current": True, "bullets": []}
UT = {"degree": "B.S. Computer Engineering", "institution": "UT Austin",
      "start": "2021-08", "end": "2025-05", "details": "",
      "field_of_study": "Computer Engineering", "gpa": "3.6"}
COMMUNITY = {"degree": "Associate of Science", "institution": "Austin CC",
             "start": "2019-08", "end": "2021-05", "details": "",
             "field_of_study": "General Engineering", "gpa": ""}


class TestItAnswersFromTheRightBlock:
    """FR-011/FR-012."""

    @pytest.mark.parametrize("tag,expected", [
        ("exp_employer", "Acme Semiconductors"),
        ("exp_title", "Verification Intern"),
        ("exp_start", "2024-05"),
        ("exp_end", "2024-08"),
        ("exp_location", "Austin, TX"),
    ])
    def test_the_first_block_uses_the_first_entry(self, tag, expected):
        data = sections(experience=[ACME, GLOBEX])
        assert history_answers.value_for(tag, 0, data) == expected

    def test_the_second_block_uses_the_second_entry(self):
        data = sections(experience=[ACME, GLOBEX])
        assert history_answers.value_for(
            "exp_employer", 1, data) == "Globex"
        assert history_answers.value_for("exp_title", 1, data) == \
            "RTL Design Intern"

    @pytest.mark.parametrize("tag,expected", [
        ("edu_school", "UT Austin"),
        ("edu_degree", "B.S. Computer Engineering"),
        ("edu_field", "Computer Engineering"),
        ("edu_gpa", "3.6"),
        ("edu_start", "2021-08"),
        ("edu_end", "2025-05"),
    ])
    def test_education_answers_from_its_own_block(self, tag, expected):
        data = sections(education=[UT, COMMUNITY])
        assert history_answers.value_for(tag, 0, data) == expected

    def test_education_and_experience_index_independently(self):
        """Both are "block 1" on the page; they must not cross."""
        data = sections(experience=[ACME, GLOBEX], education=[UT, COMMUNITY])
        assert history_answers.value_for(
            "exp_employer", 1, data) == "Globex"
        assert history_answers.value_for(
            "edu_school", 1, data) == "Austin CC"


class TestItNeverSubstitutes:
    """FR-013 — the rule 017 was spent establishing. This is the class of bug
    that filled "Do you have a preferred name?" with the legal full name."""

    def test_a_block_past_the_end_returns_nothing(self):
        data = sections(experience=[ACME, GLOBEX])
        assert history_answers.value_for("exp_employer", 2, data) is None

    def test_it_does_not_fall_back_to_the_first_entry(self):
        data = sections(experience=[ACME])
        assert history_answers.value_for("exp_employer", 1, data) is None
        assert history_answers.value_for("exp_employer", 5, data) is None

    def test_it_does_not_fall_back_to_the_nearest_entry(self):
        data = sections(experience=[ACME, GLOBEX])
        assert history_answers.value_for("exp_title", 9, data) is None

    def test_an_empty_field_in_a_real_entry_is_still_nothing(self):
        """COMMUNITY has no GPA. The answer is not UT's 3.6, and it is not
        an empty string typed into the box — it is "ask the applicant"."""
        data = sections(education=[UT, COMMUNITY])
        assert history_answers.value_for("edu_gpa", 1, data) is None

    def test_a_current_role_has_no_end_date_and_does_not_borrow_one(self):
        data = sections(experience=[ACME, GLOBEX])
        assert history_answers.value_for("exp_end", 1, data) is None

    def test_no_history_at_all_returns_nothing(self):
        assert history_answers.value_for("exp_employer", 0, sections()) is None
        assert history_answers.value_for("edu_school", 0, None) is None
        assert history_answers.value_for("edu_school", 0, {}) is None

    def test_an_unrelated_tag_is_not_answered_here(self):
        data = sections(experience=[ACME])
        assert history_answers.value_for("email", 0, data) is None
        assert history_answers.value_for(None, 0, data) is None

    def test_whitespace_is_not_an_answer(self):
        data = sections(experience=[dict(ACME, organization="   ")])
        assert history_answers.value_for("exp_employer", 0, data) is None


class TestCurrentlyEmployed:
    """The applicant's page showed "I currently work here" as needs-you."""

    def test_a_current_role_answers_yes(self):
        data = sections(experience=[GLOBEX])
        assert history_answers.value_for("exp_current", 0, data) == "Yes"

    def test_a_past_role_answers_no(self):
        data = sections(experience=[ACME])
        assert history_answers.value_for("exp_current", 0, data) == "No"

    def test_it_is_driven_by_the_flag_not_the_empty_end_date(self):
        """An end date the parser simply failed to read is not evidence that
        the applicant still works there — that would tick a checkbox on a
        real application on the strength of a parsing gap."""
        unknown = dict(ACME, end="", is_current=False)
        data = sections(experience=[unknown])
        assert history_answers.value_for("exp_current", 0, data) == "No"


class TestItToleratesWhatIsActuallyStored:
    """resume_sections is written by a 1.5B model and by hand. It must not
    raise on anything it might hold."""

    @pytest.mark.parametrize("blob", [
        {"experience": None},
        {"experience": "not a list"},
        {"experience": [None]},
        {"experience": ["a string, not an entry"]},
        {"experience": [{"organization": None}]},
        {"experience": [{}]},
        [],
        "",
    ])
    def test_malformed_history_returns_nothing_and_does_not_raise(self, blob):
        assert history_answers.value_for("exp_employer", 0, blob) is None

    def test_a_v2_0_0_entry_without_the_new_fields_still_answers(self):
        """Back-compatibility: entries stored before 021 have no `location`,
        `is_current`, `field_of_study` or `gpa`."""
        old = {"title": "Intern", "organization": "Acme",
               "start": "2024-05", "end": "2024-08", "bullets": []}
        data = sections(experience=[old])
        assert history_answers.value_for("exp_employer", 0, data) == "Acme"
        assert history_answers.value_for("exp_location", 0, data) is None
        assert history_answers.value_for("exp_current", 0, data) == "No"

    def test_a_non_string_value_is_rendered_not_returned_raw(self):
        """A GPA parsed as a float would otherwise reach a native setter as a
        non-string and throw inside the filler."""
        data = sections(education=[dict(UT, gpa=3.6)])
        assert history_answers.value_for("edu_gpa", 0, data) == "3.6"


class TestTheTagSet:
    def test_every_history_tag_is_declared(self):
        """The fill layer routes on this set; a tag missing from it silently
        falls through to the drafter and gets generated instead of read."""
        assert history_answers.HISTORY_TAGS == frozenset({
            "exp_employer", "exp_title", "exp_start", "exp_end",
            "exp_current", "exp_location",
            "edu_school", "edu_degree", "edu_field", "edu_gpa",
            "edu_start", "edu_end",
        })

    def test_every_declared_tag_resolves(self):
        """The paired half: a tag in the set that the resolver ignores would
        be worse than one that is missing."""
        # ACME, not GLOBEX: a CURRENT role correctly has no end date, so
        # exp_end would be None for the right reason and mask a tag that is
        # genuinely unresolved.
        data = sections(experience=[ACME], education=[UT])
        for tag in history_answers.HISTORY_TAGS:
            assert history_answers.value_for(tag, 0, data) is not None, tag
