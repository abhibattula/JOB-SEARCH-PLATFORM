"""Greenhouse public board API: boards-api.greenhouse.io/v1/boards/{slug}/jobs"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_get, strip_html

SOURCE_NAME = "greenhouse"
log = logging.getLogger(__name__)


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            payload = polite_get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                params={"content": "true"},
            ).json()
        except Exception:
            log.warning("greenhouse board %s failed", slug, exc_info=True)
            continue
        for job in payload.get("jobs", []):
            location = (job.get("location") or {}).get("name")
            posted = job.get("first_published") or job.get("updated_at") or ""
            yield RawJob(
                title=job.get("title", "").strip(),
                company=entry["name"],
                url=job["absolute_url"],
                source=SOURCE_NAME,
                location=location,
                is_remote="remote" in (location or "").lower(),
                description=strip_html(job.get("content", "")),
                posted_date=posted[:10] or None,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
