# Feature 012 "The Discovery Copilot" (v1.2.0): score any job page you browse, save it in one click

## Context

Apply Assist (010/011) is strong once you're *on* an application form — but the
user still finds jobs the old way: scrolling LinkedIn/Indeed/company career
pages with no signal about whether a posting is worth their time. The paid
tools they asked us to beat (Simplify, JobRight, Sprout) all solve this with a
**browser overlay**: as you browse, a small badge shows your match score and a
sponsorship flag, with one click to save. We already own every ingredient —
instant offline scoring (`basic_match`), H-1B sponsorship intelligence
(`sponsorship` + the graded `companies` table), an authenticated companion
bridge, and a closed-shadow-DOM overlay — but they're only wired into the fill
flow. This release surfaces them **at discovery time**, on any job page.

### User-locked decisions (AskUserQuestion, 2026-07-24)

- **Direction:** Discovery copilot in the browser — an on-page match +
  sponsorship badge with Save-to-Job-Engine, as the user browses.
- **Overlay:** **Auto floating badge** — a small shadow-DOM badge that
  auto-appears on any detected job page, dismissable, never covering page
  controls (bottom-right, collapsible).
- **Site coverage:** **JSON-LD + LinkedIn/Indeed** — the primary extractor is
  schema.org `JobPosting` JSON-LD (covers Greenhouse/Lever/Ashby/most company
  career pages for free), plus dedicated LinkedIn and Indeed DOM extractors for
  the two biggest boards that don't emit clean JSON-LD.
- Still $0, offline-first scoring, never auto-submits, engine never imports web.

## What's new vs. what's reused

The companion gains a **second, independent mode** that runs alongside (never
interferes with) Apply Assist's fill/watch session:

- **Detect** a job posting on the current page (JSON-LD `JobPosting`, else a
  LinkedIn/Indeed DOM extractor) → title, company, description, url.
- **Score on demand** in the app: `basic_match.score` for the match (instant,
  offline) + sponsorship grade/cap-exempt for the company.
- **Show** a floating badge: match number, sponsor pill, Save button.
- **Save** upserts the posting into the normal feed/tracker (`source="manual"`).

Reused wholesale (no new scoring/sponsorship logic invented):
- `engine/basic_match.py::score(resume_text, title, description, extra_skills)`
  — the exact call `engine/pipeline.py:251-257` already makes.
- `engine/sponsorship.py::grade()`, `cap_exempt()`, `match_employer()` +
  `engine/db.py::get_company_by_name()` / `load_h1b_employers()`.
- `engine/db.py::upsert_job()` (dedup-safe; `source="manual"` already valid).
- The bridge: `relayFromContent` (tags `tab_id`) → `ext_protocol.parse_inbound`
  → `ext_backend.handle_message`; app→content via `state.onMessage`→`toContent`.
- The closed-shadow-DOM overlay technique from `extension/content/overlay.js`.

## Architecture (4 workstreams)

### WS-A — on-demand scoring + sponsorship service (engine, pure)

