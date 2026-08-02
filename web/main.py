"""FastAPI app factory and HTML page routes. Thin layer per Constitution IV:
all business logic lives in engine/, this module only wires HTTP to it."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from engine import db, paths

log = logging.getLogger(__name__)

from .routes_api import parse_feed_params, router as api_router
from .routes_autofill import router as autofill_router
from .routes_bridge import router as bridge_router

from engine import APP_VERSION

templates = Jinja2Templates(directory=paths.resource_path("web/templates"))
templates.env.globals["app_version"] = APP_VERSION


def _humandate(value) -> str:
    """013 (FR-009): render a stored date/datetime string as "24 July 2026"
    (day, title-case full month, year; no leading zero). Tolerant — returns
    None/empty as "" and anything unparseable unchanged, so a template never
    crashes on an odd value."""
    if not value:
        return ""
    from datetime import datetime

    text = str(value).strip()
    head = text[:10]  # date portion of an ISO date or datetime
    try:
        dt = datetime.strptime(head, "%Y-%m-%d")
    except ValueError:
        return text
    return f"{dt.day} {dt.strftime('%B %Y')}"


templates.env.filters["humandate"] = _humandate


def _pending_update():
    """014 (CLS fix): the update banner, computed server-side so it renders
    inline in the initial HTML instead of being injected post-load (which
    shifted the page — measured CLS 0.27). Cheap + network-free (reads the
    cached daily-check result). Returns the info dict or None."""
    from engine import updates

    with updates._lock:
        info = updates._state.get("last_check")
    return info if (info and info.get("newer")) else None


def _unseen_whats_new():
    """014 (CLS fix): the once-per-version What's New overlay, computed
    server-side for inline render (same reason as _pending_update). Returns
    {entries, version} or None."""
    from engine import APP_VERSION as _v
    from engine import settings as settings_mod

    entries = WHATS_NEW.get(_v) or []
    if not entries or settings_mod.get("WHATS_NEW_SEEN_VERSION") == _v:
        return None
    return {"entries": entries, "version": _v}


def _unclean_exit():
    """015 (FR-005): non-empty when the previous session ended without a
    clean shutdown (engine/lifecycle.py marker) and the user hasn't
    dismissed the notice yet. Rendered server-side inline (014 CLS-safe
    pattern)."""
    from engine import settings as settings_mod

    return settings_mod.get("UNCLEAN_EXIT_AT") or None


def _stamp_problem():
    """015 (FR-008): the last pairing-preparation outcome, when it FAILED —
    drives the never-log-only banner on the Apply Assist and connect pages.
    None when there is no record (never stamped) or the last stamp was OK."""
    import json as json_mod

    from engine import paths as paths_mod

    path = paths_mod.data_dir() / "stamp_status.json"
    if not path.exists():
        return None
    try:
        data = json_mod.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "stamp_status.json unreadable", "at": None}
    if data.get("ok"):
        return None
    return {"error": data.get("error") or "unknown failure",
            "at": data.get("at")}


templates.env.globals["pending_update"] = _pending_update
templates.env.globals["unseen_whats_new"] = _unseen_whats_new
templates.env.globals["unclean_exit"] = _unclean_exit
templates.env.globals["stamp_problem"] = _stamp_problem


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
    "2.0.0": [
        "Every job in your feed now has a match score. Two-thirds of your "
        "eligible jobs had none at all — the old scoring stage spent about a "
        "minute of AI per job, ran inside the refresh, and was superseded "
        "and restarted long before it could finish. Ranking is now instant "
        "and uncapped, so nothing is left unranked, and the AI is spent "
        "afterwards on the best candidates.",
        "Two kinds of score, and the feed tells you which is which. A “~” "
        "score is a quick keyword match against your resume; a “•” score is "
        "a full AI assessment with skills and gap advice. Jobs upgrade from "
        "one to the other in place, in the background, best matches first. "
        "You are never shown an approximation as though it were a judgement.",
        "The refresh finishes in seconds instead of hours. It used to hold "
        "itself open for the entire scoring pass — every source reading "
        "“done”, the Refresh button refusing as “running”, and new-match "
        "alerts waiting behind it the whole time. Background AI scoring now "
        "runs after the refresh closes, shows its progress, and can only "
        "ever run once at a time.",
        "Applying always beats ranking. Background scoring stands down "
        "completely the moment you start filling in an application, so the "
        "form in front of you is never slowed down by work on the feed.",
        "Cover letters written in a rich-text box now fill. On forms that "
        "use a styled editor rather than a plain text area, that box used to "
        "be invisible to Apply Assist — not filled, not counted, and not "
        "even flagged for you. It is now filled like any other answer, or "
        "listed as needing you.",
        "The companion is cheaper to keep installed: on ordinary pages with "
        "no application form it now checks four times less often, and wakes "
        "instantly the moment a form appears.",
    ],
    "1.9.1": [
        "The companion no longer forgets what it filled. On the review page "
        "at the end of an escorted application — and when you paused or "
        "resumed the escort — the progress row reset to “Filled 0 · "
        "Seen 0”, in the exact moment it had the most to show for "
        "itself. It now keeps the real numbers; only stopping clears them.",
    ],
    "1.9.0": [
        "Apply Assist now takes you to the door. From a posting it presses "
        "Apply, signs you in with your saved login, fills every step, and "
        "presses Continue between steps it has completely filled — then "
        "stops at the review page. You read it and press Submit. It never "
        "presses Submit, never creates an account, and never touches a "
        "“prove you're human” check.",
        "Sign-in walls are no longer a dead end. The companion used to hide "
        "on any page with a password box — the exact page you needed it on. "
        "It now appears there, uses the login saved in Windows Credential "
        "Manager, and offers to save one right on the page if you have none.",
        "Creating an account is prepared for you: a strong password is "
        "generated, filled into both boxes, and saved to your OS keychain "
        "the moment it is used. You press Create account.",
        "Five reasons real applications didn't fill are fixed. Questions "
        "that label their field by reference (Workday and most modern "
        "forms) were arriving blank; forms inside a shadow root were "
        "invisible; Workday's dropdown rows matched nothing; a dropdown "
        "showing “Select…” counted as already answered; and fields in a "
        "floating dialog were treated as off-screen.",
        "A stale companion can no longer hide. If the app updates and the "
        "browser is still running the old extension, every surface says so "
        "and tells you to press ↻ — instead of showing a green tick while "
        "quietly dropping answers.",
        "“Apply with Apply Assist” fills the tab you pressed it in. It used "
        "to open a second copy of the posting and fill THAT, leaving the "
        "tab you were looking at stuck on “filling”.",
        "You can turn the escort off in Settings if you would rather press "
        "every button yourself — filling works the same either way.",
    ],
    "1.8.0": [
        "The companion is finally where you can see it. It had been rendering "
        "at the very bottom of the page — off screen on every job posting — "
        "since v1.0.0. It now sits pinned in the corner of your browser "
        "window and stays there.",
        "“Apply with Apply Assist” on a posting actually works. The "
        "button had been dead since it shipped: clicking it did nothing at "
        "all.",
        "One companion instead of two. The match score, the sponsorship "
        "grade, the fill progress and every answer now live in a single card "
        "that rests as a small pill and opens when you click it — or on "
        "its own when a fill starts or a question needs you.",
        "It shows up on bare application pages too. On a Greenhouse "
        "“/application” URL with no job details, there used to be "
        "nothing on screen; now the companion appears and offers to fill it.",
        "Every answer is on the page, grouped: what needs you first, then AI "
        "drafts to review, then the ordinary fields filled from your profile. "
        "Copy any of them, insert one into its field, or jump to it.",
        "Typing an answer no longer gets wiped. The panel used to rebuild "
        "itself every couple of seconds and destroy what you were typing "
        "mid-word.",
        "Stop, Fill again and Next job are on the page, so a whole "
        "application needs no switching back to the app. Alt+J opens the "
        "companion; Alt+Shift+J fills the current page.",
        "Starting Apply Assist from a job no longer navigates you away from "
        "the job you were reading.",
    ],
    "1.7.0": [
        "Apply Assist no longer invents answers. If a question can't be "
        "answered from your profile or resume — whether you applied here "
        "before, whether you did their course, your offer deadlines — it is "
        "left for you instead of guessed.",
        "Answers now match the field: no more yes/no in a date box, no more "
        "paragraphs in a dropdown, and your phone number stays out of the "
        "name-pronunciation question.",
        "Your Profile now holds what a real application asks for: address, "
        "work-authorization detail, education, preferences, and optional "
        "self-identification it maps onto each form's own wording "
        "(Male/Man, Straight/Heterosexual).",
        "The resume that goes out is yours — the tailored PDF only when you "
        "actually tailored that job — and it is checked before it is attached.",
        "Every drafted answer is readable on the page: copy it, insert it, or "
        "answer a skipped question once and it fills automatically from then on.",
        "Apply with Apply Assist straight from a job — in the app, or from "
        "the badge on a posting.",
        "Stop is always reachable, and Reset learned answers on the Profile "
        "page clears anything the AI saved that isn't true about you.",
    ],
    "1.6.0": [
        "Apply Assist now fills the page for real: known answers land in "
        "seconds, drafts arrive by themselves, and dropdown/yes-no questions "
        "are answered from the field's actual options.",
        "Everything happens on the page: the form opens itself on supported "
        "job boards, a small panel shows progress, and anything needing your "
        "eye is highlighted — you correct it right there and submit yourself.",
        "Tailoring can no longer crash the app: the on-device AI runs "
        "isolated and restarts by itself if anything goes wrong.",
    ],
    "1.5.0": [
        "Apply Assist pairing rebuilt: a live Connect page that verifies each "
        "step and says exactly what's wrong when something is.",
        "The app no longer freezes or crashes from the on-device AI.",
        "Job links and the assistant window now open in your preferred "
        "browser (Chrome by default) — changeable in Settings.",
    ],
    "1.4.0": [
        "A refreshed look: cleaner typography, spacing, and color across every "
        "page, in both the light and dark themes — same fast, private engine.",
        "It feels quicker: the page no longer jumps as it loads, Save/Applied/"
        "Hide react instantly, and pages transition smoothly.",
        "Press Ctrl/Cmd-K anywhere to open a command palette — jump to any view "
        "or run actions (refresh, switch theme, start Apply Assist) from the "
        "keyboard. In the feed, j/k move between jobs, Enter opens one, and / "
        "jumps to search.",
        "The Analytics page now has real charts of your funnel, sources, match "
        "scores, and callback rate.",
    ],
    "1.3.0": [
        "Fixed: Apply Assist now fills in your default browser (and your "
        "connected companion), instead of always opening Microsoft Edge — so "
        "it fills where you're actually signed in.",
        "Faster AI: the offline model now uses all your CPU cores, and your "
        "GPU when your setup supports it; resume import skips re-reading an "
        "unchanged resume.",
        "Dates now read like '24 July 2026', the Posted and Match columns show "
        "a clickable sort arrow, and every job page has a Back button.",
        "The app now has its own icon on the window, taskbar, installer, and "
        "browser tab.",
    ],
    "1.2.0": [
        "New: the Discovery badge. As you browse job postings — LinkedIn, "
        "Indeed, Greenhouse/Lever/Ashby, or any company career page — a small "
        "badge appears showing your match score against your resume and an "
        "H-1B sponsorship flag for the company.",
        "One click on the badge saves the posting straight into your Job "
        "Engine feed (and your Saved list) — no copy-pasting links, titles, or "
        "companies.",
        "It's read-only: the badge only reads what's on the page and shows its "
        "own card. It never clicks, types, or submits anything, and the page "
        "details are scored on your own machine — nothing leaves your computer.",
        "The badge appears only while the app is running and the companion is "
        "connected. After this update, open your browser's extensions page and "
        "click the reload (↻) icon on the Job Engine Companion card once.",
    ],
    "1.1.0": [
        "Apply Assist fills a lot more now. Custom dropdowns — the fancy "
        "click-to-open menus used for work authorization, EEO, and 'how did "
        "you hear about us' — fill from your saved answers, on every job "
        "board. Type-to-search boxes (location, school) pick the matching "
        "suggestion.",
        "Workday applications fill: NVIDIA, AMD, Qualcomm, Intel and other "
        "Workday employers now get their name/contact/dropdown fields filled, "
        "page by page as you advance the application. iCIMS and Taleo forms "
        "fill too.",
        "It still never clicks Submit, Apply, Next, or Log in — it only sets "
        "field values (the same as typing). You advance every page and click "
        "the real submit yourself, exactly as before.",
        "After this update, open your browser's extensions page and click the "
        "reload (↻) icon on the Job Engine Companion card once.",
    ],
    "1.0.1": [
        "Fixed: the browser companion could fail to connect (the status dot "
        "stayed grey). The companion now reliably connects within about 30 "
        "seconds of the app starting, and automatically reconnects on its own "
        "after your computer sleeps or the app restarts.",
        "After this update, open your browser's extensions page "
        "(chrome://extensions or edge://extensions) and click the reload (↻) "
        "icon on the Job Engine Companion card once — browsers keep running an "
        "unpacked extension's old code until you reload it.",
    ],
    "1.0.0": [
        "Apply Assist now fills in YOUR OWN browser. Install the new browser "
        "companion (one-time, free — see the Companion page) and applications "
        "fill in your everyday Chrome or Edge, where you're already logged in "
        "to job sites. No companion? Apply Assist still works in a separate "
        "assistant window, exactly as before.",
        "\"Fill this page\": found a job while browsing? Click the companion "
        "and it fills the application you're already looking at.",
        "AI now drafts answers to open-ended questions (\"Why this company?\") "
        "from your resume — filled in, clearly flagged, for you to review and "
        "edit before you submit. Confirmed answers are saved and reused. Visa/"
        "sponsorship/EEO questions are never AI-answered.",
        "New home dashboard: your top matches, application stats, and a "
        "next-actions list (drafts to review, follow-ups due) the moment you "
        "open the app.",
        "Tracker board gains per-application notes and follow-up dates; due "
        "follow-ups surface on the home screen.",
        "It's still $0, still private (AI runs on the bundled offline model by "
        "default), and it still never clicks submit for you — you always do.",
    ],
    "0.9.0": [
        "Apply Assist finally FILLS: it now watches the open page "
        "continuously and fills fields the moment they exist — slow-loading "
        "forms, forms behind the site's Apply button, multi-page "
        "applications, and forms inside embedded frames all work.",
        "Jobs open at the real application form now (Lever/Ashby links "
        "used to land on the description page).",
        "New 'Test Apply Assist' button: a bundled practice application "
        "fills with your own data in seconds — proof it works, on your "
        "machine, before you touch a real posting.",
        "Profile import rebuilt: upload returns instantly, extraction runs "
        "in the background with live progress, and a review screen shows "
        "every field (yours vs the resume's) — nothing changes without "
        "your say-so. It now genuinely works on the offline model.",
        "The bundled offline model is the default AI everywhere (private, "
        "$0); your cloud key automatically takes over if it ever fails — "
        "toggle in Settings.",
    ],
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
    from engine import matcher, upgrade
    from engine.ingest import SOURCE_ORDER, linkedin_linkout

    return {
        # 020 (FR-011): the background assessment pass, shown in the channel
        # strip beside the sources. It outlives the run, so it is its own
        # value rather than another entry in run.sources.
        "assessment": upgrade.progress(),
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
    from contextlib import asynccontextmanager

    def _run_startup() -> None:
        import threading

        db.init_db()

        # 010: dev-server equivalent of desktop.py's companion stamping —
        # when uvicorn runs web.main directly (quickstart dev flow), stamp
        # the extension for the conventional dev port so the companion can
        # pair. The desktop app stamps with its real dynamic port instead.
        if not getattr(sys, "frozen", False):
            try:
                from scripts import stamp_extension

                stamp_extension.stamp(
                    int(os.environ.get("JOBS_DEV_PORT", "8000"))
                )
            except Exception:
                log.debug("dev companion stamp skipped", exc_info=True)

        threading.Thread(target=_bootstrap_sponsorship, daemon=True).start()

        def _quiet_update_check() -> None:
            from engine import updates

            try:
                updates.startup_check()  # once daily; silent offline (FR-030)
            except Exception:
                pass

        threading.Thread(target=_quiet_update_check, daemon=True).start()

        # 020 (FR-004): pick the AI assessment backlog up on startup, not only
        # after a refresh. Ranking gives every job a keyword score during the
        # refresh that finds it, but the slower assessment is bounded per pass
        # — so a large backlog needs several passes. Without this, opening the
        # app inside the refresh cooldown would start no pass at all and the
        # backlog would sit there. start() is single-flight, so this can never
        # race the one a refresh kicks off.
        from engine import upgrade as _upgrade

        _upgrade.start("startup")

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        # 014: replaces the deprecated @app.on_event("startup").
        _run_startup()
        yield

    app = FastAPI(title="Personalized AI Job Engine", lifespan=_lifespan)
    app.mount(
        "/static",
        StaticFiles(directory=paths.resource_path("web/static")),
        name="static",
    )
    app.include_router(api_router)
    app.include_router(autofill_router)
    app.include_router(bridge_router)

    @app.middleware("http")
    async def _static_long_cache(request: Request, call_next):
        # 014 (perf): static assets are referenced with a ?v=<APP_VERSION>
        # buster in base.html, so a long immutable cache is safe — a new
        # release changes the URL and invalidates. Speeds up repeat visits
        # (chrome-devtools "Cache" insight).
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.post("/api/os/default-apps")
    def open_os_default_apps():
        """015 (FR-019): one-click jump to the OS default-browser setting —
        Windows only (the mismatch line renders without the button elsewhere)."""
        from fastapi import HTTPException

        if sys.platform != "win32":
            raise HTTPException(status_code=409, detail="Windows only")
        os.startfile("ms-settings:defaultapps")  # noqa: S606 — fixed URI
        return {"opened": True}

    @app.post("/api/unclean-exit/dismiss")
    def dismiss_unclean_exit():
        """015 (FR-005): one-time banner — dismissing clears the record."""
        from engine import settings as settings_mod

        settings_mod.set("UNCLEAN_EXIT_AT", "")
        return {"ok": True}

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
        # 010 FR-017: the home lead — top matches, application stats.
        # next-actions load client-side from /api/next-actions.
        top_matches, _ = db.query_jobs(
            window=None, statuses=("none", "saved"), entry_level=None,
            sort="score", limit=5,
        )
        analytics = db.application_analytics()
        _, saved_total = db.query_jobs(window=None, statuses=("saved",),
                                       entry_level=None)
        context["dashboard"] = {
            "top_matches": [
                {"id": j["id"], "title": j["title"], "company": j["company"],
                 "match_score": j.get("match_score")}
                for j in top_matches if j.get("match_score") is not None
            ],
            "stats": {
                "applied": analytics.get("total_applied", 0),
                "interview": analytics.get("interviews", 0),
                "saved": saved_total,
            },
        }
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
        from .routes_bridge import companion_doctor

        return templates.TemplateResponse(
            request,
            "diagnostics.html",
            {
                "log_tail": tail,
                "legacy_bytes": browser_setup.legacy_size_bytes(),
                # 015 (FR-014): the pairing chain, human-readable
                "doctor": companion_doctor(),
            },
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        from engine import credentials, db, watchlist

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
                # 019 (FR-034/FR-037): the escort's on/off state, shown
                # where the saved logins it uses are entered.
                "escort_enabled": (db.get_setting("escort_enabled") or "1") != "0",
            },
        )

    @app.get("/partials/profile/import", response_class=HTMLResponse)
    def profile_import_partial(request: Request):
        """009 (FR-012/FR-014): the import region — progress banner while
        extracting (or failed with the real error + Retry), the review
        screen when ready, empty when idle."""
        from engine import profile_import

        state = profile_import.status()
        if state["state"] in ("extracting", "failed"):
            return templates.TemplateResponse(
                request, "partials/import_progress.html", {"status": state}
            )
        if state["state"] == "ready":
            return templates.TemplateResponse(
                request,
                "partials/import_review.html",
                {"proposal": profile_import.proposal()},
            )
        return HTMLResponse("")

    @app.get("/practice/apply", response_class=HTMLResponse)
    def practice_apply(request: Request):
        """009 (FR-009): the bundled practice application — a realistic
        local form Apply Assist fills with the user's real data, no job
        site involved. Doubles as the on-machine proof the engine works."""
        return templates.TemplateResponse(request, "practice_apply.html", {})

    @app.get("/practice/frame", response_class=HTMLResponse)
    def practice_frame(request: Request):
        return templates.TemplateResponse(request, "practice_frame.html", {})

    @app.get("/practice/posting", response_class=HTMLResponse)
    def practice_posting(request: Request, newtab: int = 0):
        """016 (T014): a Greenhouse-shaped posting fixture — the form is
        hidden until the Apply control is clicked (the D1 apply-opener
        case); ?newtab=1 opens the form in a child tab (watch transfer)."""
        return templates.TemplateResponse(
            request, "practice_posting.html", {"newtab": bool(newtab)})

    # 016 (T014): server-side submit-click log — the E2E's proof that NO
    # automated click ever hits a submit control (SC-004).
    app.state.practice_submit_clicks = 0
    # 016 (T022): the practice pages beacon their own DOM state here —
    # extension-opened tabs aren't reachable via Playwright page handles,
    # so the fixtures self-report and the E2E polls this (still DOM truth).
    app.state.practice_fixture_state = {}

    @app.post("/practice/fixture-state")
    async def practice_fixture_state_write(request: Request):
        payload = await request.json()
        key = str(payload.get("page") or "unknown")
        request.app.state.practice_fixture_state[key] = payload
        return {"ok": True}

    @app.get("/practice/fixture-state")
    def practice_fixture_state_read(request: Request):
        return request.app.state.practice_fixture_state

    @app.post("/practice/submit-log")
    def practice_submit_log(request: Request):
        request.app.state.practice_submit_clicks += 1
        return {"clicks": request.app.state.practice_submit_clicks}

    @app.get("/practice/submit-log")
    def practice_submit_log_read(request: Request):
        return {"clicks": request.app.state.practice_submit_clicks}

    def _browser_intent() -> dict:
        """015 (FR-019): OS default vs preference, for the mismatch line.
        Auto IS the OS default, so no mismatch is possible there."""
        from engine import settings as settings_mod
        from engine.autofill import default_browser

        pref = settings_mod.get("PREFERRED_BROWSER") or "chrome"
        os_default = default_browser.default_channel_order()[0]
        return {
            "preference": pref,
            "os_default": os_default,
            "mismatch": pref != "auto" and os_default != pref,
            "is_windows": sys.platform == "win32",
        }

    @app.get("/companion", response_class=HTMLResponse)
    def companion_page(request: Request):
        """010 (FR-001/FR-022): the guided one-time install for the browser
        companion. Shows the exact folder path to load unpacked and a live
        connection check."""
        from scripts import stamp_extension

        ext_path = str(stamp_extension.dest_dir())
        return templates.TemplateResponse(
            request, "companion.html",
            {"ext_path": ext_path, "browser_intent": _browser_intent()},
        )

    @app.get("/autofill", response_class=HTMLResponse)
    def autofill_page(request: Request):
        jobs, _ = db.query_jobs(
            window=None, statuses=("saved",), entry_level=True
        )
        return templates.TemplateResponse(
            request, "autofill.html",
            {"jobs": jobs, "browser_intent": _browser_intent()},
        )

    @app.get("/partials/autofill/status", response_class=HTMLResponse)
    def autofill_status_partial(request: Request):
        from engine.autofill import browser_controller, drafts

        snapshot = browser_controller.queue_snapshot()
        current = browser_controller.current_job()
        current_title = None
        draft_rows = []
        if current is not None:
            entry = next(
                (e for e in snapshot["queue"] if e["job_id"] == current["job_id"]), None
            )
            if entry:
                current_title = f'{entry["title"]} — {entry["company"]}'
            lookup_id = (current["job_id"]
                         if current["job_id"] and current["job_id"] > 0 else None)
            draft_rows = drafts.list_for_job(lookup_id)
        return templates.TemplateResponse(
            request,
            "partials/autofill_status.html",
            {"current": current, "snapshot": snapshot,
             "current_title": current_title, "drafts": draft_rows},
        )

    return app


app = create_app()
