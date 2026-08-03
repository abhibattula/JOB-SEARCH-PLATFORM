"""017-T008: engine/autofill/profile_answers.py — the single place that maps
a classified question to a value the applicant actually gave us.

Replaces the 75-line `if tag ==` ladder inside browser_controller._value_for_tag
(017, R12) so the mapping is unit-testable without a browser and identical for
both fill backends.

The rule that matters most: a blank profile field yields None, which leaves
the form field untouched and flagged. It is never an empty string, never a
guess, and never a fallback to a related field (FR-023).
"""
import pytest

from engine.autofill import profile_answers


def profile(**overrides):
    """A profile dict as db.get_profile returns it — every key present,
    most of them empty, which is the realistic starting state."""
    base = {
        "first_name": "", "last_name": "", "preferred_name": "",
        "middle_name": "", "pronouns": "", "email": "", "phone": "",
        "linkedin_url": "", "portfolio_url": "", "github_url": "",
        "other_url": "",
        "address_line1": "", "address_line2": "", "city": "",
        "state_region": "", "postal_code": "", "country": "",
        "current_location": "",
        "authorized_without_sponsorship": "", "visa_status": "",
        "work_auth_type": "", "work_auth_expiry": "",
        "work_auth_extensions": "", "sponsorship_future": "",
        "sponsorship_detail": "",
        "desired_salary": "", "earliest_start_date": "", "notice_period": "",
        "willing_to_relocate": "", "remote_preference": "",
        "willing_to_travel": "",
        "years_experience": "", "current_employer": "", "current_title": "",
        "highest_education": "", "graduation_month": "",
        "graduation_year": "", "gpa": "",
        "how_heard_default": "",
        "selfid_gender": "", "selfid_race": "", "selfid_veteran": "",
        "selfid_disability": "", "selfid_orientation": "",
    }
    base.update(overrides)
    return base


# --- the blank rule ----------------------------------------------------

@pytest.mark.parametrize("tag", sorted(profile_answers.PROFILE_ANSWER_TAGS))
def test_every_tag_returns_none_on_an_empty_profile(tag):
    """Nothing is invented, nothing falls back to a related field."""
    assert profile_answers.answer_for(tag, profile()) is None


def test_unknown_tag_returns_none():
    assert profile_answers.answer_for("free_text_unknown", profile()) is None
    assert profile_answers.answer_for(None, profile()) is None


# --- identity ----------------------------------------------------------

def test_name_parts():
    p = profile(first_name="Abhinav", last_name="Battula")
    assert profile_answers.answer_for("first_name", p) == "Abhinav"
    assert profile_answers.answer_for("last_name", p) == "Battula"
    assert profile_answers.answer_for("full_name", p) == "Abhinav Battula"


def test_full_name_includes_a_middle_name_only_when_asked_for_the_legal_name():
    p = profile(first_name="Abhinav", middle_name="K", last_name="Battula")
    assert profile_answers.answer_for("full_name", p) == "Abhinav Battula"
    assert profile_answers.answer_for("middle_name", p) == "K"


def test_full_name_needs_both_parts():
    assert profile_answers.answer_for(
        "full_name", profile(first_name="Abhinav")) is None


def test_preferred_name_never_falls_back_to_the_legal_name():
    """The live run filled "Do you have a preferred name…?" with the legal
    full name. Blank means blank."""
    p = profile(first_name="Abhinav", last_name="Battula")
    assert profile_answers.answer_for("preferred_name", p) is None
    p2 = profile(first_name="Abhinav", last_name="Battula",
                 preferred_name="Abhi")
    assert profile_answers.answer_for("preferred_name", p2) == "Abhi"


# --- location -----------------------------------------------------------

def test_location_parts():
    p = profile(address_line1="1 Main St", city="Arlington",
                state_region="TX", postal_code="76010", country="United States")
    assert profile_answers.answer_for("location_address1", p) == "1 Main St"
    assert profile_answers.answer_for("location_city", p) == "Arlington"
    assert profile_answers.answer_for("location_state", p) == "TX"
    assert profile_answers.answer_for("location_postal", p) == "76010"
    assert profile_answers.answer_for("location_country", p) == "United States"


