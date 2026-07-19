# Personalized AI Job Engine — Complete Manual

Everything about this program in one place: what it is, how to run and test
it, how every module works, and how the pieces connect. For a short daily-use
reference see [USER_GUIDE.md](USER_GUIDE.md); for the original requirements
and design see [../specs/001-ai-job-engine/](../specs/001-ai-job-engine/).

---

## 1. What this program is

A **local web application** that automates the tedious part of an entry-level
engineering job search:

1. **Collects** job postings from many public sources into one local database.
2. **Filters** them to entry-level software/hardware roles (new-grad, junior,
   firmware, FPGA, ASIC, verification…), dropping senior/staff postings.
3. **Rates visa-sponsorship likelihood** for every job by combining the
   company's real H-1B history (US government data) with the wording of the
   job description.
4. **Scores** each job 0–100 against *your resume* using a free LLM, telling
   you which skills match, which are missing, and what to add to your resume.
5. **Tracks** your progress: mark jobs Saved / Applied / Hidden so the feed
   only ever shows what still needs your attention.

Everything runs on your machine. The database, your resume text, and your
preferences never leave it (the only external calls are fetching public job
postings and the LLM scoring calls to the provider you configure). Total
recurring cost: **$0**.

---

## 2. How to run it

### First-time setup (once)

```powershell
# from the project root (I:\PROJECTS\JOB SEARCH TOOL)
python -m venv .venv                  # already exists if you followed along
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# open .env and paste your free Groq API key into LLM_API_KEY=
# (console.groq.com -> API Keys -> Create; no credit card needed)
```

### Start the app

```powershell
.\run.bat          # Windows: opens the desktop window (double-clickable too)
```
```bash
./run.sh           # macOS/Linux (first time: chmod +x run.sh run.command jobs.sh)
                   # or double-click run.command in Finder
```

Both launchers run **`desktop.py`**: the web server starts inside the process
and a native window opens onto it (Edge WebView2 on Windows, WKWebView on
macOS). Closing the window shuts everything down. If no webview backend is
available, the app opens your default browser instead and keeps serving until
Ctrl+C. Server-only mode (no window — for scripts or future hosting):
`.venv\Scripts\python.exe app.py` → http://127.0.0.1:8000.

All launchers always use the project's `.venv` — plain `python desktop.py`
with the *system* Python fails with `ModuleNotFoundError` because the
dependencies are installed only in the venv.

- First ever open: the feed is empty and a refresh starts automatically —
  watch the channel strip fill in over a few minutes.
- Later opens: the feed shows instantly from the database; a new background
  refresh only starts if the last one is older than 30 minutes.
- Stop the app with `Ctrl+C` in the terminal.

### One-time enrichment steps (recommended)

```powershell
# Sponsorship data (turns UNKNOWN badges into HIGH/MEDIUM):
#   put USCIS CSV files into data\uscis\  (data\uscis\h1b_datahubexport-2023.csv
#   is already there), then:
python cli.py load-sponsorship

# Resume (turns "—" match scores into 0-100 + gap analysis):
#   open http://127.0.0.1:8000/profile and upload your resume PDF,
#   then click "Refresh now" in the feed.
```

### Run without the browser (headless)

```powershell
.\jobs.bat refresh              # full pipeline, prints per-source counts
.\jobs.bat refresh --force      # ignore the 30-minute cooldown
.\jobs.bat load-sponsorship     # load USCIS/DOL files from data\
```

(`jobs.bat` is the venv-safe wrapper around `cli.py`.)

Useful for Windows Task Scheduler; alternatively set `SCHEDULE_REFRESH=1` in
`.env` and the app refreshes itself nightly at 07:00 while running.

---

## 3. How to test it

### Automated tests (no network needed, ~7 seconds)

```powershell
.venv\Scripts\python.exe -m pytest              # all 78 tests
.venv\Scripts\python.exe -m pytest -q           # terse output
.venv\Scripts\python.exe -m pytest tests\test_filters.py   # one area
```

What the suite covers, file by file:

