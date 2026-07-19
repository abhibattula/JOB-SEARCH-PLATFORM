"""Check GitHub Releases for a newer version. Best-effort and silent on any
failure — an offline machine must never notice this exists."""
from __future__ import annotations

import logging
import re

from . import APP_VERSION

log = logging.getLogger(__name__)

RELEASES_API = (
    "https://api.github.com/repos/abhibattula/JOB-SEARCH-PLATFORM/releases/latest"
)
RELEASES_PAGE = "https://github.com/abhibattula/JOB-SEARCH-PLATFORM/releases"


def _parse(version: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (version or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer(candidate: str, than: str) -> bool:
    parsed_candidate, parsed_current = _parse(candidate), _parse(than)
    if parsed_candidate is None or parsed_current is None:
        return False
    return parsed_candidate > parsed_current


def _fetch_latest() -> dict:
    import httpx

    response = httpx.get(
        RELEASES_API,
        timeout=5,
        headers={"Accept": "application/vnd.github+json"},
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.json()


def check() -> dict | None:
    """Return {latest, url, newer} or None when the check can't run."""
    try:
        release = _fetch_latest()
        tag = release.get("tag_name") or ""
        return {
            "latest": tag.lstrip("v"),
            "url": release.get("html_url") or RELEASES_PAGE,
            "newer": is_newer(tag, than=APP_VERSION),
        }
    except Exception:
        log.info("update check unavailable", exc_info=True)
        return None
