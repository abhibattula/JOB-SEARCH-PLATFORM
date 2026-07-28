"""017-T004: engine/autofill/vocab.py — canonical values and the surface
forms real ATS forms use for them.

Why this exists: match_option's three passes are exact / prefix /
rapidfuzz>=87. "Male" vs "Man" scores ~57 and "Y" vs "Yes" scores 50, so a
stored self-identification simply never matched a form that worded its
options differently (feature 017, C15). Matching is EXACT on canonical form
— it must never introduce fuzziness, because the same machinery decides
work-authorization dropdowns where a wrong answer is worse than a blank.
"""
import pytest

from engine.autofill import vocab


# --- gender -----------------------------------------------------------

@pytest.mark.parametrize("surface,expected", [
    ("Man", "Man"),
    ("man", "Man"),
    ("Male", "Man"),
    ("male", "Man"),
    ("M", "Man"),
    ("Woman", "Woman"),
    ("Female", "Woman"),
    ("F", "Woman"),
    ("Non-binary", "Non-binary"),
    ("Nonbinary", "Non-binary"),
    ("Non binary", "Non-binary"),
    ("Prefer not to say", "Prefer not to say"),
])
def test_gender_surfaces_resolve_to_canonical(surface, expected):
    assert vocab.canonical("gender", surface) == expected


def test_gender_never_cross_matches():
    """The failure that would be worse than not matching at all."""
    assert vocab.canonical("gender", "Male") != "Woman"
    assert vocab.canonical("gender", "Female") != "Man"


# --- sexual orientation ----------------------------------------------

@pytest.mark.parametrize("surface,expected", [
    ("Straight", "Straight"),
    ("Heterosexual", "Straight"),
    ("heterosexual", "Straight"),
    ("Gay", "Gay"),
    ("Lesbian", "Lesbian"),
    ("Bisexual", "Bisexual"),
])
def test_orientation_surfaces(surface, expected):
    assert vocab.canonical("orientation", surface) == expected


# --- decline / prefer not to say --------------------------------------

@pytest.mark.parametrize("surface", [
    "Prefer not to say",
    "I don't wish to answer",
    "I do not wish to answer",
    "Decline to self-identify",
    "Decline to self identify",
    "I don't wish to disclose",
    "I prefer not to answer",
])
def test_decline_surfaces(surface):
    assert vocab.canonical("decline", surface) == "Prefer not to say"


def test_decline_is_reachable_from_every_selfid_family():
    """A stored 'Prefer not to say' must match the decline option whatever
    family the question belongs to."""
    for family in ("gender", "race", "veteran", "disability", "orientation",
                   "pronouns"):
        assert vocab.canonical(family, "Decline to self-identify") == \
            "Prefer not to say", family


# --- yes / no ---------------------------------------------------------

@pytest.mark.parametrize("surface,expected", [
    ("Yes", "Yes"),
    ("yes", "Yes"),
    ("Y", "Yes"),
    ("No", "No"),
    ("N", "No"),
])
def test_yes_no_surfaces(surface, expected):
    assert vocab.canonical("yes_no", surface) == expected


def test_yes_no_never_cross_matches():
    assert vocab.canonical("yes_no", "Yes") != "No"
    assert vocab.canonical("yes_no", "N") != "Yes"


# --- work authorization: strictness must NOT be loosened (FR-025) -----

def test_work_auth_accepts_only_bare_affirmatives():
    assert vocab.canonical("work_auth", "Yes") == "Yes"
    assert vocab.canonical("work_auth", "No") == "No"


@pytest.mark.parametrize("loose", [
    "authorized",
    "eligible",
    "citizen",
    "I am authorized",
    "work permit",
])
def test_work_auth_rejects_semantic_expansion(loose):
    """A wrong authorization answer is worse than an unfilled one — this
    family carries no semantic synonyms, only literal yes/no tokens."""
    assert vocab.canonical("work_auth", loose) is None


# --- pronouns ---------------------------------------------------------

@pytest.mark.parametrize("surface,expected", [
    ("He/him", "He/him"),
    ("He/him/his", "He/him"),
    ("he / him / his", "He/him"),
    ("She/her", "She/her"),
    ("She/her/hers", "She/her"),
    ("They/them", "They/them"),
    ("They/them/theirs", "They/them"),
])
def test_pronoun_surfaces(surface, expected):
    assert vocab.canonical("pronouns", surface) == expected


# --- race / ethnicity -------------------------------------------------

