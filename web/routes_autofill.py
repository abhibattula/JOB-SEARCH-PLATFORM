"""Apply Assist JSON API per contracts/http-api.md. Thin routes only — all
automation logic lives in engine/autofill/browser_controller.py and
browser_setup.py (Constitution IV: Reusable Core, Thin Web Layer)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autofill")


class QueueRequest(BaseModel):
    job_ids: list[int]


# 008: cached result of the last launchability probe — status polls read
# this instead of re-probing (a preflight launches a real browser; running
# one every 3s poll would be absurd).
_last_preflight: dict | None = None


@router.post("/setup")
def setup_apply_assist():
    """008 (FR-008): the first-use Chromium download is gone — Apply Assist
    now uses the browser already installed on this machine."""
    raise HTTPException(
        status_code=410,
        detail="Apply Assist no longer needs a browser download — it uses"
        " your installed Microsoft Edge or Google Chrome directly.",
    )


@router.post("/preflight")
def preflight():
    """008 (FR-010): verify the browser layer can actually start."""
    global _last_preflight
    from engine.autofill import browser_controller

    _last_preflight = browser_controller.preflight()
    return _last_preflight


@router.post("/queue")
def start_queue(body: QueueRequest):
    global _last_preflight
    from engine.autofill import browser_controller

    check = browser_controller.preflight()
    _last_preflight = check
    if not check["ok"]:
        raise HTTPException(
            status_code=409,
            detail=f"Couldn't start a browser: {check['error']} — install"
            " Microsoft Edge or Google Chrome, then try again.",
        )
    try:
        current = browser_controller.start_queue(body.job_ids)
    except Exception as exc:
        log.warning("Apply Assist failed to start", exc_info=True)
        return {"started": False, "current_job_id": None, "error": str(exc)[:300]}
    return {
        "started": current is not None,
        "current_job_id": current["job_id"] if current else None,
    }


@router.post("/next")
def next_job():
    from engine.autofill import browser_controller

    try:
        current = browser_controller.advance()
    except Exception as exc:
        log.warning("Apply Assist failed to advance", exc_info=True)
        return {"current_job_id": None, "finished": False, "error": str(exc)[:300]}
    if current is None:
        return {"current_job_id": None, "finished": True}
    return {"current_job_id": current["job_id"]}


@router.post("/stop")
def stop_queue():
    from engine.autofill import browser_controller

    browser_controller.stop_queue()
    return {"stopped": True}


@router.get("/status")
def autofill_status():
    from engine.autofill import browser_controller

    current = browser_controller.current_job()
    snapshot = browser_controller.queue_snapshot()
    return {
        # 008: last launchability probe (never re-probed on a poll)
        "browser": _last_preflight
        or {"ok": None, "channel": None, "error": None},
        "queue_active": current is not None,
        "current_job_id": current["job_id"] if current else None,
        "remaining": current["remaining"] if current else 0,
        "fell_back": current["fell_back"] if current else False,
        # 007 mission-control payload (FR-026)
        "queue": snapshot["queue"],
        "progress": snapshot["progress"],
        "fill_report": snapshot["fill_report"],
        "interrupted": snapshot["interrupted"],
        "summary": snapshot["summary"],
        # 008 (FR-009): per-job reason classes
        "outcomes": snapshot["outcomes"],
    }


@router.post("/rescan")
def rescan_current_page():
    """007 (FR-003 fallback): manual re-classify-and-fill of the current
    page, for SPA re-renders that never navigate."""
    from engine.autofill import browser_controller

    result = browser_controller.rescan()
    if result is None:
        raise HTTPException(status_code=409, detail="no active Apply Assist session")
    return result


@router.post("/resume-queue")
def resume_queue():
    """007 (FR-008): relaunch the browser at the current queue position
    after the window was closed."""
    from engine.autofill import browser_controller

    try:
        current = browser_controller.resume_queue()
    except Exception as exc:
        log.warning("Apply Assist failed to resume", exc_info=True)
        return {"resumed": False, "error": str(exc)[:300]}
    if current is None:
        raise HTTPException(status_code=409, detail="nothing to resume")
    return {"resumed": True, "current_job_id": current["job_id"]}


class ConfirmAnswerRequest(BaseModel):
    question_raw: str
    answer: str
    category: str | None = None


@router.post("/answers/confirm")
def confirm_answer(body: ConfirmAnswerRequest):
    """The only write path into answer_bank (FR-011) — a drafted suggestion
    is never saved until the user explicitly confirms/edits it here. Also
    records the per-application snapshot (FR-021) if a queue is active."""
    from engine.autofill import answer_bank, browser_controller

    bank_id = answer_bank.save(body.question_raw, body.answer, category=body.category)
    current = browser_controller.current_job()
    if current is not None:
        answer_bank.record_application_answer(
            current["job_id"], body.question_raw, bank_id, body.answer
        )
    browser_controller.resolve_pending(body.answer)
    return {"saved": True}


@router.get("/answers")
def list_answer_bank():
    """006-B: backs the Profile page's Common Questions management UI —
    lets the user view/pre-populate the answer bank directly."""
    from engine.autofill import answer_bank

    return {"entries": answer_bank.list_all()}


@router.delete("/answers/{bank_id}")
def delete_answer_bank_entry(bank_id: int):
    from engine.autofill import answer_bank

    answer_bank.delete(bank_id)
    return {"deleted": True}
