# Feature Specification: Desktop App, Eligibility Filter, Coverage & Freshness

**Feature**: `002-desktop-eligibility-coverage`
**Created**: 2026-07-18
**Status**: Implemented with feature 001 as the base
**Input**: "Make it an app I run from a single file that opens as a window (Windows
and Mac), hide jobs I'm ineligible for (I need sponsorship — clearance means
ineligible), add more sources, and keep results fresh."

## User Stories

### US1 — Launch as a desktop app (P1)

As the user, I run one file (or double-click a launcher) and the Job Engine opens
in its own desktop window — no terminal-then-browser dance. Closing the window
shuts everything down. Works on Windows and macOS.

**Acceptance**: `run.bat` (Windows) / `run.command` or `run.sh` (macOS) →
native window opens with the live feed; closing the window ends the process.
If no webview backend exists on the machine, the default browser opens instead
and the app still works.

### US2 — Never see jobs I can't get (P1)

As a sponsorship-seeking candidate, roles requiring a security clearance, US
citizenship, or ITAR "U.S. person" status are ineligible for me. They must not
appear in any normal feed view. An **Ineligible** view lets me audit what was
excluded and the exact wording that triggered it.

**Acceptance**: defense/clearance/ITAR postings vanish from the default feed and
appear under Ineligible with their trigger phrase; the LLM never spends quota
scoring them.

### US3 — Wider coverage, fresher results (P2)

More companies and boards feed the engine, and stale postings stop accumulating,
so the feed stays applyable.

**Acceptance**: SmartRecruiters and Workable boards ingest jobs; the validated
seed list grows (~67 companies); jobs older than 45 days that I never touched
are pruned automatically (Saved/Applied/Hidden history is never deleted).

## Functional Requirement deltas (against feature 001)

- **FR-009 (supersedes)**: EXCLUDED is now an *eligibility* verdict. Detection
  adds ITAR/export-control/"U.S. person", active/secret/TS-SCI clearance, and
  citizens-and-green-card-holders wording (word-boundary matched — "military"
  must not trigger "ITAR").
- **FR-003 (supersedes)**: default and status views exclude EXCLUDED jobs;
  a dedicated `ineligible=1` view returns only them.
- **FR-012 (amended)**: scoring skips EXCLUDED jobs entirely.
- **FR-019 (new)**: one-file desktop launch with native window + browser
  fallback, cross-platform launchers committed with correct line endings.
- **FR-020 (new)**: SmartRecruiters (US-scoped) and Workable v3 sources, seed
  list expanded and live-validated.
- **FR-021 (new)**: automatic prune of status-`none` jobs older than 45 days at
  the end of every refresh.

## Verification

Automated: filter tests incl. ITAR false-positive guards; query tests for
default-hides-EXCLUDED / ineligible-only / prune-preserves-history; parser tests
for both new sources against recorded live fixtures; API contract for
`ineligible=1`. Live: full refresh with all 8 source families; defense postings
absent from default feed, present under Ineligible; desktop window verified on
Windows (macOS launchers code-reviewed — no Mac hardware available).
