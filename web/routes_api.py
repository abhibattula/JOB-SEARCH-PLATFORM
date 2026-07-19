"""JSON API per contracts/http-api.md. The reuse surface for future clients."""
from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from engine import db, pipeline, settings
from engine.resume import NoTextError, extract_text

MAX_RESUME_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/api")

# The default feed only shows classified entry-level jobs (US2 / FR-008);
# pass entry_level=all to see everything.
DEFAULT_ENTRY_LEVEL: bool | None = True

_WINDOWS = {"7d": "7d", "24h": "24h", "all": None}


def parse_feed_params(
    window: str = "7d",
    status: str | None = None,
    location: str | None = None,
    remote: int = 0,
    sort: str = "score",
    entry_level: str | None = None,
    limit: int = 100,
    offset: int = 0,
    ineligible: int = 0,
    min_score: float | None = None,
    seen: str | None = None,
) -> dict:
    seen_since = None
    if seen == "24h":
        from datetime import datetime, timedelta, timezone

        seen_since = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).strftime("%Y-%m-%d %H:%M:%S.000")
    statuses: tuple[str, ...] | list[str] | None
    if status:
        statuses = [s for s in status.split(",") if s in db.VALID_STATUSES]
        if not statuses:
            statuses = list(db.DEFAULT_FEED_STATUSES)
    else:
        statuses = list(db.DEFAULT_FEED_STATUSES)
    if entry_level is None:
        entry = DEFAULT_ENTRY_LEVEL
    else:
        entry = {"1": True, "0": None, "all": None}.get(entry_level, DEFAULT_ENTRY_LEVEL)
    return {
        "window": _WINDOWS.get(window, "7d"),
        "statuses": statuses,
        "entry_level": entry,
        "location": location or None,
        "remote": bool(remote),
        "sort": sort if sort in ("score", "date") else "score",
        "limit": max(1, min(limit, 500)),
        "offset": max(0, offset),
        "ineligible": bool(ineligible),
        "min_score": min_score if min_score and min_score > 0 else None,
        "seen_since": seen_since,
    }


def job_summary(job: dict) -> dict:
    return {
        "id": job["id"],
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "is_remote": job["is_remote"],
        "url": job["url"],
        "posted_date": job["posted_date"],
        "first_seen": job["first_seen"],
        "source": job["source"],
        "sponsorship": job.get("sponsorship") or "UNKNOWN",
        "match_score": job.get("match_score"),
        "match_method": job.get("match_method"),
        "status": job.get("status") or "none",
        "stage": job.get("stage"),
        "follow_up": job.get("follow_up", False),
        "is_new": job.get("is_new", False),
    }


@router.post("/refresh")
def start_refresh(force: int = 0):
    result = pipeline.trigger_refresh(
        "manual" if force else "auto", force=bool(force)
    )
    return JSONResponse(result)


@router.get("/refresh/status")
def refresh_status():
    return db.get_run_status()


@router.get("/jobs")
def list_jobs(
    window: str = "7d",
    status: str | None = None,
    location: str | None = None,
    remote: int = 0,
    sort: str = "score",
    entry_level: str | None = None,
    limit: int = 100,
    offset: int = 0,
    ineligible: int = 0,
    min_score: float | None = None,
    seen: str | None = None,
):
    params = parse_feed_params(
        window, status, location, remote, sort, entry_level, limit, offset,
        ineligible, min_score, seen,
    )
    jobs, total = db.query_jobs(**params)
    return {"jobs": [job_summary(j) for j in jobs], "total": total}


@router.get("/jobs/{job_id}")
def job_detail(job_id: int):
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = job_summary(job)
    payload["description"] = job.get("description") or ""
    payload["notes"] = job.get("notes")
    payload["applied_at"] = job.get("applied_at")
    evidence = job.get("sponsorship_evidence")
    payload["sponsorship_evidence"] = json.loads(evidence) if evidence else None
    match = job.get("match_json")
    payload["match"] = json.loads(match) if match else None
    return payload


