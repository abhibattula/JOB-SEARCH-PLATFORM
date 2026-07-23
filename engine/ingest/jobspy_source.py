"""Best-effort volume source via python-jobspy (Indeed + Google; LinkedIn
opt-in).

jobspy scrapes sites we don't rate-limit ourselves, so this source is treated
as expendable: every search isolated, failures never abort the run, LinkedIn
stays opt-in (unauthenticated scraping rate-limits within a few hundred
results — see research.md §4). Duplicates with ATS sources collapse via the
cross-source dedup key.

008: sites/volume are settings, hours_old covers the 14-day window and is
passed ALONE (jobspy treats it as mutually exclusive with
job_type/is_remote/easy_apply — those must stay client-side), and search
terms/locations come from the user's profile when present (FR-025).
"""
from __future__ import annotations

import logging
from itertools import product
from typing import Iterator

from .base import RawJob

SOURCE_NAME = "jobspy"
log = logging.getLogger(__name__)

# Built-in fallback terms — used only when the profile has none (FR-025).
SEARCH_TERMS = [
    "new grad software engineer",
    "entry level software engineer",
    "entry level hardware engineer",
    "new grad hardware engineer FPGA ASIC",
    "embedded software engineer new grad",
    "design verification engineer entry level",
    "software developer entry level",
]
HOURS_OLD = 24 * 14  # the 14-day freshness window (FR-012)
MAX_SEARCHES_PER_RUN = 8  # politeness cap: terms x locations never exceeds this


def _scrape(**kwargs):
    from jobspy import scrape_jobs  # heavy import, deferred

    return scrape_jobs(**kwargs)


def _search_plan() -> list[tuple[str, str]]:
    """(term, location) pairs: profile-driven when the profile has derived/
    edited search terms, built-in defaults otherwise. Term-major order so the
    top terms get every location before the cap cuts off."""
    from engine import db

    profile = db.get_profile() or {}
    stored = profile.get("search_terms")
    terms = None
    if isinstance(stored, dict):
        terms = [t.strip() for t in (stored.get("terms") or [])
                 if isinstance(t, str) and t.strip()]
    if not terms:
        terms = list(SEARCH_TERMS)
    locations = [loc.strip() for loc in (profile.get("target_locations") or [])
                 if isinstance(loc, str) and loc.strip()]
    if not locations:
        locations = ["United States"]
    return list(product(terms, locations))[:MAX_SEARCHES_PER_RUN]


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:  # entries unused
    import pandas as pd

    from engine import settings

    sites = [s.strip() for s in (settings.get("JOBSPY_SITES") or "indeed,google").split(",")
             if s.strip()]
    if settings.get("JOBSPY_LINKEDIN") == "1" and "linkedin" not in sites:
        sites.append("linkedin")
    results_wanted = int(settings.get("JOBSPY_RESULTS_PER_SEARCH") or "40")
    seen: set[str] = set()
    for term, location in _search_plan():
        try:
            frame = _scrape(
                site_name=sites,
                search_term=term,
                location=location,
                results_wanted=results_wanted,
                hours_old=HOURS_OLD,
                country_indeed="USA",
            )
        except Exception:
            log.warning("jobspy search %r failed", term, exc_info=True)
            continue
        if frame is None or len(frame) == 0:
            continue
        for row in frame.to_dict("records"):
            url = row.get("job_url")
            title = row.get("title")
            company = row.get("company")
            if not url or not title or not company or url in seen:
                continue
            if pd.isna(url) or pd.isna(title) or pd.isna(company):
                continue
            seen.add(url)
            posted = row.get("date_posted")
            posted_iso = None
            if posted is not None and not pd.isna(posted):
                posted_iso = str(posted)[:10]
            description = row.get("description")
            if description is None or pd.isna(description):
                description = ""
            location = row.get("location")
            if location is None or pd.isna(location):
                location = None
            yield RawJob(
                title=str(title).strip(),
                company=str(company).strip(),
                url=str(url),
                source=SOURCE_NAME,
                location=location,
                is_remote=bool(row.get("is_remote"))
                or "remote" in (location or "").lower(),
                description=str(description),
                posted_date=posted_iso,
            )