@pytest.mark.parametrize("surface,expected", [
    ("Hispanic or Latino", "Hispanic or Latino"),
    ("Hispanic/Latino", "Hispanic or Latino"),
    ("Asian", "Asian"),
    ("Black or African American", "Black or African American"),
    ("Black/African American", "Black or African American"),
    ("White", "White"),
    ("Two or More Races", "Two or more races"),
])
def test_race_surfaces(surface, expected):
    assert vocab.canonical("race", surface) == expected


# --- veteran / disability --------------------------------------------

def test_veteran_surfaces():
    assert vocab.canonical("veteran", "I am a protected veteran") == \
        "Protected veteran"
    assert vocab.canonical(
        "veteran", "I am not a protected veteran") == "Not a protected veteran"


def test_disability_surfaces():
    assert vocab.canonical("disability", "Yes") == "Yes"
    assert vocab.canonical("disability", "No") == "No"
    assert vocab.canonical(
        "disability",
        "No, I do not have a disability") == "No"


# --- education level --------------------------------------------------

@pytest.mark.parametrize("surface,expected", [
    ("Bachelor's", "Bachelor's"),
    ("Bachelors", "Bachelor's"),
    ("Bachelor's Degree", "Bachelor's"),
    ("BS", "Bachelor's"),
    ("B.S.", "Bachelor's"),
    ("Master's", "Master's"),
    ("MS", "Master's"),
    ("M.S.", "Master's"),
    ("PhD", "Doctorate"),
    ("Doctorate", "Doctorate"),
    ("High School", "High school"),
])
def test_education_surfaces(surface, expected):
    assert vocab.canonical("education_level", surface) == expected


# --- remote preference ------------------------------------------------

@pytest.mark.parametrize("surface,expected", [
    ("Remote", "Remote"),
    ("Fully remote", "Remote"),
    ("Hybrid", "Hybrid"),
    ("On-site", "On-site"),
    ("Onsite", "On-site"),
    ("In office", "On-site"),
])
def test_remote_preference_surfaces(surface, expected):
    assert vocab.canonical("remote_pref", surface) == expected


# --- tag -> family ----------------------------------------------------

@pytest.mark.parametrize("tag,family", [
    ("selfid_gender", "gender"),
    ("selfid_race", "race"),
    ("selfid_veteran", "veteran"),
    ("selfid_disability", "disability"),
    ("selfid_orientation", "orientation"),
    ("pronouns", "pronouns"),
    ("work_authorization", "work_auth"),
    ("sponsorship_requirement", "work_auth"),
    ("highest_education", "education_level"),
    ("remote_preference", "remote_pref"),
    ("age_18_plus", "yes_no"),
    ("background_check", "yes_no"),
])
def test_family_for_tag(tag, family):
    assert vocab.family_for_tag(tag) == family


@pytest.mark.parametrize("tag", [
    "free_text_unknown", "cover_letter", "first_name", "salary_expectation",
    None,
])
def test_tags_without_a_family(tag):
    """Open-ended and identity tags have no canonical vocabulary — matching
    them must fall through to the existing passes untouched."""
    assert vocab.family_for_tag(tag) is None


# --- general behaviour -------------------------------------------------

def test_unknown_family_and_unknown_text_return_none():
    assert vocab.canonical("not_a_family", "Man") is None
    assert vocab.canonical("gender", "Enterprise Architect") is None


@pytest.mark.parametrize("noisy", [
    "  Man  ",
    "Man.",
    "Man*",
    "MAN",
    "Man ",          # non-breaking space, common in ATS option labels
])
def test_surface_matching_tolerates_form_noise(noisy):
    assert vocab.canonical("gender", noisy) == "Man"


def test_empty_and_placeholder_text_is_not_a_match():
    for text in ("", "   ", None, "Select...", "--"):
        assert vocab.canonical("gender", text) is None


def test_canonical_values_are_self_resolving():
    """Every canonical value must resolve to itself — otherwise a stored
    profile value could fail to match its own option."""
    for family, canon_map in vocab.FAMILIES.items():
        for canonical_value in canon_map:
            assert vocab.canonical(family, canonical_value) == canonical_value, \
                f"{family}/{canonical_value}"


def test_surfaces_are_unambiguous_within_a_family():
    """No surface form may map to two canonical values in the same family —
    that would make matching order-dependent."""
    for family, canon_map in vocab.FAMILIES.items():
        seen = {}
        for canonical_value, surface_forms in canon_map.items():
            for surface in (canonical_value,) + tuple(surface_forms):
                key = vocab.normalize(surface)
                assert key not in seen or seen[key] == canonical_value, (
                    f"{family}: {surface!r} maps to both {seen.get(key)!r} "
                    f"and {canonical_value!r}")
                seen[key] = canonical_value
