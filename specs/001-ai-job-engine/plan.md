# Implementation Plan: Personalized AI Job Engine

**Branch**: `001-ai-job-engine` | **Date**: 2026-07-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-ai-job-engine/spec.md`

## Summary

A zero-subscription, single-user webapp that aggregates recent entry-level SWE and
hardware job postings from public JSON APIs, classifies them (entry-level, visa
sponsorship likelihood), scores them against the user's resume with a free-tier
LLM, and presents them in a feed that opens instantly from cache and auto-refreshes
in the background. Business logic lives in a reusable `engine/` package; `web/` is
a thin FastAPI + Jinja2 + HTMX layer, so future multi-user deployment is additive.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, uvicorn, Jinja2, HTMX (vendored static file),
httpx, python-jobspy, PyMuPDF, rapidfuzz, pydantic, PyYAML, python-dotenv,
openai (client only, pointed at free providers), APScheduler (polish phase)
**Storage**: SQLite at `data/jobs.db` (path overridable via `JOBS_DB_PATH` env var)
**Testing**: pytest (fixtures for classifier/dedup/recency/sponsorship; httpx
MockTransport for source parsers)
**Target Platform**: Local Windows 11 machine (dev/daily use); Linux free-tier
host later without code changes
**Project Type**: Web application — single Python codebase, `engine/` + `web/`
**Performance Goals**: Feed renders from cache in <2s; full refresh across all
sources completes in <5min; new jobs stream into the feed during refresh
**Constraints**: $0 recurring cost; ≤1 request/sec/domain; resume/profile data
stays local; LLM access via OpenAI-compatible client with env-configured
base URL/model (Groq free tier default; Gemini/Ollama swappable)
**Scale/Scope**: Single user; ~50–100 seed companies; 100+ relevant jobs/week;
thousands of stored rows — trivially within SQLite limits

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Speed-to-Value First | Every milestone ends runnable; no v2-deferred feature (auth, hosting, local LLM, CLI/MCP, Playwright) in scope | ✅ PASS — milestones map to independently testable user stories; deferral list intact |
| II. Zero-Subscription Cost | No paid tier, trial, or card required anywhere | ✅ PASS — free APIs, public data, Groq free tier via provider-agnostic client |
| III. API-First, Polite Ingestion | JSON endpoints before scraping; ≤1 req/s/domain; no bot-protection fights | ✅ PASS — all six source families are JSON APIs or a maintained library; Wellfound-class sources excluded |
| IV. Reusable Core, Thin Web Layer | Logic in `engine/` (no web imports); headless pipeline; additive multi-user path | ✅ PASS — `cli.py` runs the same pipeline; single profile row is the only single-user assumption |
| V. Tested Core Logic | pytest before wiring: classifier (≥90%), dedup, recency, sponsorship join; schema-validated LLM output | ✅ PASS — test plan in tasks; pydantic validation with bounded retry |

**Post-Phase-1 re-check**: ✅ PASS — data model and contracts introduce no violations
(job `status` and `refresh_runs` additions serve P1/clarified requirements, not
speculation).

## Project Structure

### Documentation (this feature)

```text
specs/001-ai-job-engine/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── http-api.md      # Phase 1 output
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
engine/
├── __init__.py
├── ingest/
│   ├── __init__.py      # source registry
│   ├── base.py          # RawJob dataclass, source protocol, polite HTTP helpers
│   ├── greenhouse.py    # boards-api.greenhouse.io
│   ├── lever.py         # api.lever.co
│   ├── ashby.py         # api.ashbyhq.com posting-api
│   ├── workday.py       # {tenant}.wdX.myworkdayjobs.com CxS endpoint
│   ├── hn.py            # HN "Who is hiring" via Algolia
│   └── jobspy_source.py # python-jobspy (Indeed/LinkedIn)
├── filters.py           # entry-level classifier, sponsorship keyword scan
├── sponsorship.py       # USCIS/DOL loaders, name normalization, rapidfuzz join
├── matcher.py           # LLM client, prompt, pydantic-validated match analysis
├── resume.py            # PyMuPDF text extraction
├── db.py                # schema/migrations, upserts, dedup, feed queries
└── pipeline.py          # refresh orchestration, per-source progress, cooldown

web/
├── main.py              # FastAPI app factory, page routes
├── routes_api.py        # JSON API (see contracts/http-api.md)
├── templates/           # base.html, feed.html, job_detail.html, profile.html, partials/
└── static/              # htmx.min.js, styles.css

app.py                   # uvicorn entrypoint
cli.py                   # headless refresh: python cli.py refresh
companies.yml            # seed list: company → ats_type + slug/tenant
data/                    # jobs.db, USCIS/DOL downloads (gitignored)
tests/
├── test_filters.py      # classifier fixture set (~40 titles)
├── test_db.py           # dedup, recency queries, status transitions
├── test_sponsorship.py  # name matching, rating logic
├── test_sources.py      # parser tests with recorded JSON fixtures
└── fixtures/
```

**Structure Decision**: Single Python project with `engine/` (pure logic, no web
imports) and `web/` (thin FastAPI layer) — mandated by Constitution Principle IV.
Both the web app and `cli.py` call `engine.pipeline`; templates/static are the
only frontend (no Node toolchain).

## Complexity Tracking

No constitution violations — table intentionally empty.
