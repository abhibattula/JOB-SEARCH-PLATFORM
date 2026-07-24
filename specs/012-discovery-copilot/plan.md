# Implementation Plan: The Discovery Copilot

**Branch**: `012-discovery-copilot` | **Date**: 2026-07-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-discovery-copilot/spec.md`

## Summary

Surface the engine's existing match scoring and H-1B sponsorship intelligence at
**discovery time**: as the user browses any job posting, the companion extension
detects it, the local app scores it on demand over the existing authenticated
WebSocket bridge, and a closed-shadow-DOM **floating badge** shows the match
score, a sponsorship indicator, and a one-click **Save to Job Engine**. Detection
uses schema.org `JobPosting` JSON-LD (site-agnostic) plus LinkedIn/Indeed DOM
extractors. The capability is a **second, independent companion mode** that runs
alongside Apply Assist's fill flow without touching it, is strictly **read-only**
on the page, and reuses `basic_match` (offline), `sponsorship`, and `db.upsert_job`
verbatim — no new scoring logic, no cloud key, no off-machine data flow.

## Technical Context

**Language/Version**: Python 3.11+ (engine/web); plain ES-module + classic
content scripts (MV3 extension, `minimum_chrome_version: 116`).
**Primary Dependencies**: FastAPI + Jinja2 + HTMX (existing web); pydantic
(bridge message schemas); rapidfuzz (already used by `sponsorship`); no new deps.
**Storage**: existing SQLite at `data/jobs.db` — reuse `jobs`/`companies` tables
via `db.upsert_job` / `db.get_company_by_name`; add one thin read helper
(`get_job_by_url`). No schema change.
**Testing**: pytest (unit + `-m browser` real-extension integration via
Playwright `launch_persistent_context` into installed Edge/Chrome; real uvicorn +
stamped `pairing.json`), the 010/011 harness unchanged.
**Target Platform**: Windows/macOS desktop app + MV3 companion in the user's own
Chrome/Edge.
**Project Type**: desktop web-app (`engine/` core + thin `web/` FastAPI) with a
browser companion (`extension/`).
**Performance Goals**: badge shows within ~2s of the page settling (SC-001);
scoring is instant (offline `basic_match`); sponsorship lookup is an in-memory
dict match, computed off the event loop (`run_in_threadpool`, as fills already are).
**Constraints**: $0, offline-first, engine never imports web, read-only on the
page, page metadata never leaves the machine, no interference with Apply Assist.
**Scale/Scope**: single user; one score per viewed posting; no bulk/list scoring.

## Constitution Check

*GATE: evaluated against constitution v1.1.2. Re-checked after Phase 1 design.*

- **I. Speed-to-Value First** — PASS. Directly serves "get hired sooner": turns
  existing intelligence into an at-a-glance browse-time signal + one-click
  capture. No deferred capability (auth/multi-user/hosted/CLI-MCP) is built. The
  Principle III automation clarification is **not exercised** — discovery clicks
  nothing on the page (it is strictly read-only), so it stays well inside the
  no-submit/no-click boundary.
- **II. Zero-Subscription Cost** — PASS. Scoring is offline `basic_match`; no
  API key required; no new paid dependency; sponsorship reuses bundled public
  USCIS/DOL data already shipped.
- **III. API-First, Polite Ingestion** — PASS. Discovery is **not an ingestion
  source**: it reads only the single page the user has already opened in their
  own browser (no crawling, no rate concern, no auth/bot-protection bypass, no
  search-result-list scraping). A one-line note is added to the design doc
  recording that the companion may read the current page's public job metadata to
  render a local-only overlay — a bounded, read-only addition, not a new crawler.
- **IV. Reusable Core, Thin Web Layer** — PASS. New logic lives in
  `engine/discovery.py` (pure; imports only `db`/`basic_match`/`sponsorship`).
  `web/routes_bridge.py` gains nothing but message routing; the browser is the
  presentation surface. Engine never imports web.
- **V. Tested Core Logic** — PASS. `discovery.score_page` and the refactored
  `sponsorship.grade_company` get pytest coverage (score/band, sponsor grade,
  unknown-company, no-resume, parity with `apply_to_companies`); bridge handlers
  and the read-only guarantee are tested; real-browser integration proves the
  badge renders and Save persists.

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/012-discovery-copilot/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── discovery-bridge.md   # score_request/score_result + save_job/save_result
├── checklists/
│   └── requirements.md  # spec quality (from /speckit.specify)
└── tasks.md             # /speckit.tasks output (not created here)
```

