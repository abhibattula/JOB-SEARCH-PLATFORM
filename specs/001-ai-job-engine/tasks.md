# Tasks: Personalized AI Job Engine

**Input**: Design documents from `/specs/001-ai-job-engine/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-api.md, quickstart.md

**Tests**: Included — mandated by Constitution Principle V (Tested Core Logic) for
deterministic engine logic (classifier, dedup, recency, sponsorship join) and by
the contract-test plan in `contracts/http-api.md`. Test tasks precede the
implementation they gate (TDD).

**Organization**: Tasks are grouped by user story so each story is an
independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (fresh-jobs feed), US2 (entry-level + sponsorship), US3 (resume matching)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton and static assets

- [x] T001 Create project skeleton per plan.md: `engine/` + `engine/ingest/` + `web/templates/partials/` + `web/static/` + `tests/fixtures/` dirs with `__init__.py` files; `.gitignore` (data/, .env, .venv, __pycache__); `requirements.txt` (fastapi, uvicorn[standard], jinja2, python-multipart, httpx, python-jobspy, PyMuPDF, rapidfuzz, pydantic, PyYAML, python-dotenv, openai, pandas, openpyxl, pytest); `.env.example` (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, JOBS_DB_PATH, JOBSPY_LINKEDIN, SCHEDULE_REFRESH)
- [x] T002 [P] Vendor `web/static/htmx.min.js` and create minimal `web/static/styles.css`
- [x] T003 [P] Create `companies.yml` seed list: ~50 SWE companies (from SimplifyJobs/New-Grad-Positions list) + ~25 hardware employers (NVIDIA, AMD, Qualcomm, Micron, TI, Marvell, Analog Devices…) with `ats` type and slug; Workday entries carry `tenant` + `site`. Include a throwaway validation script (`scripts/check_seeds.py`) that hits each board endpoint once and reports slugs returning errors/empty — wrong slugs silently produce zero jobs

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database core, ingestion primitives, and app shell that every story builds on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [P] Write failing tests in `tests/test_db.py`: idempotent schema init; upsert dedup by `url` and by `dedup_key`; `first_seen`/`status`/`match_score` preserved on re-upsert; recency queries (7d/24h windows using `COALESCE(posted_date, first_seen)`); status transitions
- [x] T005 Implement `engine/db.py` to pass T004: 4 tables + indexes per data-model.md, WAL mode, `JOBS_DB_PATH` env override, `upsert_job` (creates the `companies` row on the fly with `ats_type NULL` for non-seed companies from HN/jobspy), feed query with all contract filters, `refresh_runs` helpers (cooldown lookup, stale-run supersede), status update. Connections are per-call/thread-safe (background refresh writes while web reads); all timestamps stored as UTC ISO strings
- [x] T006 Implement `engine/ingest/base.py`: `RawJob` dataclass (title, company, location, remote, description, url, posted_date, source), Source protocol, polite httpx helper (≤1 req/s/domain, timeout, single retry), and source registry in `engine/ingest/__init__.py`
- [x] T007 Implement `web/main.py` FastAPI app factory + `web/templates/base.html` + `app.py` uvicorn entrypoint serving a shell page at GET /

**Checkpoint**: `pytest tests/test_db.py` green; `python app.py` serves a page

## Phase 3: User Story 1 - Open the App and See Fresh, Relevant Jobs (Priority: P1) 🎯 MVP

**Goal**: Open browser → cached feed of last-7-days jobs renders instantly, background refresh auto-starts, new jobs stream in, 24h toggle works, statuses (saved/applied/hidden) keep the feed actionable.

**Independent Test**: Clean DB → `python app.py` → feed populates from real sources without manual action; 24h toggle narrows; re-open within 30 min uses cache; marking Applied removes a job from the default feed.

### Tests for User Story 1

- [x] T008 [P] [US1] Record real JSON responses as fixtures in `tests/fixtures/` and write failing parser tests in `tests/test_sources.py` for Greenhouse, Lever, Ashby (httpx MockTransport; assert title/url/description/posted_date mapping)
- [x] T009 [P] [US1] Write contract tests in `tests/test_api.py` (TestClient + temp DB): response shapes for `/api/jobs`, `/api/refresh` cooldown + single-flight + `?force=1`, `/api/refresh/status`, `/api/jobs/{id}/status` round-trip and 400/404 cases

### Implementation for User Story 1

- [x] T010 [P] [US1] Implement `engine/ingest/greenhouse.py` (boards-api.greenhouse.io, `?content=true`, HTML-strip description) to pass its T008 tests
- [x] T011 [P] [US1] Implement `engine/ingest/lever.py` (api.lever.co `?mode=json`) to pass its T008 tests
- [x] T012 [P] [US1] Implement `engine/ingest/ashby.py` (api.ashbyhq.com posting-api) to pass its T008 tests
- [x] T013 [US1] Implement `engine/pipeline.py`: run registered sources for all `companies.yml` entries, write jobs per source as each completes, per-source status/counts into `refresh_runs`, module-level single-flight lock, 30-min cooldown, stale-unfinished-run supersede, per-source exception isolation; unit tests with fake sources in `tests/test_pipeline.py`
- [x] T014 [US1] Implement `cli.py` with `refresh` command running the same pipeline headless and printing per-source counts (Constitution IV / FR-014)
- [x] T015 [US1] Implement JSON API in `web/routes_api.py` to pass T009: POST `/api/refresh` (BackgroundTasks), GET `/api/refresh/status`, GET `/api/jobs`, GET `/api/jobs/{id}`, POST `/api/jobs/{id}/status`
- [x] T016 [US1] Implement feed page: `web/templates/feed.html` + `web/templates/partials/feed_table.html`, GET `/` and GET `/partials/feed` with `window/status/location/remote/sort` params; HTMX auto-fires refresh on load, polls partial every 5s while active, per-source progress strip, "new" badges, 24h/7d toggle, and a manual "Refresh now" button (POST `/api/refresh?force=1`)
- [x] T017 [US1] Implement job detail page GET `/jobs/{id}` in `web/templates/job_detail.html`: description, source link, posted date, status buttons
- [x] T018 [US1] Wire status buttons (Save/Applied/Hidden) via HTMX in feed rows + detail page; default feed excludes `applied`/`hidden`; add Saved/Applied/Hidden filter views
- [x] T019 [P] [US1] Implement `engine/ingest/workday.py` (CxS POST endpoint, pagination, `tenant`/`site` from companies.yml; use a `searchText` term per company — default "engineer" — and cap page count, since large tenants list thousands of roles; parse relative `postedOn` strings like "Posted 3 Days Ago" into ISO dates) + fixture test in `tests/test_sources.py`
- [x] T020 [P] [US1] Implement `engine/ingest/hn.py` (Algolia: locate latest "Ask HN: Who is hiring?" story, parse top-level comments using the conventional pipe-delimited first line — "Company | Role | Location | …" — skipping comments that don't fit the pattern; use each comment's `created_at` as `posted_date` — never the thread date) + fixture test in `tests/test_sources.py`
- [x] T021 [P] [US1] Implement `engine/ingest/jobspy_source.py` as a best-effort source (python-jobspy searches for entry-level SWE/hardware terms; Indeed-only by default, LinkedIn only when `JOBSPY_LINKEDIN=1`; map `date_posted`; rely on `dedup_key` for overlap) + unit test with mocked jobspy call in `tests/test_sources.py`
- [x] T022 [US1] US1 checkpoint verification per quickstart.md: full pytest green; clean DB → `python app.py` → feed populates live, toggle/cooldown/dedup/status behaviors confirmed in browser

**Checkpoint**: US1 fully functional MVP — daily usable job feed

## Phase 4: User Story 2 - Filter for Entry-Level and Visa-Friendly Jobs (Priority: P2)

**Goal**: Default feed shows only entry-level roles; every job carries an evidence-backed sponsorship rating (HIGH/MEDIUM/EXCLUDED/UNKNOWN); explicit "no sponsorship" wording excludes regardless of history.

**Independent Test**: Load sponsorship data, run a refresh: 10 known sponsors show HIGH/MEDIUM; a "citizens only" posting shows EXCLUDED; senior titles absent from default feed; classifier ≥90% on fixture set.

### Tests for User Story 2

- [x] T023 [P] [US2] Create `tests/fixtures/titles.yml` (~40 real titles: new-grad SWE, hardware/firmware/FPGA/ASIC/verification, senior/staff negatives, and boundary cases — "Software Engineer I", "Engineer 1", "Associate Engineer", bare "Software Engineer" with seniority only in the description) and failing tests in `tests/test_filters.py` asserting ≥90% classification accuracy plus sponsorship phrase-scan cases (negative overrides positive)
- [x] T024 [P] [US2] Write failing tests in `tests/test_sponsorship.py`: company name normalization (suffix stripping, casefold), rapidfuzz join at ratio ≥90 ("NVIDIA Corp" ↔ "NVIDIA CORPORATION"), sponsor_score derivation from approval counts

### Implementation for User Story 2

- [x] T025 [US2] Implement entry-level classifier + sponsorship phrase scan in `engine/filters.py` (include/exclude regex sets from plan, extended with "engineer I/1" patterns; titles with no seniority marker fall back to a description scan for years-of-experience phrases; positive/negative sponsorship phrase lists; negative wins) to pass T023
- [x] T026 [US2] Implement `engine/sponsorship.py` to pass T024: USCIS Data Hub CSV loader; DOL LCA XLSX loader via pandas/openpyxl reading only needed columns in chunks (disclosure files are very large — filter to engineering-relevant SOC codes before storing titles into `companies.lca_titles`); normalized+fuzzy join; `sponsor_score` computation
- [x] T027 [US2] Add `load-sponsorship` command to `cli.py` reading `data/uscis/` and `data/dol/` per quickstart.md
- [x] T028 [US2] Wire classification into `engine/pipeline.py`: after ingest, set `is_entry_level`, per-job `sponsorship` (company score + JD scan, EXCLUDED override) and `sponsorship_evidence` JSON
- [x] T029 [US2] UI: sponsorship badges in feed rows + evidence panel in job detail; default feed filters `entry_level=1`; senior roles reachable only via explicit filter
- [x] T030 [US2] US2 checkpoint verification: classifier accuracy report from pytest; live spot-check of 10 known sponsors and one "citizens only" fixture per spec SC-004/SC-005

**Checkpoint**: Feed is relevance-filtered and sponsorship-aware

## Phase 5: User Story 3 - Match My Resume and See What's Missing (Priority: P3)

**Goal**: Upload resume once → every entry-level job gets a 0–100 score; detail view shows matching/missing skills and actionable gap suggestions; analysis failures leave jobs visible unscored.

**Independent Test**: Upload a resume, refresh, confirm scores in feed sort sensibly and a job detail shows skills + at least one gap action; kill the LLM key and confirm jobs still appear unscored.

### Tests for User Story 3

- [x] T031 [P] [US3] Create `tests/fixtures/sample_resume.pdf` and write failing tests in `tests/test_resume.py` (text extraction; scanned-PDF/no-text → error path) and `tests/test_matcher.py` (mocked LLM client: valid JSON → stored MatchAnalysis; invalid JSON → one retry → None; prompt includes resume + JD)

### Implementation for User Story 3

- [x] T032 [US3] Implement `engine/resume.py` (PyMuPDF extraction) to pass its T031 tests
- [x] T033 [US3] Implement `engine/matcher.py` to pass its T031 tests: OpenAI-compatible client from `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY`, `MatchAnalysis` pydantic model (match_score, matching_skills, missing_skills, gap_actions[{action,impact}], reasoning), strict-JSON prompt, one-retry-then-null
- [x] T034 [US3] Implement profile (depends on T033 for skill extraction): GET/POST `/api/profile` in `web/routes_api.py` (multipart resume upload — PDF-only validation, sane size limit → extract text + LLM skill extraction, degrading to empty skills when no LLM key; 422 on no-text PDF) and `web/templates/profile.html`; `target_locations` pre-populate the feed location filter (FR-018) without hard-excluding
- [x] T035 [US3] Add scoring stage to `engine/pipeline.py`: after classification, score new entry-level jobs when a resume exists (skip already-scored; throttle to the provider's free-tier rate — ~30 requests/min for Groq — and cap per-run volume so a huge first refresh can't exhaust the daily quota); feed default sort becomes score-then-recency
- [x] T036 [US3] Job detail split view in `web/templates/job_detail.html`: JD alongside match score, matching/missing skills, gap actions; "add resume" prompt on feed when no profile exists
- [ ] T037 [US3] (BLOCKED on user input: needs a Groq API key in .env and the real resume uploaded) US3 checkpoint verification: real resume vs 5 hand-picked JDs — scores rank plausibly, JSON validates, unscored-on-failure path confirmed (spec SC-006)

**Checkpoint**: All three user stories independently functional

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T038 [P] Optional nightly refresh via APScheduler in `app.py` behind an env flag (SCHEDULE_REFRESH=1)
- [x] T039 [P] Implement GET `/api/export` CSV of current filtered feed in `web/routes_api.py` + export button in feed UI
- [x] T040 [P] Write `README.md` (what/why, link to specs/001-ai-job-engine/quickstart.md, screenshots placeholder) and finalize `.env.example`
- [x] T041 Full quickstart.md walkthrough on a clean environment (fresh venv, empty DB): pytest, real refresh, browser verification of SC-001/002/003/008; fix any gaps found

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** → user stories.
- **US1 (Phase 3)** depends only on Foundational. **US2 (Phase 4)** depends on the pipeline (T013) existing but not on US1's UI polish. **US3 (Phase 5)** depends on the pipeline and (for full value) US2's entry-level flag; both remain independently testable.
- Within each story: tests → sources/models → pipeline wiring → API → UI → checkpoint.
- **Polish (Phase 6)** after desired stories complete.

### Parallel opportunities

- Phase 1: T002, T003 together after T001.
- Phase 3: T008 + T009 together; then T010/T011/T012 in parallel; later T019/T020/T021 in parallel.
- Phase 4: T023 + T024 together.
- Phase 6: T038/T039/T040 in parallel.

## Implementation Strategy

**MVP first**: Phases 1–3 (T001–T022) deliver the daily-usable job feed — stop and
use it for real applications while building US2/US3. Each subsequent story is an
independent increment; commit after each task or logical group (auto-commit hooks
fire at workflow boundaries). Every checkpoint task (T022, T030, T037, T041) is a
verification gate: evidence before moving on (Constitution I & V).
