"""Shared ingestion primitives: RawJob, polite HTTP helpers, HTML stripping.

Politeness contract (Constitution III): at most one request per second per
domain, honest User-Agent, no auth or bot-protection bypass. The rate limit is
enforced process-wide and is thread-safe (sources run concurrently).
"""
from __future__ import annotations

import html
import re
import threading
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

import httpx

MIN_REQUEST_INTERVAL = 1.0  # seconds, per domain
USER_AGENT = "PersonalJobEngine/1.0 (personal job search; single user)"

_LAST_REQUEST: dict[str, float] = {}
_RATE_LOCK = threading.Lock()
_client: httpx.Client | None = None
_CLIENT_LOCK = threading.Lock()


@dataclass
class RawJob:
    title: str
    company: str
    url: str
    source: str
    location: str | None = None
    is_remote: bool = False
    description: str = ""
    posted_date: str | None = None  # ISO date (YYYY-MM-DD)
    company_ats_type: str | None = None
    company_ats_slug: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _get_client() -> httpx.Client:
    global _client
    with _CLIENT_LOCK:
        if _client is None:
            _client = httpx.Client(
                timeout=25,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
        return _client


def _respect_rate_limit(domain: str) -> None:
    with _RATE_LOCK:
        last = _LAST_REQUEST.get(domain)
        if last is not None:
            wait = MIN_REQUEST_INTERVAL - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        _LAST_REQUEST[domain] = time.monotonic()


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    _respect_rate_limit(urlparse(url).netloc)
    client = _get_client()
    try:
        response = client.request(method, url, **kwargs)
        if response.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"server error {response.status_code}",
                request=response.request,
                response=response,
            )
    except (httpx.TransportError, httpx.HTTPStatusError):
        time.sleep(2)
        _respect_rate_limit(urlparse(url).netloc)
        response = client.request(method, url, **kwargs)
    response.raise_for_status()
    return response


def polite_get(url: str, **kwargs) -> httpx.Response:
    return _request("GET", url, **kwargs)


def polite_post(url: str, **kwargs) -> httpx.Response:
    return _request("POST", url, **kwargs)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """Flatten (possibly escaped) HTML into readable plain text."""
    if not text:
        return ""
    unescaped = html.unescape(text)
    unescaped = re.sub(r"<(br|/p|/div|/li|/h[1-6])[^>]*>", " ", unescaped, flags=re.I)
    stripped = _TAG_RE.sub("", unescaped)
    return _WS_RE.sub(" ", html.unescape(stripped)).strip()
