# Personalized AI Job Engine — User Manual

Everything about this program in one place: what it is, how to run and test
it, how every module works, and how the pieces connect. For a short daily-use
reference see [USER_GUIDE.md](USER_GUIDE.md); for the original requirements
and design see [../specs/001-ai-job-engine/](../specs/001-ai-job-engine/)
(core engine) and [../specs/005-apply-assist/](../specs/005-apply-assist/)
(local AI + Apply Assist).

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

### Installed the app from an installer?

Just launch **Job Engine** from the Start menu (Windows) or Applications
(macOS) — nothing below applies to you. Your data lives in
`%LOCALAPPDATA%\JobEngine` (Windows) or
`~/Library/Application Support/JobEngine` (macOS), and if anything goes wrong
there's an `app.log` in that folder. First-run setup happens inside the app
(welcome steps + Settings page).

### Running from source — first-time setup (once)

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
| `ingest/jobspy_source.py` | Indeed + Google Jobs (and opt-in LinkedIn) via python-jobspy — search terms and locations come from your Profile (falling back to built-in new-grad terms), 14-day window, volume knobs in Settings. Best-effort by design. | `fetch_jobs([])` |
| `basic_match.py` | Deterministic local scorer (curated SWE/hardware skill dictionary): powers `~NN` scores with no AI key; upgraded to LLM scores automatically. Also accepts the user's explicit Profile skills list (`extra_skills`) alongside resume-text regex extraction. |
| `resume_extract.py` | (007) LLM extraction of the uploaded resume into structured sections (experience/education/projects/skills) via the tier dispatcher — schema-validated, bounded retry, None without an AI tier (manual forms take over). User review in the Resume builder is the quality gate. |
| `resume_pdf.py` | (007) ATS-safe resume + cover-letter PDF rendering (fpdf2 + bundled DejaVu fonts, fully offline). Per-job tailored variants lead with `tailor.py`'s output; a fingerprint cache re-renders whenever sections or tailoring change — a stale PDF can never be served. |
| `alerts.py` | Post-refresh "new strong matches" computation + desktop notification (plyer, best-effort, toggleable). |
| `tailor.py` | Per-job tailored bullets/cover letter/ATS keywords via the LLM, no-invention prompt guard, cached in `jobs.tailor_json` until the resume changes. |
| `updates.py` | GitHub Releases version check (silent when offline). |
| `filters.py` | The two classifiers. Entry-level: seniority markers always lose, then entry markers / hardware families / description scan — and the title must be an engineering role at all. Eligibility: negative wording ("unable to sponsor", citizens-only, security clearance, ITAR/"U.S. person" — word-boundary regexes so "military" never matches ITAR) beats positive wording (visa sponsorship, H-1B, OPT/CPT) → EXCLUDED, which is hidden from all normal views and never scored. | `classify_entry_level`, `scan_sponsorship`, `rate_sponsorship` |
| `sponsorship.py` | Loads USCIS CSVs (approval **and denial** counts per employer) and DOL LCA files (engineering job titles **plus wage levels and offered wages**), stores them, and joins company names to records with three-stage matching. (007) Also computes the local A–F sponsor grade (≥10-petition floor, else UNKNOWN), the word-boundary cap-exempt heuristic, and the wage-weighted lottery hint. | `load_all`, `match_employer`, `apply_to_companies`, `grade`, `cap_exempt`, `lottery_hint` |
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
| `templates/profile.html` | Sectioned "one form" profile: Basic info (name/email/phone/LinkedIn/portfolio), Work authorization, Common Questions + EEO disclosures (`partials/profile_answer_bank.html`), Resume & job search (resume upload, editable skills list, preferred locations). |
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

Seven tables, created automatically on first run:

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
- **user_profile** — a single row: your resume text, extracted + manually
  edited skills, preferred locations, work-authorization/visa facts, and
  (feature 006) identity fields (name, email, phone, LinkedIn, portfolio)
  Apply Assist fills directly.
- **refresh_runs** — one row per refresh with per-source progress JSON;
  powers the channel strip, the cooldown, and crash recovery (an unfinished
  run older than 30 minutes is treated as crashed and superseded).
- **answer_bank** (feature 005) — one row per confirmed application
  question/answer, reused automatically across jobs by exact-or-fuzzy match.
