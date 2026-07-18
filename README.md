# Personalized AI Job Engine

A zero-subscription, local-first web app that finds **entry-level software and
hardware engineering jobs**, flags **visa-sponsorship likelihood** (OPT/H-1B),
and scores every posting against **your resume** with actionable gap analysis —
the things tools like Simplify and Jobright charge subscriptions for, running
entirely on your machine for $0.

## What it does

- **Open the app → see fresh jobs.** The feed renders instantly from the local
  database (last 7 days by default, one-click 24-hour view) while a background
  refresh pulls all sources and streams new postings in live.
- **Aggregates real sources, no scraping fights**: Greenhouse, Lever, and Ashby
  public JSON APIs across ~47 validated companies, Hacker News "Who is hiring"
  threads, and Indeed via python-jobspy. One refresh ≈ 14,000+ postings.
- **Entry-level filter tuned for SWE + hardware**: new-grad/junior markers plus
  the hardware families (firmware, embedded, FPGA, ASIC, verification,
  validation, silicon, RTL), with senior/staff/II+ roles excluded. 100% on the
  44-title test fixture (gate: ≥90%).
- **Sponsorship badges with evidence**: USCIS H-1B Employer Data Hub history
  fuzzy-joined to each company, combined with JD wording. Explicit "unable to
  sponsor" / "citizens only" / clearance requirements always win → EXCLUDED.
- **Resume matching (free LLM)**: upload a PDF once; new entry-level jobs get a
  0–100 score, matching/missing skills, and concrete "add X to your resume"
  actions via the Groq free tier (any OpenAI-compatible endpoint works).
- **A feed that stays actionable**: mark jobs Saved / Applied / Hidden —
  handled jobs never re-clutter the default view. Export any view as CSV.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # add your free Groq key to unlock scoring
python app.py                 # -> http://127.0.0.1:8000
```

Full setup (sponsorship data download, seed-list management, smoke tests):
**[specs/001-ai-job-engine/quickstart.md](specs/001-ai-job-engine/quickstart.md)**
· Daily usage: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

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
