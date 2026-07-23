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
from .routes_autofill import router as autofill_router

from engine import APP_VERSION

templates = Jinja2Templates(directory=paths.resource_path("web/templates"))
templates.env.globals["app_version"] = APP_VERSION


def _current_theme() -> str:
    """Explicit user choice ('light'/'dark') or '' when unset — '' lets the
    CSS prefers-color-scheme fallback decide (FR-021)."""
    from engine import settings

    value = settings.get("THEME") or ""
    return value if value in ("light", "dark") else ""


templates.env.globals["current_theme"] = _current_theme

# 008 (FR-032): plain-language changelog behind the What's New overlay —
# keyed by APP_VERSION, shown once per version.
WHATS_NEW: dict[str, list[str]] = {
    "0.8.0": [
        "Apply Assist now opens your installed Edge or Chrome directly — no "
        "browser download step, and when something fails you see exactly why.",
        "The desktop window behaves: select and copy any text, copy apply "
        "links with one click, open postings in your own browser, download PDFs.",
        "Fresher, more genuine jobs: 2-week default window, closed postings "
        "auto-delisted, 450+ company career boards monitored (editable in "
        "Settings), Google Jobs added, one-click LinkedIn searches.",
        "Your resume fills your whole profile (with your consent), and the "
        "job search now follows your profile's terms and locations.",
        "Updates install from inside the app with a progress bar.",
        "New Diagnostics page (Settings → Diagnostics) if anything misbehaves.",
    ],
}


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


def _onboarding_state(profile: dict | None) -> dict | None:
    """FR-027: setup steps derived live from real state — no stored step
    flags to drift. None (hidden) once dismissed or everything's done."""
    from engine import matcher, settings

    if settings.get("ONBOARDING_DISMISSED") == "1":
        return None
    steps = [
        {
            "label": "Upload your resume",
            "href": "/profile",
            "hint": "unlocks match scores and the Resume builder",
            "done": bool(profile and profile.get("resume_text")),
        },
        {
            "label": "Fill in your profile basics",
            "href": "/profile",
            "hint": "name, email, work authorization — Apply Assist fills from these",
            "done": bool(profile and profile.get("first_name") and profile.get("email")),
        },
        {
            "label": "Load sponsorship data",
            "href": "/settings",
            "hint": "turns UNKNOWN badges into grades",
            "done": db.h1b_employer_count() > 0,
        },
        {
            "label": "Add a free AI key (optional)",
            "href": "/settings",
            "hint": "the bundled offline model already works without one",
            "done": matcher.llm_available(),
        },
        {
            "label": "Apply to your first job",
            "href": "/autofill",
            "hint": "Apply Assist uses your installed Edge/Chrome — nothing to download",
            "done": db.query_jobs(window=None, statuses=["applied"])[1] > 0,
        },
    ]
    if all(step["done"] for step in steps):
        return None
    return {"steps": steps}


def _replace_query(request: Request, **overrides) -> str:
    """Rebuild the feed URL keeping every current filter, overriding only
    what's passed (008 FR-019: window/sort/view switches never drop state).
    None/'' removes the key."""
    from urllib.parse import urlencode

    params = {k: v for k, v in request.query_params.items()}
    for key, value in overrides.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = str(value)
    query = urlencode(params)
    return f"/?{query}" if query else "/"


