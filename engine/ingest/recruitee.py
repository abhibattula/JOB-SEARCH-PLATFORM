"""Recruitee public careers API:
GET {slug}.recruitee.com/api/offers/

021 (FR-033): a keyless, official JSON board endpoint on the same shape as
greenhouse/lever/ashby, so it qualifies as a FULL_BOARD source — absence from
a successful fetch authoritatively means the posting is gone, which the
delisting logic already depends on. It also reaches the employer's own
careers page, so the apply URL is the genuine one rather than an aggregator's
copy of it.
"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, board_ok, polite_get, strip_html

SOURCE_NAME = "recruitee"
log = logging.getLogger(__name__)


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        slug = entry["slug"]
        try:
            payload = polite_get(
                f"https://{slug}.recruitee.com/api/offers/").json()
        except Exception:
            # Constitution III / FR-033: one source failing must never abort
            # the others.
            log.warning("recruitee %s failed", slug, exc_info=True)
            continue
        for job in payload.get("offers") or []:
            city = job.get("city") or ""
            country = job.get("country") or ""
            yield RawJob(
                title=(job.get("title") or "").strip(),
                company=entry["name"],
                url=job.get("careers_url") or job.get("url") or "",
                source=SOURCE_NAME,
                location=", ".join(filter(None, (city, country))) or None,
                is_remote=bool(job.get("remote")),
                description=strip_html(job.get("description") or ""),
                posted_date=(job.get("published_at") or "")[:10] or None,
                company_ats_type=SOURCE_NAME,
                company_ats_slug=slug,
            )
        board_ok(SOURCE_NAME, slug)
