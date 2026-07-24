"""012 (Discovery Copilot): on-demand scoring for a job page the user browses.

Pure engine (Principle IV — no web imports). Reuses the offline `basic_match`
scorer (instant, $0, no cloud key) and the existing `sponsorship` intelligence
(two-tier: already-graded fast path, else on-demand fuzzy match against the
bundled H-1B records — never a fabricated grade). Called from the companion
bridge (`ext_backend`) for a posting the user is viewing; independent of the
Apply Assist fill session.
"""
from __future__ import annotations

from . import basic_match, db, sponsorship

# Band cutoffs — the single source of truth for the badge color. "strong" ≥ 80
# aligns with the dashboard's `high` score chip (match_score >= 80).
BAND_STRONG = 80
BAND_GOOD = 60

# How many skill chips the badge shows (keeps the message small).
_MAX_SKILLS = 8


def _band(score: float | int) -> str:
    if score >= BAND_STRONG:
        return "strong"
    if score >= BAND_GOOD:
        return "good"
    return "fair"


def score_page(title: str, company: str, description: str, url: str = "") -> dict:
    """Score one browsed posting. Returns the discovery result dict the badge
    renders (see specs/012-discovery-copilot/data-model.md). Never raises on a
    thin/empty posting — returns an honest low-information result instead."""
    profile = db.get_profile() or {}
    resume_text = (profile.get("resume_text") or "").strip()

    # Match (offline, instant). No resume → honest prompt, not a fake score.
    if not resume_text:
        match_score: float | None = None
        band = "none"
        matching: list[str] = []
        missing: list[str] = []
        needs_resume = True
    else:
        extra_skills = {s for s in (profile.get("skills") or []) if isinstance(s, str)}
        analysis = basic_match.score(resume_text, title or "", description or "",
                                     extra_skills=extra_skills)
        match_score = analysis.match_score
        band = _band(match_score)
        matching = list(analysis.matching_skills)[:_MAX_SKILLS]
        missing = list(analysis.missing_skills)[:_MAX_SKILLS]
        needs_resume = False

    # Sponsorship — two-tier. Fast path: the company may already be graded in
    # the feed. Miss → on-demand grade against the bundled H-1B records.
    sponsor = _sponsorship_for(company)

    already_saved = bool(url) and db.get_job_by_url(url) is not None

    return {
        "match_score": match_score,
        "band": band,
        "matching_skills": matching,
        "missing_skills": missing,
        "sponsor_grade": sponsor["sponsor_grade"],
        "cap_exempt": sponsor["cap_exempt"],
        "approvals": sponsor["approvals"],
        "has_sponsor_data": sponsor["has_sponsor_data"],
        "needs_resume": needs_resume,
        "already_saved": already_saved,
    }


def _sponsorship_for(company: str) -> dict:
    name = (company or "").strip()
    if not name:
        return {"sponsor_grade": None, "cap_exempt": False, "approvals": 0,
                "has_sponsor_data": False}
    existing = db.get_company_by_name(name)
    if existing is not None and existing.get("sponsor_checked"):
        # already graded by the pipeline — trust the stored verdict
        grade_val = existing.get("sponsor_grade")
        return {
            "sponsor_grade": grade_val,
            "cap_exempt": bool(existing.get("cap_exempt")),
            "approvals": int(existing.get("h1b_approvals") or 0),
            "has_sponsor_data": grade_val is not None
            or bool(existing.get("h1b_approvals")),
        }
    graded = sponsorship.grade_company(name)
    return {
        "sponsor_grade": graded["sponsor_grade"],
        "cap_exempt": graded["cap_exempt"],
        "approvals": graded["approvals"],
        "has_sponsor_data": graded["has_sponsor_data"],
    }
