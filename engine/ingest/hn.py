"""Hacker News "Ask HN: Who is hiring?" via the Algolia API.

Comments conventionally start with a pipe-delimited header line:
"Company | Role | Location | ...". Comments that don't fit are skipped.
Each comment's own created_at is the posting date (never the thread date).
"""
from __future__ import annotations

import logging
from typing import Iterator

from .base import RawJob, polite_get, strip_html

SOURCE_NAME = "hn"
log = logging.getLogger(__name__)

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"


def _find_latest_thread_id() -> str | None:
    payload = polite_get(
        SEARCH_URL,
        params={
            "query": "Ask HN: Who is hiring?",
            "tags": "story,author_whoishiring",
            "hitsPerPage": 5,
        },
    ).json()
    for hit in payload.get("hits", []):
        if str(hit.get("title", "")).startswith("Ask HN: Who is hiring?"):
            return str(hit["objectID"])
    return None


def _parse_comment(comment: dict) -> RawJob | None:
    text = comment.get("text") or ""
    if not text:
        return None
    first_line = strip_html(text.split("<p>", 1)[0])
    parts = [part.strip() for part in first_line.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    company, title = parts[0], parts[1]
    if len(company) > 60 or len(title) > 120:
        return None  # prose that happened to contain a pipe
    location = parts[2] if len(parts) > 2 else None
    header = " ".join(parts).lower()
    return RawJob(
        title=title,
        company=company,
        url=f"https://news.ycombinator.com/item?id={comment['id']}",
        source=SOURCE_NAME,
        location=location,
        is_remote="remote" in header,
        description=strip_html(text),
        posted_date=(comment.get("created_at") or "")[:10] or None,
    )


def fetch_jobs(entries: list[dict]) -> Iterator[RawJob]:  # entries unused
    thread_id = _find_latest_thread_id()
    if thread_id is None:
        log.warning("hn: no who-is-hiring thread found")
        return
    item = polite_get(ITEM_URL.format(id=thread_id)).json()
    for comment in item.get("children") or []:
        job = _parse_comment(comment)
        if job is not None:
            yield job
