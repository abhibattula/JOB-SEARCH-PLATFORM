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

- **Open the app → see fresh, genuine jobs.** The feed renders instantly
  from the local database (last **14 days** by default, with 24-hour/7-day
  views) while a background refresh pulls all sources and streams new
  postings in live. Sort by match score or newest in one click; page through
  everything; filter by source.
- **Aggregates real sources, no scraping fights**: Greenhouse, Lever, Ashby,
  SmartRecruiters, and Workable public JSON APIs across **450+ validated
  company career boards** (user-editable watchlist in Settings), Hacker News
  "Who is hiring" threads, and Indeed + Google Jobs via python-jobspy — with
  a one-click "Search on LinkedIn" link-out built from your own terms.
  Postings that vanish from their company's board are **auto-delisted**, so
  closed jobs don't waste your time; jobs whose posted date is unknown are
  marked approximate instead of faked; search terms and locations come from
  **your profile**, not hardcoded defaults.
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
- **Apply Assist — fills in your own browser (v1.0)**: install the free
  one-time **browser companion** (a Chrome/Edge extension — see the in-app
  Companion page) and applications fill in *your everyday browser*, where
  you're already signed in to job sites. Without it, Apply Assist still fills
  in a dedicated assistant window exactly as before — the screen shows which
  mode is active. Either way it opens each shortlisted job at its real
  application form and then **watches the page continuously**, filling every
  recognized field
  the moment it exists: slow-rendering forms, forms revealed by the site's
  own Apply button, every page of a multi-step application, and forms
  embedded in iframes. A **Test Apply Assist** button runs a bundled
  practice application so you can watch your own data fill in seconds —
  proof on your machine before any real posting. Recognized fields —
  name, contact info, links, **your resume file itself**, work
  authorization/sponsorship dropdowns (matched to the site's own option
  wording), and common short-answer questions — from your profile and a
  reusable answer bank. **Open-ended questions** ("Why this company?") get an
  **AI draft** grounded in your resume, filled and flagged for your review
  before you submit; confirmed answers are saved and reused, and sensitive
  (visa/EEO) questions are never AI-answered. Multi-page applications keep filling as *you* click
  the site's own Next button; a per-field fill report shows exactly what was
  entered; closing the browser mid-queue is resumable; a batch summary wraps
  every run. **You always click the actual submit/login button yourself; the
  app never does.** Unrecognized or legally-sensitive questions pause for
  your review before anything is saved or typed. Saved logins autofill from
  your OS's own credential store (never this app's database) the same way —
  filled, never auto-submitted.
- **Resume builder + tailored PDFs**: uploading a resume returns
  instantly and extraction runs in the background with live progress; a
  **review screen** then shows every profile field — yours vs the
  resume's — with per-field Keep / Use resume's / Merge choices. Nothing
  changes silently, visa questions are never imported, and it genuinely
  works on the offline model (long resumes are processed in parts); every job can then export an ATS-safe **tailored resume PDF**
  and cover-letter PDF — generated fully offline, and attached automatically
  by Apply Assist when available.
- **Sponsorship intelligence nobody else has**: a local A–F **sponsor grade**
  per company computed from real USCIS approval/denial history and DOL wage
  data, **cap-exempt detection** (universities/nonprofits that skip the H-1B
  lottery entirely), a wage-weighted lottery-odds hint, and a "Strong
  sponsors only" feed filter — all free, all offline, no lookups leave your
  machine.
- **An instrument, not a webpage**: a full design-token UI with a light
  "datasheet" theme and a dark "scope screen" theme, a kanban pipeline
  board, toast feedback on every action, and a first-run checklist that
  tracks real setup state.
- **Smarter matching within free limits**: every new job gets an **offline
  semantic ranking** against your resume (a bundled 330MB embeddings model —
  no network, no key), so the limited free AI quota is always spent on the
  most relevant jobs first; structured extraction uses the most
  schema-reliable free cloud models, with Groq and Google AI Studio presets. **The bundled offline model is the default AI everywhere** (private, $0) with the cloud key as automatic fallback — one toggle in Settings flips the preference.
