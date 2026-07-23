"""Ashby public posting API: api.ashbyhq.com/posting-api/job-board/{slug}"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_get, strip_html

SOURCE_NAME = "ashby"
log = logging.getLogger(__name__)


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            payload = polite_get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
            ).json()
        except Exception:
            log.warning("ashby board %s failed", slug, exc_info=True)
            continue
        for job in payload.get("jobs", []):
            if job.get("isListed") is False:
                continue
            posted = (job.get("publishedAt") or "")[:10] or None
            location = job.get("location")
            yield RawJob(
                title=job.get("title", "").strip(),
                company=entry["name"],
                url=job.get("jobUrl") or job.get("applyUrl"),
                source=SOURCE_NAME,
                location=location,
                is_remote=bool(job.get("isRemote"))
                or "remote" in (location or "").lower(),
                description=job.get("descriptionPlain")
                or strip_html(job.get("descriptionHtml", "")),
                posted_date=posted,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
