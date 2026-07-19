"""FastAPI app factory and HTML page routes. Thin layer per Constitution IV:
all business logic lives in engine/, this module only wires HTTP to it."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from engine import db, paths

from .routes_api import parse_feed_params, router as api_router

from engine import APP_VERSION

templates = Jinja2Templates(directory=paths.resource_path("web/templates"))
templates.env.globals["app_version"] = APP_VERSION


def _bootstrap_sponsorship() -> None:
    """Load the bundled USCIS data on first run so installed users get
    sponsor badges with zero setup. No-op once the table has rows."""
    from engine import sponsorship

    if db.h1b_employer_count() > 0:
        return
    bundled = paths.resource_path("assets/uscis")
    if not bundled.exists():
        return
    employers, _ = sponsorship.load_uscis_dir(bundled)
    if employers:
        sponsorship.store_employers(employers)
        sponsorship.apply_to_companies()


def _feed_context(
    request: Request,
    window: str = "7d",
    status: str | None = None,
    location: str | None = None,
    remote: int = 0,
    sort: str = "score",
    entry_level: str | None = None,
    ineligible: int = 0,
    min_score: float | None = None,
    seen: str | None = None,
) -> dict:
    params = parse_feed_params(
        window, status, location, remote, sort, entry_level,
        ineligible=ineligible, min_score=min_score, seen=seen,
    )
    jobs, total = db.query_jobs(**params)
    run = db.get_run_status()
    profile = db.get_profile()
    from engine import matcher

    return {
        "has_llm_key": matcher.llm_available(),
        "request": request,
        "jobs": jobs,
        "total": total,
        "run": run,
        "window": window if window in ("7d", "24h", "all") else "7d",
        "status_view": status or "",
        "location": location or "",
        "remote": bool(remote),
        "sort": sort,
        "has_profile": bool(profile and profile.get("resume_text")),
        "entry_level": entry_level or "",
        "ineligible": bool(ineligible),
        "min_score": int(min_score) if min_score else 0,
        "query_string": request.url.query,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Personalized AI Job Engine")
    app.mount(
        "/static",
        StaticFiles(directory=paths.resource_path("web/static")),
        name="static",
    )
    app.include_router(api_router)

    @app.on_event("startup")
    def _startup() -> None:
        import threading

        db.init_db()
        threading.Thread(target=_bootstrap_sponsorship, daemon=True).start()

    @app.get("/", response_class=HTMLResponse)
    def index(
        request: Request,
        window: str = "7d",
        status: str | None = None,
        location: str | None = None,
        remote: int = 0,
        sort: str = "score",
        entry_level: str | None = None,
        ineligible: int = 0,
        min_score: float | None = None,
        seen: str | None = None,
    ):
        context = _feed_context(
            request, window, status, location, remote, sort, entry_level,
            ineligible, min_score, seen,
        )
        return templates.TemplateResponse(request, "feed.html", context)

    @app.get("/partials/feed", response_class=HTMLResponse)
    def feed_partial(
        request: Request,
        window: str = "7d",
        status: str | None = None,
        location: str | None = None,
        remote: int = 0,
        sort: str = "score",
        entry_level: str | None = None,
        ineligible: int = 0,
        min_score: float | None = None,
        seen: str | None = None,
    ):
        context = _feed_context(
            request, window, status, location, remote, sort, entry_level,
            ineligible, min_score, seen,
        )
        return templates.TemplateResponse(request, "partials/feed_table.html", context)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: int):
        import json

        job = db.get_job(job_id)
        if job is None:
            return HTMLResponse("<h1>Job not found</h1>", status_code=404)
        match = json.loads(job["match_json"]) if job.get("match_json") else None
        evidence = (
            json.loads(job["sponsorship_evidence"])
            if job.get("sponsorship_evidence")
            else None
        )
        return templates.TemplateResponse(
            request,
            "job_detail.html",
            {"job": job, "match": match, "evidence": evidence},
        )

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request):
        return templates.TemplateResponse(
            request, "profile.html", {"profile": db.get_profile()}
        )

    @app.get("/analytics", response_class=HTMLResponse)
    def analytics_page(request: Request):
        return templates.TemplateResponse(
            request, "analytics.html", {"stats": db.application_analytics()}
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        from .routes_api import get_settings

        return templates.TemplateResponse(
            request, "settings.html", {"settings": get_settings()}
        )

    return app


app = create_app()
