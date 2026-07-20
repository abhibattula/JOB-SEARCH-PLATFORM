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

_WORK_AUTH_RE = re.compile(
    r"authoriz(e|ation)\w*\s.{0,30}work|legally\s.{0,20}work|work\s.{0,20}(authorization|permit)",
    re.IGNORECASE,
)
_SPONSORSHIP_RE = re.compile(r"sponsor(ship)?", re.IGNORECASE)
_EEO_RE = re.compile(
    r"disabilit\w*|veteran|race\b|ethnicit\w*|gender\s*identity|\beeo\b|equal\s*employment",
    re.IGNORECASE,
)
_YEARS_EXPERIENCE_RE = re.compile(
    r"years?\s.{0,15}experience|experience\s.{0,15}years?", re.IGNORECASE
)
_SALARY_RE = re.compile(r"salary|compensation|pay\s.{0,10}expect", re.IGNORECASE)
_HOW_HEARD_RE = re.compile(
    r"how\s.{0,15}(did you\s)?hear|referral\s*source|how\sdid\syou\sfind", re.IGNORECASE
)
_LINKEDIN_RE = re.compile(r"linkedin", re.IGNORECASE)
_PORTFOLIO_RE = re.compile(r"portfolio|github|personal\s*website|website\s*url", re.IGNORECASE)
_PHONE_RE = re.compile(r"phone|mobile|telephone", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\bemail\b", re.IGNORECASE)
_FIRST_NAME_RE = re.compile(r"first\s*name", re.IGNORECASE)
_LAST_NAME_RE = re.compile(r"last\s*name", re.IGNORECASE)
_FULL_NAME_RE = re.compile(r"full\s*name|your\s*name|\bname\b", re.IGNORECASE)
_COVER_LETTER_RE = re.compile(r"cover\s*letter", re.IGNORECASE)
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

    # Links.
    if _LINKEDIN_RE.search(text):
        return "linkedin_url"
    if _PORTFOLIO_RE.search(text):
        return "portfolio_url"

    # Basic identity fields.
    if field_type == "tel" or _PHONE_RE.search(text):
        return "phone"
    if is_email_shaped:
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
