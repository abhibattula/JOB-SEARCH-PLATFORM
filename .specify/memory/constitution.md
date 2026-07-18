<!--
Sync Impact Report
==================
Version change: (template) → 1.0.0
Modified principles: n/a (initial ratification)
Added sections:
  - Core Principles (5): Speed-to-Value First; Zero-Subscription Cost;
    API-First, Polite Ingestion; Reusable Core, Thin Web Layer;
    Tested Core Logic
  - Additional Constraints (stack, privacy)
  - Development Workflow
  - Governance
Removed sections: none
Templates status:
  - .specify/templates/plan-template.md ✅ compatible (generic Constitution Check gate;
    gates below apply as written)
  - .specify/templates/spec-template.md ✅ compatible (no constitution-specific fields)
  - .specify/templates/tasks-template.md ⚠ note: template marks tests as OPTIONAL;
    per Principle V, test tasks are REQUIRED for engine/ logic (classifier, dedup,
    recency queries, sponsorship join). Include them when generating tasks.md.
Follow-up TODOs: none
-->

# Personalized AI Job Engine Constitution

## Core Principles

### I. Speed-to-Value First

The purpose of this project is to get its user hired. Every feature, refactor, and
dependency MUST be justified by "does this surface applyable jobs sooner or rank them
better?" Each milestone MUST end in a runnable state that delivers user-visible value.
Speculative abstraction is prohibited (YAGNI): capabilities listed as deferred in the
approved plan (auth/multi-user, hosted deployment, local LLM, CLI/MCP layer, Playwright
scraping) MUST NOT be built in v1 unless the plan is amended first.

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
  is the past 7 days with a last-24-hours toggle.

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

**Version**: 1.0.0 | **Ratified**: 2026-07-18 | **Last Amended**: 2026-07-18
