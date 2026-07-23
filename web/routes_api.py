"""JSON API per contracts/http-api.md. The reuse surface for future clients."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from engine import db, pipeline, settings
from engine.resume import NoTextError, extract_text

MAX_RESUME_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/api")

# The default feed only shows classified entry-level jobs (US2 / FR-008);
# pass entry_level=all to see everything.
DEFAULT_ENTRY_LEVEL: bool | None = True


# --- 008 desktop-shell support (FR-002/FR-004) ------------------------------
# Inside the pywebview shell, target=_blank and navigator.clipboard are
# unreliable; these endpoints are the guaranteed paths. The server only ever
# runs on the user's own machine (127.0.0.1), so "open a browser" and "write
# the clipboard" act on the user's own session.


class OpenRequest(BaseModel):
    url: str


@router.post("/open")
def open_external(body: OpenRequest):
    from urllib.parse import urlparse

    parsed = urlparse(body.url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="only http/https links can be opened")
    import webbrowser

    webbrowser.open(body.url)
    return {"opened": True}


class ClipboardRequest(BaseModel):
    text: str


@router.post("/clipboard")
def copy_to_clipboard(body: ClipboardRequest):
    from engine import clipboard

    try:
        clipboard.copy_text(body.text)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Couldn't write to the clipboard: {exc}"
        )
    return {"copied": True}

_WINDOWS = {"14d": "14d", "7d": "7d", "24h": "24h", "all": None}


def parse_feed_params(
    window: str = "14d",
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
    strong_sponsors: int = 0,
    page: int = 1,
    source: str | None = None,
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
        # 008 (FR-021): '0' now genuinely means non-entry-only
        entry = {"1": True, "0": False, "all": None}.get(entry_level, DEFAULT_ENTRY_LEVEL)
    limit = max(1, min(limit, 500))
    if page and page > 1 and not offset:
        offset = (page - 1) * limit
    return {
        "window": _WINDOWS.get(window, "14d"),
        "statuses": statuses,
        "entry_level": entry,
        "location": location or None,
        "remote": bool(remote),
        "sort": sort if sort in ("score", "date") else "score",
        "limit": limit,
        "offset": max(0, offset),
        "ineligible": bool(ineligible),
        "min_score": min_score if min_score and min_score > 0 else None,
        "seen_since": seen_since,
        "strong_sponsors": bool(strong_sponsors),
        "source": source or None,
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
        "sponsor_grade": job.get("sponsor_grade"),
        "cap_exempt": bool(job.get("cap_exempt")),
        # 008: freshness honesty (FR-013/FR-014)
        "delisted": bool(job.get("delisted")),
        "posted_approx": job.get("posted_approx", job.get("posted_date") is None),
        "last_seen_at": job.get("last_seen_at"),
    }


@router.get("/jobs/{job_id}/linkedin-url")
def job_linkedin_url(job_id: int):
    """008 (FR-016): a genuine LinkedIn search for this job's title."""
    from engine.ingest import linkedin_linkout

    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"url": linkedin_linkout.url_for_job(job)}


# --- 008 company watchlist (FR-015) -----------------------------------------


class WatchlistAddRequest(BaseModel):
    ats: str
    slug: str
    name: str | None = None


class WatchlistPatchRequest(BaseModel):
    enabled: bool


@router.get("/watchlist")
def list_watchlist():
    from engine import watchlist

    watchlist.ensure_seeded()
    return {"companies": watchlist.list_all()}


