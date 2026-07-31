"""Per-ATS deterministic field maps (feature 009, FR-005).

Native Greenhouse/Lever/Ashby application forms use stable, known
name/id attributes — mapping them exactly beats heuristics on the boards
that dominate the watchlist. Consulted BEFORE the generic classifier
(engine/autofill/fields.py), which remains the fallback everywhere, so a
stale map degrades gracefully instead of failing.

The ATS is detected from the FRAME URL host (not job.source): jobspy and
curated-list rows frequently carry ATS-hosted apply URLs, and an embedded
Greenhouse iframe on a company site is still a Greenhouse form.

Maps are seeded from known ATS markup and verified by the fixture pages
(tests/fixtures/ats_pages/) and the release live gate. Custom questions
(e.g. Greenhouse job_application[answers_attributes][...]) deliberately
return None → the generic classifier / pause-for-review flow handles
them. Pure module: no browser or HTTP imports.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .fields import FieldDescriptor

# 016 (T015, constitution v1.1.4): per-ATS APPLY-OPENER selectors — the
# controls that ONLY open/reveal the application form on a posting page.
# SINGLE SOURCE for the allowlist; extension/content/opener.js mirrors
# these strings verbatim (asset-parity-tested). Never a submit control.
APPLY_OPENERS = {
    # 019 (T038, FR-022): modern job-boards.greenhouse.io does not reveal an
    # embedded form — its Apply control NAVIGATES to a separate application
    # page, and matches none of the 016 selectors. Both shapes are listed;
    # the opener still refuses anything of type=submit or any form already
    # holding typed values, so "navigates" never means "submits".
    "greenhouse": ("#apply_button, a[href='#application'], a[href*='#app'], "
                   "a.apply-button, a[href$='/application'], "
                   "a[href*='/application?']"),
    "lever": "a.postings-btn[href*='/apply'], a[href$='/apply']",
    "ashby": "a[href*='/application'], button[data-testid*='apply']",
}

# 019 (T062, FR-024): allowlist-first progression controls, per ATS. The
# advancer consults these before its conservative generic fallback, and a
# final-class name refuses the click regardless of which one matched.
# Mirrored in extension/content/advancer.js (asset-parity-tested).
ADVANCE_ALLOWLIST = {
    "workday": ("[data-automation-id='bottom-navigation-next-button'], "
                "[data-automation-id='next'], "
                "[data-automation-id='wd-CommandButton_uic_okButton']"),
    "greenhouse": "#btn-next, button[data-source='save_and_continue']",
    "lever": "button.template-btn-continue",
    "ashby": "button[data-testid*='continue']",
    "icims": "#quickApplyNextButton, .iCIMS_nextButton",
}

_HOSTS = {
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
    # 011: iCIMS + Taleo careers hosts (exact-or-subdomain match below)
    "icims.com": "icims",
    "taleo.net": "taleo",
}

# 011: Workday tenants are per-company dynamic subdomains
# (e.g. nvidia.wd5.myworkdayjobs.com) — matched by suffix, not exact host.
_WORKDAY_SUFFIX = "myworkdayjobs.com"

# exact name/id attribute → taxonomy tag, per ATS
_MAPS: dict[str, dict[str, str]] = {
    "greenhouse": {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "phone": "phone",
        "resume": "resume_upload",
        "cover_letter": "cover_letter",
        # classic embed (boards.greenhouse.io/embed) name= style
        "job_application[first_name]": "first_name",
        "job_application[last_name]": "last_name",
        "job_application[email]": "email",
        "job_application[phone]": "phone",
        "job_application[resume]": "resume_upload",
        "job_application[cover_letter]": "cover_letter",
        # 017 (C18): was free_text_unknown, so the model was asked
        # to guess where the applicant lives.
        "candidate-location": "location_full",
    },
    "lever": {
        "name": "full_name",
        "email": "email",
        "phone": "phone",
        "org": "free_text_unknown",  # current company — answer-bank territory
        "resume": "resume_upload",
        "comments": "cover_letter",
        "urls[LinkedIn]": "linkedin_url",
        "urls[GitHub]": "portfolio_url",
        "urls[Portfolio]": "portfolio_url",
        "urls[Other]": "free_text_unknown",
    },
    "ashby": {
        "_systemfield_name": "full_name",
        "_systemfield_email": "email",
        "_systemfield_phone": "phone",
        "_systemfield_resume": "resume_upload",
        "_systemfield_location": "location_full",  # 017 (C18)
    },
    # 011: iCIMS — stable lowercased field ids/names
    "icims": {
        "firstname": "first_name",
        "lastname": "last_name",
        "email": "email",
        "phone": "phone",
        "resume": "resume_upload",
    },
    # 011: Taleo — legacy camelCase names
    "taleo": {
        "firstName": "first_name",
        "lastName": "last_name",
        "email": "email",
        "emailAddress": "email",
        "phoneNumber": "phone",
        "homePhone": "phone",
    },
}

# 011: Workday keys on data-automation-id, not name/id — stable across
# tenants. Consulted first for the "workday" ATS.
_WORKDAY_AUTOMATION = {
    "legalNameSection_firstName": "first_name",
    "legalNameSection_lastName": "last_name",
    "legalNameSection_middleName": "middle_name",
    "preferredNameSection_firstName": "preferred_name",
    "email": "email",
    "phone-number": "phone",
    "phoneNumber": "phone",
    # 019 (T030, FR-013): the map covered seven keys, so every other Workday
    # control reached the classifier with an empty haystack. These are the
    # ones a new-grad application actually presents. Every value here is a
    # tag `profile_answers` can resolve — an invented tag would look mapped
    # and still fill nothing. Fields with no profile column (phone device
    # type, previous-worker) are deliberately absent: the automation_id now
    # reaches the classifier haystack, so they become an answerable question
    # instead of a silent nothing.
    "addressSection_addressLine1": "location_address1",
    "addressSection_addressLine2": "location_address2",
    "addressSection_city": "location_city",
    "addressSection_countryRegion": "location_state",
    "addressSection_postalCode": "location_postal",
    "countryDropdown": "location_country",
    "country": "location_country",
    "source": "how_heard",
    "sourceSection_source": "how_heard",
    "linkedinQuestion": "linkedin_url",
    "websiteSection_url": "portfolio_url",
    "degree": "degree",
    "gpa": "gpa",
    "startDate": "start_date",
}

# HTML autocomplete attribute — the highest-confidence signal any form can
# carry; shared across all known ATSes
_AUTOCOMPLETE = {
    "given-name": "first_name",
    "family-name": "last_name",
    "name": "full_name",
    "email": "email",
    "tel": "phone",
    "url": "portfolio_url",
}


def ats_from_url(url: str | None) -> str | None:
    host = urlsplit(url or "").netloc.lower()
    # Workday tenants are dynamic subdomains under myworkdayjobs.com
    if host == _WORKDAY_SUFFIX or host.endswith(f".{_WORKDAY_SUFFIX}"):
        return "workday"
    for known, ats in _HOSTS.items():
        if host == known or host.endswith(f".{known}"):
            return ats
    return None


def classify(ats: str | None, field: FieldDescriptor) -> str | None:
    """Deterministic tag for a known ATS's native attribute, else None
    (caller falls back to the generic classifier)."""
    # 011: Workday keys on data-automation-id first.
    if ats == "workday":
        aid = field.get("automation_id") or ""
        if aid in _WORKDAY_AUTOMATION:
            return _WORKDAY_AUTOMATION[aid]
        autocomplete = (field.get("autocomplete") or "").lower()
        return _AUTOCOMPLETE.get(autocomplete)

    mapping = _MAPS.get(ats or "")
    if not mapping:
        return None
    for key in (field.get("name"), field.get("id")):
        if key and key in mapping:
            return mapping[key]
    autocomplete = (field.get("autocomplete") or "").lower()
    if autocomplete in _AUTOCOMPLETE:
        return _AUTOCOMPLETE[autocomplete]
    return None
