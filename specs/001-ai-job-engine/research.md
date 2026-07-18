# Phase 0 Research: Personalized AI Job Engine

All Technical Context unknowns were resolved during the 2026-07-17/18 planning
sessions (brainstorming + approach selection with the user). This document records
each decision with rationale and rejected alternatives. No NEEDS CLARIFICATION
markers remain.

## D1. Web framework: FastAPI + Jinja2 + HTMX (not Streamlit)

- **Decision**: FastAPI serving server-rendered Jinja2 pages with vendored HTMX
  for dynamic behavior (feed polling during refresh, filter toggles, status
  buttons). JSON API routes alongside pages.
- **Rationale**: The confirmed open-app flow (instant cached render + background
  refresh + streaming updates) fights Streamlit's rerun model but is natural with
  background tasks + HTMX polling. "Shareable later without rewrite" requires a
  real API layer. No Node build keeps the stack one-language and free-host ready.
- **Alternatives considered**: Streamlit (fastest first pixel; rejected — poor
  fit for background refresh/streaming and multi-user later). React/Vite SPA
  (rejected — build toolchain + time cost with no v1 payoff).

## D2. Ingestion strategy: public JSON APIs first, no scraping in v1

- **Decision**: Six source families, all JSON: Greenhouse
  (`boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`), Lever
  (`api.lever.co/v0/postings/{slug}?mode=json`), Ashby
  (`api.ashbyhq.com/posting-api/job-board/{slug}`), Workday CxS
  (`https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`,
  POST with JSON body, paginated), Hacker News "Who is hiring" (Algolia
  `hn.algolia.com/api/v1/` — find monthly thread, fetch comments), and
  python-jobspy (maintained scrapers for Indeed/LinkedIn). jobspy is treated as
  **best-effort**: it scrapes sites we don't rate-limit ourselves, so it runs
  Indeed-only by default with LinkedIn behind an env flag
  (`JOBSPY_LINKEDIN=1`), and its failures never block the run (per-source
  isolation).
- **Rationale**: Structured JSON, no selector breakage, no bot-protection
  arms race (Constitution III). Workday covers the big hardware employers
  (NVIDIA, AMD, Qualcomm, Micron, TI, Marvell) central to the user's target
  roles.
- **Alternatives considered**: Playwright/Scrapy scraping of Wellfound, Dice,
  Google Jobs (rejected for v1 — DataDome/anti-bot fights, high maintenance);
  GitHub Jobs API and StackOverflow Jobs (rejected — services shut down in
  2021/2022 despite appearing in the original research).

## D3. Company seed list: checked-in `companies.yml`

- **Decision**: YAML mapping company → `ats: greenhouse|lever|ashby|workday` +
  slug/tenant(+site for Workday). Seeded from the SimplifyJobs/New-Grad-Positions
  GitHub list plus a hand-picked hardware employer list (~50–100 entries).
- **Rationale**: ATS board APIs are per-company, so a seed list is required;
  YAML keeps "add a company" a one-line, no-code operation (spec assumption).
- **Alternatives considered**: Automatic company discovery via crawling ATS
  directories (rejected — v2 scope; violates Speed-to-Value).

## D4. Storage: SQLite, single file

- **Decision**: SQLite at `data/jobs.db`; path via `JOBS_DB_PATH` env var;
  schema created idempotently on startup; WAL mode for concurrent read (web)
  + write (background refresh).
- **Rationale**: Zero-config, free, single-user scale; env-var path and clean
  `db.py` boundary keep a future Postgres swap additive.
- **Alternatives considered**: Postgres (rejected for v1 — hosting/setup cost
  with no benefit at this scale); JSON files (rejected — recency/status queries
  and joins needed).

## D5. Sponsorship signal: USCIS H-1B Employer Data Hub + DOL LCA disclosures

- **Decision**: Load USCIS employer CSV (approvals by employer/year) and DOL LCA
  disclosure XLSX (job titles + wages per petition) into the `companies` table.
  Join postings to records via normalized names (strip Inc/LLC/Corp/Corporation,
  casefold) + rapidfuzz ratio ≥ 90. JD text scan for positive/negative phrases;
  negative phrases override history. Ratings: HIGH / MEDIUM / EXCLUDED / UNKNOWN.
