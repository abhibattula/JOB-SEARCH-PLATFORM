<!--
Sync Impact Report
==================
Version change: 1.1.2 → 1.1.3 (2026-07-24)
Modified sections:
  - Principle I › closing paragraph — appended a Principle III CLARIFICATION
    (feature 012): the companion MAY READ the current page's public job
    metadata (title/company/description the user is already viewing) to render
    a LOCAL-ONLY, READ-ONLY discovery overlay (a match/sponsorship badge). This
    reads nothing it isn't shown, clicks/mutates/submits NOTHING on the page,
    scrapes no search-result lists or other pages, and sends the metadata only
    to the local app. A bounded read-only addition — not a relaxation of the
    no-click/no-submit rule (III) or the polite-ingestion rule (III proper).
Templates status: all compatible (no template references the read rule).

Previous report (1.1.1 → 1.1.2, 2026-07-24):
Version change: 1.1.1 → 1.1.2 (2026-07-24)
Modified sections:
  - Principle I › closing paragraph — appended a Principle III CLARIFICATION
    (feature 011): app-driven browser automation MAY click a form field's own
    input widget to set a value (custom dropdown option, typeahead
    suggestion), but MUST NEVER click submit/apply/next/continue/save/finish/
    login/register/pay controls; the human still performs every submit/login
    and advances every multi-step wizard. A bounded relaxation of the
    implementation's prior zero-click rule, not a change to any principle.
Templates status: all compatible (no template references the click rule).

Previous report (1.1.0 → 1.1.1, 2026-07-22):
Modified sections:
  - Additional Constraints › "Recency is a first-class requirement" — default
    feed window changed from 7 days to 14 days at the user's explicit
    direction (feature 008; "okay to show reasonably old postings … past
    2 weeks"). 24h/7d/all remain as toggles. No principle changed.
Templates status: all compatible (no template references the 7-day default).

Previous report (1.0.0 → 1.1.0):
Version change: 1.0.0 → 1.1.0
Modified principles:
  - I. Speed-to-Value First — narrowed the deferred/MUST-NOT-build list: "local
    LLM" and "Playwright scraping" removed (feature 005 "Apply Assist" plan
    approved, requires both — a bundled local model for offline Q&A/drafting
    and app-driven headed-browser automation for application autofill).
    "auth/multi-user", "hosted deployment", "CLI/MCP layer" remain deferred.
Added sections: none
Removed sections: none
Templates status:
  - .specify/templates/plan-template.md ✅ compatible (generic Constitution Check
    gate; local LLM / Playwright no longer trip it for feature 005)
  - .specify/templates/spec-template.md ✅ compatible (no constitution-specific
    fields)
  - .specify/templates/tasks-template.md ⚠ note (unchanged from 1.0.0): template
    marks tests as OPTIONAL; per Principle V, test tasks are REQUIRED for engine/
    logic. Include them when generating tasks.md.
Follow-up TODOs: none
-->

# Personalized AI Job Engine Constitution

## Core Principles

### I. Speed-to-Value First

