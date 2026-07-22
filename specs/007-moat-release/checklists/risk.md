# Risk Checklist: The Moat Release — Highest-Risk Requirement Areas

**Purpose**: Unit-test the requirements writing in the six highest-risk areas before implementation (never-click rule under multi-page, fill idempotency, credential masking, resume-sections lifecycle, sponsor-grade integrity, redesign correctness)
**Created**: 2026-07-21
**Feature**: [spec.md](../spec.md)

## Never-Click Rule Under Multi-Page Auto-Rescan (FR-003/FR-004)

- [x] CHK001 - Is the prohibition on the system clicking navigation/submit/login controls stated as an absolute requirement, not an implementation preference? [Clarity, Spec §FR-004]
- [x] CHK002 - Do the multi-page requirements state who performs page advancement in every scenario (user clicks Next; system only reacts)? [Completeness, Spec §FR-003, US1-AS3]
- [x] CHK003 - Are requirements defined for the case where the "new page" is actually a different site (redirect), so auto-fill rules stay conservative? [Edge Case, Spec §Edge Cases]
- [x] CHK004 - Is there a success criterion making "never clicks" objectively verifiable (test assertions + live walkthrough)? [Measurability, Spec §SC-006]
- [x] CHK005 - Do confirmation-gate requirements (sensitive questions, login credentials) explicitly survive into auto-rescanned pages? [Consistency, Spec §FR-003 "subject to all existing confirmation rules", US1-AS5]

## Fill Idempotency (FR-007)

- [x] CHK006 - Is "never overwrite a user-edited field" stated as an unconditional requirement covering repeated fill passes? [Clarity, Spec §FR-007]
- [x] CHK007 - Are requirements defined for repeated DOM mutation/SPA re-render scenarios (no duplicated values)? [Edge Case, Spec §Edge Cases]
- [x] CHK008 - Are file-input requirements consistent with text-input idempotency (already-populated inputs skipped)? [Consistency, Spec §Edge Cases "File input rejects programmatic attachment", research §5]
- [x] CHK009 - Is the outcome for unfillable/unmatched fields specified (reported, left untouched) rather than left undefined? [Completeness, Spec §FR-006]

## Credential Masking in the Fill Report (FR-005)

- [x] CHK010 - Does the requirement state the password value never enters the report (masked at record time), not merely "not displayed"? [Clarity, Spec §FR-005 + Clarifications]
- [x] CHK011 - Is the login email's appearance in the report explicitly specified (shown normally) so implementers don't over- or under-mask? [Completeness, Spec §Clarifications]
- [x] CHK012 - Are the fill-report requirements consistent with the existing vault write-only rule (secrets never redisplayed anywhere)? [Consistency, Spec §FR-005; 005 spec FR-017 lineage]
- [x] CHK013 - Is the lifetime/persistence of fill-report data specified (session-scoped, not persisted across app restarts)? [Completeness, Spec §Assumptions, data-model "In-memory only"]

## Resume-Sections Lifecycle (FR-016/FR-017/FR-020)

- [x] CHK014 - Is the re-upload-with-existing-edits flow fully specified (explicit keep-vs-re-extract prompt, never silent overwrite, never unprompted merge)? [Clarity, Spec §FR-016 + Clarifications]
- [x] CHK015 - Are manual-entry requirements defined with parity whether or not an AI tier exists? [Completeness, Spec §FR-017, US2-AS2]
- [x] CHK016 - Is partial/malformed extraction behavior specified (show what extracted, empty forms for the rest, no crash)? [Edge Case, Spec §Edge Cases]
- [x] CHK017 - Is PDF staleness defined with a concrete rule (regenerate or clearly invalidate when resume or tailoring changes), not just "keep fresh"? [Measurability, Spec §FR-020, US2-AS3]
- [x] CHK018 - Do the no-invention requirements trace through the whole chain (extraction → user review → tailoring → PDF)? [Consistency, Spec §FR-019]
- [x] CHK019 - Is the no-LLM PDF path specified (untailored render from sections alone, not an error)? [Coverage, Spec §US2-AS6, FR-018]

## Sponsor Grade Integrity (FR-011/FR-013/SC-003)

- [x] CHK020 - Is the minimum-evidence floor quantified (approvals+denials ≥ 10) rather than "sufficient data"? [Clarity, Spec §FR-011 + Clarifications]
- [x] CHK021 - Is the below-floor outcome explicitly UNKNOWN (never a fabricated grade), with a measurable success criterion? [Measurability, Spec §FR-011, SC-003, US3-AS5]
- [x] CHK022 - Are estimate-labeling requirements present for the lottery hint and grades (decision support, not fact)? [Completeness, Spec §FR-013, Assumptions]
- [x] CHK023 - Is grade evidence visibility specified (which signals appear on the detail page)? [Completeness, Spec §FR-015]
- [x] CHK024 - Are requirements defined for partial data (USCIS match but no DOL wage rows → grade from available signals, absent wage hint)? [Edge Case, Spec §Edge Cases]
- [x] CHK025 - Is cap-exempt flagged independently of the grade (a cap-exempt employer may still be UNKNOWN-graded)? [Consistency, research §9; Spec §FR-012 does not couple them]
- [x] CHK026 - Are malformed/unexpected data-file requirements defined (skip with warning, grade only from parsed data)? [Edge Case, Spec §Edge Cases]

## Redesign Correctness (FR-021/FR-023/FR-024/FR-028)

- [x] CHK027 - Is "no silent actions" quantified with a time bound and universal scope (every action, feedback within 1 second)? [Measurability, Spec §FR-023, SC-004]
- [x] CHK028 - Is the poll-clobber requirement stated as preservation of in-progress edits (open editors, focused inputs) under background refreshes, with a measurable session criterion? [Clarity, Spec §FR-024, SC-004]
- [x] CHK029 - Is theme precedence fully specified (explicit user choice persists and beats OS preference; default when unset)? [Completeness, Spec §FR-021, Edge Cases]
- [x] CHK030 - Are kanban interaction requirements accessible-by-design (drag AND button paths, same action, visible confirmation)? [Consistency, Spec §FR-025 + Clarifications]
- [x] CHK031 - Is the contrast requirement quantified with a testable standard rather than a subjective adjective? [Measurability, Spec §FR-028 — **fixed**: was "reasonable contrast", now WCAG 2.1 AA]
- [x] CHK032 - Are accessible-name requirements scoped to all interactive controls (including icon-only buttons) rather than examples only? [Coverage, Spec §FR-028, US4-AS8]
- [x] CHK033 - Is onboarding-checklist state derivation specified (reflects actual completion, stops appearing when done)? [Completeness, Spec §FR-027]

## Notes

- CHK031 initially FAILED: FR-028 said "reasonable contrast for their text
  sizes" — a subjective adjective. Fixed in spec (same session): now
  requires WCAG 2.1 AA contrast ratios (4.5:1 normal text, 3:1 large
  text/UI components). All other items passed on evaluation against the
  clarified spec.
- 33/33 items pass after the CHK031 fix. Traceability: 100% of items
  carry a spec/research reference or marker.
