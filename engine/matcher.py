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
    """Which tier will actually serve the next call. 009 (FR-017): with
    PREFER_LOCAL_LLM on (the default), the bundled offline model serves
    everything when present — even with a cloud key saved; the key becomes
    the automatic fallback on local failure. 'basic' means no LLM tier at
    all; callers use engine/basic_match.py (no _chat call)."""
    from . import settings

    prefer_local = settings.get("PREFER_LOCAL_LLM") != "0"
    if prefer_local and local_llm.available():
        return "local"
    if settings.get("LLM_API_KEY"):
        return "cloud"
    if local_llm.available():
        return "local"
    return "basic"


def _min_interval() -> float:
    # ~28 requests/min default, under Groq's 30 RPM free-tier limit
    return float(os.environ.get("LLM_MIN_INTERVAL", "2.2"))


def _chat_cloud(messages: list[dict], purpose: str = "prose") -> str:
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
    # 008 (FR-026): structured tasks use the strict-JSON model with JSON
    # mode (on Groq, gpt-oss models guarantee schema-valid output); prose
    # (bullets, cover letters) keeps the conversational default.
    if purpose == "json":
        kwargs = {
            "model": settings.get("LLM_JSON_MODEL")
            or settings.get("LLM_MODEL") or DEFAULT_MODEL,
            "response_format": {"type": "json_object"},
        }
    else:
        kwargs = {"model": settings.get("LLM_MODEL") or DEFAULT_MODEL}
    completion = client.chat.completions.create(
        messages=messages,
        temperature=0.2,
        **kwargs,
    )
    return completion.choices[0].message.content or ""


def _chat_local(messages: list[dict], purpose: str = "prose") -> str:
    return local_llm.chat(messages, json_mode=purpose == "json")


def _chat(messages: list[dict], purpose: str = "prose") -> str:
    """Tier dispatcher, driven by scoring_tier() (single source of truth).
    009 (FR-017): a preferred-local failure falls through to the cloud key
    automatically when one exists. purpose="json" routes structured tasks
    to the schema-reliable model/decoding on each tier."""
    from . import settings

    tier = scoring_tier()
    if tier == "local":
        try:
            return _chat_local(messages, purpose=purpose)
        except Exception:
            if settings.get("LLM_API_KEY"):
                log.warning("local tier failed — falling through to cloud",
                            exc_info=True)
                return _chat_cloud(messages, purpose=purpose)
            raise
    if tier == "cloud":
        return _chat_cloud(messages, purpose=purpose)
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
            raw = _chat(messages, purpose="json")
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
