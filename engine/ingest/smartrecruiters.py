"""SmartRecruiters public postings API:
api.smartrecruiters.com/v1/companies/{company}/postings

The list payload has no full description, but it does carry the experience
level and function labels — those are appended to the description text so the
entry-level classifier's description scan can use them without a per-posting
detail request.
"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_get

SOURCE_NAME = "smartrecruiters"
log = logging.getLogger(__name__)

PAGE_LIMIT = 100
MAX_PAGES = 2  # politeness cap per company


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        offset = 0
        complete = False
        for _ in range(MAX_PAGES):
            try:
                payload = polite_get(
                    f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                    # country=us keeps global tenants (e.g. Bosch: 4.7k postings
                    # worldwide, ~280 US) inside the spec's US scope
                    params={"limit": PAGE_LIMIT, "offset": offset, "country": "us"},
                ).json()
            except Exception:
                log.warning("smartrecruiters %s failed", slug, exc_info=True)
                break
            postings = payload.get("content") or []
            for job in postings:
                location = job.get("location") or {}
                level = (job.get("experienceLevel") or {}).get("label") or ""
                function = (job.get("function") or {}).get("label") or ""
                meta_desc = ". ".join(
                    part for part in (
                        f"Experience level: {level}" if level else "",
                        f"Function: {function}" if function else "",
                    ) if part
                )
                yield RawJob(
                    title=(job.get("name") or "").strip(),
                    company=entry["name"],
                    url=f"https://jobs.smartrecruiters.com/{slug}/{job['id']}",
                    source=SOURCE_NAME,
                    location=location.get("fullLocation")
                    or ", ".join(filter(None, (location.get("city"), location.get("region")))),
                    is_remote=bool(location.get("remote")),
                    description=meta_desc,
                    posted_date=(job.get("releasedDate") or "")[:10] or None,
                    company_ats_type=SOURCE_NAME,
                    company_ats_slug=slug,
                )
            offset += PAGE_LIMIT
            total = payload.get("totalFound") or 0
            if offset >= total or not postings:
                complete = True
                break
        # partial fetches (page cap hit / error) never authorize delisting
        if complete:
            board_ok(SOURCE_NAME, slug)