- **Updates itself**: the app checks GitHub Releases daily, and one click
  downloads the installer with a progress bar, verifies its SHA-256, installs
  silently, and relaunches — with a What's New screen after every update. A
  Diagnostics page runs real self-checks (PDF render, AI model, browser
  launch, source reachability) and exports logs when something misbehaves.

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
The installer is large (~1.5GB) because it bundles the offline AI model and
the semantic-ranking model. From v0.8.0 on, newer versions install from
inside the app (Settings → Check for updates).

### Connect the browser companion (v1.0, optional but recommended)

The companion (a Chrome/Edge extension) lets Apply Assist fill applications
in **your own browser**, where you're already logged in to job sites.
Without it, Apply Assist still works in a separate assistant window — so this
is optional. It's free, installs from the copy bundled with the app (nothing
to download), and takes about a minute:

1. In the app, open the **Companion** page (top nav, under *Apply*). It shows
   a folder path with a **Copy** button — this is the extension folder the
   app keeps up to date for you.
2. In Chrome or Edge, open the extensions page: paste `chrome://extensions`
   (Chrome) or `edge://extensions` (Edge) into the address bar.
3. Turn on **Developer mode** (top-right toggle).
4. Click **Load unpacked** and pick the folder from step 1 (paste the copied
   path into the folder dialog).
5. Back in the app, the Companion page's status turns **green** within a few
   seconds — you're connected. You only do this once; app updates keep the
   extension current automatically.

**Using it:** click **Test Apply Assist** on the Apply Assist page to watch
it fill a bundled practice application with your own data, or just browse to
any real posting and click the companion's **"Fill this page"** button. For
open-ended questions ("Why this company?") it drafts an answer from your
resume and flags it for your review — you always edit/confirm and click
*Submit* yourself. Full walkthrough in
[docs/USER_GUIDE.md](docs/USER_GUIDE.md).

> The extension loads *unpacked* (developer mode) rather than from the Chrome
> Web Store, so Chrome may show a "Disable developer mode extensions?" nag on
> startup — that's expected and harmless; the companion runs entirely on your
> machine and never sends your data anywhere.

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
| Bundled local AI model + embeddings model (ship in the installer) | $0 |
| Apply Assist browser automation (your installed Edge/Chrome) | $0 |
| Storage (SQLite), UI (FastAPI + HTMX, no build step) | $0 |

## Known limitations

- **Workday career sites** (NVIDIA, AMD, Qualcomm…) sit behind Cloudflare
  fingerprinting as of mid-2026 and reject plain HTTP clients; the source is
  implemented and tested but ships with no default entries (we don't fight bot
  protection). Their postings still arrive via the Indeed source. Apply
  Assist applies the same principle: if a page's fields can't be confidently
  read (Workday included), it just opens the tab for you to fill manually and
  moves on to the next job — it never tries to bypass a site's protections.
- **LinkedIn** rate-limits anonymous scraping within a few hundred results,
  so scraping stays opt-in (Settings) and unreliable by nature; the feed's
  "Search on LinkedIn" button is the dependable path — it opens a genuine
  LinkedIn search for your terms (last 14 days) in your own browser.
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
.venv\Scripts\python.exe -m pytest    # 500+ tests, no network needed
python cli.py refresh                  # real end-to-end pull
python scripts/check_seeds.py          # validate companies.yml entries
```

Building an installer needs two extra one-time steps (see
[docs/RELEASING.md](docs/RELEASING.md) for the full sequence):
`pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`
(the bundled local AI model's runtime has no default PyPI wheel) and
`python packaging/fetch_model.py` (downloads + verifies the ~1GB LLM and
the ~330MB embeddings model into a gitignored `models/` directory before
`pyinstaller` runs).

Built spec-first (GitHub Spec Kit) with TDD; see `specs/001-ai-job-engine/`
(core engine) and `specs/005-apply-assist/` (local AI + Apply Assist) for
the complete requirement → plan → task → verification trail.
