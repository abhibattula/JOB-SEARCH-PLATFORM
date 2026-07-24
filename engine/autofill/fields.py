"""Pure field-taxonomy classifier for Apply Assist (feature 005).

Operates on plain-dict field descriptors serialized from the DOM by
engine/autofill/browser_controller.py — never on live Playwright handles —
so this module stays fully unit-testable with literal fixtures and has no
browser/HTTP imports (Constitution IV: Reusable Core).

Legally-sensitive categories (work_authorization, sponsorship_requirement,
eeo_disclosure) are matched before any generic catch-all, per spec FR-012 —
this taxonomy is intentionally open/extensible, not a fixed two-item list.
login_email/login_password require corroborating context beyond a bare
field type, so a saved credential is never routed into an unrelated field
(research.md §6).
"""
from __future__ import annotations

import re
from typing import Any

FieldDescriptor = dict[str, Any]

# Deliberately excludes <button> and input[type=submit|button|reset] — the
# fill engine has nothing to click, so it collects nothing clickable in the
# first place (first layer of the never-clicks invariant; the second is
# that no fill path contains a click call). Lives here (pure module) so
# every serializer shares one definition.
FIELD_QUERY_SELECTOR = (
    "input:not([type=submit]):not([type=button]):not([type=reset]),"
    " textarea, select,"
    # 011: custom dropdowns that are not native <select> — React-Select and
    # ARIA comboboxes/listboxes (Workday, Greenhouse's newer widgets, etc.)
    " [role=combobox], [role=listbox], [aria-haspopup=listbox],"
    " [class*=select__control]"
)

