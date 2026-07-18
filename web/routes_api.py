"""JSON API per contracts/http-api.md. The reuse surface for future clients."""
from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from engine import db, pipeline
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
) -> dict:
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
        "status": job.get("status") or "none",
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
):
    params = parse_feed_params(
        window, status, location, remote, sort, entry_level, limit, offset, ineligible
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
):
    import csv
    import io

    from fastapi.responses import Response

    params = parse_feed_params(
        window, status, location, remote, sort, entry_level,
        limit=500, ineligible=ineligible,
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
