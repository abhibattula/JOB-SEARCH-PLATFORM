# Checklist: Truthfulness, safety and containment

**Purpose**: The quality gate specific to this feature. Apply Assist writes on
real job applications; a wrong or invented answer costs the applicant an
opportunity and cannot be recalled after submission. Every item is checked
against `spec.md` and the contracts, not against code.
**Created**: 2026-07-28

## Never states something untrue

- [x] No answer is produced for a question the applicant's own material cannot
      ground (FR-006)
- [x] Company and role text cannot leak into a factual answer (FR-007)
- [x] Questions about the applicant's history are never generated at all
      (FR-008)
- [x] A refusal is visible to the applicant rather than silently skipped
      (FR-034, `askable`)
- [x] Self-identification is answered only from values the applicant entered
      themselves (FR-026)
- [x] Self-identification values are never sent to a model in any prompt
      (contracts/profile-schema.md §3)
- [x] An answer captured from the applicant is stored verbatim, not rewritten
      (contracts/bridge-protocol-additions.md §3)

## Never commits the applicant

- [x] No submit, login, registration, payment or wizard-advance click (FR-043)
- [x] No binding commitment agreed on the applicant's behalf (FR-044)
- [x] Binding acknowledgements are excluded from every automatic path,
      including the answer library (contracts/answer-resolution.md §5)
- [x] Consequence, not topic, distinguishes binding from routine (FR-027)

## Never writes the wrong shape

- [x] A yes/no fact can only fill a yes/no choice control (FR-012)
- [x] Prose can never reach a choice control, including one whose options are
      unreadable at scan time (FR-012, FR-013)
- [x] An unmatched value leaves the field untouched rather than approximating
      (FR-028)
- [x] Matching strictness for authorization questions is not loosened (FR-025)
- [x] The applicant's existing input is never overwritten
      (contracts/answer-resolution.md §6)

## Stays bounded and stoppable

- [x] Completing one draft cannot cause others to regenerate (FR-001)
- [x] Generation is capped per question and per job (FR-002, FR-003)
- [x] A restart does not re-draft an answered form (FR-004)
- [x] One stored draft per question (FR-005)
- [x] Stop is reachable at any form size (FR-009)
- [x] The status view does not move under the applicant (FR-010)

## Attaches only what it verified

- [x] File retrieval cannot resolve to the job board's origin (FR-029)
- [x] Content is verified before attachment; failure attaches nothing (FR-030)
- [x] An application-generated rendering never replaces the applicant's own
      résumé on an untailored job (FR-032)
- [x] The applicant can see which file was attached (FR-032)

## Recoverable

- [x] Fabricated answers already saved can be purged (FR-011)
- [x] A purge cannot destroy answers the applicant wrote (FR-046)

## Degrades safely

- [x] Protocol changes are additive; an older companion cannot mis-fill
      (FR-042)
- [x] The assistant-window fallback surfaces the same answers, refusals and
      capture inputs in the application view (FR-047)
- [x] A question appearing in two documents of one application is answered once
      and generated once (FR-048)
- [x] A shortened answer feed is disclosed, and the application view stays
      complete (FR-049)

## Notes

- The last three items were **gaps found by this checklist**: the spec had no
  stated behaviour for the no-companion fallback, for the same question
  appearing in a page and an embedded frame, or for a truncated answer feed.
  All three were resolved by adding FR-047, FR-048 and FR-049 before any code
  was written.
- Every checked item traces to a requirement or a contract clause, not to an
  implementation detail.
