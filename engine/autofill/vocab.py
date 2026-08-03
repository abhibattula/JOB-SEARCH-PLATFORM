"""017 (R14): canonical values and the surface forms real ATS forms use.

WHY THIS EXISTS
---------------
`fields.match_option` matches a stored answer against a form's real options
in three passes: exact, prefix-on-word-boundary, then rapidfuzz >= 87. Those
passes cannot bridge vocabulary: "Male" vs "Man" scores ~57 and "Y" vs "Yes"
scores 50, so a self-identification the user had stored simply never matched
a form that worded its options differently (017, C15).

This module supplies a fourth, EXACT pass: map both sides into a canonical
form and compare. It deliberately adds no fuzziness — the same matcher
decides work-authorization dropdowns, where a wrong answer is worse than a
blank one, so `work_auth` carries literal yes/no tokens only and no semantic
expansion whatsoever (FR-025).

Pure module: no I/O, no model, no imports beyond the standard library.
"""
from __future__ import annotations

import re
import unicodedata

# Surface forms that mean "I decline to answer". Merged into every
# self-identification family below, because a stored "Prefer not to say"
# must match whichever wording the form happens to use.
_DECLINE_SURFACES = (
    "i don't wish to answer",
    "i do not wish to answer",
    "i don't wish to disclose",
    "i do not wish to disclose",
    "i prefer not to answer",
    "prefer not to answer",
    "decline to self-identify",
    "decline to self identify",
    "i decline to self-identify",
    "i decline to self identify",
    "decline to answer",
    "do not wish to answer",
)

_SELF_ID_FAMILIES = ("gender", "race", "veteran", "disability", "orientation",
                     "pronouns")

# family -> {canonical value: (surface forms, ...)}
FAMILIES: dict[str, dict[str, tuple[str, ...]]] = {
    "gender": {
        "Man": ("male", "m"),
        "Woman": ("female", "f"),
        "Non-binary": ("nonbinary", "non binary", "non-binary/third gender",
                       "genderqueer"),
        "Prefer not to say": (),
    },
    "orientation": {
        "Straight": ("heterosexual", "straight/heterosexual",
                     "heterosexual/straight"),
        "Gay": ("gay/lesbian", "homosexual"),
        "Lesbian": (),
        "Bisexual": ("bi",),
        "Prefer not to say": (),
    },
    "race": {
        "Hispanic or Latino": ("hispanic/latino", "hispanic",
                               "latino", "hispanic or latino (not of "
                               "hispanic origin)"),
        "White": ("white (not hispanic or latino)", "caucasian"),
        "Black or African American": ("black/african american", "black",
                                      "african american"),
        "Asian": ("asian (not hispanic or latino)",),
        "Native Hawaiian or Other Pacific Islander": (
            "native hawaiian/other pacific islander", "pacific islander"),
        "American Indian or Alaska Native": (
            "american indian/alaska native", "native american"),
        "Two or more races": ("two or more races (not hispanic or latino)",
                              "two or more", "multiracial"),
        "Prefer not to say": (),
    },
    "veteran": {
        "Protected veteran": (
            "i am a protected veteran",
            "i identify as one or more of the classifications of a "
            "protected veteran",
            "yes, i am a protected veteran"),
        "Not a protected veteran": (
            "i am not a protected veteran",
            "no, i am not a protected veteran",
            "i am not a veteran"),
        "Prefer not to say": (
            "i don't wish to answer, i decline to identify",),
    },
    "disability": {
        "Yes": ("y", "yes, i have a disability, or have had one in the past",
                "yes, i have a disability"),
        "No": ("n", "no, i do not have a disability",
               "no, i don't have a disability and have not had one in "
               "the past"),
        "Prefer not to say": (),
    },
    "pronouns": {
        "He/him": ("he/him/his", "he", "him"),
        "She/her": ("she/her/hers", "she", "her"),
        "They/them": ("they/them/theirs", "they", "them"),
        "Prefer not to say": (),
    },
    "yes_no": {
        "Yes": ("y", "true"),
        "No": ("n", "false"),
    },
    # FR-025: authorization answers carry NO semantic synonyms. Literal
    # yes/no tokens only — never "authorized", "eligible", "citizen".
    "work_auth": {
        "Yes": ("y",),
        "No": ("n",),
    },
    "education_level": {
        "High school": ("high school diploma", "hs", "ged",
                        "high school or equivalent"),
        "Associate": ("associates", "associate's", "associate's degree",
                      "associates degree", "aa", "as"),
        "Bachelor's": ("bachelors", "bachelor's degree", "bachelors degree",
                       "bachelor", "bs", "ba", "undergraduate"),
        "Master's": ("masters", "master's degree", "masters degree",
                     "master", "ms", "ma", "mba", "graduate"),
        "Doctorate": ("phd", "ph d", "doctoral", "doctorate degree",
                      "doctor of philosophy"),
    },
    "remote_pref": {
        "Remote": ("fully remote", "100% remote", "work from home"),
        "Hybrid": ("partially remote", "flexible"),
        "On-site": ("onsite", "in office", "in-office", "in person",
                    "in-person"),
        "No preference": ("any", "no preference/flexible"),
    },
}

