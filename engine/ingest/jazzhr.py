"""JazzHR public board feed:
GET {slug}.applytojob.com/apply/jobs.json

021 (FR-033): keyless and official. JazzHR carries a lot of small US
employers, which is exactly the band a new grad is competing least hard in.
"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_get, strip_html

SOURCE_NAME = "jazzhr"
log = logging.getLogger(__name__)


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            payload = polite_get(
                f"https://{slug}.applytojob.com/apply/jobs.json").json()
        except Exception:
            log.warning("jazzhr %s failed", slug, exc_info=True)
            continue
        jobs = payload if isinstance(payload, list) else (
            payload.get("jobs") or [])
        for job in jobs:
            city = str(job.get("city") or "").strip()
            state = str(job.get("state") or "").strip()
            board_code = job.get("board_code")
            yield RawJob(
                title=(job.get("title") or "").strip(),
                company=entry["name"],
                url=(f"https://{slug}.applytojob.com/apply/{board_code}"
                     if board_code else (job.get("url") or "")),
                source=SOURCE_NAME,
                location=", ".join(filter(None, (city, state))) or None,
                is_remote="remote" in f"{city} {state}".lower(),
                description=strip_html(job.get("description") or ""),
                posted_date=(job.get("original_open_date") or "")[:10] or None,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