@router.post("/jobs/{job_id}/status")
async def set_job_status(job_id: int, request: Request, status: str | None = None):
    if status is None:
        try:
            body = await request.json()
            status = body.get("status")
        except Exception:
            status = None
    if status is None:
        raise HTTPException(status_code=400, detail="status is required")
    try:
        db.set_status(job_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return job_summary(db.get_job(job_id))


@router.get("/export")
def export_csv(
    window: str = "7d",
    status: str | None = None,
    location: str | None = None,
    remote: int = 0,
    sort: str = "score",
    entry_level: str | None = None,
    ineligible: int = 0,
    min_score: float | None = None,
):
    import csv
    import io

    from fastapi.responses import Response

    params = parse_feed_params(
        window, status, location, remote, sort, entry_level,
        limit=500, ineligible=ineligible, min_score=min_score,
    )
    jobs, _ = db.query_jobs(**params)
    buffer = io.StringIO()
    fields = [
        "title", "company", "location", "is_remote", "posted_date", "source",
        "sponsorship", "match_score", "status", "url",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for job in jobs:
        writer.writerow(job_summary(job))
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs.csv"},
    )


@router.get("/settings")
def get_settings():
    key = settings.get("LLM_API_KEY") or ""
    return {
        "llm_key_set": bool(key),
        "llm_api_key_masked": settings.mask_key(key),
        "llm_base_url": settings.get("LLM_BASE_URL"),
        "llm_model": settings.get("LLM_MODEL"),
        "jobspy_linkedin": settings.get("JOBSPY_LINKEDIN") == "1",
        "schedule_refresh": settings.get("SCHEDULE_REFRESH") == "1",
        "alerts_enabled": settings.get("ALERTS_ENABLED") != "0",
        "max_score_per_run": int(settings.get("MAX_SCORE_PER_RUN") or "150"),
    }


@router.post("/settings")
async def save_settings(
    request: Request,
    llm_api_key: str | None = Form(None),
    llm_base_url: str | None = Form(None),
    llm_model: str | None = Form(None),
    jobspy_linkedin: str | None = Form(None),
    schedule_refresh: str | None = Form(None),
    alerts_enabled: str | None = Form(None),
):
    if llm_api_key:  # blank never clears an existing key
        settings.set("LLM_API_KEY", llm_api_key.strip())
    if llm_base_url:
        settings.set("LLM_BASE_URL", llm_base_url.strip())
    if llm_model:
        settings.set("LLM_MODEL", llm_model.strip())
    if jobspy_linkedin is not None:
        settings.set("JOBSPY_LINKEDIN", "1" if jobspy_linkedin == "1" else "0")
    if schedule_refresh is not None:
        settings.set("SCHEDULE_REFRESH", "1" if schedule_refresh == "1" else "0")
    if alerts_enabled is not None:
        settings.set("ALERTS_ENABLED", "1" if alerts_enabled == "1" else "0")
    if "text/html" in (request.headers.get("accept") or ""):
        return RedirectResponse("/settings", status_code=303)
    return get_settings()


@router.post("/settings/test")
def test_llm_key(request: Request):
    from fastapi.responses import HTMLResponse

    from engine import matcher

    if not matcher.llm_available():
        result = {"ok": False, "error": "No API key saved yet."}
    else:
        try:
            matcher._chat([{"role": "user", "content": "Reply with the word: pong"}])
            result = {"ok": True, "model": settings.get("LLM_MODEL")}
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    if request.headers.get("hx-request"):
        if result["ok"]:
            return HTMLResponse(f"✓ Key works ({result['model']})")
        return HTMLResponse(f"✕ {result['error']}")
    return result


@router.post("/jobs/{job_id}/stage")
async def set_job_stage(job_id: int, request: Request, stage: str | None = None):
    if stage is None:
        try:
            form = await request.form()
            stage = form.get("stage")
        except Exception:
            stage = None
    if stage is None:
        raise HTTPException(status_code=400, detail="stage is required")
    try:
        db.set_stage(job_id, stage)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return job_summary(db.get_job(job_id))


@router.post("/jobs/{job_id}/notes")
async def set_job_notes(job_id: int, request: Request):
    form = await request.form()
    notes = form.get("notes")
    if notes is None:
        try:
            body = await request.json()
            notes = body.get("notes", "")
        except Exception:
            notes = ""
    try:
        db.set_notes(job_id, notes or "")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.get("/analytics")
def analytics():
    return db.application_analytics()


def _profile_payload() -> dict:
    profile = db.get_profile() or {}
    return {
        "resume_filename": profile.get("resume_filename"),
        "skills": profile.get("skills") or [],
        "target_locations": profile.get("target_locations") or [],
        "preferences": profile.get("preferences") or {},
        "updated_at": profile.get("updated_at"),
    }


@router.get("/profile")
def get_profile():
    return _profile_payload()


@router.post("/profile")
async def save_profile(
    request: Request,
    resume: UploadFile | None = File(None),
    target_locations: str | None = Form(None),
):
    fields: dict = {}
    if resume is not None and resume.filename:
        raw = await resume.read()
        if len(raw) > MAX_RESUME_BYTES:
            raise HTTPException(status_code=422, detail="resume larger than 10 MB")
        try:
            text = extract_text(raw)
        except NoTextError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        from engine import matcher

        fields["resume_text"] = text
        fields["resume_filename"] = resume.filename
        fields["skills"] = matcher.extract_skills(text)  # [] without an LLM key
    if target_locations is not None:
        fields["target_locations"] = [
            part.strip() for part in target_locations.split(",") if part.strip()
        ]
    if fields:
        db.save_profile(**fields)
    if "text/html" in (request.headers.get("accept") or ""):
        return RedirectResponse("/profile", status_code=303)
    return _profile_payload()
