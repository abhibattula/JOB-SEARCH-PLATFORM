# Requirements Quality Checklist: Refinements Release high-risk areas

**Purpose**: Unit-test the *requirements* (not the implementation) in the eight
highest-risk areas of feature 013 before tasks/implementation.
**Created**: 2026-07-24
**Feature**: [spec.md](../spec.md)

## Browser routing (the blocking bug)

- [x] CHK001 - Is the browser preference order stated as a clear precedence (connected companion first, else OS default browser, else another automatable browser), with no ambiguity about which wins? [Clarity, Spec §FR-001, §FR-002]
- [x] CHK002 - Is the "Edge is genuinely the default" case explicitly in scope (use Edge then), so the fix reads as "use the default" not "always Chrome"? [Consistency, Spec §Edge Cases]
- [x] CHK003 - Is the un-automatable-default case (e.g., Firefox as default) resolved by a stated fallback rather than left undefined? [Edge Case, Spec §Edge Cases]
- [x] CHK004 - Is the stale-companion-heartbeat case specified (still prefer the companion, don't bounce to a different browser)? [Completeness, Spec §Edge Cases]
- [x] CHK005 - Is the "no silent wrong browser" guarantee measurable (a stated 0%/100% outcome), not a soft goal? [Measurability, Spec §SC-001, §SC-002]
- [x] CHK006 - Is "the active backend and browser are visible to the user" specified as a requirement, so a mismatch is surfaced rather than silent? [Completeness, Spec §FR-004]
- [x] CHK007 - Is "Open posting / external links use the OS default handler" specified distinctly from the fill path? [Clarity, Spec §FR-003]
- [x] CHK008 - Is the missing/undetectable-default case handled without crashing (sensible fixed order)? [Edge Case, Spec §Edge Cases]

## GPU / CPU AI

- [x] CHK009 - Is graceful CPU fallback stated as absolute — no error surfaced, results unchanged — for both "no GPU" and "GPU init fails"? [Clarity, Spec §FR-005, §Edge Cases]
- [x] CHK010 - Is "no installer bloat / the CPU build is unchanged / GPU is opt-in via one documented step" stated as a hard requirement? [Completeness, Spec §FR-008]
- [x] CHK011 - Is the CPU thread-tuning default specified (use all cores unless overridden) rather than left implicit? [Clarity, Spec §FR-006]
- [x] CHK012 - Is the no-GPU-machine outcome specified as "behavior and results identical to v1.2.0" (no regression), and is that measurable? [Measurability, Spec §SC-004, §FR-013]
- [x] CHK013 - Are the tuning controls (GPU offload amount, thread count) documented as overridable, with defined defaults? [Completeness, Spec §Key Entities]

## Resume-extraction speed

- [x] CHK014 - Is "faster than v1.2.0" quantified with a measurable target rather than a vague "faster"? [Measurability, Spec §SC-003]
- [x] CHK015 - Is "skip extraction when the resume is unchanged" specified, including what counts as unchanged? [Clarity, Spec §FR-007]
- [x] CHK016 - Is it stated that the speedup MUST NOT regress extraction correctness for a genuinely new/changed resume? [Consistency, Spec §FR-007, §SC-004]

## Human dates

- [x] CHK017 - Is the exact date format unambiguous ("24 July 2026" — day, title-case full month, year), leaving no room for uppercase/abbreviated interpretations? [Clarity, Spec §FR-009, §Clarifications]
- [x] CHK018 - Is the scope bounded to the feed and job detail only, with other screens explicitly out of scope this release? [Consistency, Spec §FR-009, §Clarifications]
- [x] CHK019 - Is the approximate-date marker (source-less dates shown as approximate) required to be preserved under the new format? [Completeness, Spec §FR-009, §Edge Cases]
- [x] CHK020 - Is the "must not crash on absent/already-formatted date values" behavior specified? [Edge Case, Spec §Edge Cases]

## Sort affordances

- [x] CHK021 - Is "a persistent, clickable indicator on BOTH sortable columns" specified (not only the active one)? [Completeness, Spec §FR-010]
- [x] CHK022 - Is "the active column's indicator reflects the current sort" specified? [Clarity, Spec §FR-010]
- [x] CHK023 - Is it explicit that this is a visibility/affordance change over the existing sort, not a new sort backend or an asc/desc toggle? [Consistency, Spec §Assumptions, Non-goals]

## Back button

- [x] CHK024 - Is the Back behavior specified for both cases — return to the prior view when history exists, and land on the feed when opened directly (no dead-end)? [Completeness, Spec §FR-011, §SC-007]
- [x] CHK025 - Is "preserve the feed's filters/scroll when returning" specified as the desired outcome? [Clarity, Spec §FR-011]

## App icon

- [x] CHK026 - Are all four surfaces enumerated (app window, taskbar, installer + its shortcuts, browser favicon) as required? [Completeness, Spec §FR-012, §SC-008]
- [x] CHK027 - Is "one source mark reused across surfaces" specified rather than independent per-surface art? [Consistency, Spec §Key Entities, §Assumptions]
- [x] CHK028 - Is the icon scope bounded to an app mark (not a full brand redesign)? [Clarity, Spec §Assumptions, Non-goals]

## Constitution invariants preserved

- [x] CHK029 - Is "$0 / GPU is optional / no paid dependency" restated as a requirement for this release? [Assumption, Spec §FR-013]
- [x] CHK030 - Is "offline works without a GPU (CPU path always available)" stated as an invariant, not an aspiration? [Completeness, Spec §FR-013, §FR-005]
- [x] CHK031 - Is "the engine core does not depend on the web layer" preserved by the requirements (browser/AI logic stays engine-side)? [Consistency, Spec §FR-013]
- [x] CHK032 - Is "Apply Assist still never auto-submits and fills only in the user's own/default browser" preserved as an invariant? [Consistency, Spec §FR-013, §FR-001]

## Cross-cutting

- [x] CHK033 - Does each functional requirement have at least one acceptance scenario or success criterion for traceability? [Traceability, Spec §Requirements, §Success Criteria]
- [x] CHK034 - Are all four user stories independently testable as written, matching their stated priorities (P1 browser fix first)? [Completeness, Spec §US1–US4]
