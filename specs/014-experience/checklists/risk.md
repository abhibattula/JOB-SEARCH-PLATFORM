# Requirements Quality Checklist: Experience Release high-risk areas

**Purpose**: Unit-test the *requirements* (not the implementation) in the
highest-risk areas of feature 014 before tasks/implementation.
**Created**: 2026-07-24
**Feature**: [spec.md](../spec.md)

## Measured baseline & performance

- [x] CHK001 - Is "improve on the baseline" made concrete — a captured pre-redesign number per key page, not a vague "faster"? [Measurability, Spec §SC-001, research.md]
- [x] CHK002 - Is the CLS goal specified as a threshold (≤ 0.1) given the measured 0.27, not just "better"? [Clarity, Spec §SC-001, research.md]
- [x] CHK003 - Are the "key pages" for measurement enumerated so before/after is comparable? [Completeness, Spec §Assumptions]
- [x] CHK004 - Is "no layout jump / blank flash on load-triggered regions" specified as a requirement (the CLS root cause), not just implied? [Completeness, Spec §FR-006]

## Accessibility (holding a 100 baseline)

- [x] CHK005 - Is AA contrast required in BOTH themes as an absolute (zero failures), not a best-effort? [Measurability, Spec §FR-002, §SC-002]
- [x] CHK006 - Is full keyboard operability + visible focus + no keyboard traps specified for every interactive element, including the NEW command palette and skeleton/optimistic states? [Completeness, Spec §FR-003, §SC-003]
- [x] CHK007 - Is "the new interactive pieces must not regress the existing a11y score" captured (a hold-the-line requirement, not only greenfield)? [Consistency, Spec §FR-014, §SC-008]
- [x] CHK008 - Is the command palette's dialog semantics + Escape-to-dismiss + focus behavior specified? [Clarity, Spec §FR-009]

## Both-theme correctness

- [x] CHK009 - Is "every page renders correctly in light AND dark with zero mis-themed/unstyled elements" stated as a measurable outcome across ALL pages? [Measurability, Spec §SC-004]
- [x] CHK010 - Is theme-toggle re-render (no leftover mis-themed elements) covered as an edge case? [Edge Case, Spec §Edge Cases]
- [x] CHK011 - Are the new inline Analytics charts required to be correct/legible in both themes? [Completeness, Spec §FR-005]

## Interactivity correctness

- [x] CHK012 - Is optimistic status defined with its FAILURE path (revert + error) not just the happy path? [Completeness, Spec §FR-007]
- [x] CHK013 - Is the optimistic responsiveness quantified (reflect < ~100 ms, independent of round-trip)? [Measurability, Spec §SC-009]
- [x] CHK014 - Is reduced-motion honored stated for ALL motion (transitions + micro-interactions)? [Clarity, Spec §FR-008, §Edge Cases]
- [x] CHK015 - Is graceful degradation with JS unavailable/loading specified (core content server-rendered, enhancements layer on)? [Coverage, Spec §Edge Cases]

## Scope & constraint fidelity

- [x] CHK016 - Is the "no JS framework, no build step, no new paid dependency" constraint stated as a hard requirement (Analytics charts + palette must comply)? [Consistency, Spec §FR-015, §Assumptions]
- [x] CHK017 - Is "evolve the identity, don't replace it" bounded clearly enough to prevent scope creep into a new brand? [Clarity, Spec §Assumptions, Non-goals]
- [x] CHK018 - Is the command-palette scope bounded to navigation + global actions (not per-job) per the clarification? [Consistency, Spec §FR-009, §Clarifications]
- [x] CHK019 - Is the Analytics scope bounded to the named charts (funnel/sources/score-band/callback) rather than open-ended? [Clarity, Spec §FR-005, §Clarifications]

## No functional regressions

- [x] CHK020 - Is "all existing functionality continues to work unchanged" stated as a requirement, with the full test battery + frozen smoke as the gate? [Completeness, Spec §FR-014, §SC-008]
- [x] CHK021 - Is "engine core untouched / web-only change / Apply Assist behavior unchanged" preserved as an invariant? [Consistency, Spec §FR-014, §FR-015]

## Tech-debt / audit

- [x] CHK022 - Is "CI green on a clean checkout including Linux" a measurable acceptance criterion, not an aspiration? [Measurability, Spec §FR-011, §SC-005]
- [x] CHK023 - Is "zero deprecation warnings from our own code + materially reduced total" quantified against the current ~329? [Measurability, Spec §FR-012, §SC-006]
- [x] CHK024 - Is "human-readable dates on EVERY screen (tracker/analytics/digests, not just feed+detail)" specified as 100% coverage? [Completeness, Spec §FR-013, §SC-007]

## Cross-cutting

- [x] CHK025 - Does each functional requirement have at least one acceptance scenario or success criterion for traceability? [Traceability, Spec §Requirements, §Success Criteria]
- [x] CHK026 - Are the four user stories independently testable as written, matching their priorities (P1 look first)? [Completeness, Spec §US1–US4]
