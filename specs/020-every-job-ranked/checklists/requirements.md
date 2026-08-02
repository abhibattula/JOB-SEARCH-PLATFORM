# Specification Quality Checklist: Every Job Ranked

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-01
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs)
- [X] Focused on user value and business needs
- [X] Written for non-technical stakeholders
- [X] All mandatory sections completed

## Requirement Completeness

- [X] No [NEEDS CLARIFICATION] markers remain
- [X] Requirements are testable and unambiguous
- [X] Success criteria are measurable
- [X] Success criteria are technology-agnostic (no implementation details)
- [X] All acceptance scenarios are defined
- [X] Edge cases are identified
- [X] Scope is clearly bounded
- [X] Dependencies and assumptions identified

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria
- [X] User scenarios cover primary flows
- [X] Feature meets measurable outcomes defined in Success Criteria
- [X] No implementation details leak into specification

## Notes

Validation pass 1 findings, all fixed inline before this file was written:

- **Implementation leak** — the first draft of FR-001/FR-004 named the
  `basic_match` module and the `local`/`basic` method strings directly. Reworded
  to "quick keyword matching" and "full AI assessment"; the concrete mapping
  belongs in data-model.md, not the spec.
- **Untestable success criterion** — an early SC read "the refresh feels fast".
  Replaced with SC-003 (under 60 seconds on a backlog that previously held the
  run open for over two hours), which is measurable against the real database.
- **Missing edge case** — nothing covered a job becoming ineligible between
  ranking and assessment; added.
- **Unstated guarantee** — the spec did not say the automation line and secret
  hygiene are untouched. Made explicit as FR-024/FR-025 so a reviewer can
  confirm this feature does not quietly widen v1.9.0's automation reach.

Three baselines in this spec are measurements taken on the applicant's own
machine and database, not estimates: 937 eligible jobs of which 627 unscored,
~67 s per AI assessment, and a 2 h 47 m capped scoring pass. Success criteria
are stated against those numbers so the release can be proved rather than
asserted.