@router.post("/watchlist", status_code=201)
def add_watchlist_entry(body: WatchlistAddRequest):
    from engine import watchlist

    if body.ats not in watchlist.VALID_ATS:
        raise HTTPException(status_code=400, detail=f"unknown board type {body.ats!r}")
    try:
        return watchlist.add(body.ats, body.slug, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/watchlist/{entry_id}")
def patch_watchlist_entry(entry_id: int, body: WatchlistPatchRequest):
    from engine import watchlist

    watchlist.set_enabled(entry_id, body.enabled)
    return {"id": entry_id, "enabled": body.enabled}


@router.delete("/watchlist/{entry_id}")
def delete_watchlist_entry(entry_id: int):
    from engine import watchlist

    result = watchlist.remove(entry_id)
    if result == "missing":
        raise HTTPException(status_code=404, detail="no such watchlist entry")
    return {"result": result}


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
    window: str = "14d",
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
    strong_sponsors: int = 0,
    page: int = 1,
    source: str | None = None,
):
    params = parse_feed_params(
        window, status, location, remote, sort, entry_level, limit, offset,
        ineligible, min_score, seen, strong_sponsors, page=page, source=source,
    )
    jobs, total = db.query_jobs(**params)
    pages = max(1, -(-total // params["limit"]))
    return {
        "jobs": [job_summary(j) for j in jobs],
        "total": total,
        "page": max(1, page),
        "pages": pages,
    }


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
    payload["sponsor_evidence"] = sponsor_evidence_for(job)
    return payload


def sponsor_evidence_for(job: dict) -> dict:
    """007 (FR-015): the sponsor-intelligence evidence panel — nulls where
    data is absent, never fabricated values. Shared by the JSON detail and
    the job page template."""
    from engine import sponsorship

    approvals = job.get("h1b_approvals") or 0
    denials = job.get("h1b_denials") or 0
    total = approvals + denials
    return {
        "approvals": approvals,
        "denials": denials,
        "approval_rate": round(approvals / total, 3) if total else None,
        "wage_level_median": job.get("wage_level_median"),
        "wage_offered_median": job.get("wage_offered_median"),
        "lottery_hint": sponsorship.lottery_hint(job.get("wage_level_median")),
        "cap_exempt": bool(job.get("cap_exempt")),
        "grade": job.get("sponsor_grade"),
        "grade_reasons": _grade_reasons(job),
    }


def _grade_reasons(job: dict) -> list[str]:
    """Plain-language evidence lines for the grade panel (FR-015)."""
    from engine.sponsorship import GRADE_MIN_PETITIONS

    approvals = job.get("h1b_approvals") or 0
    denials = job.get("h1b_denials") or 0
    reasons = []
    if approvals or denials:
        reasons.append(f"{approvals} H-1B approvals, {denials} denials in loaded years")
    if (approvals + denials) and (approvals + denials) < GRADE_MIN_PETITIONS:
        reasons.append(
            f"Below the {GRADE_MIN_PETITIONS}-petition evidence floor — shown as UNKNOWN"
        )
    if job.get("wage_level_median"):
        reasons.append(f"Median engineering wage level: {job['wage_level_median']}")
    if job.get("cap_exempt"):
        reasons.append("Likely cap-exempt: can sponsor year-round outside the lottery")
    return reasons


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
    window: str = "14d",
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
        "theme": settings.get("THEME") or "",
        "autofill_use_tailored_pdf": settings.get("AUTOFILL_USE_TAILORED_PDF") != "0",
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
    theme: str | None = Form(None),
    autofill_use_tailored_pdf: str | None = Form(None),
    onboarding_dismissed: str | None = Form(None),
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
    if theme in ("light", "dark"):
        settings.set("THEME", theme)
    if autofill_use_tailored_pdf is not None:
        settings.set(
            "AUTOFILL_USE_TAILORED_PDF",
            "1" if autofill_use_tailored_pdf == "1" else "0",
        )
    if onboarding_dismissed == "1":
        settings.set("ONBOARDING_DISMISSED", "1")
    if "text/html" in (request.headers.get("accept") or ""):
        return RedirectResponse("/settings", status_code=303)
    return get_settings()


@router.post("/settings/check-update")
def check_update(request: Request):
    from fastapi.responses import HTMLResponse

    from engine import updates

    result = updates.check()
    if request.headers.get("hx-request"):
        if result is None:
            return HTMLResponse("✕ Couldn't reach GitHub — check your connection.")
        if result["newer"]:
            # 008 (FR-030): a real in-app update, not just a link
            return HTMLResponse(
                f'⬆ Version {result["latest"]} is available — '
                f'<button type="button" onclick="runUpdate(this)">Update now</button> '
                f'<span id="update-progress" class="data"></span> '
                f'<a href="{result["url"]}" target="_blank" rel="noopener">manual download ↗</a>'
            )
        return HTMLResponse("✓ You're on the latest version.")
    return result or {"error": "check failed"}


@router.post("/settings/test")
def test_llm_key(request: Request):
    from fastapi.responses import HTMLResponse

    from engine import matcher

    # 005: this button specifically validates a pasted cloud API key — the
    # local tier has nothing to "test" (it's a synchronous file-presence
    # check, not a network round-trip), so this must not fall through to
    # matcher.llm_available()'s tier-inclusive check, which would silently
    # attempt an expensive local model load with no cloud key configured.
    if not settings.get("LLM_API_KEY"):
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


@router.post("/jobs/{job_id}/tailor")
def tailor_job(job_id: int, request: Request):
    from engine import matcher, tailor

    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    profile = db.get_profile()
    if not profile or not profile.get("resume_text"):
        raise HTTPException(
            status_code=409, detail="Upload a resume on the Profile page first."
        )
    if not matcher.llm_available():
        raise HTTPException(
            status_code=409, detail="Add an AI key in Settings to generate tailoring."
        )
    result = tailor.tailor_for_job(
        profile["resume_text"], job["title"], job["company"],
        job.get("description") or "",
    )
    if result is None:
        raise HTTPException(
            status_code=502, detail="The AI response was invalid — try again."
        )
    db.set_tailor(job_id, result.model_dump_json())
    return result.model_dump()


def _profile_payload() -> dict:
    profile = db.get_profile() or {}
    return {
        "resume_filename": profile.get("resume_filename"),
        "skills": profile.get("skills") or [],
        "target_locations": profile.get("target_locations") or [],
        "preferences": profile.get("preferences") or {},
        "updated_at": profile.get("updated_at"),
        "authorized_without_sponsorship": profile.get("authorized_without_sponsorship"),
        "visa_status": profile.get("visa_status"),
        "first_name": profile.get("first_name"),
        "last_name": profile.get("last_name"),
        "email": profile.get("email"),
        "phone": profile.get("phone"),
        "linkedin_url": profile.get("linkedin_url"),
        "portfolio_url": profile.get("portfolio_url"),
        # 007 resume builder — resume_file_path itself never leaves the
        # server (local filesystem path), only its existence does.
        "has_resume_file": bool(profile.get("resume_file_path")),
        "resume_sections": profile.get("resume_sections"),
        "sections_edited_at": profile.get("sections_edited_at"),
    }


def _store_resume_file(raw: bytes, filename: str) -> str:
    """Persist the original upload under data_dir()/resume/ (FR-001) —
    Playwright's set_input_files needs a real file path, and the extracted
    text alone can't be attached to an application."""
    from engine import paths

    resume_dir = paths.data_dir() / "resume"
    resume_dir.mkdir(parents=True, exist_ok=True)
    safe_name = os.path.basename(filename) or "resume.pdf"
    target = resume_dir / safe_name
    target.write_bytes(raw)
    return str(target)


@router.get("/profile")
def get_profile():
    return _profile_payload()


@router.post("/profile")
async def save_profile(
    request: Request,
    resume: UploadFile | None = File(None),
    target_locations: str | None = Form(None),
    skills: str | None = Form(None),
    authorized_without_sponsorship: str | None = Form(None),
    visa_status: str | None = Form(None),
    first_name: str | None = Form(None),
    last_name: str | None = Form(None),
    email: str | None = Form(None),
    phone: str | None = Form(None),
    linkedin_url: str | None = Form(None),
    portfolio_url: str | None = Form(None),
):
    fields: dict = {}
    extraction_conflict = False
    if resume is not None and resume.filename:
        raw = await resume.read()
        if len(raw) > MAX_RESUME_BYTES:
            raise HTTPException(status_code=422, detail="resume larger than 10 MB")
        try:
            text = extract_text(raw)
        except NoTextError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        from engine import matcher, resume_extract

        fields["resume_text"] = text
        fields["resume_filename"] = resume.filename
        fields["resume_file_path"] = _store_resume_file(raw, resume.filename)
        fields["skills"] = matcher.extract_skills(text)  # [] without an LLM key
        # 007 (FR-016): structured extraction — but user-edited sections
        # are never silently overwritten; flag the conflict and let the
        # user choose keep vs re-extract (POST /api/profile/reextract).
        existing = db.get_profile() or {}
        if existing.get("sections_edited_at"):
            extraction_conflict = True
        else:
            sections = resume_extract.extract(text)
            if sections is not None:
                fields["resume_sections"] = sections.model_dump()
        # 008 (FR-022/FR-023): identity details — the LLM's contact block
        # when available, the pattern-based fallback otherwise, so
        # auto-fill works on every tier. Applied after the form fields
        # below (fill-only-blank + consent, never a silent overwrite).
        contact_pending = (fields.get("resume_sections") or {}).get("contact")
        if not contact_pending or not any(
            (v or "").strip() for v in contact_pending.values()
        ):
            contact_pending = resume_extract.extract_contact(text).model_dump()
        fields["_contact_pending"] = contact_pending
    if target_locations is not None:
        fields["target_locations"] = [
            part.strip() for part in target_locations.split(",") if part.strip()
        ]
    if skills is not None:
        manual_skills = [part.strip() for part in skills.split(",") if part.strip()]
        # If a resume was ALSO uploaded in this same request, union rather
        # than overwrite (006-E) — never lose either the fresh extraction
        # or an explicit manual edit, regardless of which the user did.
        extracted = fields.get("skills")
        fields["skills"] = (
            list(dict.fromkeys(manual_skills + list(extracted)))
            if extracted is not None
            else manual_skills
        )
    for key, value in {
        "authorized_without_sponsorship": authorized_without_sponsorship,
        "visa_status": visa_status,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "linkedin_url": linkedin_url,
        "portfolio_url": portfolio_url,
    }.items():
        if value is not None:
            fields[key] = value

    # 008 (FR-022): apply identity auto-fill AFTER the form values above so
    # a value the user just typed always wins; blanks fill silently,
    # disagreements become explicit keep-or-replace decisions. Visa/work-
    # authorization fields are deliberately not in this list (FR-024).
    identity_conflicts: list[dict] = []
    contact_pending = fields.pop("_contact_pending", None)
    if contact_pending:
        existing = db.get_profile() or {}
        for field in ("first_name", "last_name", "email", "phone",
                      "linkedin_url", "portfolio_url"):
            extracted_value = (contact_pending.get(field) or "").strip()
            if not extracted_value:
                continue
            current = fields.get(field)
            if current is None:
                current = existing.get(field) or ""
            current = current.strip()
            if not current:
                fields[field] = extracted_value
            elif current != extracted_value:
                identity_conflicts.append({
                    "field": field, "current": current, "extracted": extracted_value,
                })
        location = (contact_pending.get("location") or "").strip()
        if location and not fields.get("target_locations") and not (
            existing.get("target_locations") or []
        ):
            fields["target_locations"] = [location]
        settings.set(
            "PENDING_IDENTITY_CONFLICTS",
            json.dumps(identity_conflicts) if identity_conflicts else "",
        )
        # FR-025: derive search terms from the fresh extraction — unless the
        # user has taken ownership of them (derived_from == "user").
        from engine import search_terms as search_terms_mod

        stored_terms = existing.get("search_terms") or {}
        if not (isinstance(stored_terms, dict) and stored_terms.get("derived_from") == "user"):
            merged = dict(existing)
            merged.update(fields)
            derived = search_terms_mod.derive(merged)
            if derived:
                fields["search_terms"] = {
                    "terms": derived, "derived_from": "resume",
                    "updated_at": db._utcnow(),
                }

    if fields:
        db.save_profile(**fields)
    if "text/html" in (request.headers.get("accept") or ""):
        target = "/profile?extraction_conflict=1" if extraction_conflict else "/profile"
        return RedirectResponse(target, status_code=303)
    return {
        **_profile_payload(),
        "extraction_conflict": extraction_conflict,
        "identity_conflicts": identity_conflicts,
    }


class IdentityDecisions(BaseModel):
    decisions: dict[str, str]  # field -> "keep" | "replace"


@router.post("/profile/identity-conflicts")
def resolve_identity_conflicts(body: IdentityDecisions):
    """008 (FR-022): explicit consent for extracted values that disagreed
    with what the user typed. 'replace' adopts the extracted value; 'keep'
    (or no decision) leaves the user's value. Either way the conflict is
    consumed."""
    pending = json.loads(settings.get("PENDING_IDENTITY_CONFLICTS") or "[]")
    by_field = {c["field"]: c for c in pending}
    updates = {}
    for field, decision in body.decisions.items():
        conflict = by_field.pop(field, None)
        if conflict and decision == "replace":
            updates[field] = conflict["extracted"]
    if updates:
        db.save_profile(**updates)
    settings.set(
        "PENDING_IDENTITY_CONFLICTS",
        json.dumps(list(by_field.values())) if by_field else "",
    )
    return {"applied": list(updates), "remaining": list(by_field)}


class SearchTermsRequest(BaseModel):
    terms: list[str]


@router.put("/profile/search-terms")
def put_search_terms(body: SearchTermsRequest):
    """008 (FR-025): the user takes ownership of the search terms."""
    from engine.search_terms import MAX_TERMS

    terms = [t.strip() for t in body.terms if t and t.strip()]
    if len(terms) > MAX_TERMS:
        raise HTTPException(
            status_code=422, detail=f"at most {MAX_TERMS} search terms"
        )
    db.save_profile(search_terms={
        "terms": terms, "derived_from": "user", "updated_at": db._utcnow(),
    })
    return {"terms": terms, "derived_from": "user"}


@router.put("/profile/resume-sections")
async def put_resume_sections(request: Request):
    """Full replace of the structured resume (FR-017) — the manual-edit
    path, identical with or without an AI tier. Stamps sections_edited_at,
    which is what protects these edits from later silent re-extraction."""
    from engine.resume_extract import ResumeSections

    try:
        body = await request.json()
        sections = ResumeSections.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:300])
    db.save_profile(
        resume_sections=sections.model_dump(),
        sections_edited_at=db._utcnow(),
    )
    return _profile_payload()


