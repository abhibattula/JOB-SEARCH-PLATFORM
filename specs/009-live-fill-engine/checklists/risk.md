# Risk Checklist: The Live Fill Engine (009)

**Purpose**: Validate that requirements fully specify the highest-risk
areas: the never-click invariant on the new fill path, user-data safety
during live filling, worker isolation, honest progress/consent semantics,
offline-tier viability, and preservation of prior guarantees.
**Created**: 2026-07-23
**Feature**: [spec.md](../spec.md)

## Never-Click & Automation Safety

- [x] CHK001 - Is "never clicks anything, ever" restated as a requirement of the NEW fill path (not inherited by implication)? [Consistency, Spec §FR-006, §US1-AS6, §SC-003]
- [x] CHK002 - Are click-requiring widgets (custom dropdowns) explicitly declared unfillable and honestly reported? [Edge Case, Spec §Edge Cases, §Assumptions]
- [x] CHK003 - Is the practice run required to go through the NORMAL engine (no special fill path that could mask defects)? [Completeness, Spec §FR-009]

## User-Data Safety While Filling Live

- [x] CHK004 - Is the never-overwrite-non-empty rule preserved for a continuously-scanning engine? [Consistency, Spec §FR-006]
- [x] CHK005 - Is the actively-typing case specified (focused-field guard + just-before-write re-check)? [Edge Case, Spec §FR-006, §Edge Cases]
- [x] CHK006 - Is re-render/re-fill behavior specified without duplicate report rows? [Edge Case, Spec §Edge Cases, §FR-006]
- [x] CHK007 - Are credential fills still masked at record time on the new path? [Consistency, Spec §FR-006]

## Worker Isolation & Responsiveness

- [x] CHK008 - Is "user actions return immediately / no browser work on request threads" a stated requirement (not an implementation nicety)? [Completeness, Spec §FR-001]
- [x] CHK009 - Are interruption (window closed) and resume specified for the new engine? [Coverage, Spec §FR-008, §Edge Cases]
- [x] CHK010 - Is the steady watch cadence (no idle backoff) recorded as a clarified decision with its cost assumption? [Clarity, Spec §Clarifications, §Assumptions]
- [x] CHK011 - Is the frame-count bound specified with defined behavior beyond the bound? [Edge Case, Spec §FR-003, §Edge Cases]

## Honest Progress & Guidance

- [x] CHK012 - Is the no-terminal-"couldn't read" requirement explicit (watching continues while a job is current)? [Completeness, Spec §FR-003]
- [x] CHK013 - Are live activity fields (seen/filled/phase/guidance) enumerated? [Clarity, Spec §FR-007]
- [x] CHK014 - Do launch/navigation failures keep distinct visible reasons? [Consistency, Spec §FR-007, §FR-008]

## Import Consent & Privacy

- [x] CHK015 - Is "nothing changes without applying the proposal" stated absolutely? [Completeness, Spec §FR-014]
- [x] CHK016 - Are the per-row defaults fully enumerated (blank/conflict/list/edited-sections)? [Clarity, Spec §FR-014]
- [x] CHK017 - Is the zero-difference case specified (compact confirmation)? [Edge Case, Spec §Clarifications, §FR-014]
- [x] CHK018 - Is the visa/work-auth exclusion restated for the import path? [Consistency, Spec §FR-015]
- [x] CHK019 - Is proposal lifetime (session-scoped, restart drops it, stale-after-apply) specified? [Edge Case, Spec §Edge Cases, §Assumptions]
- [x] CHK020 - Are extraction failures required to be visible with retry (no silent no-op)? [Completeness, Spec §FR-012, §US3-AS5]

## Offline Tier Viability

- [x] CHK021 - Is the local context bound a requirement ("no single request may exceed context capacity") rather than an implementation hope? [Measurability, Spec §FR-013]
- [x] CHK022 - Is partial-failure behavior (one bad part) specified? [Edge Case, Spec §FR-013, §US3-AS2]
- [x] CHK023 - Is cloud fall-through on local failure specified for ALL AI features? [Coverage, Spec §FR-017, §US4-AS2]
- [x] CHK024 - Is the missing/corrupt local model case covered? [Edge Case, Spec §Edge Cases]

## Preservation of Prior Guarantees

- [x] CHK025 - Are all preserved 005-008 behaviors enumerated somewhere binding (queue semantics, pending-answer flow, tailored-PDF preference, masking)? [Coverage, Spec §FR-006, §FR-008, §Assumptions]
- [x] CHK026 - Is the real-browser regression suite a REQUIREMENT (runs before any release), given fakes-only testing shipped a broken engine twice? [Measurability, Spec §FR-010, §SC-001..003]
- [x] CHK027 - Is the practice page's coverage scope stated (fidelity aid, not a per-site guarantee)? [Assumption, Spec §Assumptions]

## Notes

- 27/27 pass on the clarified spec (2026-07-23). No spec edits required
  by this checklist; CHK010/CHK017 point at the Clarifications session
  entries integrated into FR-003/FR-014.
