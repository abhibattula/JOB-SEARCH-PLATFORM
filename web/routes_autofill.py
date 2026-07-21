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


@router.post("/setup")
def setup_apply_assist():
    from engine.autofill import browser_setup

    if browser_setup.is_installed():
        return {"started": False, "reason": "already_installed"}
    browser_setup.start_install()
    return {"started": True}


@router.post("/queue")
def start_queue(body: QueueRequest):
    from engine.autofill import browser_controller, browser_setup

    if not browser_setup.is_installed():
        raise HTTPException(
            status_code=409,
            detail="Chromium not installed yet — run setup first.",
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
    from engine.autofill import browser_controller, browser_setup

    current = browser_controller.current_job()
    return {
        "chromium_installed": browser_setup.is_installed(),
        "queue_active": current is not None,
        "current_job_id": current["job_id"] if current else None,
        "remaining": current["remaining"] if current else 0,
        "fell_back": current["fell_back"] if current else False,
    }


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
