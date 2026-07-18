"""Best-effort volume source via python-jobspy (Indeed; LinkedIn opt-in).

jobspy scrapes sites we don't rate-limit ourselves, so this source is treated
as expendable: Indeed-only unless JOBSPY_LINKEDIN=1, every search isolated,
and failures never abort the run. Duplicates with ATS sources collapse via the
cross-source dedup key.
"""
from __future__ import annotations

import logging
import os
from typing import Iterator

from .base import RawJob

SOURCE_NAME = "jobspy"
log = logging.getLogger(__name__)

SEARCH_TERMS = [
    "new grad software engineer",
    "entry level software engineer",
    "entry level hardware engineer",
    "new grad hardware engineer FPGA ASIC",
    "embedded software engineer new grad",
    "design verification engineer entry level",
    "software developer entry level",
]
RESULTS_PER_SEARCH = 40
HOURS_OLD = 24 * 8  # slightly beyond the 7-day feed window


def _scrape(**kwargs):
    from jobspy import scrape_jobs  # heavy import, deferred

    return scrape_jobs(**kwargs)


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:  # entries unused
    import pandas as pd

    sites = ["indeed"]
    if os.environ.get("JOBSPY_LINKEDIN") == "1":
        sites.append("linkedin")
    seen: set[str] = set()
    for term in SEARCH_TERMS:
        try:
            frame = _scrape(
                site_name=sites,
                search_term=term,
                location="United States",
                results_wanted=RESULTS_PER_SEARCH,
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