@router.post("/profile/reextract")
def reextract_resume_sections():
    """The explicit-consent path after an extraction_conflict (FR-016):
    replaces sections from the stored resume text and clears the edit
    stamp — the ONLY way extraction may overwrite user edits."""
    from engine import resume_extract

    profile = db.get_profile()
    if not profile or not profile.get("resume_text"):
        raise HTTPException(status_code=409, detail="no resume on file")
    sections = resume_extract.extract(profile["resume_text"])
    if sections is None:
        return {"extracted": False, "reason": "no-ai-tier"}
    updates: dict = {
        "resume_sections": sections.model_dump(),
        "sections_edited_at": None,
    }
    # 008: re-extraction also refreshes derived search terms (same
    # ownership rule — user-edited terms are never overwritten)
    stored_terms = profile.get("search_terms") or {}
    if not (isinstance(stored_terms, dict) and stored_terms.get("derived_from") == "user"):
        from engine import search_terms as search_terms_mod

        merged = dict(profile)
        merged.update(updates)
        derived = search_terms_mod.derive(merged)
        if derived:
            updates["search_terms"] = {
                "terms": derived, "derived_from": "resume",
                "updated_at": db._utcnow(),
            }
    db.save_profile(**updates)
    return _profile_payload()


@router.get("/jobs/{job_id}/resume-pdf")
def download_resume_pdf(job_id: int):
    """Tailored resume PDF for this job (untailored render when the job
    has no tailoring output yet — FR-018/US2-AS6)."""
    from engine import resume_pdf

    try:
        path = resume_pdf.tailored_resume_path(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return Response(
        path.read_bytes(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=resume-job{job_id}.pdf"
        },
    )


@router.get("/jobs/{job_id}/cover-letter-pdf")
def download_cover_letter_pdf(job_id: int):
    from engine import resume_pdf

    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.get("tailor_json"):
        raise HTTPException(
            status_code=409, detail="Generate tailoring for this job first."
        )
    try:
        tailoring = json.loads(job["tailor_json"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="tailoring output unreadable")
    profile = db.get_profile() or {}
    data = resume_pdf.render_cover_letter(
        {k: profile.get(k) for k in ("first_name", "last_name", "email",
                                     "phone", "linkedin_url", "portfolio_url")},
        job["company"], job["title"], tailoring.get("cover_letter") or "",
    )
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=cover-letter-job{job_id}.pdf"
        },
    )