| Test file | Proves |
|---|---|
| `tests/test_db.py` | schema creation, duplicate handling, 7-day/24-hour window queries, status transitions, refresh cooldown + crash recovery |
| `tests/test_sources.py` | each job source parses correctly (checked against recorded real API responses in `tests/fixtures/`), rate limiter waits 1s/domain |
| `tests/test_pipeline.py` | a failing source never blocks the others; runs are recorded; entry-level jobs get scored; failures leave jobs visible |
| `tests/test_api.py` | every HTTP endpoint returns the promised shape and status codes, including error cases |
| `tests/test_filters.py` | entry-level classifier ≥90% accurate on 44 real titles; sponsorship phrase detection (negative always wins) |
| `tests/test_sponsorship.py` | company-name fuzzy matching ("NVIDIA Corp" = "NVIDIA CORPORATION"), score thresholds |
| `tests/test_resume.py` | PDF text extraction; scanned/garbage files rejected cleanly |
| `tests/test_matcher.py` | LLM output validated against a schema, one retry, graceful behavior with no API key |

### Manual smoke test (real network, ~5 minutes)

```powershell
python cli.py refresh        # expect non-zero "found" for 5 sources (workday=0 is normal)
python scripts\check_seeds.py   # every companies.yml entry should print OK
python app.py                # then in the browser:
```

1. Feed shows jobs; **Today** narrows the list; **This week** restores it.
2. Click a job → detail page shows description, sponsor badge + evidence.
3. Click ✓ (applied) on a job → it disappears from the feed → find it under
   **Applied** in the top nav.