- `engine/discovery.py` (NEW, engine-only — imports `db`, `basic_match`,
  `sponsorship`; **never** web): `score_page(title, company, description) ->
  dict` returning `{match_score, band, matching_skills, missing_skills,
  sponsor_grade, cap_exempt, approvals, has_sponsor_data}`.
  - Match: load `db.get_profile()`; if no `resume_text`, return a neutral,
    honest result flagged "add your resume for a match". Else
    `basic_match.score(profile["resume_text"], title, description,
    extra_skills=set(profile.get("skills") or []))` — same as the feed pipeline.
    `band` = Strong/Good/Fair from the score (reuse the feed's thresholds).
  - Sponsorship: try `db.get_company_by_name(company)` first (already-graded
    fast path — returns `sponsor_grade`, `cap_exempt`, `h1b_approvals`); on miss
    fall back to on-demand `sponsorship.match_employer(company,
    db.load_h1b_employers())` → `grade(...)` + `cap_exempt(company)`. Never a
    fabricated grade below the petition floor (returns None = "unknown"), same
    guarantee as `apply_to_companies`.
- **Refactor for DRY:** extract the per-company grading block inside
  `sponsorship.apply_to_companies()` (lines ~177-200) into
  `sponsorship.grade_company(name, employers=None) -> dict` and call it from
  both `apply_to_companies` and `discovery.score_page`, so on-demand grading and
  batch grading can never diverge (unit-tested for parity).
- `engine/db.py`: add `get_job_by_url(url) -> dict | None` (thin, indexed on the
  existing `jobs.url UNIQUE`) for the "already saved" check — cheaper and
  clearer than scanning `list_all_jobs_minimal()`.

### WS-B — bridge messages (protocol + backend, independent of the fill session)

- `engine/autofill/ext_protocol.py`: two new inbound models + registrations —
  `ScoreRequest{tab_id, url, title, company, description}` and
  `SaveJob{tab_id, url, title, company, description, location=""}` added to
  `_INBOUND`. (1 MB bound + strict validation already apply; `description` is
  truncated defensively in the handler.) Outbound `score_result` and
  `save_result` use the existing `outbound()` envelope — no schema needed.
- `engine/autofill/ext_backend.py`: `_handle_score_request(msg)` →
  `discovery.score_page(...)` + `get_job_by_url` → `send(_outbound(
  "score_result", tab_id=msg.tab_id, **result, already_saved=bool))`;
  `_handle_save_job(msg)` → `db.upsert_job({...,"source":"manual"})` →
  `send(_outbound("save_result", tab_id=msg.tab_id, status=..., job_id=...,
  already=...))`. Dispatch both from `handle_message`. **Crucially these read
  NOTHING from `_watch`/`bc._state`** — discovery works whether or not an Apply
  Assist queue is running, and never mutates fill state.
- `extension/background/service-worker.js`: in `state.onMessage`, add
  `case "score_result"` / `case "save_result"` → `toContent(msg.tab_id, {...},
  0)` (top frame). The content→app path already forwards `{_je, payload}` via
  `relayFromContent` (which stamps `tab_id`) — no SW change needed outbound.

### WS-C — job detection + the floating discovery badge (extension)

- `extension/content/discovery.js` (NEW; added to `manifest.json`
  `content_scripts.js` after `overlay.js`). Guards to **top frame only**
  (`window === window.top`). Responsibilities:
  - **Detect** on load + on SPA navigation (URL-change poll / history hook,
    debounced): primary = parse `script[type="application/ld+json"]` for an
    object (or `@graph` entry) with `@type` == `JobPosting`, reading `title`,
    `hiringOrganization.name`, `description`. Fallbacks keyed by host:
    `linkedin.com/jobs/view/...` and `indeed.com` (`/viewjob`, `/jobs`) DOM
    extractors (title/company nodes). No match → no badge.
  - **Request** a score: `chrome.runtime.sendMessage({_je:true, payload:{
    type:"score_request", url, title, company, description}})` (same `toApp`
    idiom as `main.js`). It **never clicks or mutates the page** — read-only.
  - **Render** the badge only when `score_result` arrives (so a badge never
    appears dead when the app is closed/disconnected). Closed shadow root, own
    host id `je-discovery-badge-host`, fixed bottom-right, small, collapsible,
    with a ✕ dismiss (per-URL). Shows company · title, the match number with a
    Strong/Good/Fair band color, a sponsor pill (grade `A`–`F`, or "cap-exempt
    likely", or "H-1B: unknown"), and a **Save to Job Engine** button.
  - **Save**: button → `{_je, payload:{type:"save_job", ...}}`; on `save_result`
    the button becomes "Saved ✓" (or shows "Already saved" when
    `already_saved`/`already` is true). Re-detects & re-renders on nav.
- Styling: brand-consistent with `overlay.js` (dark card, same radius/shadow),
  but visually distinct (it's discovery, not an active fill) and theme-safe.

### WS-D — verification, docs, ship

- **Unit** (`tests/test_discovery.py`): `score_page` returns a real score/band
  from a seeded profile + JD; sponsor grade from a seeded graded company;
  unknown company → grade None + cap-exempt heuristic still fires; no-resume →
  neutral flagged result. `sponsorship.grade_company` parity test (same output
  as the `apply_to_companies` path on identical inputs). `db.get_job_by_url`.
- **Protocol** (`tests/test_ext_backend.py` / protocol test): `ScoreRequest`/
  `SaveJob` parse; oversize/unknown rejected; `_handle_score_request` emits a
  `score_result` with the expected fields via an injected `send`;
  `_handle_save_job` upserts `source="manual"` and reports `already` on the
  second call — all with **no `_watch` session set** (proves independence).
- **Static assets** (`tests/test_extension_assets.py`): `discovery.js` is
  present and listed in `manifest.json`; it contains the JSON-LD selector and
  the LinkedIn/Indeed host checks; it makes **no `.click()` on page elements**
  (read-only) and uses a closed shadow root.
- **Real browser** (`-m browser`, `--load-extension`, real uvicorn + stamped
  pairing — the 010/011 harness): fixtures `jsonld_jobposting.html` (schema.org
  `JobPosting`), `linkedin_jobs_view.html`, `indeed_viewjob.html`. Assert the
  badge renders with a numeric score and the right company; clicking **Save**
  upserts the job (verified via the app DB / a query) and the button flips to
  Saved; a second load of the same URL shows "Already saved".
- **Docs**: README (new "Discovery badge" capability + the always-read-only,
  local-only note), USER_MANUAL new section, USER_GUIDE quick walkthrough, the
  companion page copy ("Browse any job site — the badge shows your match +
  H-1B sponsorship; one click saves it"). What's New **1.2.0** entry.
- **Ship**: version **1.2.0** (minor — new capability). Full `pytest -q` ×2 +
  `-m browser` + `-m slow` green; frozen build + `packaging/smoke_test.py`
  (assert `discovery.js` bundled + version 1.2.0) PASS; manual live gate on a
  real LinkedIn + Indeed + a Greenhouse/JSON-LD posting (badge shows a score,
  Save lands the job in the feed). Then merge → mirror `main:001-ai-job-engine`
  → keep branch → tag `v1.2.0` → verify BOTH installers on the Release page.

## Constitution guardrails (enforced by test)

$0 · scoring is **offline** (`basic_match`; no cloud key needed) · engine never
imports web (`discovery.py` uses only `db`/`basic_match`/`sponsorship`) · the
discovery script is **read-only** — it never clicks, mutates, or submits the
page (only renders its own shadow badge) · never bypass bot protection (it reads
the page the user is already viewing, in their own browser; no scraping of
search-result lists at scale) · page metadata is sent **only** to the local
authenticated bridge, never off-machine · sensitive visa/EEO logic untouched
(discovery never fills). A one-line **constitution clarification** records that
the companion may read the current page's public job metadata to render an
on-demand, local-only discovery overlay (a bounded, read-only addition — not a
relaxation of the no-click/no-submit or no-bulk-scrape rules).

## Verification (must pass before shipping)

- `discovery.score_page` unit matrix green; `grade_company` parity proven.
- Protocol accepts `score_request`/`save_job`, rejects malformed/oversize.
- Backend emits correct `score_result`/`save_result` with **no fill session** —
  discovery never touches Apply Assist state (regression guard).
- Real browser: JSON-LD, LinkedIn, and Indeed fixtures each render the badge
  with the right score; Save upserts (`source="manual"`) and dedups on repeat;
  the discovery script is proven to click nothing on the page.
- Existing 20 browser tests + fill/idle-recovery tests stay green (no
  interference between the discovery script and the fill content scripts).
- Full `pytest` ×2 + `-m browser` + `-m slow` green; frozen smoke PASS; manual
  live gate on real LinkedIn/Indeed/Greenhouse postings.

## Process

New branch `012-discovery-copilot` → design doc committed →
speckit chain (specify → clarify → plan → checklist → tasks → analyze, fix all
findings BEFORE implementation) → hybrid `/speckit-implement` + superpowers TDD
(red→green) → docs → frozen smoke → live gate → ship v1.2.0. (Same pipeline as
010/011; ask before starting implementation.)

## Non-goals

Auto-apply from the badge (the user clicks through to Apply Assist as today) ·
bulk scoring of whole search-result lists / crawling boards · cloud scoring by
default (offline `basic_match` is the on-demand tier) · overlays on non-job
pages · Chrome Web Store publishing or code signing · scanned-image resume OCR.