_WORK_AUTH_RE = re.compile(
    r"authoriz(e|ation)\w*\s.{0,30}work|legally\s.{0,20}work|work\s.{0,20}(authorization|permit)",
    re.IGNORECASE,
)
_SPONSORSHIP_RE = re.compile(r"sponsor(ship)?", re.IGNORECASE)
_EEO_RE = re.compile(
    r"disabilit\w*|veteran|race\b|ethnicit\w*|gender\s*identity|\beeo\b|equal\s*employment",
    re.IGNORECASE,
)
# 009 (FR-005): word separators are [\s_-]* — real ATS markup carries raw
# attributes like first_name / first-name / firstname, which plain \s*
# never matched (root cause A7: fills silently depended on visible labels).
_YEARS_EXPERIENCE_RE = re.compile(
    r"years?[\s_-].{0,15}experience|experience[\s_-].{0,15}years?", re.IGNORECASE
)
_SALARY_RE = re.compile(r"salary|compensation|pay[\s_-].{0,10}expect", re.IGNORECASE)
_HOW_HEARD_RE = re.compile(
    r"how[\s_-].{0,15}hear|referral[\s_-]*source|how[\s_-]did[\s_-]you[\s_-]find",
    re.IGNORECASE,
)
# 011: Workday-style typeahead fields — factual, answer-bank-driven (never
# AI-drafted). "city"/"location" and "school"/"university".
_LOCATION_CITY_RE = re.compile(
    r"\bcity\b|current[\s_-]*location|where[\s_-].{0,20}(located|live)|"
    r"\blocation\b(?!.*preferen)",
    re.IGNORECASE,
)
_SCHOOL_RE = re.compile(
    r"\bschool\b|\buniversity\b|\bcollege\b|\binstitution\b|alma[\s_-]*mater",
    re.IGNORECASE,
)
_LINKEDIN_RE = re.compile(r"linkedin", re.IGNORECASE)
_PORTFOLIO_RE = re.compile(
    r"portfolio|github|personal[\s_-]*website|website[\s_-]*url", re.IGNORECASE
)
_PHONE_RE = re.compile(r"phone|mobile|telephone", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\bemail\b", re.IGNORECASE)
_FIRST_NAME_RE = re.compile(r"first[\s_-]*name|given[\s_-]*name", re.IGNORECASE)
_LAST_NAME_RE = re.compile(r"last[\s_-]*name|family[\s_-]*name|surname", re.IGNORECASE)
_FULL_NAME_RE = re.compile(r"full[\s_-]*name|your[\s_-]*name|\bname\b", re.IGNORECASE)
_COVER_LETTER_RE = re.compile(r"cover[\s_-]*letter", re.IGNORECASE)
_RESUME_RE = re.compile(r"resume|r[eé]sum[eé]|\bcv\b", re.IGNORECASE)


def _haystack(field: FieldDescriptor) -> str:
    parts = (
        field.get("label_text") or "",
        field.get("placeholder") or "",
        field.get("aria_label") or "",
        field.get("name") or "",
        field.get("id") or "",
    )
    return " ".join(parts)


def classify(field: FieldDescriptor) -> str:
    """Return one taxonomy tag for a serialized form-field descriptor."""
    field_type = (field.get("type") or "").lower()
    tag = (field.get("tag") or "").lower()
    text = _haystack(field)
    autocomplete = (field.get("autocomplete") or "").lower()
    form_context = field.get("form_context")

    # Login fields: require corroborating context, never just a bare type.
    if field_type == "password":
        # type=password has no other legitimate use on a job application —
        # it is itself the corroborating signal.
        return "login_password"
    is_email_shaped = field_type == "email" or _EMAIL_RE.search(text)
    if is_email_shaped and form_context == "login" and autocomplete in ("username", "email"):
        return "login_email"

    # Legally-sensitive categories — checked before any generic catch-all.
    if _WORK_AUTH_RE.search(text):
        return "work_authorization"
    if _SPONSORSHIP_RE.search(text):
        return "sponsorship_requirement"
    if _EEO_RE.search(text):
        return "eeo_disclosure"

    # File uploads — default to resume unless clearly a cover letter upload.
    if field_type == "file":
        if _COVER_LETTER_RE.search(text) and not _RESUME_RE.search(text):
            return "cover_letter"
        return "resume_upload"

    # Q&A-bank style fields.
    if _YEARS_EXPERIENCE_RE.search(text):
        return "years_experience"
    if _SALARY_RE.search(text):
        return "salary_expectation"
    if _HOW_HEARD_RE.search(text):
        return "how_heard"
    if _SCHOOL_RE.search(text):
        return "school"
    if _LOCATION_CITY_RE.search(text):
        return "location_city"

    # Links.
    if _LINKEDIN_RE.search(text):
        return "linkedin_url"
    if _PORTFOLIO_RE.search(text):
        return "portfolio_url"

    # Basic identity fields. The HTML autocomplete attribute is the
    # highest-confidence identity signal a form can carry (009 FR-005).
    if autocomplete == "given-name":
        return "first_name"
    if autocomplete == "family-name":
        return "last_name"
    if autocomplete == "name":
        return "full_name"
    if field_type == "tel" or autocomplete == "tel" or _PHONE_RE.search(text):
        return "phone"
    if is_email_shaped or autocomplete == "email":
        return "email"
    if _FIRST_NAME_RE.search(text):
        return "first_name"
    if _LAST_NAME_RE.search(text):
        return "last_name"
    if _FULL_NAME_RE.search(text):
        return "full_name"

    if tag == "textarea" and _COVER_LETTER_RE.search(text):
        return "cover_letter"

    return "free_text_unknown"


# --- structured-input option matching (007, FR-006) --------------------------

# Minimum rapidfuzz ratio for a fuzzy option match. Deliberately strict:
# a wrong structured answer (especially on an authorization dropdown) is
# worse than an unfilled one, which is merely reported for manual review.
# Exercised from both sides by tests/test_fields.py::TestMatchOption.
OPTION_MATCH_CONFIDENCE = 87


def match_option(answer: str, options: list[str]) -> str | None:
    """Pick the option whose text best matches a confirmed answer, or None
    when no option matches confidently (the field is then left untouched
    and reported unfilled — never guessed)."""
    from rapidfuzz import fuzz

    normalized_answer = (answer or "").strip().casefold()
    if not normalized_answer or not options:
        return None

    normalized = [(option, (option or "").strip().casefold()) for option in options]

    for option, text in normalized:
        if text == normalized_answer:
            return option
    # "Yes" -> "Yes, I am authorized": the answer as the option's leading
    # word(s), ending at a word boundary — checked before any fuzzy pass so
    # yes/no pairs can never cross-match.
    for option, text in normalized:
        if text.startswith(normalized_answer):
            rest = text[len(normalized_answer):]
            if rest == "" or not rest[:1].isalnum():
                return option

    best_option, best_score = None, 0.0
    for option, text in normalized:
        score = fuzz.ratio(normalized_answer, text)
        if score > best_score:
            best_option, best_score = option, score
    if best_score >= OPTION_MATCH_CONFIDENCE:
        return best_option
    return None
