# Personalized AI Job Engine

> **📚 Documentation**
>
> | Document | What it covers |
> |---|---|
> | **[docs/USER_MANUAL.md](docs/USER_MANUAL.md)** | **The complete manual** — what the program is, how every part works and connects, how to run and test it, all settings, troubleshooting |
> | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Short daily-use guide — reading the feed, filters, statuses, profile |
> | [docs/RELEASING.md](docs/RELEASING.md) | Building and publishing the Windows/Mac installers |
> | [specs/](specs/) | Full requirement → design → task history (spec-kit) |

A zero-subscription, local-first web app that finds **entry-level software and
hardware engineering jobs**, flags **visa-sponsorship likelihood** (OPT/H-1B),
and scores every posting against **your resume** with actionable gap analysis —
the things tools like Simplify and Jobright charge subscriptions for, running
entirely on your machine for $0.

## What it does

- **Open the app → see fresh jobs.** The feed renders instantly from the local
  database (last 7 days by default, one-click 24-hour view) while a background
  refresh pulls all sources and streams new postings in live.
- **Aggregates real sources, no scraping fights**: Greenhouse, Lever, Ashby,
  SmartRecruiters, and Workable public JSON APIs across ~67 validated
  companies, Hacker News "Who is hiring" threads, and Indeed via python-jobspy.
  One refresh ≈ 14,000+ postings; untouched postings older than 45 days are
  pruned automatically so the feed stays current.
- **Entry-level filter tuned for SWE + hardware**: new-grad/junior markers plus
  the hardware families (firmware, embedded, FPGA, ASIC, verification,
  validation, silicon, RTL), with senior/staff/II+ roles excluded. 100% on the
  44-title test fixture (gate: ≥90%).
- **Sponsorship-aware, eligibility-first**: USCIS H-1B Employer Data Hub
  history fuzzy-joined to each company, combined with JD wording. Roles you
  can't get as a sponsorship-seeking candidate — security clearance, US
  citizens only, ITAR "U.S. persons" — are detected and **hidden from the
  feed entirely** (an Ineligible view lets you audit them with the exact
  trigger phrase).
- **Resume matching that always works**: scores appear instantly via a built-in
  local matcher (no account needed, shown as `~NN`), and upgrade to full AI
  analysis — matching/missing skills and "add X to your resume" actions — once
  you paste a free Groq key (any OpenAI-compatible endpoint works).
- **Apply fast, apply well**: desktop notifications when a refresh finds new
  70+ matches, a "New today" view of everything just discovered, and one-click
  **tailored resume bullets + cover letter** per job (generated from your real
  resume only — nothing invented).
- **A pipeline, not just a list**: Applied jobs track stages (OA → interview →
  offer), notes, and 7-day follow-up nudges; the Analytics page shows your
  funnel and which sources/score-bands actually produce callbacks. Export any
  view as CSV.

## Install (for users)

Grab the latest installer from the **GitHub Releases** page once the repo is
published (see [docs/RELEASING.md](docs/RELEASING.md)):

- **Windows**: `JobEngine-Setup-<version>.exe` — SmartScreen will warn because
  the app is unsigned; click *More info → Run anyway* the first time.
- **macOS**: `JobEngine-<version>.dmg` — drag *Job Engine* to Applications;
  first launch needs *right-click → Open → Open* (unsigned app).

First run: the app opens with a 3-step welcome — upload your resume, paste a
free Groq AI key on the Settings page (guided link, no card needed), hit
Refresh. Sponsorship data ships preloaded. All data stays on your computer
(`%LOCALAPPDATA%\JobEngine` / `~/Library/Application Support/JobEngine`).

## Quick start (from source)

**Windows**
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env        # add your free Groq key to unlock scoring
.\run.bat                     # opens the app in its own desktop window
```

**macOS**
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
chmod +x run.sh run.command jobs.sh   # first time only
./run.sh                              # or double-click run.command in Finder
```

The launcher runs `desktop.py`: the server starts inside the process and a
native window opens (Edge WebView2 on Windows, WKWebView on macOS — no browser
tab, no Node). Closing the window shuts everything down; if no webview backend
exists, your default browser opens instead. `jobs.bat` / `./jobs.sh` run the
headless commands (`refresh`, `load-sponsorship`). Launchers always use
`.venv`, so nothing needs activating. Server-only mode (for scripts/hosting):
`.venv\Scripts\python.exe app.py`.

Full setup (sponsorship data download, seed-list management, smoke tests):
**[specs/001-ai-job-engine/quickstart.md](specs/001-ai-job-engine/quickstart.md)**
· Daily usage: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**
· Complete manual (how everything works and connects):
**[docs/USER_MANUAL.md](docs/USER_MANUAL.md)**

## Architecture (30 seconds)

```
engine/   pure-Python core: sources → SQLite → classify → sponsor-rate → score
web/      thin FastAPI + Jinja2 + HTMX layer over the same engine
cli.py    the identical pipeline, headless (python cli.py refresh)
```

Single-user today; the JSON API under `/api` is the reuse surface, so adding
auth + per-user rows later is additive, not a rewrite. All data (jobs DB,
resume text) stays in `data/` on your disk. Principles are codified in
[.specify/memory/constitution.md](.specify/memory/constitution.md); the full
spec/plan/tasks live under [specs/001-ai-job-engine/](specs/001-ai-job-engine/).

## Costs

| Component | Cost |
|---|---|
| Job sources (public JSON APIs, HN Algolia, jobspy) | $0 |
| Sponsorship data (USCIS Data Hub, DOL LCA disclosures) | $0 |
| LLM scoring (Groq free tier, ~28 req/min throttled) | $0 |
| Storage (SQLite), UI (FastAPI + HTMX, no build step) | $0 |

## Known limitations

- **Workday career sites** (NVIDIA, AMD, Qualcomm…) sit behind Cloudflare
  fingerprinting as of mid-2026 and reject plain HTTP clients; the source is
  implemented and tested but ships with no default entries (we don't fight bot
  protection). Their postings still arrive via the Indeed source.
- **LinkedIn** via jobspy is off by default (`JOBSPY_LINKEDIN=1` to try it) —
  it bot-blocks aggressively.
- Scanned-image resumes (no text layer) are not supported.

## Development

```powershell
.venv\Scripts\python.exe -m pytest    # 78 tests, no network needed
python cli.py refresh                  # real end-to-end pull
python scripts/check_seeds.py          # validate companies.yml entries
```

Built spec-first (GitHub Spec Kit) with TDD; see `specs/001-ai-job-engine/`
for the complete requirement → plan → task → verification trail.
