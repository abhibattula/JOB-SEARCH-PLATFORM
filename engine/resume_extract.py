"""Structured resume extraction (feature 007, US2).

Parses the uploaded resume's raw text into editable structured sections
via the existing LLM tier dispatcher (matcher._chat: cloud > local) with
the established schema-validate + one-bounded-retry idiom. Extraction
quality is deliberately not load-bearing: the Profile "Resume builder"
review step is the quality gate (spec FR-016), and with no AI tier the
same sections are simply filled in manually (FR-017).
"""
from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, field_validator

log = logging.getLogger(__name__)


class Contact(BaseModel):
    """008 (FR-022): identity details found in the resume header. Everything
    optional — a missing field stays blank, it is never invented."""

    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    location: str = ""


class ExperienceEntry(BaseModel):
    title: str = ""
    organization: str = ""
    start: str = ""
    end: str = ""
    bullets: list[str] = []


class EducationEntry(BaseModel):
    degree: str = ""
    institution: str = ""
    start: str = ""
    end: str = ""
    details: str = ""


class ProjectEntry(BaseModel):
    name: str = ""
    description: str = ""
    bullets: list[str] = []


def _non_empty(entry: BaseModel) -> bool:
    for value in entry.model_dump().values():
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and any(str(v).strip() for v in value):
            return True
    return False


class ResumeSections(BaseModel):
    experience: list[ExperienceEntry] = []
    education: list[EducationEntry] = []
    projects: list[ProjectEntry] = []
    skills: list[str] = []
    # 008 (FR-022/FR-025)
    contact: Contact | None = None
    target_titles: list[str] = []

    @field_validator("experience", "education", "projects")
    @classmethod
    def _drop_empty_entries(cls, entries):
        return [e for e in entries if _non_empty(e)]

    @field_validator("target_titles")
    @classmethod
    def _cap_titles(cls, titles):
        return [t.strip() for t in titles if t and t.strip()][:5]


_SYSTEM = (
    "You are a precise resume parser. Extract the candidate's resume into "
    "structured sections. Respond with ONLY a JSON object, no prose, matching "
    "exactly this schema: {\"experience\": [{\"title\": string, "
    "\"organization\": string, \"start\": string, \"end\": string, "
    "\"bullets\": [string]}], \"education\": [{\"degree\": string, "
    "\"institution\": string, \"start\": string, \"end\": string, "
    "\"details\": string}], \"projects\": [{\"name\": string, "
    "\"description\": string, \"bullets\": [string]}], \"skills\": [string], "
    "\"contact\": {\"first_name\": string, \"last_name\": string, "
    "\"email\": string, \"phone\": string, \"linkedin_url\": string, "
    "\"portfolio_url\": string, \"location\": string}, "
    "\"target_titles\": [string]}. "
    "Copy wording faithfully from the resume — never invent, embellish, or "
    "summarize away specifics. Dates as written (e.g. \"2025-05\" or "
    "\"May 2025\"). contact holds ONLY details literally present in the "
    "resume (empty string when absent — never guess). target_titles: up to "
    "5 job titles this resume is clearly aimed at, inferred from its "
    "experience and objective. Omit sections the resume does not contain."
)

# --- pattern-based contact fallback (FR-023: works with zero AI) ------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+", re.I)
_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/[\w-]+"
    r"|https?://[\w.-]+\.[a-z]{2,}(?:/[\w./-]*)?",
    re.I,
)


def _with_scheme(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


def extract_contact(resume_text: str) -> Contact:
    """Deterministic email/phone/link extraction from the resume header —
    the every-tier floor for identity auto-fill. Names and locations are
    left blank (not reliably regexable; blank beats wrong)."""
    head = "\n".join((resume_text or "").splitlines()[:15])
    email = _EMAIL_RE.search(head)
    phone = _PHONE_RE.search(head)
    linkedin = _LINKEDIN_RE.search(head)
    portfolio = None
    for match in _URL_RE.finditer(head):
        candidate = match.group(0)
        if "linkedin.com" in candidate.lower():
            continue
        if email and email.group(0) in candidate:
            continue
        portfolio = candidate
        break
    return Contact(
        email=email.group(0) if email else "",
        phone=phone.group(0).strip() if phone else "",
        linkedin_url=_with_scheme(linkedin.group(0)) if linkedin else "",
        portfolio_url=_with_scheme(portfolio) if portfolio else "",
    )


def extract(resume_text: str) -> ResumeSections | None:
    """Extract structured sections, or None when no AI tier is available
    or the model's output never validates (one bounded retry — the UI
    then falls back to manual entry; this function never raises)."""
    from . import matcher

    if matcher.scoring_tier() == "basic":
        return None
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": resume_text[:24000]},
    ]
    for attempt in (1, 2):
        try:
            raw = matcher._chat(messages)
            payload = json.loads(matcher._extract_json(raw))
            return ResumeSections.model_validate(payload)
        except Exception as exc:  # malformed JSON, schema mismatch, LLM error
            log.warning("resume extraction attempt %d failed: %s", attempt, exc)
    return None
