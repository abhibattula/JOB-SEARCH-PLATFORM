"""Teamtailor public careers feed:
GET {slug}.teamtailor.com/jobs.json

021 (FR-033): keyless and official. Teamtailor hosts a large number of
startup boards that never surface on the aggregators.
"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_get, strip_html

SOURCE_NAME = "teamtailor"
log = logging.getLogger(__name__)


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            payload = polite_get(
                f"https://{slug}.teamtailor.com/jobs.json").json()
        except Exception:
            log.warning("teamtailor %s failed", slug, exc_info=True)
            continue
        jobs = payload if isinstance(payload, list) else (
            payload.get("jobs") or [])
        for job in jobs:
            yield RawJob(
                title=(job.get("title") or "").strip(),
                company=entry["name"],
                url=job.get("careersite-job-url") or job.get("url") or "",
                source=SOURCE_NAME,
                location=job.get("location") or None,
                is_remote=job.get("remote-status") in ("fully", "hybrid", True),
                description=strip_html(job.get("body") or ""),
                posted_date=(job.get("created-at") or "")[:10] or None,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
