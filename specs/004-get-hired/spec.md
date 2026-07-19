# Feature Specification: Get-Hired Stage

**Feature**: `004-get-hired`
**Created**: 2026-07-19
**Status**: Implemented
**Input**: "Best personalized job search platform that definitely gets me hired" +
alerts/tailoring/pipeline/SimplifyJobs picks + update check, local AI fallback,
latest-jobs emphasis. Interview-prep coach deferred by choice.

## User Stories (all P1 unless noted)

- **US1 Scores without setup**: match scores appear immediately after installing
  — a deterministic local skill-overlap matcher (`~NN`, "basic") runs when no AI
  key exists and is automatically upgraded to full AI analysis once a key is
  added.
- **US2 The canonical new-grad feed**: SimplifyJobs/New-Grad-Positions listings
  flow in as a source, including their explicit sponsorship labels ("Offers
  Sponsorship" → positive evidence; "U.S. Citizenship is Required" / "Does Not
  Offer Sponsorship" → EXCLUDED).
- **US3 Follow-through**: Applied jobs carry stages (applied → OA → interview →
  offer/rejected), dates, and notes; quiet applications get a ⚑ follow-up flag
  after 7 days; `/analytics` shows the funnel and response rates by source and
  score band.
- **US4 Speed-to-apply**: after each refresh, a desktop notification announces
  newly discovered eligible 70+ matches (toggleable); a "New today" view lists
  everything the engine discovered in the last 24 hours.
- **US5 Apply well** (P2): one click on a job generates JD-mirrored resume
  bullets, a ~180-word cover letter, and ATS keywords from the real resume only
  (hard no-invention constraint), cached until the resume changes.
- **US6 Stay current** (P2): a Check-for-updates button compares the running
  version against GitHub Releases.

## Functional Requirement deltas

- FR-027 basic local scoring + method tagging + LLM upgrade path
- FR-028 SimplifyJobs source with sponsorship-label mapping
- FR-029 stages/notes schema, follow-up flags, analytics aggregates + endpoints
- FR-030 post-refresh alert computation + notification, `seen_since` filtering
- FR-031 tailoring generation/caching/invalidation, 409 guards
- FR-032 release update check (silent offline)

## Verification

143 automated tests (TDD throughout: scorer determinism, upgrade query,
listings fixture + label mapping, stage transitions + analytics, alert gating
incl. notification-failure safety, tailor schema/guards/cache-invalidation,
version comparison). Live: real-repo update check; dev app refresh with basic
scores; frozen rebuild + smoke; v0.4.0 tag → CI installers.