4. **CSV ↓** downloads the current view.
5. Re-run `python cli.py refresh` immediately → it prints
   `Refresh not started: cooldown` (that's correct behavior).

---

## 4. The big picture — how everything is linked

```
                      ┌──────────────────────────────────────────────┐
                      │  YOU (browser at 127.0.0.1:8000)             │
                      └───────────────┬──────────────────────────────┘
                                      │ pages + HTMX partial polling
┌───────────────┐     ┌───────────────▼──────────────────────────────┐
│ cli.py        │     │  web/  (thin FastAPI layer)                  │
│ (headless:    │     │  main.py: HTML pages (feed, detail, profile) │
│  refresh,     │     │  routes_api.py: JSON API under /api          │
│  load-        │     └───────────────┬──────────────────────────────┘
│  sponsorship) │                     │ function calls (no logic here)
└──────┬────────┘     ┌───────────────▼──────────────────────────────┐
       └─────────────►│  engine/  (ALL business logic, pure Python)  │
                      │                                              │
                      │  pipeline.py  ── orchestrates a refresh ──┐  │
                      │      │                                    │  │
                      │      ▼                                    │  │
                      │  ingest/  greenhouse lever ashby          │  │
                      │           smartrecruiters workable        │  │
                      │           workday hn jobspy (RawJobs)     │  │
                      │      │                                    │  │
                      │      ▼            after ingest:           │  │
                      │  db.py (SQLite) ◄─ filters.py (classify)◄─┘  │
                      │      ▲            sponsorship.py (H-1B join) │
                      │      │            matcher.py (LLM scoring)   │
                      │      │            resume.py (PDF text)       │
                      └──────┼───────────────────────────────────────┘
                             ▼
                      data/jobs.db  +  data/uscis/, data/dol/
```

The **one rule** that keeps this reusable: `web/` may import from `engine/`,
but `engine/` never imports from `web/`. The CLI and the web app are two thin
faces over the same engine — anything the app can do, a script can do.

### Life of a refresh (the core data flow)

1. You open the app (or click **Refresh now**, or run `cli.py refresh`).
   `pipeline.trigger_refresh()` asks `db.start_run()` for permission — refused
   if another refresh is active or one finished < 30 min ago (the cooldown).
2. A background thread runs **all six sources in parallel** (one thread each).
   Each source module reads its entries from `companies.yml`, calls the
   public JSON API politely (max 1 request/second per domain, honest
   User-Agent), and yields normalized `RawJob` objects.
3. Every `RawJob` goes through `db.upsert_job()`:
   - Same URL seen before → update the posting date/description, but **never**
     touch your status, the match score, or when it was first seen.
   - Same company+title+location from a *different* source → duplicate, skip.
   - Otherwise → insert (creating the company row if it's new).
4. When sources finish, the **post-ingest stages** run:
   - `sponsorship.apply_to_companies()` — any new company is matched against
     the stored USCIS records (exact, then fuzzy, then suffix-stripped name
     matching).
   - `filters` — each unclassified job gets `is_entry_level` (title rules +
     description scan) and a sponsorship rating (`rate_sponsorship` combines
     company history with JD phrases; a negative phrase always wins →
     EXCLUDED).
   - `matcher` — if you have a resume and an LLM key, unscored entry-level
     jobs are scored (throttled to ~28 calls/min, capped per run) and the
     validated result JSON is stored on the job.
5. Throughout, per-source progress is written to the `refresh_runs` table —
   that's what the channel strip and `/api/refresh/status` read. The feed
   partial polls every 5 seconds, so new jobs appear without a reload.

---

## 5. Module reference (what each file does)

### engine/ — the core

| File | Responsibility | Key functions |
|---|---|---|
| `db.py` | All SQLite access: schema, upserts/dedup, feed queries, refresh-run bookkeeping, profile storage. Opens a fresh connection per call (thread-safe), WAL mode, UTC timestamps. | `init_db`, `upsert_job`, `query_jobs`, `set_status`, `start_run`/`finish_run`, `save_profile` |
| `pipeline.py` | Orchestrates a refresh: source threads, failure isolation, cooldown/single-flight, then classification and scoring stages. | `run_refresh` (sync), `trigger_refresh` (web, background thread) |
| `ingest/base.py` | Shared ingestion kit: the `RawJob` dataclass every source produces, polite HTTP helpers (rate limit, retry), HTML-to-text stripping. | `RawJob`, `polite_get/post`, `strip_html` |
| `ingest/greenhouse.py` | Greenhouse boards API (`boards-api.greenhouse.io`). Posting date = `first_published`. | `fetch_jobs(entries)` |
| `ingest/lever.py` | Lever postings API (`api.lever.co`). Converts epoch-ms `createdAt` to a date. | `fetch_jobs(entries)` |
| `ingest/ashby.py` | Ashby posting API (`api.ashbyhq.com`). Skips unlisted jobs. | `fetch_jobs(entries)` |
| `ingest/smartrecruiters.py` | SmartRecruiters postings API, US-scoped (`country=us`); feeds the posting's experience-level label into the description so the classifier can use it. | `fetch_jobs(entries)` |
| `ingest/workable.py` | Workable v3 jobs endpoint (POST — the v1 widget returns empty as of 2026-07). Title-based classification like Workday. | `fetch_jobs(entries)` |
| `ingest/workday.py` | Workday CxS endpoint with pagination and relative-date parsing ("Posted 3 Days Ago"). Implemented + tested, but no default seeds — Workday blocks non-browser clients (Cloudflare) as of 2026-07. | `fetch_jobs(entries)`, `parse_posted_on` |
| `ingest/hn.py` | Latest "Ask HN: Who is hiring?" thread via the Algolia API. Parses the conventional `Company \| Role \| Location` first line; each comment's own timestamp is the posting date. | `fetch_jobs([])` |
| `ingest/jobspy_source.py` | Indeed (and optionally LinkedIn) via the python-jobspy library, searching entry-level SWE/hardware terms. Best-effort by design. | `fetch_jobs([])` |
| `filters.py` | The two classifiers. Entry-level: seniority markers always lose, then entry markers / hardware families / description scan — and the title must be an engineering role at all. Eligibility: negative wording ("unable to sponsor", citizens-only, security clearance, ITAR/"U.S. person" — word-boundary regexes so "military" never matches ITAR) beats positive wording (visa sponsorship, H-1B, OPT/CPT) → EXCLUDED, which is hidden from all normal views and never scored. | `classify_entry_level`, `scan_sponsorship`, `rate_sponsorship` |
| `sponsorship.py` | Loads USCIS CSVs (approval counts per employer) and DOL LCA files (job titles, filtered to engineering SOC codes), stores them, and joins company names to records with three-stage matching. | `load_all`, `match_employer`, `apply_to_companies` |
| `matcher.py` | LLM calls through the OpenAI-compatible client (Groq by default — swap providers via `.env` only). Output must validate against the `MatchAnalysis` schema; one retry, then the job stays unscored. Throttled for free-tier limits. | `analyze_match`, `extract_skills`, `MatchAnalysis` |
| `resume.py` | PDF → text with PyMuPDF. Raises `NoTextError` for scanned/garbage files. | `extract_text` |

### web/ — the interface

| File | Responsibility |
|---|---|
| `main.py` | App factory + HTML routes: `/` (feed), `/partials/feed` (the polled fragment), `/jobs/{id}` (split-view detail), `/profile`. Builds template context by calling engine functions — no logic of its own. |
| `routes_api.py` | The JSON API (section 7). Also the future reuse surface if this ever becomes multi-user. |
| `templates/base.html` | Layout shell: top nav (Feed / Saved / Applied / Hidden / Profile), loads HTMX + styles. |
| `templates/feed.html` | Toolbar (time window, location, remote, sort, seniority, Refresh now, CSV) + the auto-refresh trigger + the polled feed region. |
| `templates/partials/feed_table.html` | The channel strip + job table itself — re-rendered every 5s poll. |
| `templates/job_detail.html` | Description on the left; sponsorship evidence, match score, matching/missing skills, and gap actions on the right. |
| `templates/profile.html` | Resume upload + preferred locations form. |
| `static/htmx.min.js` | Vendored HTMX (no CDN, works offline). |
| `static/styles.css` | The "datasheet" look: monospace data values, instrument-colored badges. |

### Root files

| File | Responsibility |
|---|---|
| `desktop.py` | **The single-file desktop entrypoint**: starts the server in-process, opens the native window (pywebview), falls back to the browser, shuts down cleanly on close. |
| `app.py` | Server-only entrypoint: loads `.env`, optionally starts the nightly scheduler, runs uvicorn. Also exports `maybe_start_scheduler` for desktop.py. |
| `run.bat` / `run.sh` / `run.command` | Venv-safe desktop launchers (Windows / POSIX / macOS-double-click). `jobs.bat` / `jobs.sh` wrap the CLI. |
| `cli.py` | `refresh` and `load-sponsorship` commands — the same engine, headless. |
| `companies.yml` | The seed list of monitored boards (every entry live-validated). Add a company = add one line. |
| `scripts/check_seeds.py` | Validates every seed entry against its live endpoint (wrong slugs otherwise fail silently as zero jobs). |
| `requirements.txt` / `.env.example` / `.gitignore` | Dependencies, configuration template, and what never gets committed (`data/`, `.env`, `.venv`). |

---

## 6. The database (data/jobs.db)

Five tables, created automatically on first run:

- **jobs** — one row per posting: title, company link, location, description,
  URL, source, `posted_date` (from the source) + `first_seen` (when this app
  found it), `is_entry_level`, `sponsorship` rating + evidence JSON,
  `match_score` + full analysis JSON, and your `status`
  (none/saved/applied/hidden). Feed windows use
  `COALESCE(posted_date, first_seen)` so jobs without a source date still
  behave correctly.
- **companies** — one row per employer (seeded or discovered), with its H-1B
  approval count and company-level sponsor score after the USCIS join.
- **h1b_employers** — the loaded USCIS/DOL records (~28,000 employers), kept
  so companies discovered later can still be matched.
- **user_profile** — a single row: your resume text, extracted skills,
  preferred locations.
- **refresh_runs** — one row per refresh with per-source progress JSON;
  powers the channel strip, the cooldown, and crash recovery (an unfinished
  run older than 30 minutes is treated as crashed and superseded).

Rules that protect your data: updates from refreshes never overwrite
`first_seen`, `status`, or match results; deleting `data/jobs.db` resets
everything (next run rebuilds it, but statuses are lost).

## 7. The HTTP API (under /api)

| Endpoint | What it does |
|---|---|
| `POST /api/refresh` | Start a background refresh. Returns `{started: false, reason: "cooldown"/"running"}` when blocked; `?force=1` bypasses the cooldown (never the running lock). |
| `GET /api/refresh/status` | Active flag + per-source `{state, found, added, error}`. |
| `GET /api/jobs` | The feed as JSON. Params: `window=7d\|24h\|all`, `status`, `location`, `remote=1`, `entry_level=all`, `ineligible=1` (audit view of excluded jobs), `sort=score\|date`, `limit`, `offset`. EXCLUDED jobs are hidden unless `ineligible=1`. |
| `GET /api/jobs/{id}` | Full job incl. description, sponsorship evidence, parsed match analysis. |
| `POST /api/jobs/{id}/status` | Set `saved\|applied\|hidden\|none` (query param or JSON body). |
| `GET /api/export` | The current filtered view as a CSV download. |
| `GET/POST /api/profile` | Read/update resume + preferences (multipart upload). |
| `GET/POST /api/settings` | Read (masked key) / save the AI key, provider, and toggles — the packaged-app replacement for `.env`. |
| `POST /api/settings/test` | Live 1-token LLM call to validate the saved key. |

Interactive docs are auto-generated at **http://127.0.0.1:8000/docs** while
the app runs.

## 8. Configuration (.env)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_API_KEY` | *(empty)* | Free Groq key. Empty = app fully works, jobs just stay unscored. |
| `LLM_BASE_URL` | Groq endpoint | Any OpenAI-compatible URL (Ollama: `http://localhost:11434/v1`). |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Model name at that provider. |
| `JOBS_DB_PATH` | `data/jobs.db` | Database location — must be a local disk. |
| `JOBSPY_LINKEDIN` | `0` | `1` adds LinkedIn to the jobspy searches (often blocked). |
| `SCHEDULE_REFRESH` | `0` | `1` = nightly auto-refresh at 07:00 while the app runs. |
| `MAX_SCORE_PER_RUN` | `150` | Cap on LLM scoring calls per refresh (protects the free-tier quota). |

## 9. Extending the program

- **Monitor a new company**: find its careers page; if the URL looks like
  `boards.greenhouse.io/X`, `jobs.lever.co/X`, or `jobs.ashbyhq.com/X`, add
  `- {name: Company, ats: greenhouse|lever|ashby, slug: X}` to
  `companies.yml`, then run `python scripts/check_seeds.py` to confirm.
- **Add a whole new source**: create `engine/ingest/<name>.py` exposing
  `SOURCE_NAME` and `fetch_jobs(entries)` yielding `RawJob`s, register it in
  `engine/ingest/__init__.py`, add a fixture test in `tests/test_sources.py`.
  Everything else (dedup, classification, scoring, UI) picks it up
  automatically.
- **Tune the classifier**: the keyword lists live at the top of
  `engine/filters.py`; add a case to `tests/fixtures/titles.yml` first, watch
  the test fail, then adjust — the suite enforces ≥90% accuracy.
- **Swap the LLM**: change three `.env` values. Nothing else knows which
  provider is in use.

## 10. Design decisions worth knowing (the "why")

- **Why no Workday scraping?** Workday career sites (NVIDIA, AMD, Qualcomm…)
  are behind Cloudflare fingerprinting that rejects plain HTTP clients. This
  project's constitution forbids bot-protection fights, so those postings
  arrive via Indeed instead. The Workday module is ready if that changes.
- **Where did the EXCLUDED jobs go?** Since feature 002 they're hidden from
  every normal view — as a sponsorship-seeking candidate you can't get roles
  requiring clearance/citizenship/ITAR status, so they only appear under the
  **Ineligible** tab (with the exact wording that triggered the exclusion).
- **Why did a job reappear after I refreshed?** It shouldn't — statuses
  survive refreshes by design. If it looks that way, it's likely the same
  role posted at a second location (a separate row by design).
- **Why is a company UNKNOWN when I know they sponsor?** Only the USCIS years
  you've downloaded count. Add more year files to `data/uscis/` and re-run
  `python cli.py load-sponsorship`.

## 11. Troubleshooting

See the table at the end of [USER_GUIDE.md](USER_GUIDE.md#troubleshooting).
The two most common: empty feed = wait for the first refresh to finish;
UNKNOWN badges everywhere = run `python cli.py load-sponsorship`.