@router.get("/diagnostics/pdf-selftest")
def pdf_selftest():
    """007: a real fpdf2 render using the bundled DejaVu fonts (unicode
    included) — packaging/smoke_test.py asserts this in the frozen build,
    so a dropped font data file fails the release loudly instead of
    surfacing as broken PDF downloads in production (v0.4.0 lesson)."""
    from engine import resume_pdf

    try:
        data = resume_pdf.render_resume(
            {"experience": [], "education": [], "projects": [],
             "skills": ["self-test — unicode dash", "résumé"]},
            {"first_name": "Self", "last_name": "Test"},
            tailoring=None,
        )
        return {"ok": bool(data[:5] == b"%PDF-"), "bytes": len(data)}
    except Exception as exc:
        return {"ok": False, "bytes": 0, "error": f"{type(exc).__name__}: {exc}"[:300]}


@router.get("/diagnostics/local-llm-selftest")
def local_llm_selftest():
    """005: a real inference call against the bundled model, not just an
    import check — packaging/smoke_test.py depends on this being genuine
    (the exact class of blind spot that let the v0.4.0 tls_client bug ship).
    Always 200; success/failure is signaled via the "ok" field so a missing
    local model doesn't itself look like a server error."""
    from engine import local_llm

    try:
        reply = local_llm.chat(
            [{"role": "user", "content": "Reply with a short greeting."}]
        )
        return {"ok": True, "reply": reply}
    except Exception:
        return {"ok": False, "reply": ""}


