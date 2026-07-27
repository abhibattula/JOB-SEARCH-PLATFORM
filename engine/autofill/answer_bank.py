"""Reusable "answered once, reused everywhere" question/answer store, plus
the per-application audit record (feature 005, spec FR-010/FR-011/FR-021).

Hard rules enforced here, not just in the UI: `save()` writes confirmed
answers and is only ever called after the user has explicitly confirmed or
typed one. 016 (fill-first, FR-004) adds `save_auto()` — the drafter's
ONLY persistence path: reusable facts land as source='ai' and NEVER
overwrite a human-confirmed entry; job-specific prose (cover letter /
why-us) is recorded per-application only and never enters the reusable
bank; practice/ad-hoc sentinel job ids persist nothing.
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
            # 016: explicit user curation adopts an AI row — the source flip
            # is what clears the on-page ai_draft highlight semantics
            " source='user', updated_at=excluded.updated_at",
            (normalized, question_raw, answer, category, "user", now, now),
        )
        row = conn.execute(
            "SELECT id FROM answer_bank WHERE question_normalized = ?", (normalized,)
        ).fetchone()
    return row["id"]


def save_with_provenance(question_raw: str, answer: str, provenance: str,
                         source_job_id: int | None = None) -> int:
    """Save a confirmed or auto-saved answer (010). `provenance` is one of
    'user' | 'confirmed' | 'auto_saved' and rides answer_bank.source; the
    draft origin is stamped in drafted_at/source_job_id."""
    normalized = _normalize(question_raw)
    now = _utcnow()
    with db._conn() as conn:
        conn.execute(
            "INSERT INTO answer_bank (question_normalized, question_raw, answer,"
            " category, source, drafted_at, source_job_id, confirmed_at,"
            " updated_at) VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(question_normalized) DO UPDATE SET"
            " answer=excluded.answer, source=excluded.source,"
            " drafted_at=excluded.drafted_at, source_job_id=excluded.source_job_id,"
            " updated_at=excluded.updated_at",
            (normalized, question_raw, answer, None, provenance, now,
             source_job_id, now, now),
        )
        row = conn.execute(
            "SELECT id FROM answer_bank WHERE question_normalized = ?", (normalized,)
        ).fetchone()
    return row["id"]


def save_auto(*, question: str, answer: str, tag: str | None,
              origin: str = "ai", job_id: int | None = None) -> int | None:
    """016 (T004): auto-save a completed draft (see module docstring for
    the scoping rules). Returns the bank row id for reusable-fact saves,
    None when the save was job-scoped, skipped (sentinel id), or refused
    (a human-confirmed entry holds the question)."""
    if job_id is not None:
        if job_id > 0:  # sentinel practice/ad-hoc ids never touch the db
            record_application_answer(job_id, question, None, answer)
        return None
    normalized = _normalize(question)
    now = _utcnow()
    with db._conn() as conn:
        conn.execute(
            "INSERT INTO answer_bank (question_normalized, question_raw, answer,"
            " category, source, confirmed_at, updated_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(question_normalized) DO UPDATE SET"
            " answer=excluded.answer, category=excluded.category,"
            " updated_at=excluded.updated_at"
            " WHERE answer_bank.source = 'ai'",
            (normalized, question, answer, tag, origin, now, now),
        )
        row = conn.execute(
            "SELECT id, source FROM answer_bank WHERE question_normalized = ?",
            (normalized,),
        ).fetchone()
    return row["id"] if row is not None and row["source"] == "ai" else None


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


_PLACEHOLDER_OPTION = re.compile(r"^(please\s+)?(select|choose)\b|^--", re.I)


def suggest(question_raw: str, category: str | None, profile: dict,
            descriptor_ctx: dict | None = None) -> str:
    """Draft a suggested answer via the matcher._chat tier dispatcher
    (cloud -> local). 016 (T012, R7): descriptor-aware — option fields get
    a pick-exactly-one prompt over the field's REAL options, custom
    comboboxes get a short-literal-label prompt, prose obeys the field's
    length limit. Never writes to the bank itself (the drafter validates
    and persists). Returns "" (never fabricates) if no tier is available."""
    from .. import matcher

    if not matcher.llm_available():
        return ""
    resume_text = (profile or {}).get("resume_text") or ""
    ctx = descriptor_ctx or {}
    options = [option for option in (ctx.get("options") or [])
               if option and option.strip()
               and not _PLACEHOLDER_OPTION.search(option.strip())]
    grounding = f"RESUME/PROFILE:\n{resume_text[:4000]}"
    if options:
        system = (
            "You are answering a multiple-choice job-application question "
            "for an applicant, using ONLY the applicant facts below. Pick "
            "exactly one of the OPTIONS. Respond with ONLY that option's "
            "text, exactly as written — nothing else."
        )
        user = (f"QUESTION ({category or 'general'}): {question_raw}\n\n"
                "OPTIONS:\n" + "\n".join(f"- {o}" for o in options)
                + f"\n\n{grounding}")
    elif (ctx.get("widget") or "") == "custom_combobox":
        system = (
            "You are answering a dropdown job-application question whose "
            "options are hidden until clicked. Respond with ONLY the "
            "literal option label the form most likely offers — at most "
            "4 words, no punctuation, never a sentence."
        )
        user = (f"QUESTION ({category or 'general'}): {question_raw}\n\n"
                f"{grounding}")
    else:
        length_rule = ""
        if ctx.get("maxlength"):
            length_rule = (" Keep the answer under "
                           f"{int(ctx['maxlength'])} characters.")
        system = (
            "You are helping a job applicant draft a short, honest answer to an "
            "application question, using ONLY the facts in their resume/profile "
            "below. Never invent experience, credentials, or facts not present. "
            "Respond with ONLY the answer text, no preamble." + length_rule
        )
        user = (f"QUESTION ({category or 'general'}): {question_raw}\n\n"
                f"{grounding}")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
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
