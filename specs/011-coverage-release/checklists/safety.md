# Checklist: Safety & Correctness Requirements Quality (011)

**Purpose**: Unit-test the requirements writing in the six highest-risk
areas of The Coverage Release before implementation hardens them.
**Created**: 2026-07-24
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [fill-widgets contract](../contracts/fill-widgets.md)

## 1. The never-click denylist (now that field clicks are allowed)

- [x] CHK001 - Is the set of never-click control classes enumerated explicitly (submit, apply, next, continue, save, finish, login, register, create-account, pay) rather than left as "etc."? [Completeness, Spec §FR-002]
- [x] CHK002 - Is the denylist matching SCOPE specified unambiguously (clicked element's own text/type/role + descendants, never ancestors)? [Clarity, Spec §Clarifications, §FR-002]
- [x] CHK003 - Is the "submit styled as a dropdown option" case explicitly addressed as an edge case the denylist must still catch? [Edge Case, Spec §Edge-Cases]
- [x] CHK004 - Is a disabled Next/Submit control required to be never-clicked regardless of its disabled state? [Edge Case, Spec §Edge-Cases]
- [x] CHK005 - Is the requirement stated to hold in BOTH fill paths (companion + assistant window), not just one? [Consistency, Spec §FR-002]
- [x] CHK006 - Is the guarantee made measurable (zero submit-class clicks across suite + live, no exceptions)? [Measurability, Spec §SC-003]
- [x] CHK007 - Is it specified that the denylist is the single authority for "clickable-ness" (one contract, both languages), rather than each backend judging independently? [Consistency, contract §Executor]

## 2. Custom-dropdown / typeahead fill correctness

- [x] CHK008 - Is "never a wrong/guessed option" stated as an absolute (no match → leave untouched, never a non-matching pick)? [Clarity, Spec §FR-004]
- [x] CHK009 - Is post-set verification required (the widget's displayed value must have actually changed before reporting filled)? [Completeness, Spec §FR-004]
- [x] CHK010 - Is the abandon budget quantified (~1.5s) for both dropdown-options and typeahead-suggestions? [Clarity, Spec §FR-006, §SC-004]
- [x] CHK011 - Is the "never leave a popup stuck open" cleanup requirement stated for the timeout/failure path? [Completeness, Spec §FR-006]
- [x] CHK012 - Is the option-matching rule consistent with the existing native-select matcher (so behavior doesn't diverge between native and custom dropdowns)? [Consistency, Spec §FR-004]
- [x] CHK013 - Is the non-empty-is-sacred rule required for custom widgets (a user-set combo is not overwritten)? [Coverage, Spec §US1-AS3]
- [x] CHK014 - Is the focused-widget skip preserved (a widget the user is engaging with is not touched)? [Edge Case, Spec §Edge-Cases]
- [x] CHK015 - Is the combobox+typeahead hybrid (options only appear after typing) assigned an unambiguous handling rule? [Edge Case, Spec §Edge-Cases]
- [x] CHK016 - Are multi-select custom widgets explicitly scoped out (reported manual, not half-filled)? [Coverage, Spec §Edge-Cases]

## 3. Backend parity

- [x] CHK017 - Is it required that EVERY new fill ability (dropdown, typeahead, new ATS) behaves identically in the companion and the assistant-window fallback? [Completeness, Spec §FR-011]
- [x] CHK018 - Is parity made measurable (same result on the same test pages in both backends)? [Measurability, Spec §SC-005]
- [x] CHK019 - Is the fill DECISION required to be single-sourced (both backends consume the same classifier), preventing drift? [Consistency, plan §Key-Decisions-3]
- [x] CHK020 - Is the denylist required to be shared/identical across the two languages, with drift explicitly prevented? [Consistency, contract §Invariants-1]

## 4. Workday multi-step behavior

- [x] CHK021 - Is "the app never advances the wizard" stated as an absolute (the USER clicks Workday's Next/Continue)? [Clarity, Spec §FR-008, §US2-AS3]
- [x] CHK022 - Is per-page fill-on-appearance specified (each new page fills as it renders after the user advances)? [Completeness, Spec §FR-008]
- [x] CHK023 - Is the Workday field-recognition basis specified as stable per-field identifiers, with graceful degradation when a tenant deviates? [Clarity, Spec §Assumptions, §FR-007]
- [x] CHK024 - Are Workday location/school typeaheads covered by the same typeahead requirement, not left unspecified? [Coverage, Spec §FR-007]

## 5. Sensitive-question safety (preserved through the new widgets)

- [x] CHK025 - Is it required that work-auth/visa/EEO questions stay confirm-gated and never AI-drafted EVEN when presented as a custom dropdown? [Completeness, Spec §FR-013]
- [x] CHK026 - Is this stated as invariant across both the new combobox path and the existing native paths (no bypass introduced by the widget change)? [Consistency, Spec §FR-013]

## 6. No regressions to existing fills

- [x] CHK027 - Is it required that native inputs and native `<select>` keep their exact current behavior (custom-widget work must not alter the native path)? [Consistency, Spec §FR-012]
- [x] CHK028 - Are all prior capabilities enumerated as must-remain (native fields/selects, file upload, AI drafts, pause-for-review, saved-login, activity feed, per-job reports)? [Completeness, Spec §FR-012]
- [x] CHK029 - Is a zero-regression criterion stated (existing checks continue to pass)? [Measurability, Spec §SC-006]
- [x] CHK030 - Is the $0 / offline constraint reaffirmed for this release (no new paid service/store/signing)? [Completeness, Spec §SC-007]

## 7. Governance

- [x] CHK031 - Is the requirement to record the field-value-click boundary in the governing principles stated (documented, not silent)? [Traceability, Spec §FR-015]

## Notes

- All 31 items PASS against the current spec/plan/contract — the two clarify
  answers (denylist scope, ~1.5s budget) closed what would have been
  CHK002/CHK010 gaps.
- Re-run mentally during /speckit-analyze; any item that stops passing after
  tasks.md is an analyze finding to fix before implementation.
