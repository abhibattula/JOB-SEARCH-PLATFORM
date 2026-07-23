"""Lever public postings API: api.lever.co/v0/postings/{slug}?mode=json"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

from .base import RawJob, board_ok, polite_get, strip_html

SOURCE_NAME = "lever"
log = logging.getLogger(__name__)


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            postings = polite_get(
                f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}
            ).json()
        except Exception:
            log.warning("lever board %s failed", slug, exc_info=True)
            continue
        if not isinstance(postings, list):
            continue
        for job in postings:
            categories = job.get("categories") or {}
            location = categories.get("location")
            workplace = (job.get("workplaceType") or "").lower()
            posted = None
            if job.get("createdAt"):
                posted = datetime.fromtimestamp(
                    job["createdAt"] / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d")
            yield RawJob(
                title=job.get("text", "").strip(),
                company=entry["name"],
                url=job["hostedUrl"],
                source=SOURCE_NAME,
                location=location,
                is_remote=workplace == "remote" or "remote" in (location or "").lower(),
                description=job.get("descriptionPlain")
                or strip_html(job.get("description", "")),
                posted_date=posted,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