def test_location_full_is_derived_when_not_stored():
    p = profile(city="Arlington", state_region="TX", country="United States")
    assert profile_answers.answer_for("location_full", p) == \
        "Arlington, TX, United States"


def test_stored_current_location_wins_over_the_derived_form():
    p = profile(city="Arlington", state_region="TX",
                current_location="Dallas-Fort Worth, TX")
    assert profile_answers.answer_for("location_full", p) == \
        "Dallas-Fort Worth, TX"


def test_location_full_needs_at_least_a_city():
    assert profile_answers.answer_for(
        "location_full", profile(country="United States")) is None


# --- work authorization -------------------------------------------------

def test_work_authorization_yes_when_authorized_without_sponsorship():
    p = profile(authorized_without_sponsorship="yes")
    assert profile_answers.answer_for("work_authorization", p) == "Yes"
    assert profile_answers.answer_for("sponsorship_requirement", p) == "No"


def test_work_authorization_stays_with_the_human_when_sponsorship_is_needed():
    """Deliberately conservative, carried over from qa.profile_fact_answer:
    someone who needs future sponsorship may still be authorized today (OPT),
    which one field cannot express."""
    p = profile(authorized_without_sponsorship="no")
    assert profile_answers.answer_for("work_authorization", p) is None
    assert profile_answers.answer_for("sponsorship_requirement", p) == "Yes"


def test_sponsorship_future_column_answers_directly_when_set():
    p = profile(sponsorship_future="no")
    assert profile_answers.answer_for("sponsorship_requirement", p) == "No"


def test_the_four_descriptive_work_auth_questions_have_their_own_columns():
    """These are the fields that received "Yes" on the live run. Each now has
    a real answer of its own shape."""
    p = profile(work_auth_type="F-1 STEM OPT",
                work_auth_expiry="2027-06-30",
                work_auth_extensions="24-month STEM extension available",
                sponsorship_detail="Will require H-1B sponsorship in 2027")
    assert profile_answers.answer_for("work_auth_status", p) == "F-1 STEM OPT"
    assert profile_answers.answer_for("work_auth_expiry", p) == "2027-06-30"
    assert profile_answers.answer_for("work_auth_extensions", p) == \
        "24-month STEM extension available"
    assert profile_answers.answer_for("sponsorship_detail", p) == \
        "Will require H-1B sponsorship in 2027"


def test_a_yes_no_fact_is_never_returned_for_a_descriptive_tag():
    """Even with authorization known, the expiry question has no answer
    unless its own column is filled."""
    p = profile(authorized_without_sponsorship="yes")
    assert profile_answers.answer_for("work_auth_expiry", p) is None
    assert profile_answers.answer_for("work_auth_extensions", p) is None
    assert profile_answers.answer_for("sponsorship_detail", p) is None


# --- voluntary self-identification (D1) ---------------------------------

@pytest.mark.parametrize("tag,column", [
    ("selfid_gender", "selfid_gender"),
    ("selfid_race", "selfid_race"),
    ("selfid_veteran", "selfid_veteran"),
    ("selfid_disability", "selfid_disability"),
    ("selfid_orientation", "selfid_orientation"),
])
def test_self_identification_is_returned_verbatim(tag, column):
    p = profile(**{column: "Man"})
    assert profile_answers.answer_for(tag, p) == "Man"


@pytest.mark.parametrize("tag", [
    "selfid_gender", "selfid_race", "selfid_veteran", "selfid_disability",
    "selfid_orientation",
])
def test_prefer_not_to_say_is_a_real_stored_answer(tag):
    """Distinct from blank: the applicant chose to decline, so the decline
    option gets selected rather than the field being left for them."""
    p = profile(**{tag: "Prefer not to say"})
    assert profile_answers.answer_for(tag, p) == "Prefer not to say"


@pytest.mark.parametrize("tag", [
    "selfid_gender", "selfid_race", "selfid_veteran", "selfid_disability",
    "selfid_orientation",
])
def test_blank_self_identification_is_left_to_the_human(tag):
    assert profile_answers.answer_for(tag, profile()) is None


def test_self_identification_is_never_derived_from_anything_else():
    """No inference from pronouns, name, résumé or any other field."""
    p = profile(pronouns="He/him", first_name="Abhinav")
    assert profile_answers.answer_for("selfid_gender", p) is None