- **application_answers** (feature 005) — a per-application snapshot of
  exactly which confirmed answer was used where, independent of
  `answer_bank` so later edits don't rewrite history. Saved-login secrets
  are never in this database at all — only in your OS's own credential
  store, via the `keyring` package.

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
| `POST /api/jobs/{id}/stage` | Move an application through `applied\|oa\|interview\|offer\|rejected`. |
| `POST /api/jobs/{id}/notes` | Save free-text notes on an application. |
| `POST /api/jobs/{id}/tailor` | Generate tailored bullets + cover letter (409 without resume/key). |
| `GET /api/analytics` | Funnel + response-rate aggregates. |
| `POST /api/settings/check-update` | Compare the running version against GitHub Releases. |
| `GET /api/export` | The current filtered view as a CSV download. |
| `POST /api/autofill/setup` \| `queue` \| `next` \| `stop` \| `GET .../status` | Apply Assist session control. (007) `status` also returns the full queue with per-job state, N-of-M progress, the per-field fill report (passwords pre-masked), the interrupted flag, and the batch summary. |
| `POST /api/autofill/rescan` \| `resume-queue` | (007) Re-fill the current page manually (SPA fallback) / relaunch the browser at the saved queue position after the window was closed. |
| `PUT /api/profile/resume-sections` \| `POST /api/profile/reextract` | (007) Resume builder: full structured-sections replace (manual edit path) / explicit-consent re-extraction from the stored resume. |
| `GET /api/jobs/{id}/resume-pdf` \| `cover-letter-pdf` | (007) Tailored (or untailored) resume PDF and cover-letter PDF downloads. |
| `POST /api/autofill/answers/confirm` | The only write path into the answer bank — always requires explicit confirmation. |
| `GET /api/autofill/answers` \| `DELETE /{bank_id}` | List/delete saved Common Questions answers (Profile page management). |
| `POST /api/credentials` \| `GET` \| `DELETE /{domain}` | Per-domain saved-login vault; password never appears in any response. |
| `POST /api/credentials/default` \| `DELETE /default` | The default login used when no per-domain override exists (registered before `/{domain}` to avoid route collision). |
| `GET /api/diagnostics/local-llm-selftest` \| `chromium-launch-selftest` \| `pdf-selftest` | Real (not just import-check) health checks used by the release smoke test — the pdf one renders an actual unicode document with the bundled fonts. |
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
| `JOBSPY_LINKEDIN` | `0` | `1` adds LinkedIn to the jobspy searches (rate-limited quickly; the feed's "Search on LinkedIn" button is the dependable path). |
| `JOBSPY_SITES` | `indeed,google` | Which jobspy boards run by default. |
| `JOBSPY_RESULTS_PER_SEARCH` | `40` | Results requested per search term. |
| `FEED_WINDOW_DEFAULT` | `14d` | Default feed freshness window. |
| `LLM_JSON_MODEL` | `openai/gpt-oss-120b` | Model used for structured extraction/scoring (guaranteed-JSON on Groq); `LLM_MODEL` stays the prose model. |
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

## 11. Apply Assist & the offline AI model (feature 005)

### 11.1 The bundled local AI model

Starting with this release, a small AI model (Qwen2.5-1.5B-Instruct,
Apache 2.0 licensed) ships **inside the installer** — no download, no
account, no API key needed. Scoring precedence, best tier first:

1. **Cloud** — if you've pasted a Groq (or other OpenAI-compatible) key in
   Settings, that's always used first. Scores show plain (no prefix).
2. **Local** — the bundled model, used automatically whenever no cloud key
   is set. Fully offline. Scores show a `•` prefix.
3. **Basic** — the original deterministic keyword matcher, used only if
   somehow neither AI tier is available (e.g. the model file is missing).
   Scores show a `~` prefix.

Jobs scored by a lower tier are automatically re-scored by a better tier the
moment it becomes available (e.g. adding a cloud key later upgrades every
`•` and `~` score without you doing anything). A future improved model
ships as part of a normal app update — Settings → **Check for updates** —
there is no separate "update the model" step.

### 11.2 Apply Assist

Once you've shortlisted jobs (marked **Saved**), the **Apply Assist** page
lets the app do the repetitive part of applying:

1. Nothing to enable or download (v0.8.0): Apply Assist launches the
   **Microsoft Edge or Google Chrome already installed on your machine**,
   with a separate profile dedicated to this app — never your everyday
   browsing profile. Click **Check my browser** any time to verify the
   browser layer can start.
2. Select which saved jobs to include and click **Start Apply Assist**. A
   dedicated browser window opens on the first job's real application page.
   If anything prevents that (no supported browser, page down, unreadable
   form), the status panel tells you the specific reason and what to do —
   never a silent nothing.
3. Recognized fields (name, email, phone, **your resume file** — the job's
   tailored PDF when one exists, LinkedIn/portfolio links, work
   authorization, sponsorship, years of experience, salary expectation,
   "how did you hear about us," cover letter) are filled in automatically
   from your Profile and the answer bank. Dropdowns and radio buttons are
   answered by matching your confirmed answer to the site's own option
   wording — and left untouched (reported, never guessed) when nothing
   matches confidently.
4. **The app never clicks submit, apply, next, or login for you — ever,
   under any circumstance.** Review what was filled (the mission panel
   lists every field and value; passwords show only as `•••`), make
   corrections, and click the site's own button yourself. When *you* click
   Next on a multi-page application, the newly loaded page is scanned and
   filled automatically; a "Re-scan this page" button covers sites that
   redraw their form without navigating. If you close the automation
   browser window mid-run, your queue position is kept — Resume queue
   reopens it right where you were, and a batch summary wraps up every run.
5. If a question is new or legally significant (work authorization,
   sponsorship, EEO-style disclosures), the queue pauses and shows an
   AI-drafted suggestion for you to confirm or edit — nothing is saved or
   typed until you do. Once confirmed, the same question is answered
   automatically on every later job.
6. When you're done with a job (or want to skip it), click **Done, next
   application** — the next one opens automatically. Nothing advances on
   its own; that button is the only thing that moves the queue forward.
7. On a site the field-reader can't confidently handle (a heavy multi-step
   application system, or one — like Workday — already known to block
   automated access), the tab just opens for you to complete manually and
   the queue still advances afterward.

