# Requirements Quality Checklist: Discovery Copilot high-risk areas

**Purpose**: Unit-test the *requirements* (not the implementation) in the seven
highest-risk areas of feature 012 before tasks/implementation.
**Created**: 2026-07-24
**Feature**: [spec.md](../spec.md)

## Read-Only Guarantee (page is never touched)

- [x] CHK001 - Is "read-only" defined precisely enough to be testable — does the spec enumerate the forbidden actions (click, type/input, submit, DOM mutation) rather than a vague "does not interact"? [Clarity, Spec §FR-011]
- [x] CHK002 - Is the badge's own DOM (its shadow host) explicitly excluded from the read-only prohibition, so "renders its own badge" and "mutates nothing" don't read as a conflict? [Consistency, Spec §FR-011]
- [x] CHK003 - Is there a measurable acceptance criterion that the number of page actions taken by discovery is exactly zero? [Measurability, Spec §SC-005]
- [x] CHK004 - Are the sensitive-question boundaries (never read/infer/fill visa/EEO) stated as a discovery-scope requirement, not left implied by Apply Assist's rules? [Completeness, Spec §FR-017]

## Badge Visibility Rules

- [x] CHK005 - Are the preconditions for the badge appearing stated as a conjunction (app running AND connected AND a score returned), with no ambiguity about partial states? [Clarity, Spec §FR-006]
- [x] CHK006 - Is the disconnected/app-closed behavior specified as "no badge at all" (zero footprint), consistent with the clarification, and not contradicted elsewhere? [Consistency, Spec §Clarifications, §FR-006]
- [x] CHK007 - Are the pages that MUST NOT show a badge enumerated (non-job pages, search-result lists, pages with JobPosting-like data that aren't single postings)? [Coverage, Spec §Edge Cases, §FR-001]
- [x] CHK008 - Is the in-place (SPA) navigation refresh requirement specified so the badge reflects the posting currently on screen, and is "stale data" defined as a failure? [Completeness, Spec §FR-014, §Edge Cases]
- [x] CHK009 - Is the timing expectation for the badge appearing quantified (a bound, e.g. within N seconds of page settling) rather than "quickly"? [Measurability, Spec §SC-001]
- [x] CHK010 - Are dismiss and collapse specified as distinct states with defined outcomes (dismiss = gone for this posting; collapse = minimal re-expandable indicator)? [Clarity, Spec §FR-010, §US3]

## Detection Correctness

- [x] CHK011 - Is the primary detection signal (published structured job metadata) distinguished from the LinkedIn/Indeed fallbacks, with the precedence order specified? [Clarity, Spec §FR-001]
- [x] CHK012 - Are the fields to extract (title, company, description, URL) each named as required outputs of detection, and is behavior defined when any one is absent? [Completeness, Spec §FR-002, §Edge Cases]
- [x] CHK013 - Is the confidential/absent-company case specified (score still renders from title+description; sponsorship reads "unknown")? [Edge Case, Spec §Edge Cases]
- [x] CHK014 - Is the "multiple job-related structured blocks on one page" case resolved by a stated rule (first genuine single posting; never more than one badge)? [Ambiguity, Spec §Edge Cases]
- [x] CHK015 - Is a measurable correctness target for title/company extraction defined across the covered site families? [Measurability, Spec §SC-002]
- [x] CHK016 - Is the scope boundary between "single-posting page" (in) and "search-result list" (out) defined clearly enough to be decidable? [Clarity, Spec §Assumptions, §Edge Cases]

## Sponsorship Honesty

- [x] CHK017 - Is the two-tier lookup order specified (already-graded fast path, then on-demand fuzzy match) without ambiguity about when each applies? [Clarity, Spec §FR-004, §Clarifications]
- [x] CHK018 - Is "insufficient evidence → unknown, never a fabricated grade" stated as an absolute (100%) requirement, not a best-effort? [Measurability, Spec §SC-003, §FR-004]
- [x] CHK019 - Are the distinct sponsorship indicator outputs (letter grade / cap-exempt likelihood / unknown) enumerated so the badge's states are complete? [Completeness, Spec §FR-004]
- [x] CHK020 - Is the cap-exempt signal specified as a likelihood/estimate rather than a definitive claim, consistent with the rest of the app's sponsorship language? [Consistency, Spec §FR-004]

## Save Correctness

- [x] CHK021 - Are the persisted fields for a saved posting explicitly listed (title, company, URL, description) and is the URL identified as the identity/dedup key? [Completeness, Spec §FR-008, §Key Entities]
- [x] CHK022 - Is the "mark as saved" outcome specified (appears in the Saved/bookmarked view), distinct from merely appearing in the feed? [Clarity, Spec §FR-008, §Clarifications]
- [x] CHK023 - Is "no duplicates on repeat save" stated as a hard requirement, and is the already-saved state defined for both first render and repeat save? [Completeness, Spec §FR-009, §SC-004]
- [x] CHK024 - Is the saved job's equivalence to other tracked jobs specified (openable, markable applied, etc.) so "manual source" doesn't imply a lesser record? [Consistency, Spec §FR-008, §US2]
- [x] CHK025 - Is a measurable success target for save correctness defined (correct fields in 100% of successful saves; zero duplicates)? [Measurability, Spec §SC-004]

## Independence & Privacy

- [x] CHK026 - Is discovery's independence from the Apply Assist fill session stated bidirectionally (discovery doesn't alter/pause/depend on a fill session; a fill session isn't affected by discovery)? [Completeness, Spec §FR-013]
- [x] CHK027 - Is "no regression to existing fill behavior when the badge is present" captured as a measurable outcome? [Measurability, Spec §SC-006]
- [x] CHK028 - Is the requirement that page metadata never leaves the machine stated absolutely, and is "sent only to the local companion channel" specified? [Clarity, Spec §FR-012, §SC-007]
- [x] CHK029 - Is the "no new trust boundary / no new stored secret — reuse existing pairing" requirement documented rather than assumed? [Completeness, Spec §FR-015]
- [x] CHK030 - Is a bound on the extracted metadata size specified so a hostile/huge page cannot overwhelm the local channel? [Edge Case, Spec §Edge Cases]

## Honest Degraded States

- [x] CHK031 - Is the no-resume/no-profile state specified as an honest "add your resume" prompt rather than a zero or misleading score? [Completeness, Spec §FR-016, §Edge Cases]
- [x] CHK032 - Are the distinct "no score available" causes (app closed, disconnected, no resume) each mapped to a defined badge state without overlap or contradiction? [Consistency, Spec §FR-006, §FR-016]

## Cross-Cutting Requirement Quality

- [x] CHK033 - Does each functional requirement have at least one corresponding acceptance scenario or success criterion for traceability? [Traceability, Spec §Requirements, §Success Criteria]
- [x] CHK034 - Are the $0 / offline-scoring constraints restated as requirements for this feature (no new paid dependency, no cloud key), not only inherited from the constitution? [Assumption, Spec §Assumptions]
- [x] CHK035 - Are all three user stories independently testable as written (each delivers value without the others), matching their stated priorities? [Completeness, Spec §US1–US3]