class SaveCredentialRequest(BaseModel):
    domain: str
    email: str
    password: str


class SaveDefaultCredentialRequest(BaseModel):
    email: str
    password: str


@router.post("/credentials/default")
def save_default_credential(body: SaveDefaultCredentialRequest):
    """006-D: one default login used for any domain without its own
    override — most job sites reuse the same email/password, so this
    avoids requiring a per-domain save for every new site."""
    from engine import credentials

    credentials.save_default(body.email, body.password)
    return {"saved": True}


@router.delete("/credentials/default")
def delete_default_credential():
    # Registered before /credentials/{domain} — a dynamic path parameter
    # would otherwise greedily match the literal string "default" too.
    from engine import credentials

    credentials.delete_default()
    return {"deleted": True}


@router.post("/credentials")
def save_credential(body: SaveCredentialRequest):
    """Write-only, like a real password manager — the password is never
    echoed back in this or any other response (FR-017)."""
    from engine import credentials

    credentials.save(body.domain, body.email, body.password)
    return {"saved": True}


@router.get("/credentials")
def list_credentials():
    from engine import credentials

    default = credentials.get_default()
    return {
        "domains": credentials.list_domains(),
        "default": {"email": default["email"]} if default else None,
    }


@router.delete("/credentials/{domain}")
def delete_credential(domain: str):
    from engine import credentials

    credentials.delete(domain)
    return {"deleted": True}


