"""Workable public jobs API (v3):
POST apply.workable.com/api/v3/accounts/{slug}/jobs

Note: the v1 widget API returns an empty jobs list as of 2026-07; the v3
POST endpoint (used by the hosted board itself) is the working path. Boards
are small (startups), so one page suffices; descriptions are not fetched
(one request per job would be impolite) — classification is title-based,
like Workday.
"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_post

SOURCE_NAME = "workable"
log = logging.getLogger(__name__)

_BODY = {
    "query": "", "department": [], "location": [],
    "remote": [], "workplace": [], "worktype": [],
}
_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            payload = polite_post(
                f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
                json=_BODY,
                headers={**_HEADERS, "Referer": f"https://apply.workable.com/{slug}/"},
            ).json()
        except Exception:
            log.warning("workable %s failed", slug, exc_info=True)
            continue
        for job in payload.get("results") or []:
            location = job.get("location") or {}
            city = location.get("city") or ""
            country = location.get("country") or ""
            yield RawJob(
                title=(job.get("title") or "").strip(),
                company=entry["name"],
                url=f"https://apply.workable.com/{slug}/j/{job['shortcode']}/",
                source=SOURCE_NAME,
                location=", ".join(filter(None, (city, country))) or None,
                is_remote=bool(job.get("remote")),
                description="",
                posted_date=(job.get("published") or "")[:10] or None,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