**A note on Terms of Service**: even though a human always performs the
actual submission and login, automating page navigation and field-filling
on third-party sites may still touch the edges of some sites' Terms of
Service. Use your own judgment per site — this is a co-pilot that saves you
retyping, not a bot that applies on your behalf.

### 11.3 Profile: fill it once, reuse everywhere

The Profile page is one sectioned form, designed so filling it in once feeds
every later application and improves matching, not just Apply Assist:

- **Basic info** — first/last name, email, phone, LinkedIn, portfolio/GitHub
  URL. These back the `full_name`/`email`/`phone`/`linkedin_url`/
  `portfolio_url` fields Apply Assist fills directly, no confirmation needed
  (they're facts, not judgment calls).
- **Work authorization** — authorized-without-sponsorship + visa status,
  grounding the AI's drafted sponsorship/work-authorization answers. It never
  invents anything beyond what you've entered here.
- **Common Questions** — every confirmed answer bank entry (sponsorship,
  years of experience, salary expectation, "how did you hear about us,"
  etc.) is listed with an edit/delete control, so you can pre-fill answers
  *before* Apply Assist ever asks, not just react to its pauses. An
  **EEO disclosures (optional)** subsection lets you pre-set the standard
  voluntary gender/race/veteran/disability questions many US applications
  include — entirely optional, and used only if you fill it in.
- **Resume & job search** — resume upload, an editable **skills** list, and
  preferred locations. The skills list isn't just cosmetic: it's unioned
  with whatever the resume-text extraction finds (your entries listed
  first, duplicates removed) and fed into the deterministic basic matcher,
  so a skill you know but phrased differently — or not at all — in your
  resume still counts when scoring jobs without a cloud AI key.

### 11.4 Saved logins: one default, per-site overrides

Realistically the same email/password covers most job-site logins, so
**Settings → Saved logins** now has two tiers:

- **Default login** — set once, used for any domain without its own
  override.
- **Per-site overrides** — save a different email/password for a specific
  domain when it needs one; it wins over the default for that domain only.

Apply Assist fills matching login pages from whichever applies — default,
or the domain's override if one exists — but, same rule as everywhere else,
never clicks the login button. Passwords are stored in your OS's own
credential store (Windows Credential Manager / macOS Keychain), never in
this app's database, and are never displayed again once saved (write-only,
like a real password manager).

## 11.5 The Moat Release (feature 007, v0.7.0)

- **Resume builder** (Profile): the uploaded resume is parsed into editable
  structured sections — experience, education, projects, skills — by the
  AI tier (manual forms without one). You review/correct once; your edits
  always win (re-uploading a new resume *asks* keep-vs-re-extract, never
  silently overwrites). These sections power the PDFs below.
- **Tailored resume + cover-letter PDFs** (job detail page): ATS-safe
  single-column PDFs rendered fully offline — identity header, the job's
  tailored summary/bullets, then your reviewed sections. Apply Assist
  attaches the tailored PDF automatically (Settings toggle, default on).