@router.get("/diagnostics/chromium-launch-selftest")
def chromium_launch_selftest():
    """005: a real Chromium launch, not just an import check — catches a
    silently-dropped Playwright driver the same way local-llm-selftest
    catches a dropped llama_cpp native lib."""
    from engine.autofill import browser_controller

    try:
        ok = browser_controller.chromium_selftest()
        return {"ok": bool(ok)}
    except Exception as exc:
        # 008: the audit found this returned a bare false with no reason —
        # the error text is the whole point of a self-test
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


# --- 008 diagnostics (FR-033) -----------------------------------------------


def _diag_pdf() -> str:
    from engine import resume_pdf

    data = resume_pdf.render_resume(
        {"experience": [], "education": [], "projects": [],
         "skills": ["self-test — unicode dash", "résumé"]},
        {"first_name": "Self", "last_name": "Test"},
        tailoring=None,
    )
    if data[:5] != b"%PDF-":
        raise RuntimeError("render did not produce a PDF header")
    return f"{len(data)} bytes"


def _diag_local_llm() -> str:
    from engine import local_llm

    reply = local_llm.chat(
        [{"role": "user", "content": "Reply with a short greeting."}]
    )
    if not reply:
        raise RuntimeError("empty reply from the local model")
    return "responded"


def _diag_browser() -> str:
    from engine.autofill import browser_controller

    result = browser_controller.preflight()
    if not result["ok"]:
        raise RuntimeError(result["error"] or "browser launch failed")
    return f"ready ({result['channel']})"


