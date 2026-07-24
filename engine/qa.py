"""Grounded AI drafting for open-ended application questions (feature 010).

Draft → the caller fills and flags it → the user reviews before submitting.
This module only produces the draft text, and it does so under three hard
rules:

1. **Fail-closed sensitivity.** Only questions whose classified tag is on a
   small ALLOWLIST are ever drafted. Work-authorization, visa/sponsorship,
   and EEO/demographic questions are never AI-answered (FR-014); neither is
   anything unrecognized — a novel tag defaults to *not* eligible.
2. **Grounding only.** The prompt carries only the user's own resume/
   profile/saved answers plus the job's title/company/description. The model
   is told to invent nothing (FR-011).
3. **Refusal over fabrication.** Thin grounding, an empty response, or the
   model's explicit refusal token all yield None — the caller then leaves
   the field untouched and reports needs_manual (FR-015). We never fill a
   guess.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# The ONLY tags that may receive an AI draft. Allowlist, not blocklist:
# fail-closed means a tag we don't recognize is never drafted.
AI_ELIGIBLE_TAGS = frozenset({"cover_letter", "free_text_unknown"})

# Concise by default (~60-120 words); competitors' "obviously templated"
# essays are the anti-goal.
DEFAULT_MAXLEN = 700
MAX_PROMPT_CHARS = 6000
_MIN_GROUNDING_CHARS = 40
_REFUSAL_TOKEN = "CANNOT_ANSWER"


def is_ai_eligible(tag: str | None) -> bool:
    return tag in AI_ELIGIBLE_TAGS


def _grounding(profile: dict) -> str:
    parts = []
    resume = (profile or {}).get("resume_text") or ""
    if resume.strip():
        parts.append(resume.strip())
    for key in ("first_name", "last_name"):
        if profile.get(key):
            parts.append(f"{key}: {profile[key]}")
    return "\n".join(parts).strip()


def _generate(prompt: str, maxlen: int) -> str:
    """Run the prompt through the existing tier dispatcher (offline-first,
    cloud fall-through). Isolated so tests can stub the model."""
    from . import matcher

    messages = [
        {"role": "system", "content":
            "You help a job applicant draft a short, specific, honest answer "
            "using ONLY the facts provided. Invent nothing — no employers, "
            "dates, or credentials not present. If the provided facts do not "
            f"support an answer, reply with exactly {_REFUSAL_TOKEN}. "
            "Answer in 60-120 words, professional and direct, citing one or "
            "two concrete facts. Output ONLY the answer."},
        {"role": "user", "content": prompt},
    ]
    return matcher._chat(messages).strip()


def draft(question: str, tag: str | None, profile: dict, job: dict | None = None,
          maxlength: int | None = None) -> str | None:
    """Return a grounded draft answer, or None to leave the field alone."""
    if not is_ai_eligible(tag):
        return None  # fail-closed: sensitive/unknown questions are never drafted

    grounding = _grounding(profile)
    if len(grounding) < _MIN_GROUNDING_CHARS:
        return None  # nothing real to ground in — refuse, never fabricate

    from . import matcher

    if not matcher.llm_available():
        return None

    job = job or {}
    job_ctx = (
        f"ROLE: {job.get('title', '')} at {job.get('company', '')}\n"
        f"ABOUT THE ROLE: {(job.get('description') or '')[:800]}\n"
    )
    prompt = (
        f"QUESTION: {question}\n\n{job_ctx}\n"
        f"APPLICANT FACTS (use only these):\n{grounding}"
    )[:MAX_PROMPT_CHARS]

    target = DEFAULT_MAXLEN
    if maxlength and maxlength > 0:
        target = min(target, maxlength)

    try:
        out = _generate(prompt, target)
    except Exception:
        log.debug("draft generation failed", exc_info=True)
        return None

    out = (out or "").strip()
    if not out or _REFUSAL_TOKEN in out:
        return None
    if maxlength and maxlength > 0 and len(out) > maxlength:
        out = out[:maxlength].rsplit(" ", 1)[0]
    return out
