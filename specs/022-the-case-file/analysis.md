# Cross-Artifact Analysis — 022 The Case File

**Date**: 2026-08-03 · **Artifacts**: spec.md · plan.md · tasks.md · checklists/design.md · contracts/ · data-model.md · research.md
**Constitution**: v1.2.0

## Findings

| ID | Category | Severity | Location | Summary | Resolution |
|----|----------|----------|----------|---------|------------|
| **O1** | Ordering | **CRITICAL** | tasks.md T033 | T033 measures jobs-visible-per-screen to prove SC-012, but sits in Phase 3 **after** T028–T031 have already rebuilt the feed. There is nothing left to compare against — the v2.1.0 baseline is gone by the time the measurement runs. | Capture the baseline in Phase 1, before any styling changes. New T004a. |
| **C1** | Coverage gap | **HIGH** | tasks.md Phase 2–6 | The design-system test's T1 assertion (zero undefined classes) fails from Phase 2 until Phase 6. The suite is therefore red for four phases, so a genuinely new breakage cannot be distinguished from the expected one. | Convert T1 into a **shrinking allowlist**: the test carries the known-remaining set and asserts it never grows. Red becomes a ratchet. T056 empties it. |
| **C2** | Coverage gap | **HIGH** | tasks.md T045, Phase 6 | Six audited classes are named in no task: `.profile` (×4), `.unclean-banner`, `.autofill-activity`, `.saved`, plus `.whats-new` / `.update-banner` are only implied. T056 catches them as a backstop, but a backstop is not a plan. | Name them explicitly in T045, T050 and a new T055a. |
| **T1** | Traceability | **HIGH** | tasks.md, all phases | 37 of 49 FRs and 9 of 12 SCs are referenced by **no** task ID. Coverage exists semantically but cannot be verified mechanically or at review time. | Annotate every task with the FR/SC identifiers it satisfies, and add the coverage table below. |
| **G1** | Coverage gap | **MEDIUM** | spec.md FR-007 | "Each bundled typeface MUST declare a system fallback" has no implementing task and no test — only a manual checklist item (CHK032). | Fold into T008 and add an assertion to T005. |
| **G2** | Coverage gap | **MEDIUM** | spec.md FR-041, FR-043, FR-044, FR-045 | The four preservation requirements rely on the existing suite being run at T070, which is correct but implicit. If T070 is ever narrowed, they silently lose coverage. | Name them in T070. |
| **I1** | Inconsistency | **MEDIUM** | plan.md §Phases vs tasks.md | plan.md numbers the phases 0–6; tasks.md numbers them 1–9. The same work has two different phase numbers across two artifacts that are read together. | Renumber plan.md to match tasks.md. |
| **A1** | Ambiguity | **LOW** | plan.md Technical Context | "565 → ~950 lines" presents an estimate as a target. Nothing should be measured against a guessed line count. | Reword to describe scope, not a number. |
| **A2** | Ambiguity | **LOW** | data-model.md §1 | Dark token values are given as a table but marked "indicative", while the binding constraint is the AA test. A reader could take them as fixed. | Already caveated in the artifact; no change — recorded so the next reader knows it was considered. |

**Constitution alignment**: no violations. All five principles PASS, as recorded
in plan.md and re-checked here against the generated artifacts.

**Duplication**: none found. FR-026/026a/026b are a deliberate parent-and-detail
grouping, not duplicates.

**Unmapped tasks**: none. Every task traces to at least one FR or to a named
verification gate.

## Metrics

| Metric | Value |
|---|---|
| Functional requirements | 49 |
| Success criteria | 12 |
| Tasks | 81 → **84** after remediation (T004a, T005a, T055a) |
| Requirement coverage (post-remediation) | **49/49 FRs and 12/12 SCs, verified mechanically** |
| Critical issues | 1 (O1) — resolved |
| High issues | 3 (C1, C2, T1) — resolved |
| Medium issues | 3 (G1, G2, I1) — resolved |
| Low issues | 2 (A1, A2) — 1 resolved, 1 recorded |

## Requirement → task coverage

| FR | Tasks | FR | Tasks |
|---|---|---|---|
| FR-001 | T006, T007 | FR-025 | T031 |
| FR-002 | T005, T060 | FR-026 | T027, T030 |
| FR-003 | T042, T046 | FR-026a | T027, T029, T033 |
| FR-004 | T007 | FR-026b | T029 |
| FR-005 | T005, T007 | FR-027 | T018, T019, T020 |
| FR-006 | T001, T008, T075 | FR-028 | T021 |
| FR-007 | T005, T008 | FR-029 | T021 |
| FR-008 | T008 | FR-030 | T022 |
| FR-009 | T005, T056 | FR-031 | T032 |
| FR-010 | T037 | FR-032 | T009 |
| FR-011 | T037 | FR-033 | T060, T062 |
| FR-012 | T039 | FR-034 | T059, T061 |
| FR-013 | T044, T045 | FR-035 | T059, T063 |
| FR-014 | T010, T048 | FR-036 | T058, T063 |
| FR-015 | T013, T014 | FR-037 | T064 |
| FR-016 | T012, T013 | FR-038 | T068 |
| FR-017 | T017 | FR-039 | T065, T069 |
| FR-018 | T014, T015, T016, T062 | FR-040 | T065, T067 |
| FR-019 | T012, T013 | FR-041 | T070 |
| FR-020 | T023, T024 | FR-042 | T055 |
| FR-021 | T025 | FR-043 | T070 |
| FR-022 | T023, T026 | FR-044 | T070 |
| FR-023 | T038, T040 | FR-045 | T070 |
| FR-024 | T036 | FR-046 | T063, T073 |
| | | FR-047 | T057 |

| SC | Tasks |
|---|---|
| SC-001 | T056 |
| SC-002 | T005, T060 |
| SC-003 | T021, CHK015 |
| SC-004 | T023 |
| SC-005 | T012, T017 |
| SC-006 | T058, T061 |
| SC-007 | T005 |
| SC-008 | T065, T069 |
| SC-009 | T009 |
| SC-010 | T070–T074 |
| SC-011 | T035, T081 |
| SC-012 | T004a, T033 |

## Next actions

All CRITICAL, HIGH and MEDIUM findings are remediated in the artifacts before
implementation begins, as the applicant directed. Implementation may proceed
from Phase 1.
