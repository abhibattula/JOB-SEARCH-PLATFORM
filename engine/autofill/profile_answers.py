"""017 (R12): the single mapping from a classified question to a value the
applicant actually gave us.

WHY THIS EXISTS
---------------
`browser_controller._value_for_tag` had grown into a 75-line `if tag ==`
ladder that could only be exercised through a browser, and feature 017 roughly
triples the tag count. Pulling the mapping into a pure module makes it
unit-testable, keeps both fill backends identical, and gives the answer-shape
rule one place to consult.

THE RULE THAT MATTERS MOST
--------------------------
A blank profile field yields None. None means "leave the form field alone and
flag it for the applicant" — never an empty string, never a guess, and never a
fallback to a related field. The live 2026-07-28 run filled "Do you have a
preferred name?" with the legal full name precisely because a blank was
treated as an invitation to substitute something adjacent (FR-023).

Pure module: reads a profile dict, returns text. No I/O, no model, no browser.
"""
from __future__ import annotations

# tag -> profile column, for the tags that are a straight lookup.
_DIRECT: dict[str, str] = {
    # identity
    "first_name": "first_name",
    "last_name": "last_name",
    "preferred_name": "preferred_name",
    "middle_name": "middle_name",
    "pronouns": "pronouns",
    "email": "email",
    "phone": "phone",
    # links
    "linkedin_url": "linkedin_url",
    "portfolio_url": "portfolio_url",
    "github_url": "github_url",
    "other_url": "other_url",
    # address
    "location_address1": "address_line1",
    "location_address2": "address_line2",
    "location_city": "city",
    "location_state": "state_region",
    "location_postal": "postal_code",
    "location_country": "country",
    # work authorization detail — each of these was filled with "Yes" on the
    # live run because it had no column of its own to answer from.
    "work_auth_status": "work_auth_type",
    "work_auth_expiry": "work_auth_expiry",
    "work_auth_extensions": "work_auth_extensions",
    "sponsorship_detail": "sponsorship_detail",
    # experience facts
    "years_experience": "years_experience",
    "current_employer": "current_employer",
    "current_title": "current_title",
    "highest_education": "highest_education",
    "degree": "highest_education",
    "gpa": "gpa",
    # preferences
    "salary_expectation": "desired_salary",
    "start_date": "earliest_start_date",
    "notice_period": "notice_period",
    "remote_preference": "remote_preference",
    # defaults
    "how_heard": "how_heard_default",
    # voluntary self-identification (D1) — stored by the applicant only,
    # never inferred, never sent to a model.
    "selfid_gender": "selfid_gender",
    "selfid_race": "selfid_race",
    "selfid_veteran": "selfid_veteran",
    "selfid_disability": "selfid_disability",
    "selfid_orientation": "selfid_orientation",
}

# tag -> profile column, where the column stores yes/no and the form wants a
# capitalised token.
_YES_NO: dict[str, str] = {
    "relocate": "willing_to_relocate",
    "travel": "willing_to_travel",
}

# Tags this module can answer. Anything outside it falls through to the
# answer bank and then to the drafter.
PROFILE_ANSWER_TAGS = frozenset(
    set(_DIRECT)
    | set(_YES_NO)
    | {"full_name", "location_full", "graduation_date",
       "work_authorization", "sponsorship_requirement"}
)


def _get(profile: dict, column: str) -> str | None:
    """A stripped value, or None when the column is blank or absent.

    Absent matters: a database created before these columns existed will not
    carry them, and that must behave exactly like blank rather than raising.
    """
    value = (profile or {}).get(column)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _yes_no(value: str | None) -> str | None:
    if value is None:
        return None
    folded = value.strip().casefold()
    if folded in ("yes", "y", "true"):
        return "Yes"
    if folded in ("no", "n", "false"):
        return "No"
    return value


def answer_for(tag: str | None, profile: dict) -> str | None:
    """The applicant's own answer to a classified question, or None.

    None is a first-class result meaning "we were not told" — the caller
    leaves the field untouched and flags it. It never means "make something
    up" and never licenses a substitute value from a neighbouring field.
    """
    if not tag:
        return None

    if tag in _DIRECT:
        return _get(profile, _DIRECT[tag])

    if tag in _YES_NO:
        return _yes_no(_get(profile, _YES_NO[tag]))

    if tag == "full_name":
        first = _get(profile, "first_name")
        last = _get(profile, "last_name")
        # Both parts or nothing — a lone first name in a "Full name" box is a
        # wrong answer, not a partial one.
        if not first or not last:
            return None
        return f"{first} {last}"

    if tag == "location_full":
        stored = _get(profile, "current_location")
        if stored:
            return stored
        city = _get(profile, "city")
        if not city:
            return None
        parts = [city]
        for column in ("state_region", "country"):
            value = _get(profile, column)
            if value:
                parts.append(value)
        return ", ".join(parts)

    if tag == "graduation_date":
        year = _get(profile, "graduation_year")
        if not year:
            return None
        month = _get(profile, "graduation_month")
        return f"{month} {year}" if month else year

    if tag == "work_authorization":
        # Deliberately conservative, carried over from qa.profile_fact_answer:
        # work authorization is only derivable when the applicant is
        # authorized WITHOUT sponsorship. Someone who will need future
        # sponsorship may still be authorized today (OPT), which one field
        # cannot express, so that case stays with the human.
        if _get(profile, "authorized_without_sponsorship") == "yes":
            return "Yes"
        return None

    if tag == "sponsorship_requirement":
        explicit = _yes_no(_get(profile, "sponsorship_future"))
        if explicit is not None:
            return explicit
        authorized = _get(profile, "authorized_without_sponsorship")
        if authorized == "yes":
            return "No"
        if authorized == "no":
            return "Yes"
        return None

    return None
