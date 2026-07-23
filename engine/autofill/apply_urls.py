"""Posting URL → application-form URL resolution (feature 009, FR-002).

Root cause A2: the stored job.url is the POSTING page on several ATSes —
the actual form lives at a sibling path. Pure function, no network:

- Lever:  jobs.lever.co/<org>/<posting-id>       → …/apply
- Ashby:  jobs.ashbyhq.com/<org>/<posting-id>    → …/application
- Greenhouse: form is inline on the posting page — unchanged
- Everything else: unchanged (the live watcher fills whatever form the
  user reveals, and the UI guides them to click the site's own Apply)
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def _with_suffix(url: str, suffix: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    if path.endswith(f"/{suffix}"):
        return url
    # only suffix a concrete posting path (org + posting id), never an
    # org landing page
    if len([seg for seg in path.split("/") if seg]) < 2:
        return url
    return urlunsplit(
        (parts.scheme, parts.netloc, f"{path}/{suffix}", parts.query, parts.fragment)
    )


def resolve(job: dict) -> str:
    url = job.get("url") or ""
    host = urlsplit(url).netloc.lower()
    if host.endswith("jobs.lever.co"):
        return _with_suffix(url, "apply")
    if host.endswith("jobs.ashbyhq.com"):
        return _with_suffix(url, "application")
    return url
