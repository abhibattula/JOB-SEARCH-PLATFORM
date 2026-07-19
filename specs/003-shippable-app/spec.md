# Feature Specification: Shippable Installers, In-App AI Setup, Match Filter

**Feature**: `003-shippable-app`
**Created**: 2026-07-18
**Status**: Implemented
**Input**: "Build an app/software with Windows installer and Mac in order to ship
to users, add an option to show results based on resume match, and the AI should
be integrated."

## User Stories

### US1 — Install like a normal app (P1)

As a new user, I download an installer for my OS, run it, and get "Job Engine"
in my Start menu / Applications. No Python, no terminal, no config files.

**Acceptance**: GitHub Release carries `JobEngine-Setup-<v>.exe` (Windows) and
`JobEngine-<v>.dmg` (macOS), built by CI on every version tag; the installed app
opens its window, stores data in the per-user OS data directory, and ships with
the USCIS sponsorship data preloaded (badges work with zero setup).

### US2 — AI configured inside the app (P1)

As a user, I set up AI scoring entirely in the app: a Settings page where I
paste my own free Groq key (guided link), test it live, and optionally point at
a different provider (e.g., local Ollama). First run greets me with a 3-step
welcome. No shared/bundled API key ever ships (quota abuse + provider ToS).

**Acceptance**: key saved from the UI is stored locally and masked on read;
"Test key" reports success/failure from a real 1-token call; feed shows the
guided welcome when no resume+key exist; `.env` remains a developer-only
override.

### US3 — Browse by resume match (P2)

As a user with a scored feed, I can restrict results to strong matches.

**Acceptance**: "Best matches" nav tab (score ≥70, sorted by score) and a
toolbar threshold (Any/50+/70+/85+); a threshold excludes unscored jobs; no
threshold keeps today's behavior.

## Functional Requirement deltas

- **FR-022 (new)**: settings persisted in the database with env-var override
  precedence; consumed by the matcher, jobspy source, scheduler, and scoring cap.
- **FR-023 (new)**: `GET/POST /api/settings` (masked key, never returned in
  full) and `POST /api/settings/test`.
- **FR-024 (new)**: `min_score` filter across `/api/jobs`, `/api/export`, and
  pages.
- **FR-025 (new)**: frozen-run path resolution (`engine/paths.py`): per-user
  data dir + bundle-aware resource lookup; `JOBS_DATA_DIR` override.
- **FR-026 (new)**: reproducible packaging (PyInstaller spec, Inno Setup
  script, dmg script) and CI release pipeline on `v*` tags with tests gating
  both installer builds.

## Verification

106 automated tests (settings precedence/masking/test-endpoint, min_score
db+API, paths incl. frozen mode and bundled-USCIS bootstrap) plus: local frozen
build smoke-tested on Windows (fresh `JOBS_DATA_DIR`, window serves, bundled
data auto-loads); CI workflows validated by the first tagged release (requires
the repo on GitHub — handoff in docs/RELEASING.md since `gh` is not installed
on the dev machine).