The purpose of this project is to get its user hired. Every feature, refactor, and
dependency MUST be justified by "does this surface applyable jobs sooner or rank them
better, or help the user complete and submit applications faster?" Each milestone
MUST end in a runnable state that delivers user-visible value. Speculative
abstraction is prohibited (YAGNI): capabilities listed as deferred in the approved
plan (auth/multi-user, hosted deployment, CLI/MCP layer) MUST NOT be built in v1
unless the plan is amended first. A bundled local LLM and app-driven browser
automation (Playwright) are permitted as of the approved feature 005 plan, subject
to the constraints in Principle II (no size veto beyond what that plan accepts) and
Principle III (automation MUST NOT bypass bot protection or auto-submit on the
user's behalf — the human always performs the final submit/login action).
Clarification (feature 011): the automation MAY click a form field's own
input widget to SET A VALUE (e.g. open a custom dropdown and choose an
option, or pick a typeahead suggestion) — this is field-filling, the same
intent as typing. It MUST NEVER click a control that submits, applies,
advances (next/continue), saves, finishes, logs in, registers, creates an
account, or pays. The human still performs every submit/login and advances
every multi-step wizard themselves.
Clarification (feature 012): the companion MAY READ the current page's public
job metadata (the title/company/description the user is already viewing) to
render a LOCAL-ONLY, READ-ONLY discovery overlay (a match-score + sponsorship
badge). The discovery path clicks, types into, submits, or mutates NOTHING on
the page (it only renders its own shadow-DOM badge), scrapes no search-result
lists or other pages, and sends the read metadata only to the local app over
the existing authenticated companion channel. This is a bounded read-only
addition, not a relaxation of the no-click/no-submit rule above or of the
polite-ingestion rule in Principle III.

### II. Zero-Subscription Cost

The system MUST run at $0 recurring cost. Only free/open-source software, free API
tiers (e.g., Groq free tier), and public data sources (USCIS H-1B Employer Data Hub,
DOL LCA disclosures) are permitted. Any component that would require a paid plan,
trial, or credit card to function MUST be rejected or replaced. LLM access MUST go
through a provider-agnostic OpenAI-compatible client configured via environment
variables so free providers can be swapped without code changes.

### III. API-First, Polite Ingestion

Job data MUST be ingested from official or public JSON endpoints when they exist
(Greenhouse, Lever, Ashby, Workday CxS, HN Algolia) before any HTML scraping is
considered. All ingestion MUST: respect robots.txt, stay at or under 1 request/second
per domain, use honest headers, and never bypass authentication or bot protection.
Sources that require fighting bot protection (e.g., Wellfound/DataDome) are out of
scope. Ingestion failures in one source MUST NOT abort the pipeline for other sources.

### IV. Reusable Core, Thin Web Layer

All business logic (ingestion, filtering, sponsorship, matching, persistence) MUST
live in the `engine/` package as pure Python with no imports from the web layer.
`web/` MUST remain a thin FastAPI layer: routes, templates, and background-task
orchestration only. Single-user assumptions (one profile row, no auth) are acceptable
now, but any design that would force a rewrite—rather than an additive change—to
support multiple users later MUST be revised. The full pipeline MUST be runnable
headless (CLI) as well as from the web app.

### V. Tested Core Logic

Deterministic engine logic MUST have pytest coverage before it is wired into the
pipeline: the entry-level classifier (≥90% accuracy on the fixture set), dedup,
recency queries (7-day/24-hour, `posted_date` → `first_seen` fallback), and the
sponsorship name-matching join. LLM outputs MUST be schema-validated (pydantic) with
a bounded retry; unscored jobs MUST still appear in the feed rather than fail the
pipeline. Network-dependent code paths MUST degrade gracefully and are verified by
the per-milestone manual verification steps in the plan.

## Additional Constraints

- **Stack (fixed for v1)**: Python 3.11+, FastAPI + Jinja2 + HTMX (vendored),
  SQLite at `data/jobs.db` (path via env var), httpx, PyMuPDF, rapidfuzz,
  python-jobspy. No Node build step, no JS framework.
- **Privacy**: Resume text and profile data stay on the local machine. API keys live
  in `.env` (gitignored) and MUST never be committed. `data/` is gitignored.
- **Recency is a first-class requirement**: every stored job MUST carry
  `posted_date` (when the source provides it) and `first_seen`; the default feed view
  is a recent window — 14 days by default (user-directed, feature 008) — with
  24-hour/7-day/all toggles. Jobs lacking a source posted date MUST be displayed
  as approximate, not silently dated by first-seen.

## Development Workflow

- Features follow the spec-kit flow: constitution → specify → plan → tasks →
  implement, on feature branches with sequential numbering.
- Implementation follows the approved plan's milestone order; a milestone is done
  only when its verification steps pass (evidence before assertions).
- Commit after each task or logical group; auto-commit hooks in
  `.specify/extensions.yml` handle workflow-boundary commits.
- The plan-template Constitution Check gate MUST evaluate: value justification
  (Principle I), $0 cost (II), ingestion politeness (III), engine/web separation
  (IV), and test coverage for deterministic logic (V). Violations require an entry
  in Complexity Tracking with a rejected simpler alternative.

## Governance

This constitution supersedes ad-hoc practice for this repository. Amendments are made
by editing this file with: a semantic version bump (MAJOR: principle removal or
redefinition; MINOR: new principle or materially expanded guidance; PATCH:
clarification/wording), an updated Sync Impact Report, and propagation to the
templates listed there. Plans and task lists MUST pass the Constitution Check gate;
deviations discovered during implementation MUST be either corrected or recorded in
Complexity Tracking before the milestone is declared done.

**Version**: 1.1.3 | **Ratified**: 2026-07-18 | **Last Amended**: 2026-07-24