# Tag -> family. Tags absent from this map have no canonical vocabulary and
# fall through to match_option's existing passes untouched.
_TAG_FAMILY: dict[str, str] = {
    "selfid_gender": "gender",
    "selfid_race": "race",
    "selfid_veteran": "veteran",
    "selfid_disability": "disability",
    "selfid_orientation": "orientation",
    "pronouns": "pronouns",
    # FR-025: strict family, no semantic expansion.
    "work_authorization": "work_auth",
    "sponsorship_requirement": "work_auth",
    "sponsorship_future": "work_auth",
    "highest_education": "education_level",
    "degree": "education_level",
    "remote_preference": "remote_pref",
    # Plain yes/no questions.
    "age_18_plus": "yes_no",
    "background_check": "yes_no",
    "drug_test": "yes_no",
    "non_compete": "yes_no",
    "security_clearance": "yes_no",
    "currently_employed": "yes_no",
    # 021 (FR-011): "I currently work here" on a repeated employment block.
    # Answered from the stored role's is_current flag, so it needs the same
    # yes/no option family every other checkbox question uses.
    "exp_current": "yes_no",
    "drivers_licence": "yes_no",
    "relocate": "yes_no",
    "travel": "yes_no",
    "applied_before": "yes_no",
    "worked_here_before": "yes_no",
    "prior_industry_experience": "yes_no",
    "completed_course": "yes_no",
    "criminal_history": "yes_no",
    "acknowledgement": "yes_no",
}


def _merge_decline_surfaces() -> None:
    """A stored 'Prefer not to say' must match the decline option in every
    self-identification family, whatever wording the form uses."""
    for family in _SELF_ID_FAMILIES:
        canon_map = FAMILIES[family]
        existing = canon_map.get("Prefer not to say", ())
        canon_map["Prefer not to say"] = tuple(
            dict.fromkeys(existing + _DECLINE_SURFACES))


_merge_decline_surfaces()

# Standalone family so a decline answer can be resolved without knowing the
# question's family (used by the panel and by profile-driven fills).
FAMILIES["decline"] = {"Prefer not to say": _DECLINE_SURFACES}


_WS = re.compile(r"\s+")
_SLASH = re.compile(r"\s*/\s*")
_EDGE = " *,:;!?-–—_()[]\"'"


def normalize(text: str | None) -> str:
    """Fold a form's option label or a stored value to a comparable key.

    Handles the noise real ATS markup carries: non-breaking spaces, trailing
    asterisks on required labels, abbreviating periods (B.S. == BS), and
    inconsistent spacing around slashes (He / him / his == He/him/his).
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", str(text))
    folded = folded.replace(" ", " ").replace(".", "")
    folded = _WS.sub(" ", folded).strip()
    folded = _SLASH.sub("/", folded)
    return folded.strip(_EDGE).casefold()


def _index(family: str) -> dict[str, str]:
    canon_map = FAMILIES.get(family)
    if canon_map is None:
        return {}
    index: dict[str, str] = {}
    for canonical_value, surface_forms in canon_map.items():
        for surface in (canonical_value,) + tuple(surface_forms):
            key = normalize(surface)
            if key:
                index.setdefault(key, canonical_value)
    return index


_INDEXES: dict[str, dict[str, str]] = {}


def canonical(family: str | None, text: str | None) -> str | None:
    """The canonical value `text` denotes within `family`, or None.

    Matching is EXACT on the normalized form — never fuzzy. A miss returns
    None so the caller leaves the field unfilled and flagged rather than
    approximating (FR-028).
    """
    if not family:
        return None
    key = normalize(text)
    if not key:
        return None
    if family not in _INDEXES:
        _INDEXES[family] = _index(family)
    return _INDEXES[family].get(key)


def family_for_tag(tag: str | None) -> str | None:
    """The canonical vocabulary family a classified question belongs to, or
    None when the question has no fixed answer set (open-ended text,
    identity fields, salary, and so on)."""
    if not tag:
        return None
    return _TAG_FAMILY.get(tag)


def surfaces(family: str, canonical_value: str) -> tuple[str, ...]:
    """Every accepted surface form for a canonical value, canonical first.
    Used when the form's options are not readable until the widget opens and
    the filler must try candidate labels."""
    canon_map = FAMILIES.get(family) or {}
    if canonical_value not in canon_map:
        return ()
    return (canonical_value,) + tuple(canon_map[canonical_value])
