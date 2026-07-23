"""Per-job application tailoring: resume bullets rewritten to mirror a specific
JD's language, a short cover letter, and ATS keywords — generated from the
user's real resume only. The prompt hard-constrains the model to never invent
experience; tailoring means rephrasing and emphasis, not fiction.
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ValidationError

from . import matcher

log = logging.getLogger(__name__)


class TailorResult(BaseModel):
    summary_line: str
    tailored_bullets: list[str]
    cover_letter: str
    ats_keywords: list[str] = []


_SYSTEM = (
    "You tailor job applications. You will receive a candidate's REAL resume "
    "and one job posting. Produce ONLY a JSON object: {\"summary_line\": string "
    "(one resume headline tuned to this job), \"tailored_bullets\": [4-6 "
    "strings — the candidate's real experience rephrased to mirror this "
    "posting's terminology], \"cover_letter\": string (~180 words, specific, "
    "no fluff), \"ats_keywords\": [strings from the posting the resume should "
    "contain]}. HARD RULES: never invent employers, projects, degrees, "
    "metrics, tools, or experience absent from the resume; only rephrase and "
    "re-emphasize what is truly there. Do not mention visa status."
)


def tailor_for_job(
    resume_text: str, title: str, company: str, description: str
) -> TailorResult | None:
    if not matcher.llm_available():
        return None
    user = (
        f"RESUME:\n{resume_text[:matcher.MAX_CHARS]}\n\n"
        f"JOB: {title} at {company}\n"
        f"DESCRIPTION:\n{description[:matcher.MAX_CHARS]}"
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
    for attempt in range(2):
        try:
            raw = matcher._chat(messages, purpose="json")
        except Exception:
            log.warning("tailor LLM call failed (attempt %d)", attempt + 1, exc_info=True)
            continue
        try:
            return TailorResult.model_validate_json(matcher._extract_json(raw))
        except (ValidationError, json.JSONDecodeError, ValueError):
            log.info("invalid tailor output on attempt %d", attempt + 1)
    return None
