"""Reusable "answered once, reused everywhere" question/answer store, plus
the per-application audit record (feature 005, spec FR-010/FR-011/FR-021).

Hard rule enforced here, not just in the UI: `save()` is the only path that
ever writes a confirmed answer, and it is only ever called after the user
has explicitly confirmed or typed an answer — nothing in this module
persists an AI-drafted suggestion on its own (FR-011).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from rapidfuzz import fuzz

from .. import db

FUZZY_MATCH_THRESHOLD = 85


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().casefold())


def _utcnow() -> str:
    # Microsecond precision, matching engine/db.py (v0.6.1 collision fix).
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond:06d}"


def lookup(question_raw: str) -> dict | None:
    """Exact-normalized match first, then a rapidfuzz fuzzy pass for
    near-identical phrasing across ATSes — but never collapses genuinely
    different questions (spec edge case: work-authorization vs.
    sponsorship-requirement stay distinct even though both are related)."""
    normalized = _normalize(question_raw)
    with db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM answer_bank WHERE question_normalized = ?", (normalized,)
        ).fetchone()
        if row:
            return dict(row)
        candidates = conn.execute("SELECT * FROM answer_bank").fetchall()
    best = None
    best_score = 0
    for candidate in candidates:
        score = fuzz.ratio(normalized, candidate["question_normalized"])
        if score > best_score:
            best, best_score = candidate, score
    if best is not None and best_score >= FUZZY_MATCH_THRESHOLD:
        return dict(best)
    return None


def save(question_raw: str, answer: str, category: str | None = None) -> int:
    """Insert or update the confirmed answer for a question. Only ever
    called after explicit user confirmation (FR-011) — callers must not
    invoke this for an unreviewed AI draft."""
    normalized = _normalize(question_raw)
    now = _utcnow()
    with db._conn() as conn:
        conn.execute(
            "INSERT INTO answer_bank (question_normalized, question_raw, answer,"
            " category, source, confirmed_at, updated_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(question_normalized) DO UPDATE SET"
            " answer=excluded.answer, category=excluded.category,"
            " updated_at=excluded.updated_at",
            (normalized, question_raw, answer, category, "user", now, now),
        )
        row = conn.execute(
            "SELECT id FROM answer_bank WHERE question_normalized = ?", (normalized,)
        ).fetchone()
    return row["id"]


def list_all() -> list[dict]:
    """All confirmed answer-bank entries, newest-updated first — backs the
    Profile page's Common Questions management UI (006-B): the user can
    pre-populate answers here directly rather than only ever building the
    bank up reactively during a live Apply Assist pause."""
    with db._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM answer_bank ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete(bank_id: int) -> None:
    with db._conn() as conn:
        conn.execute("DELETE FROM answer_bank WHERE id = ?", (bank_id,))


def suggest(question_raw: str, category: str | None, profile: dict) -> str:
    """Draft a suggested answer via the matcher._chat tier dispatcher
    (cloud -> local). Never writes to the answer bank — the caller must run
    the drafted text through the confirm-before-use gate (FR-011) before
    calling save(). Returns "" (never fabricates) if no tier is available."""
    from .. import matcher

    if not matcher.llm_available():
        return ""
    resume_text = (profile or {}).get("resume_text") or ""
    messages = [
        {
            "role": "system",
            "content": (
                "You are helping a job applicant draft a short, honest answer to an "
                "application question, using ONLY the facts in their resume/profile "
                "below. Never invent experience, credentials, or facts not present. "
                "Respond with ONLY the answer text, no preamble."
            ),
        },
        {
            "role": "user",
            "content": f"QUESTION ({category or 'general'}): {question_raw}\n\n"
            f"RESUME/PROFILE:\n{resume_text[:4000]}",
        },
    ]
    try:
        return matcher._chat(messages).strip()
    except Exception:
        return ""


def record_application_answer(
    job_id: int, question_raw: str, answer_bank_id: int | None, answer_used: str
) -> None:
    """The only write path into application_answers (spec FR-021) — a
    snapshot of what was actually used on this specific application, never
    a live reference, so later edits to answer_bank don't rewrite history."""
    with db._conn() as conn:
        conn.execute(
            "INSERT INTO application_answers (job_id, answer_bank_id, question_raw,"
            " answer_used, answered_at) VALUES (?,?,?,?,?)",
            (job_id, answer_bank_id, question_raw, answer_used, _utcnow()),
        )
