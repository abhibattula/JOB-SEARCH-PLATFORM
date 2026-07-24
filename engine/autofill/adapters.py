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
        "candidate-location": "free_text_unknown",
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
        "_systemfield_location": "free_text_unknown",
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
    "email": "email",
    "phone-number": "phone",
    "phoneNumber": "phone",
    "addressSection_city": "location_city",
    "source": "how_heard",
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
