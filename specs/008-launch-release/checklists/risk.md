# Risk Checklist: Launch Release (008)

**Purpose**: Validate that requirements fully specify the highest-risk
areas: self-update execution safety, delisting correctness, browser-layer
fallbacks, migration safety, desktop-shell verification, consent gates,
and preservation of the never-auto-submit rule on the new browser layer.
**Created**: 2026-07-22
**Feature**: [spec.md](../spec.md)

## Automation Safety (never-auto-submit on the new browser layer)

- [x] CHK001 - Is the never-click/never-auto-submit/never-auto-login rule explicitly preserved for the rebuilt browser layer? [Consistency, Spec §FR-011, §US1-AS5]
- [x] CHK002 - Is isolation from the user's personal browsing profile specified even though their installed browser is used? [Clarity, Spec §FR-007]
- [x] CHK003 - Is handling of leftover state from the removed browser-download flow specified? [Completeness, Spec §FR-008, §Clarifications]
- [x] CHK004 - Are all fill-failure reason classes enumerated and required to be distinctly presented? [Completeness, Spec §FR-009]
- [x] CHK005 - Is queue behavior on preflight failure specified (must not start, must explain)? [Clarity, Spec §FR-010]
- [x] CHK006 - Is the no-supported-browser boundary condition addressed? [Edge Case, Spec §Edge Cases]

## Self-Update Integrity

- [x] CHK007 - Is integrity verification required before any downloaded installer executes? [Completeness, Spec §FR-030]
- [x] CHK008 - Is the partial/interrupted-download case specified (never execute partials)? [Edge Case, Spec §Edge Cases]
- [x] CHK009 - Is behavior under an OS/security block (SmartScreen) specified with a manual fallback? [Edge Case, Spec §Edge Cases, §Assumptions]
- [x] CHK010 - Is offline/unreachable update-check behavior specified as silent (startup) vs explicit (manual)? [Clarity, Spec §FR-030, §US5-AS1]
- [x] CHK011 - Is a pre-migration database backup with restore-on-failure required and testable? [Completeness, Spec §FR-034, §Edge Cases]
- [x] CHK012 - Is build-time version consistency (app/installer/tag) required? [Consistency, Spec §FR-031]
- [x] CHK013 - Is the upgrade path required to be verified against a real populated previous-version database? [Measurability, Spec §FR-034, §SC-007]

## Delisting & Freshness Correctness

- [x] CHK014 - Is mass-delisting prevented when a board fetch fails or redirects? [Edge Case, Spec §FR-013, §Edge Cases]
- [x] CHK015 - Is saved/applied history retention on delist specified (flag, never delete)? [Completeness, Spec §FR-013]
- [x] CHK016 - Is restoration of a reappearing delisted job specified? [Gap → FIXED 2026-07-22: added to FR-013]
- [x] CHK017 - Are liveness checks bounded by the ingestion politeness budget? [Gap → FIXED 2026-07-22: added to FR-013]
- [x] CHK018 - Is the unknown-posted-date case specified as approximate display rather than substituted dates? [Clarity, Spec §FR-014]
- [x] CHK019 - Is the 14-day rule's application to dateless sources documented? [Assumption, Spec §Assumptions]
- [x] CHK020 - Is same-source repost deduplication required without breaking distinct same-title/different-location jobs? [Edge Case, Spec §FR-017, §Edge Cases]

## Desktop Shell Verification

- [x] CHK021 - Are copy/link/download requirements required to be verified inside the installed shell, not a dev browser? [Measurability, Spec §SC-003, §US2 Independent Test]
- [x] CHK022 - Is honest failure reporting specified when the clipboard is unavailable? [Edge Case, Spec §FR-002, §Edge Cases]
- [x] CHK023 - Are server-generated links (not just template links) covered by the external-link requirement? [Coverage, Spec §FR-004]

## Consent & Privacy

- [x] CHK024 - Is fill-only-blank + keep-or-replace consent specified for identity auto-fill? [Completeness, Spec §FR-022]
- [x] CHK025 - Are work-authorization fields excluded from all auto-fill without explicit confirmation? [Completeness, Spec §FR-024]
- [x] CHK026 - Is the no-AI contact-extraction fallback required so consent flows exist on every tier? [Coverage, Spec §FR-023]
- [x] CHK027 - Are provider privacy caveats (e.g., training-data use) required to be disclosed in-app? [Completeness, Spec §FR-027]

## Watchlist & Search Integrity

- [x] CHK028 - Is survival of user watchlist edits across updates specified? [Completeness, Spec §FR-015]
- [x] CHK029 - Is the invalid/renamed board identifier failure mode specified as visible, not silent? [Edge Case, Spec §Edge Cases]
- [x] CHK030 - Are derived search terms required to be visible, editable, capped, and never silently changed? [Clarity, Spec §FR-025]
- [x] CHK031 - Is the empty-profile fallback to built-in defaults specified? [Edge Case, Spec §FR-025, §US4-AS5]

## Notes

- 31/31 pass. CHK016 and CHK017 were gaps found by this checklist and
  fixed in spec.md (FR-013 extended) on 2026-07-22 before task generation.
