"""Breezy HR public positions feed:
GET {slug}.breezy.hr/json

021 (FR-033): keyless and official.
"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_get, strip_html

SOURCE_NAME = "breezy"
log = logging.getLogger(__name__)


def _place(job: dict) -> tuple[str | None, bool]:
    location = job.get("location")
    if not isinstance(location, dict):
        text = str(location or "").strip()
        return (text or None, "remote" in text.lower())
    city = str(location.get("city") or "").strip()
    country = location.get("country")
    country_name = (country.get("name") if isinstance(country, dict)
                    else str(country or "")).strip()
    joined = ", ".join(filter(None, (city, country_name)))
    return (joined or None, bool(location.get("is_remote")))


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            payload = polite_get(f"https://{slug}.breezy.hr/json").json()
        except Exception:
            log.warning("breezy %s failed", slug, exc_info=True)
            continue
        jobs = payload if isinstance(payload, list) else (
            payload.get("positions") or [])
        for job in jobs:
            location, remote = _place(job)
            yield RawJob(
                title=(job.get("name") or "").strip(),
                company=entry["name"],
                url=(job.get("url")
                     or f"https://{slug}.breezy.hr/p/{job.get('id')}"),
                source=SOURCE_NAME,
                location=location,
                is_remote=remote,
                description=strip_html(job.get("description") or ""),
                posted_date=(job.get("published_date")
                             or job.get("creation_date") or "")[:10] or None,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
