"""SimplifyJobs/New-Grad-Positions — the canonical community-maintained
new-grad job list, published as listings.json in a public GitHub repo.

Listings carry an explicit `sponsorship` field ("Offers Sponsorship",
"Does Not Offer Sponsorship", "U.S. Citizenship is Required", "Other"). The
value is appended verbatim to the description so the standard scanner in
engine/filters.py turns it into the job's eligibility rating with the field
text as evidence.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

from .base import RawJob, polite_get

SOURCE_NAME = "simplify"
log = logging.getLogger(__name__)

LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions"
    "/dev/.github/scripts/listings.json"
)


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:  # entries unused
    listings = polite_get(LISTINGS_URL).json()
    for item in listings:
        if not item.get("active") or item.get("is_visible") is False:
            continue
        title = (item.get("title") or "").strip()
        company = (item.get("company_name") or "").strip()
        url = item.get("url")
        if not title or not company or not url:
            continue
        locations = [loc for loc in (item.get("locations") or []) if loc]
        location = ", ".join(locations) or None
        posted = None
        if item.get("date_posted"):
            posted = datetime.fromtimestamp(
                item["date_posted"], tz=timezone.utc
            ).strftime("%Y-%m-%d")
        parts = []
        if item.get("category"):
            parts.append(f"Category: {item['category']}.")
        if item.get("sponsorship") and item["sponsorship"] != "Other":
            parts.append(f"Sponsorship: {item['sponsorship']}.")
        yield RawJob(
            title=title,
            company=company,
            url=url,
            source=SOURCE_NAME,
            location=location,
            is_remote="remote" in (location or "").lower(),
            description=" ".join(parts),
            posted_date=posted,
        )