def _diag_sources() -> str:
    from engine.ingest.base import polite_get

    response = polite_get(
        "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"
    )
    return f"reachable (HTTP {response.status_code})"


# Named check registry — the Diagnostics page runs each and shows the REAL
# error text on failure (audit: bare ok:false told the user nothing).
DIAGNOSTIC_CHECKS: dict = {
    "pdf": _diag_pdf,
    "local-llm": _diag_local_llm,
    "browser": _diag_browser,
    "sources": _diag_sources,
}


@router.get("/diagnostics/all")
def diagnostics_all():
    import time as time_mod

    checks = []
    for name, fn in DIAGNOSTIC_CHECKS.items():
        started = time_mod.perf_counter()
        try:
            detail = fn()
            checks.append({
                "name": name, "ok": True, "detail": detail, "error": None,
                "ms": int((time_mod.perf_counter() - started) * 1000),
            })
        except Exception as exc:
            checks.append({
                "name": name, "ok": False, "detail": None,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "ms": int((time_mod.perf_counter() - started) * 1000),
            })
    return {"checks": checks}


@router.get("/diagnostics/logs")
def diagnostics_logs():
    import io
    import zipfile

    from engine import paths

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("app.log", "crash.marker"):
            path = paths.data_dir() / name
            if path.exists():
                archive.writestr(name, path.read_text(encoding="utf-8", errors="replace"))
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=jobengine-logs.zip"},
    )


@router.post("/diagnostics/cleanup-legacy-browser")
def cleanup_legacy_browser():
    from engine.autofill import browser_setup

    return {"freed_bytes": browser_setup.cleanup_legacy()}


# --- 008 self-update routes (FR-030) ----------------------------------------


@router.post("/updates/download")
def updates_download():
    from engine import updates

    if not updates.start_download():
        raise HTTPException(status_code=409, detail="a download is already running")
    return {"started": True}


@router.get("/updates/progress")
def updates_progress():
    from engine import updates

    return updates.progress()


@router.post("/updates/install")
def updates_install():
    from engine import updates

    try:
        updates.install()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    # the installer takes over; give this response time to flush, then exit
    import os
    import threading as threading_mod

    threading_mod.Timer(1.5, os._exit, args=(0,)).start()
    return {"installing": True}


@router.post("/whats-new/dismiss")
def whats_new_dismiss():
    from engine import APP_VERSION

    settings.set("WHATS_NEW_SEEN_VERSION", APP_VERSION)
    return {"dismissed": True}