# --- experience and preferences ------------------------------------------

def test_experience_facts():
    p = profile(years_experience="2", current_employer="Acme",
                current_title="Embedded Systems Intern",
                highest_education="Master's", graduation_month="December",
                graduation_year="2025", gpa="3.2")
    assert profile_answers.answer_for("years_experience", p) == "2"
    assert profile_answers.answer_for("current_employer", p) == "Acme"
    assert profile_answers.answer_for("current_title", p) == \
        "Embedded Systems Intern"
    assert profile_answers.answer_for("highest_education", p) == "Master's"
    assert profile_answers.answer_for("gpa", p) == "3.2"
    assert profile_answers.answer_for("graduation_date", p) == "December 2025"


def test_graduation_date_needs_a_year():
    assert profile_answers.answer_for(
        "graduation_date", profile(graduation_month="December")) is None


def test_preferences():
    p = profile(desired_salary="120000", earliest_start_date="2026-01-05",
                notice_period="2 weeks", willing_to_relocate="yes",
                remote_preference="Hybrid", willing_to_travel="no")
    assert profile_answers.answer_for("salary_expectation", p) == "120000"
    assert profile_answers.answer_for("start_date", p) == "2026-01-05"
    assert profile_answers.answer_for("notice_period", p) == "2 weeks"
    assert profile_answers.answer_for("relocate", p) == "Yes"
    assert profile_answers.answer_for("remote_preference", p) == "Hybrid"
    assert profile_answers.answer_for("travel", p) == "No"


def test_links():
    p = profile(linkedin_url="https://linkedin.com/in/x",
                portfolio_url="https://example.com",
                github_url="https://github.com/x")
    assert profile_answers.answer_for("linkedin_url", p) == \
        "https://linkedin.com/in/x"
    assert profile_answers.answer_for("portfolio_url", p) == \
        "https://example.com"
    assert profile_answers.answer_for("github_url", p) == "https://github.com/x"


def test_how_heard_default():
    assert profile_answers.answer_for(
        "how_heard", profile(how_heard_default="Company website")) == \
        "Company website"


# --- hygiene -------------------------------------------------------------

def test_whitespace_only_values_count_as_blank():
    assert profile_answers.answer_for(
        "first_name", profile(first_name="   ")) is None


def test_values_are_stripped():
    assert profile_answers.answer_for(
        "email", profile(email="  a@b.com \n")) == "a@b.com"


def test_a_missing_key_is_not_an_error():
    """Older databases predate these columns; get_profile may omit them."""
    assert profile_answers.answer_for("city", {}) is None
    assert profile_answers.answer_for("selfid_gender", {}) is None


def test_profile_answer_tags_and_resolution_agree():
    """Anything claimed in PROFILE_ANSWER_TAGS must actually resolve, or the
    resolver would silently fall through to the AI drafter."""
    filled = profile(
        first_name="A", last_name="B", preferred_name="C", middle_name="D",
        pronouns="He/him", email="a@b.com", phone="1", linkedin_url="l",
        portfolio_url="p", github_url="g", other_url="o",
        address_line1="a1", address_line2="a2", city="c", state_region="s",
        postal_code="z", country="US", current_location="c, s",
        authorized_without_sponsorship="yes", work_auth_type="w",
        work_auth_expiry="e", work_auth_extensions="x",
        sponsorship_future="no", sponsorship_detail="d",
        desired_salary="1", earliest_start_date="2", notice_period="3",
        willing_to_relocate="yes", remote_preference="Remote",
        willing_to_travel="yes", years_experience="2", current_employer="ce",
        current_title="ct", highest_education="Master's",
        graduation_month="December", graduation_year="2025", gpa="3.2",
        how_heard_default="hh", selfid_gender="Man", selfid_race="Asian",
        selfid_veteran="Not a protected veteran", selfid_disability="No",
        selfid_orientation="Straight",
        # 021 (FR-031): asked on the applicant's real Workday application.
        phone_country_code="+1", security_clearance="no",
        drivers_licence="yes",
    )
    unresolved = [tag for tag in profile_answers.PROFILE_ANSWER_TAGS
                  if profile_answers.answer_for(tag, filled) is None]
    assert unresolved == []