- **Rationale**: Both datasets are free public government data; DOL titles let
  "sponsors engineers" be distinguished from "sponsors other roles". Fuzzy join
  handles name variants ("NVIDIA Corp" vs "NVIDIA Corporation").
- **Alternatives considered**: Paid sponsorship APIs (violates Constitution II);
  JD keywords alone (rejected — most JDs are silent on sponsorship; history fills
  the gap).

## D6. LLM: Groq free tier via OpenAI-compatible client

- **Decision**: `openai` Python client with env-configured `LLM_BASE_URL`,
  `LLM_MODEL`, `LLM_API_KEY` (default: Groq free tier, Llama 3.3 70B class
  model). Strict JSON output parsed into a pydantic model; one retry on
  validation failure, then job left unscored. Only entry-level-passing jobs are
  scored, keeping volume well under free-tier daily limits.
- **Rationale**: Free, fast, zero local hardware requirement; provider-agnostic
  config satisfies Constitution II and lets Gemini free tier or local Ollama
  swap in with env changes only.
- **Alternatives considered**: Ollama-first (rejected for v1 — quality/speed of
  small local models is a risk to gap-analysis usefulness; deferred to v2 as a
  privacy option); paid APIs (violates Constitution II).

## D7. Recency model: `posted_date` with `first_seen` fallback

- **Decision**: Store source-provided `posted_date` (Greenhouse `updated_at`,
  Lever `createdAt`, Ashby `publishedAt`, jobspy `date_posted`, HN per-comment
  `created_at` from Algolia — never the thread month, which would date every HN
  job to the 1st and drop them from the 7-day window) and our `first_seen`
  timestamp. Feed windows (7-day default, 24h toggle) use
  `COALESCE(posted_date, first_seen)`.
- **Rationale**: Sources are inconsistent about posting dates; fallback keeps
  recency filters correct for every job (spec FR-002, edge case).

## D8. Refresh orchestration: background task + cooldown + single-flight

- **Decision**: `engine/pipeline.py` runs sources concurrently (per-domain rate
  limit ≤1 req/s), writes results per source as each completes, records a
  `refresh_runs` row (started/finished, per-source status/counts). Web layer
  triggers it via FastAPI background task; a module-level lock enforces
  single-flight; a 30-minute cooldown suppresses redundant auto-refreshes.
  Source failures are caught per-source and surfaced, never aborting the run.
- **Rationale**: Directly implements spec FR-005/FR-006/FR-013 and the
  "already running → ignore" edge case; persisting runs makes the cooldown
  survive app restarts.
- **Alternatives considered**: Celery/RQ job queue (rejected — infrastructure
  overkill for single user); refresh-on-request blocking the page (rejected —
  violates the <2s open-app requirement).

## D9. Dedup: URL unique + cross-source content hash

- **Decision**: `url` UNIQUE constraint for same-source idempotency, plus a
  `dedup_key = sha1(normalized_company | normalized_title | normalized_location)`
  unique index to collapse the same role found via an ATS API and a job board.
  First-seen record wins; later duplicates update `posted_date` if fresher.
- **Rationale**: Spec FR-007/SC-008; jobspy (Indeed/LinkedIn) heavily overlaps
  ATS sources.

## D10. Job status tracking (from clarification)

- **Decision**: `jobs.status` TEXT with values `none|saved|applied|hidden`
  (default `none`), set via one-click actions in the feed/detail views. Default
  feed excludes `applied` and `hidden`; dedicated filter views per status.
  Status is preserved on upsert (refreshes never reset it).
- **Rationale**: Clarification session answer; prevents the feed refilling with
  handled jobs; minimal schema impact.

## D11. Location handling (from clarification)

- **Decision**: Feed defaults to all US + remote; location filter control
  (state/city substring match + remote-only toggle) narrows on demand; stored
  preferences pre-populate the filter UI but never exclude jobs by default.
- **Rationale**: Clarification session answer; avoids silently hiding
  relocatable roles from an entry-level candidate.

## D12. Resume parsing: PyMuPDF text extraction only

- **Decision**: Extract raw text from the uploaded PDF with PyMuPDF; store text
  + LLM-extracted skill list in `user_profile`. No layout reconstruction; no
  OCR (scanned resumes out of scope per spec assumption).
- **Alternatives considered**: OpenResume/browser parsing (rejected — separate
  toolchain); spaCy NER skill extraction (rejected — the matcher LLM already
  extracts skills as part of analysis, one less model dependency).