def _feed_context(
    request: Request,
    window: str = "14d",
    status: str | None = None,
    location: str | None = None,
    remote: int = 0,
    sort: str = "score",
    entry_level: str | None = None,
    ineligible: int = 0,
    min_score: float | None = None,
    seen: str | None = None,
    strong_sponsors: int = 0,
    page: int = 1,
    source: str | None = None,
    limit: int = 100,
) -> dict:
    params = parse_feed_params(
        window, status, location, remote, sort, entry_level,
        limit=limit, ineligible=ineligible, min_score=min_score, seen=seen,
        strong_sponsors=strong_sponsors, page=page, source=source,
    )
    jobs, total = db.query_jobs(**params)
    run = db.get_run_status()
    profile = db.get_profile()
    from engine import matcher
    from engine.ingest import SOURCE_ORDER, linkedin_linkout

    return {
        "linkedin_search_url": linkedin_linkout.url_for_profile(profile),
        "has_llm_key": matcher.llm_available(),
        "request": request,
        "jobs": jobs,
        "total": total,
        "run": run,
        "onboarding": _onboarding_state(profile),
        "window": window if window in ("14d", "7d", "24h", "all") else "14d",
        "status_view": status or "",
        "location": location or "",
        "remote": bool(remote),
        "sort": sort,
        "has_profile": bool(profile and profile.get("resume_text")),
        "entry_level": entry_level or "",
        "ineligible": bool(ineligible),
        "min_score": int(min_score) if min_score else 0,
        "strong_sponsors": bool(strong_sponsors),
        "query_string": request.url.query,
        # 008 (FR-019/FR-020)
        "seen": seen or "",
        "source": source or "",
        "sources": list(SOURCE_ORDER),
        "page": max(1, page),
        "pages": max(1, -(-total // params["limit"])),
        "replace_query": lambda **kw: _replace_query(request, **kw),
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Personalized AI Job Engine")
    app.mount(
        "/static",
        StaticFiles(directory=paths.resource_path("web/static")),
        name="static",
    )
    app.include_router(api_router)
    app.include_router(autofill_router)

    @app.on_event("startup")
    def _startup() -> None:
        import threading

        db.init_db()
        threading.Thread(target=_bootstrap_sponsorship, daemon=True).start()

        def _quiet_update_check() -> None:
            from engine import updates

            try:
                updates.startup_check()  # once daily; silent offline (FR-030)
            except Exception:
                pass

        threading.Thread(target=_quiet_update_check, daemon=True).start()

    @app.get("/", response_class=HTMLResponse)
    def index(
        request: Request,
        window: str = "14d",
        status: str | None = None,
        location: str | None = None,
        remote: int = 0,
        sort: str = "score",
        entry_level: str | None = None,
        ineligible: int = 0,
        min_score: float | None = None,
        seen: str | None = None,
        strong_sponsors: int = 0,
        view: str | None = None,
        page: int = 1,
        source: str | None = None,
        limit: int = 100,
    ):
        context = _feed_context(
            request, window, status, location, remote, sort, entry_level,
            ineligible, min_score, seen, strong_sponsors, page, source, limit,
        )
        context["board_view"] = view == "board"
        # 008 (FR-033): surface an unclean previous shutdown exactly once
        from engine import paths

        marker = paths.data_dir() / "crash.marker"
        if marker.exists():
            context["crashed_last_run"] = marker.read_text(
                encoding="utf-8", errors="replace"
            )[:300]
            marker.unlink(missing_ok=True)
        return templates.TemplateResponse(request, "feed.html", context)

    @app.get("/partials/feed", response_class=HTMLResponse)
    def feed_partial(
        request: Request,
        window: str = "14d",
        status: str | None = None,
        location: str | None = None,
        remote: int = 0,
        sort: str = "score",
        entry_level: str | None = None,
        ineligible: int = 0,
        min_score: float | None = None,
        seen: str | None = None,
        strong_sponsors: int = 0,
        view: str | None = None,
        page: int = 1,
        source: str | None = None,
        limit: int = 100,
    ):
        context = _feed_context(
            request, window, status, location, remote, sort, entry_level,
            ineligible, min_score, seen, strong_sponsors, page, source, limit,
        )
        context["board_view"] = view == "board"
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
        tailoring = json.loads(job["tailor_json"]) if job.get("tailor_json") else None
        from .routes_api import sponsor_evidence_for

        sponsor_intel = sponsor_evidence_for(job)
        return templates.TemplateResponse(
            request,
            "job_detail.html",
            {"job": job, "match": match, "evidence": evidence,
             "tailoring": tailoring, "sponsor_intel": sponsor_intel},
        )

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request):
        from engine.autofill import answer_bank

        import json as json_mod

        from engine import settings as settings_mod

        pending = settings_mod.get("PENDING_IDENTITY_CONFLICTS") or "[]"
        return templates.TemplateResponse(
            request,
            "profile.html",
            {
                "profile": db.get_profile(),
                "answer_bank_entries": answer_bank.list_all(),
                "extraction_conflict": request.query_params.get("extraction_conflict") == "1",
                "identity_conflicts": json_mod.loads(pending or "[]"),
            },
        )

    @app.get("/analytics", response_class=HTMLResponse)
    def analytics_page(request: Request):
        return templates.TemplateResponse(
            request, "analytics.html", {"stats": db.application_analytics()}
        )

    @app.get("/partials/update-banner", response_class=HTMLResponse)
    def update_banner(request: Request):
        """008 (FR-030): rendered when the daily startup check (or a manual
        check) found a newer release."""
        from engine import updates

        with updates._lock:
            info = updates._state.get("last_check")
        if not info or not info.get("newer"):
            return HTMLResponse("")
        return templates.TemplateResponse(
            request, "partials/update_banner.html", {"update": info}
        )

    @app.get("/partials/whats-new", response_class=HTMLResponse)
    def whats_new(request: Request):
        """008 (FR-032): version-specific overlay, shown exactly once."""
        from engine import APP_VERSION, settings as settings_mod

        entries = WHATS_NEW.get(APP_VERSION) or []
        if not entries or settings_mod.get("WHATS_NEW_SEEN_VERSION") == APP_VERSION:
            return HTMLResponse("")
        return templates.TemplateResponse(
            request,
            "partials/whats_new.html",
            {"entries": entries, "version": APP_VERSION},
        )

    @app.get("/diagnostics", response_class=HTMLResponse)
    def diagnostics_page(request: Request):
        from engine import paths
        from engine.autofill import browser_setup

        log_path = paths.data_dir() / "app.log"
        tail = ""
        if log_path.exists():
            tail = "\n".join(
                log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
            )
        return templates.TemplateResponse(
            request,
            "diagnostics.html",
            {
                "log_tail": tail,
                "legacy_bytes": browser_setup.legacy_size_bytes(),
            },
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        from engine import credentials, watchlist

        from .routes_api import get_settings

        watchlist.ensure_seeded()
        default_cred = credentials.get_default()
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "watchlist_companies": watchlist.list_all(),
                "settings": get_settings(),
                "credential_domains": credentials.list_domains(),
                "default_credential_email": default_cred["email"] if default_cred else None,
            },
        )

    @app.get("/practice/apply", response_class=HTMLResponse)
    def practice_apply(request: Request):
        """009 (FR-009): the bundled practice application — a realistic
        local form Apply Assist fills with the user's real data, no job
        site involved. Doubles as the on-machine proof the engine works."""
        return templates.TemplateResponse(request, "practice_apply.html", {})

    @app.get("/practice/frame", response_class=HTMLResponse)
    def practice_frame(request: Request):
        return templates.TemplateResponse(request, "practice_frame.html", {})

    @app.get("/autofill", response_class=HTMLResponse)
    def autofill_page(request: Request):
        jobs, _ = db.query_jobs(
            window=None, statuses=("saved",), entry_level=True
        )
        return templates.TemplateResponse(request, "autofill.html", {"jobs": jobs})

    @app.get("/partials/autofill/status", response_class=HTMLResponse)
    def autofill_status_partial(request: Request):
        from engine.autofill import browser_controller

        snapshot = browser_controller.queue_snapshot()
        current = browser_controller.current_job()
        current_title = None
        if current is not None:
            entry = next(
                (e for e in snapshot["queue"] if e["job_id"] == current["job_id"]), None
            )
            if entry:
                current_title = f'{entry["title"]} — {entry["company"]}'
        return templates.TemplateResponse(
            request,
            "partials/autofill_status.html",
            {"current": current, "snapshot": snapshot, "current_title": current_title},
        )

    return app


app = create_app()
