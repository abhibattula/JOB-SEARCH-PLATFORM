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

from pydantic import BaseModel, field_validator

log = logging.getLogger(__name__)


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

    @field_validator("experience", "education", "projects")
    @classmethod
    def _drop_empty_entries(cls, entries):
        return [e for e in entries if _non_empty(e)]


_SYSTEM = (
    "You are a precise resume parser. Extract the candidate's resume into "
    "structured sections. Respond with ONLY a JSON object, no prose, matching "
    "exactly this schema: {\"experience\": [{\"title\": string, "
    "\"organization\": string, \"start\": string, \"end\": string, "
    "\"bullets\": [string]}], \"education\": [{\"degree\": string, "
    "\"institution\": string, \"start\": string, \"end\": string, "
    "\"details\": string}], \"projects\": [{\"name\": string, "
    "\"description\": string, \"bullets\": [string]}], \"skills\": [string]}. "
    "Copy wording faithfully from the resume — never invent, embellish, or "
    "summarize away specifics. Dates as written (e.g. \"2025-05\" or "
    "\"May 2025\"). Omit sections the resume does not contain."
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
