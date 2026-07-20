"""Apply Assist JSON API per contracts/http-api.md. Thin routes only — all
automation logic lives in engine/autofill/browser_controller.py and
browser_setup.py (Constitution IV: Reusable Core, Thin Web Layer)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
    current = browser_controller.start_queue(body.job_ids)
    return {
        "started": current is not None,
        "current_job_id": current["job_id"] if current else None,
    }


@router.post("/next")
def next_job():
    from engine.autofill import browser_controller

    current = browser_controller.advance()
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
