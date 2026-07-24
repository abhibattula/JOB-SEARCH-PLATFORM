"""Apply Assist JSON API per contracts/http-api.md. Thin routes only — all
automation logic lives in engine/autofill/browser_controller.py and
browser_setup.py (Constitution IV: Reusable Core, Thin Web Layer)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
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
        # 009 (FR-007): live watch activity
        "activity": snapshot["activity"],
        # 010 (FR-003/FR-004): which fill path is active + companion state
        "backend": snapshot["backend"],
        "extension": snapshot["extension"],
    }


@router.post("/rescan")
def rescan_current_page():
    """009: forces an immediate fill pass (the watcher already re-scans
    every ~2s on its own)."""
    from engine.autofill import browser_controller

    result = browser_controller.rescan()
    if result is None:
        raise HTTPException(status_code=409, detail="no active Apply Assist session")
    return result


@router.post("/practice")
def start_practice(request: Request):
    """009 (FR-009): queue the bundled practice application — the ten-second
    on-machine proof that the fill engine works, using the user's real
    profile data through the normal engine."""
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
    url = str(request.base_url).rstrip("/") + "/practice/apply"
    result = browser_controller.start_practice(url)
    if result is None:
        raise HTTPException(
            status_code=409, detail="an Apply Assist session is already running"
        )
    return {"started": True}


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


@router.get("/drafts")
def list_drafts():
    """010 FR-012: the AI drafts awaiting review for the current job/session."""
    from engine.autofill import browser_controller, drafts

    current = browser_controller.current_job()
    job_id = current["job_id"] if current else None
    # a job_id sentinel <=0 (practice/ad-hoc) maps to the NULL-job draft list
    lookup_id = job_id if (job_id and job_id > 0) else None
    return {"drafts": drafts.list_for_job(lookup_id)}


class DraftDecision(BaseModel):
    action: str  # "confirm" | "discard"
    text: str | None = None


@router.post("/drafts/{draft_id}")
def decide_draft(draft_id: int, body: DraftDecision):
    """010 FR-013: confirm (optionally edited) a draft → saved answer +
    re-fill if the field still holds the draft; or discard it."""
    from engine.autofill import browser_controller, drafts

    if body.action == "discard":
        drafts.discard(draft_id)
        return {"ok": True, "status": "discarded"}
    if body.action == "confirm":
        result = drafts.confirm(draft_id, body.text)
        if result is None:
            raise HTTPException(status_code=404, detail="draft not found")
        # unlock the field so the confirmed text refills over the draft
        browser_controller.resolve_pending(result["answer"])
        return {"ok": True, "status": "confirmed", **result}
    raise HTTPException(status_code=400, detail="action must be confirm or discard")


class AdhocLinkRequest(BaseModel):
    tab_id: int
    create: bool = False


@router.post("/adhoc/link")
def adhoc_link(body: AdhocLinkRequest):
    """010 FR-004a: offer to track an ad-hoc 'Fill this page' session as an
    application. Matches the page URL to a known posting; with create=True
    and no match, records a new job. Always user-initiated."""
    from engine import db
    from engine.autofill import ext_backend

    linked = ext_backend.link_adhoc(body.tab_id)
    if linked["job_id"] is None and body.create and linked.get("url"):
        db.upsert_job({
            "title": linked.get("title") or "Application",
            "company": "", "url": linked["url"], "source": "manual",
            "location": None, "is_remote": False, "description": "",
            "posted_date": None,
        })
        job = next((j for j in db.list_all_jobs_minimal()
                    if j["url"] == linked["url"]), None)
        linked["job_id"] = job["id"] if job else None
    if linked["job_id"] is not None:
        db.set_status(linked["job_id"], "applied")
    return linked


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
