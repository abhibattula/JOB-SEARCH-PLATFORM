"""Workday CxS JSON endpoint: {host}/wday/cxs/{tenant}/{site}/jobs

NOTE (2026-07): most Workday tenants sit behind Cloudflare fingerprinting that
serves the HTML shell to plain HTTP clients, so no Workday entries ship in the
default companies.yml. The parser is fixture-tested and works if that changes;
failures degrade gracefully via per-source isolation.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Iterator

from .base import RawJob, polite_post

SOURCE_NAME = "workday"
log = logging.getLogger(__name__)

PAGE_SIZE = 20
MAX_PAGES = 5  # large tenants list thousands of roles; cap politely

_JSON_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
_DAYS_RE = re.compile(r"posted\s+(\d+)(\+?)\s+days?\s+ago", re.I)


def parse_posted_on(posted_on: str | None) -> str | None:
    """Convert Workday's relative strings ("Posted 3 Days Ago") to ISO dates."""
    if not posted_on:
        return None
    text = posted_on.strip().lower()
    today = date.today()
    if "today" in text or "just posted" in text:
        return today.isoformat()
    if "yesterday" in text:
        return (today - timedelta(days=1)).isoformat()
    match = _DAYS_RE.search(text)
    if match:
        days = int(match.group(1)) + (1 if match.group(2) else 0)
        return (today - timedelta(days=days)).isoformat()
    return None


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:
    for entry in entries:
        host, site = entry["host"], entry["site"]
        tenant = host.split(".")[0]
        search = entry.get("search", "engineer")
        endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        offset = 0
        for _ in range(MAX_PAGES):
            try:
                payload = polite_post(
                    endpoint,
                    json={
                        "appliedFacets": {},
                        "limit": PAGE_SIZE,
                        "offset": offset,
                        "searchText": search,
                    },
                    headers=_JSON_HEADERS,
                ).json()
            except Exception:
                log.warning("workday %s/%s failed", tenant, site, exc_info=True)
                break
            postings = payload.get("jobPostings") or []
            for job in postings:
                path = job.get("externalPath") or ""
                yield RawJob(
                    title=job.get("title", "").strip(),
                    company=entry["name"],
                    url=f"https://{host}/en-US/{site}{path}",
                    source=SOURCE_NAME,
                    location=job.get("locationsText"),
                    is_remote="remote" in (job.get("locationsText") or "").lower(),
                    description="",  # detail view requires one request per job
                    posted_date=parse_posted_on(job.get("postedOn")),
                    company_ats_type=SOURCE_NAME,
                    company_ats_slug=f"{host}|{site}",
                )
            offset += PAGE_SIZE
            total = payload.get("total") or 0
            if offset >= total or not postings:
                break
