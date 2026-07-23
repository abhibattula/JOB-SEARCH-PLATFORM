"""LinkedIn link-outs (feature 008, FR-016).

Unauthenticated LinkedIn scraping rate-limits within a few hundred results
and sustaining it needs paid proxies (rejected: $0 constitution), so the
honest way to keep LinkedIn reachable is one-click search URLs the user
opens in their own logged-in browser. f_TPR=r1209600 = posted within
1,209,600 seconds (14 days) — matching the app's freshness window.
"""
from __future__ import annotations

from urllib.parse import urlencode

FOURTEEN_DAYS_SECONDS = 14 * 24 * 3600


def search_url(keywords: str, location: str | None = None) -> str:
    params = {"keywords": keywords, "f_TPR": f"r{FOURTEEN_DAYS_SECONDS}"}
    if location:
        params["location"] = location
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def url_for_job(job: dict) -> str:
    return search_url(job.get("title") or "")


def url_for_profile(profile: dict | None) -> str:
    """Search built from the profile's first derived term (falls back to a
    sensible new-grad query), targeted at the first preferred location."""
    profile = profile or {}
    stored = profile.get("search_terms") or {}
    terms = stored.get("terms") if isinstance(stored, dict) else None
    keywords = (terms[0] if terms else None) or "entry level engineer"
    locations = profile.get("target_locations") or []
    return search_url(keywords, location=locations[0] if locations else None)
