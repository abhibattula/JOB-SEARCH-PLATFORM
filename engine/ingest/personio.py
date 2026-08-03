"""Personio public jobs feed:
GET {slug}.jobs.personio.com/search.json

021 (FR-033): keyless and official.
"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_get, strip_html

SOURCE_NAME = "personio"
log = logging.getLogger(__name__)


def _description(job: dict) -> str:
    """Personio splits the description into named blocks."""
    blocks = job.get("jobDescriptions")
    if isinstance(blocks, list):
        return strip_html(" ".join(
            str(block.get("value") or "") if isinstance(block, dict)
            else str(block) for block in blocks))
    return strip_html(str(blocks or job.get("description") or ""))


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            payload = polite_get(
                f"https://{slug}.jobs.personio.com/search.json").json()
        except Exception:
            log.warning("personio %s failed", slug, exc_info=True)
            continue
        jobs = payload if isinstance(payload, list) else (
            payload.get("jobs") or [])
        for job in jobs:
            office = job.get("office") or job.get("location") or ""
            yield RawJob(
                title=(job.get("name") or job.get("title") or "").strip(),
                company=entry["name"],
                url=(job.get("url")
                     or f"https://{slug}.jobs.personio.com/job/{job.get('id')}"),
                source=SOURCE_NAME,
                location=office or None,
                is_remote="remote" in str(office).lower(),
                description=_description(job),
                posted_date=(job.get("createdAt") or "")[:10] or None,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
