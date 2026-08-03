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


def _system(bullets: str, words: int) -> str:
    return (
        "You tailor job applications. You will receive a candidate's REAL "
        "resume and one job posting. Produce ONLY a JSON object: "
        "{\"summary_line\": string (one resume headline tuned to this job), "
        f"\"tailored_bullets\": [{bullets} strings — the candidate's real "
        "experience rephrased to mirror this posting's terminology], "
        f"\"cover_letter\": string (~{words} words, specific, no fluff), "
        "\"ats_keywords\": [strings from the posting the resume should "
        "contain]}. HARD RULES: never invent employers, projects, degrees, "
        "metrics, tools, or experience absent from the resume; only rephrase "
        "and re-emphasize what is truly there. Do not mention visa status."
    )


_SYSTEM = _system("4-6", 180)

# 021 (T059): the same request, sized to the tier that will serve it.
#
# Output tokens are the dominant cost on-device — 020 measured generation at
# ~5-6 tok/s against prompt evaluation at ~42 tok/s, so a ~180-word cover
# letter plus 6 bullets is 500-700 tokens ≈ two minutes of pure generation.
# The cloud tier does not have that problem, so it is NOT asked for less:
# cutting quality to save time on a path that is already seconds long would
# be a bad trade made for no reason.
_SYSTEM_LOCAL = _system("3-4", 120)


# 016 (T021, R13): the combined prompt stays inside the documented safe
# local band (resume_extract.py: a >6k-char prompt overflowed the local
# context and failed silently 100% of the time) — tailor used to send 2×
# that. One LLM attempt with an explicit time budget; the tier dispatcher's
# cloud fallthrough is unchanged.
TAILOR_RESUME_CHARS = 3600
TAILOR_DESC_CHARS = 2400
TAILOR_TIMEOUT_S = 300.0


class TailorError(RuntimeError):
    """021 (FR-022): why tailoring did not complete, in words the applicant
    can act on. `tailor_for_job` still returns None on an unusable result;
    this carries the reason when there IS one, so the button can never again
    appear to do nothing."""


def tailor_for_job(
    resume_text: str, title: str, company: str, description: str
) -> TailorResult | None:
    if not matcher.llm_available():
        return None
    user = (
        f"RESUME:\n{resume_text[:TAILOR_RESUME_CHARS]}\n\n"
        f"JOB: {title} at {company}\n"
        f"DESCRIPTION:\n{description[:TAILOR_DESC_CHARS]}"
    )
    # Sized to whichever tier will actually serve this call.
    on_device = matcher.scoring_tier(purpose="interactive") == "local"
    messages = [
        {"role": "system", "content": _SYSTEM_LOCAL if on_device else _SYSTEM},
        {"role": "user", "content": user},
    ]
    # 021 (FR-021): the applicant is sitting in front of this. Background
    # assessment stands down for the whole call, and with a cloud key saved
    # it is served there — on-device this is ~500-700 output tokens at the
    # measured 5-6 tok/s, which is over two minutes of pure generation.
    from . import upgrade

    try:
        with upgrade.interactive():
            raw = matcher._chat(messages, purpose="json",
                                timeout_s=TAILOR_TIMEOUT_S, interactive=True)
    except Exception as exc:
        log.warning("tailor LLM call failed", exc_info=True)
        raise TailorError(str(exc)[:300] or "the AI did not respond") from exc
    try:
        return TailorResult.model_validate_json(matcher._extract_json(raw))
    except (ValidationError, json.JSONDecodeError, ValueError):
        log.info("invalid tailor output")
        return None
