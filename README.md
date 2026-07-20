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
- **Resume matching that always works, three tiers deep**: a deterministic
  keyword matcher scores instantly with zero setup (`~NN`); the bundled
  offline AI model upgrades that automatically the moment you have a resume
  on file — still zero setup, fully offline (`•NN`); pasting a free Groq key
  (or any OpenAI-compatible endpoint) upgrades everything again to full cloud
  analysis with matching/missing skills and "add X to your resume" actions.
  Each tier's scores are visually distinct and auto-upgrade in place — you
  never lose anything by adding a key later.
- **Apply fast, apply well**: desktop notifications when a refresh finds new
  70+ matches, a "New today" view of everything just discovered, and one-click
  **tailored resume bullets + cover letter** per job (generated from your real
  resume only — nothing invented).
- **A pipeline, not just a list**: Applied jobs track stages (OA → interview →
  offer), notes, and 7-day follow-up nudges; the Analytics page shows your
  funnel and which sources/score-bands actually produce callbacks. Export any
  view as CSV.
- **Works fully offline, zero setup**: a small AI model ships bundled inside
  the installer, so match scoring and tailoring work immediately — no
  account, no API key, no internet connection needed for the AI itself (an
  optional cloud key still gives the highest-quality results and is always
  preferred when set).
- **Apply Assist**: opens each shortlisted job's real application page in
  its own dedicated browser window and fills in the fields it recognizes —
  name, contact info, links, work authorization/sponsorship, common
  short-answer questions — from your profile and a reusable answer bank.
  **You always click the actual submit/login button yourself; the app never
  does.** Unrecognized or legally-sensitive questions pause for your review
  before anything is saved or typed. Saved logins autofill from your OS's own
  credential store (never this app's database) the same way — filled, never
  auto-submitted.

## Install (for users)

Grab the latest installer from the **GitHub Releases** page once the repo is
published (see [docs/RELEASING.md](docs/RELEASING.md)):

- **Windows**: `JobEngine-Setup-<version>.exe` — SmartScreen will warn because
  the app is unsigned; click *More info → Run anyway* the first time.
- **macOS**: `JobEngine-<version>.dmg` — drag *Job Engine* to Applications;
  first launch needs *right-click → Open → Open* (unsigned app).

First run: the app opens with a 3-step welcome — upload your resume, hit
Refresh, done. Match scoring works immediately via the bundled offline AI
model — a free Groq key on the Settings page is optional and only upgrades
quality further. Sponsorship data ships preloaded. All data stays on your
computer (`%LOCALAPPDATA%\JobEngine` / `~/Library/Application Support/JobEngine`).
The installer is noticeably larger than earlier versions (~1GB+) because it
bundles that AI model; Apply Assist's one-time browser-engine download
(~150-280MB) only happens the first time you use that specific feature.

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
| Bundled local AI model (Apache 2.0, ships in the installer) | $0 |
| Apply Assist browser automation (Chromium, one-time download) | $0 |
| Storage (SQLite), UI (FastAPI + HTMX, no build step) | $0 |

## Known limitations

- **Workday career sites** (NVIDIA, AMD, Qualcomm…) sit behind Cloudflare
  fingerprinting as of mid-2026 and reject plain HTTP clients; the source is
  implemented and tested but ships with no default entries (we don't fight bot
  protection). Their postings still arrive via the Indeed source. Apply
  Assist applies the same principle: if a page's fields can't be confidently
  read (Workday included), it just opens the tab for you to fill manually and
  moves on to the next job — it never tries to bypass a site's protections.
- **LinkedIn** via jobspy is off by default (`JOBSPY_LINKEDIN=1` to try it) —
  it bot-blocks aggressively.
- Scanned-image resumes (no text layer) are not supported.
- **Apply Assist is an assistant, not an autopilot**: it never clicks a
  final submit or login button, and it never automates intra-form page
  navigation (multi-step application wizards are advanced by you). Even
  though a human performs every submission and login, automating page
  navigation and field-filling on third-party sites may still touch the
  edges of some sites' Terms of Service — the app shows a one-time notice
  before your first Apply Assist session; use your own judgment per site.

## Development

```powershell
.venv\Scripts\python.exe -m pytest    # 269 tests, no network needed
python cli.py refresh                  # real end-to-end pull
python scripts/check_seeds.py          # validate companies.yml entries
```

Building an installer needs two extra one-time steps (see
[docs/RELEASING.md](docs/RELEASING.md) for the full sequence):
`pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`
(the bundled local AI model's runtime has no default PyPI wheel) and
`python packaging/fetch_model.py` (downloads + verifies the ~1GB model
into a gitignored `models/` directory before `pyinstaller` runs).

Built spec-first (GitHub Spec Kit) with TDD; see `specs/001-ai-job-engine/`
(core engine) and `specs/005-apply-assist/` (local AI + Apply Assist) for
the complete requirement → plan → task → verification trail.
