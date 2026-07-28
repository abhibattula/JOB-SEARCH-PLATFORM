"""AI-draft ledger (feature 010, US2).

Every AI-drafted answer that gets filled is recorded here, tied to its job
and question, so the app can list drafts awaiting review and reconcile them
on confirmation or detected submission. Confirming a draft (explicitly, or
via a detected submission) writes it into the answer bank with the right
provenance so it refills directly next time — no AI, no flag.
"""
from __future__ import annotations

from .. import db


def _utcnow() -> str:
    return db._utcnow()


def _normalized(question: str) -> str:
    from . import drafter

    return drafter.normalize_question(question)


def record(job_id: int | None, question: str, draft_text: str,
           tier: str | None) -> int:
    """017 (FR-005): upsert — one row per (job, question).

    Previously an INSERT, so the same question accumulated a row per run.
    The 2026-07-28 install carried 170 rows for ~30 questions of one job,
    which the review block rendered in full every 3 seconds.
    """
    normalized = _normalized(question)
    now = _utcnow()
    with db._conn() as conn:
        row = conn.execute(
            "SELECT id FROM ai_drafts WHERE question_normalized = ?"
            " AND (job_id = ? OR (? IS NULL AND job_id IS NULL))",
            (normalized, job_id, job_id),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE ai_drafts SET question = ?, draft_text = ?,"
                " status = 'drafted', tier = ?, updated_at = ? WHERE id = ?",
                (question, draft_text, tier, now, row["id"]),
            )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO ai_drafts (job_id, question, question_normalized,"
            " draft_text, status, tier, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (job_id, question, normalized, draft_text, "drafted", tier,
             now, now),
        )
        return cur.lastrowid


def answers_for_job(job_id: int | None) -> dict[str, str]:
    """017 (FR-004): stored answers for restart durability — the drafter
    rehydrates from these so a crash or restart does not re-draft a form
    the applicant already has answers for."""
    return {row["question"]: row["draft_text"]
            for row in list_for_job(job_id) if row["draft_text"]}


def list_for_job(job_id: int | None) -> list[dict]:
    with db._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ai_drafts WHERE status = 'drafted'"
            " AND (job_id = ? OR (? IS NULL AND job_id IS NULL))"
            " ORDER BY created_at",
            (job_id, job_id),
        ).fetchall()
    return [dict(r) for r in rows]


def get(draft_id: int) -> dict | None:
    with db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM ai_drafts WHERE id = ?", (draft_id,)
        ).fetchone()
    return dict(row) if row else None


def confirm(draft_id: int, text: str | None = None) -> dict | None:
    """User confirmed (optionally edited) a draft in the app: mark it and
    save the answer with provenance 'confirmed'."""
    from . import answer_bank

    row = get(draft_id)
    if row is None:
        return None
    final = (text if text is not None else row["draft_text"]).strip()
    answer_bank.save_with_provenance(row["question"], final, "confirmed",
                                     source_job_id=row["job_id"])
    with db._conn() as conn:
        conn.execute("UPDATE ai_drafts SET status = 'confirmed' WHERE id = ?",
                     (draft_id,))
    return {"question": row["question"], "answer": final}


def discard(draft_id: int) -> None:
    with db._conn() as conn:
        conn.execute("UPDATE ai_drafts SET status = 'discarded' WHERE id = ?",
                     (draft_id,))


def auto_save_for_job(job_id: int, final_by_question: dict[str, str]) -> int:
    """On a confirmed submission, persist the AS-SUBMITTED text of every
    still-open draft for the job (clarify Q2). Provenance 'auto_saved'."""
    from . import answer_bank

    saved = 0
    for row in list_for_job(job_id):
        q = row["question"]
        final = (final_by_question.get(q) or row["draft_text"]).strip()
        if not final:
            continue
        answer_bank.save_with_provenance(q, final, "auto_saved",
                                         source_job_id=job_id)
        with db._conn() as conn:
            conn.execute(
                "UPDATE ai_drafts SET status = 'auto_saved' WHERE id = ?",
                (row["id"],))
        saved += 1
    return saved


def count_unconfirmed() -> int:
    with db._conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM ai_drafts WHERE status = 'drafted'"
        ).fetchone()
    return int(row["n"])


def purge_unconfirmed() -> int:
    """017 (FR-011): drop drafts the applicant never confirmed. Confirmed and
    auto-saved rows are kept — they are already part of the answer bank's
    history."""
    with db._conn() as conn:
        cur = conn.execute("DELETE FROM ai_drafts WHERE status = 'drafted'")
        return cur.rowcount or 0


def prune_stale(max_age_days: int = 30) -> None:
    """Drop 'drafted' rows older than the cutoff (data-model retention)."""
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
    with db._conn() as conn:
        conn.execute(
            "DELETE FROM ai_drafts WHERE status = 'drafted' AND created_at < ?",
            (cutoff,))