### Source Code (repository root)

```text
engine/
├── discovery.py                 # NEW — score_page(): match + two-tier sponsorship + already_saved
├── sponsorship.py               # EDIT — extract grade_company(name, employers=None); reuse in apply_to_companies
├── basic_match.py               # REUSE — score() unchanged
├── db.py                        # EDIT — add get_job_by_url(url); upsert_job/get_company_by_name reused
└── autofill/
    ├── ext_protocol.py          # EDIT — ScoreRequest, SaveJob inbound models + _INBOUND registration
    └── ext_backend.py           # EDIT — _handle_score_request / _handle_save_job (independent of _watch)

web/
├── routes_bridge.py             # (no change — /ws/ext already routes all inbound to handle_message)
├── main.py                      # EDIT — WHATS_NEW 1.2.0 entry
└── templates/                   # EDIT — companion page copy: "browse any job site…"

extension/
├── manifest.json                # EDIT — add content/discovery.js; version 1.2.0
├── content/
│   └── discovery.js             # NEW — JSON-LD + LinkedIn/Indeed detect; read-only; shadow-DOM badge; save
└── background/
    └── service-worker.js        # EDIT — route score_result/save_result to top frame via toContent

tests/
├── test_discovery.py            # NEW — score_page + grade_company parity + get_job_by_url
├── test_ext_backend.py          # EDIT — score/save handlers, independence from _watch
├── test_ext_protocol.py         # EDIT (or within test_ext_backend) — new inbound models
├── test_extension_assets.py     # EDIT — discovery.js present/in-manifest/read-only/closed shadow
├── fixtures/discovery_pages/    # NEW — jsonld_jobposting.html, linkedin_jobs_view.html, indeed_viewjob.html
└── integration/
    └── test_discovery_badge.py  # NEW (-m browser) — badge renders w/ score; Save upserts; already-saved

packaging/
└── smoke_test.py                # EDIT — assert discovery.js bundled + version 1.2.0
```

**Structure Decision**: existing desktop-web + companion layout. The only new
engine module is `engine/discovery.py`; the only new extension file is
`extension/content/discovery.js`. Everything else is an additive edit to a file
that already owns that concern (protocol, backend, service worker, manifest).

## Phasing (maps to user stories)

- **Foundational** (blocks US1/US2): `sponsorship.grade_company` refactor +
  `db.get_job_by_url` + `engine/discovery.py` + protocol models + backend
  handlers + SW routing. Pure/unit-testable first (TDD red→green).
- **US1 (P1) — see match + sponsorship**: `discovery.js` detection (JSON-LD +
  LinkedIn/Indeed) + badge render on `score_result`; real-browser test that the
  badge shows the right score/company on all three fixture shapes.
- **US2 (P2) — save in one click**: Save button → `save_job` → `upsert_job`
  (source `manual`, status `saved`) → `save_result`; already-saved state; test
  that Save persists and dedups.
- **US3 (P3) — stay out of the way**: dismiss/collapse, non-overlapping placement,
  read-only assertion, and a no-interference check with an Apply Assist session.
- **Polish/Ship**: docs, WHATS_NEW 1.2.0, version bump, smoke, live gate, release.

## Complexity Tracking

No constitution violations — section intentionally empty.