- **Sponsor grades**: each company with ≥10 H-1B petitions on record gets a
  local A–F grade from approval rate, volume, engineering filings, and
  wage levels — below the floor it stays UNKNOWN, never guessed. University/
  nonprofit/hospital employers get a **cap-exempt** badge (they sponsor
  year-round outside the lottery). The job page shows the full evidence:
  approvals, denials, approval rate, median engineering wage, and a
  wage-weighted lottery-odds hint (all labeled estimates). Toolbar filter:
  **Strong sponsors only** (grade ≥ B or cap-exempt).
- **Instrument UI**: light "datasheet" theme by default with a dark "scope
  screen" alternate (Settings → Theme; your choice persists and beats the
  OS preference). Grouped navigation with a visible current page, toast
  confirmation on every action, a kanban **Board** view of the Applied
  pipeline (drag cards or use the ◀/▶ buttons), a first-run setup
  checklist driven by real state, and background refreshes that never
  clobber an open editor.

## 12. Known issues (fixed)

- **v0.4.0 installer**: "the specified module could not be found" on any
  refresh (jobspy/Indeed searches always failed). Caused by a native DLL
  (`tls_client`) that PyInstaller didn't bundle. **Fixed in v0.4.1** — if
  you have v0.4.0 installed, download v0.4.1 from the Releases page (Settings
  → Check for updates will also tell you). CI now runs a real smoke test on
  every release build so this class of bug can't ship silently again.
- **v0.5.0–v0.5.5 installers**: clicking "Start Apply Assist" did nothing —
  no browser window opened, no error shown. The Chromium installer used
  `sys.executable` to invoke Playwright's setup, which inside the installed
  app is `JobEngine.exe` itself, not a Python interpreter — Chromium was
  never actually being downloaded. **Fixed in v0.5.6**, verified against a
  real rebuilt installer (a genuine Chromium window was confirmed opening).
  Failures anywhere in Apply Assist now also show a visible error message
  instead of silently doing nothing.
- **v0.5.x**: Profile had no identity fields (name/email/phone/links), so
  Apply Assist could never fill them despite the field-classifier already
  recognizing those tags; no in-app way to pre-fill or manage Common
  Questions answers; one shared login required a separate save per domain.
  **Fixed in v0.6.0** — see §11.3/§11.4.

## 13. Troubleshooting

See the table at the end of [USER_GUIDE.md](USER_GUIDE.md#troubleshooting).
The two most common: empty feed = wait for the first refresh to finish;
UNKNOWN badges everywhere = run `python cli.py load-sponsorship`.


## 12. What changed in v0.8.0 (the Launch Release)

- **Apply Assist rebuilt on your installed browser.** The 150-280MB Chromium
  download is gone — Playwright now drives the Edge/Chrome already on your
  machine via its channel mechanism, with an isolated app-only profile. Every
  failure carries a reason (browser couldn't start / page failed to load /
  page unreadable / fields unrecognized) with the real error text, and a
  preflight check runs before any queue starts. The old downloaded-Chromium
  directory can be reclaimed from the Diagnostics page.
- **The desktop window behaves like a browser.** Text selection, clipboard
  (three-tier fallback ending at a host-side copy), external links (always
  open in your system browser), and PDF downloads all work inside the shell
  now — these were silently broken in v0.7.0.
- **Freshness is enforced end-to-end.** 14-day default window, ingest-time
  age gate, `last_seen` tracking with board-diff delisting (a job missing
  from a successfully fetched company board is flagged delisted), HEAD
  liveness checks for scraped rows, same-source repost dedup, and honest
  "seen ~" dates when a source provides no posted date.
- **The watchlist is yours.** 450+ validated company boards ship seeded into
  a database-backed watchlist; add/disable/remove companies in Settings, and
  your changes survive updates.
- **Profile auto-fill + profile-driven search.** Resume upload extracts your
  contact details (regex fallback works with zero AI) and target titles,
  fills blank fields, asks keep-or-replace on conflicts, never touches visa
  fields. Derived search terms are visible/editable on Profile and drive the
  jobspy searches together with your preferred locations.
- **Semantic pre-ranking.** EmbeddingGemma-300M (bundled, offline) ranks new
  jobs against your resume so AI scoring quota is spent top-down.
- **Self-update.** Daily throttled check → banner → SHA-256-verified
  download with progress → silent Inno install → automatic relaunch, with a
  What's New screen once per version. macOS remains a manual .dmg download.
- **Diagnostics page** (top nav): real self-checks with error text, log
  export, legacy-browser cleanup; crashes in background threads are logged
  and surfaced once on the next launch.
