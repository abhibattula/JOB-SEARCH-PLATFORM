"""LLM match analysis via any OpenAI-compatible endpoint (Groq free tier by
default; Gemini or local Ollama swap in through env vars — Constitution II).

Output is schema-validated (pydantic); one retry on invalid output, then the
job is simply left unscored (FR-012). Calls are throttled to stay inside
free-tier rate limits.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

from pydantic import BaseModel, Field, ValidationError

from . import local_llm

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
MAX_CHARS = 6000  # truncate resume/JD to keep prompts inside context politely

_throttle_lock = threading.Lock()
_last_call = 0.0


class GapAction(BaseModel):
    action: str
    impact: str = ""


class MatchAnalysis(BaseModel):
    match_score: float = Field(ge=0, le=100)
    matching_skills: list[str] = []
    missing_skills: list[str] = []
    gap_actions: list[GapAction] = []
    reasoning: str = ""


def llm_available() -> bool:
    from . import settings

    return bool(settings.get("LLM_API_KEY")) or local_llm.available()


def scoring_tier() -> str:
    """Which tier will actually serve the next call: cloud > local > basic.
    'basic' means neither an LLM tier is available; callers fall back to
    engine/basic_match.py entirely (no _chat call at all) in that case."""
    from . import settings

    if settings.get("LLM_API_KEY"):
        return "cloud"
    if local_llm.available():
        return "local"
    return "basic"


def _min_interval() -> float:
    # ~28 requests/min default, under Groq's 30 RPM free-tier limit
    return float(os.environ.get("LLM_MIN_INTERVAL", "2.2"))


def _chat_cloud(messages: list[dict]) -> str:
    global _last_call
    with _throttle_lock:
        wait = _min_interval() - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    from openai import OpenAI

    from . import settings

    client = OpenAI(
        base_url=settings.get("LLM_BASE_URL") or DEFAULT_BASE_URL,
        api_key=settings.get("LLM_API_KEY"),
    )
    completion = client.chat.completions.create(
        model=settings.get("LLM_MODEL") or DEFAULT_MODEL,
        messages=messages,
        temperature=0.2,
    )
    return completion.choices[0].message.content or ""


def _chat_local(messages: list[dict]) -> str:
    return local_llm.chat(messages)


def _chat(messages: list[dict]) -> str:
    """Tier dispatcher: cloud (Groq/OpenAI-compatible API) > local (bundled
    model) > raise. Existing callers (analyze_match, extract_skills) already
    try/except around _chat and degrade gracefully on failure, so no call
    site needs to change for the new tier."""
    from . import settings

    if settings.get("LLM_API_KEY"):
        return _chat_cloud(messages)
    if local_llm.available():
        return _chat_local(messages)
    raise RuntimeError("no LLM tier available (no cloud key, no local model)")


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def _extract_json(raw: str) -> str:
    match = _FENCE_RE.search(raw)
    if match:
        return match.group(1)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        return raw[start : end + 1]
    return raw


_SYSTEM = (
    "You are a precise technical recruiter assistant. Compare the candidate's "
    "resume against the job description. Respond with ONLY a JSON object, no "
    "prose, matching exactly this schema: {\"match_score\": 0-100, "
    "\"matching_skills\": [string], \"missing_skills\": [string], "
    "\"gap_actions\": [{\"action\": string, \"impact\": string}], "
    "\"reasoning\": string}. gap_actions are specific resume improvements "
    "(e.g. \"Add your FPGA lab project with cycle-accurate simulation results\")."
)


def analyze_match(
    resume_text: str, title: str, company: str, description: str
) -> MatchAnalysis | None:
    if not llm_available():
        return None
    user = (
        f"RESUME:\n{resume_text[:MAX_CHARS]}\n\n"
        f"JOB: {title} at {company}\n"
        f"DESCRIPTION:\n{description[:MAX_CHARS]}"
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
    for attempt in range(2):
        try:
            raw = _chat(messages)
        except Exception:
            log.warning("LLM call failed (attempt %d)", attempt + 1, exc_info=True)
            continue
        try:
            return MatchAnalysis.model_validate_json(_extract_json(raw))
        except (ValidationError, json.JSONDecodeError, ValueError):
            log.info("invalid LLM output on attempt %d", attempt + 1)
    return None


def extract_skills(resume_text: str) -> list[str]:
    if not llm_available():
        return []
    messages = [
        {
            "role": "system",
            "content": "Extract the candidate's technical skills. Respond with ONLY "
            "a JSON array of short skill strings, no prose.",
        },
        {"role": "user", "content": resume_text[:MAX_CHARS]},
    ]
    try:
        raw = _chat(messages)
        parsed = json.loads(_extract_json(raw).replace("```", ""))
        if isinstance(parsed, list):
            return [str(skill) for skill in parsed][:40]
    except Exception:
        log.warning("skill extraction failed", exc_info=True)
    return []
