# Safety & Risk Checklist: Apply Assist

**Purpose**: Validate that the requirements governing this feature's highest-risk
areas (auto-submit/auto-login safety, legally-sensitive answer handling,
credential secrecy, native-dependency packaging, and graceful fallback) are
complete, unambiguous, and consistent — before implementation begins.
**Created**: 2026-07-20
**Feature**: [spec.md](../spec.md), [plan.md](../plan.md), [data-model.md](../data-model.md)

## Never-Auto-Submit / Never-Auto-Login Safety Rule

- [x] CHK001 Is "final submit/apply button" distinguished, in the requirements, from intermediate "Next"/"Continue" controls within a multi-step application wizard — i.e., is it clear whether the app may click page-to-page navigation controls while still never clicking the true final submission? [Gap, Spec §FR-008] — **Resolved**: FR-008 now explicitly scopes the prohibition to submitting/authenticating actions and explicitly permits non-submitting page-to-page navigation.
- [ ] CHK002 Is there a requirement for how the system behaves when a page's submission is triggered by something other than a distinct clickable button (e.g., a form's own JS-driven auto-submit on the last required field being filled)? [Edge Case, Gap] — still open; carry into `tasks.md`/implementation as a field-fill-order safety consideration (e.g., avoid filling a page's genuinely last required field automatically on forms with known auto-submit-on-completion behavior).
- [x] CHK003 Is "login button" defined precisely enough to cover single-sign-on/social-login flows (e.g., "Sign in with Google") as well as a standard username/password submit, or could those read as out of scope for FR-016's prohibition? [Clarity, Spec §FR-016] — **Resolved**: FR-008 now names SSO/social-login buttons explicitly.
- [ ] CHK004 Is there a verifiable, after-the-fact way (per the requirements, not the implementation) to confirm that no automated submit/login click occurred during a session, supporting SC-003's "0%, no exceptions" claim? [Measurability, Spec §SC-003] — still open; a genuine residual gap. Recommend an implementation-level action log (distinct from `application_answers`) as a `tasks.md` item, not a spec change, since "how it's verified" is an implementation/testing concern once the requirement itself (FR-008) is unambiguous.

## Confirm-Before-Use Gate for Legally-Sensitive Answers

- [x] CHK005 Is the set of question categories requiring mandatory user confirmation exhaustively enumerated, or could other legally-significant question types (e.g., disability status, veteran status, demographic self-identification — common on real applications) fall outside "work_authorization"/"sponsorship_requirement" and risk being treated as ordinary free text? [Coverage, Gap, Spec §FR-012] — **Resolved**: FR-012 broadened to an open/extensible category (`eeo_disclosure` added to the taxonomy in research.md).
- [ ] CHK006 Is "clearly-equivalent previously-confirmed answer" (distinguishing reusable near-identical questions from genuinely different ones) defined with objective criteria, rather than left to implementation judgment? [Clarity, Spec §FR-013] — accepted as an implementation-level calibration (fuzzy-match threshold in `answer_bank.lookup()`, research.md §7), not a spec gap; revisit if `/speckit.analyze` disagrees.
- [x] CHK007 Does the spec define what happens if the user neither confirms nor edits a drafted answer but instead dismisses/ignores the prompt — does the queue stay paused indefinitely, time out, or skip the field? [Edge Case, Gap] — **Resolved**: new edge case — stays paused, never times out into an unreviewed fill.
- [x] CHK008 Are the requirements for the per-application answer record (FR-021) explicit that a record is only ever created from an answer that already passed the confirmation gate — i.e., no path exists for an unconfirmed draft to be recorded as "used"? [Consistency, Spec §FR-021, §FR-011] — reviewed, already consistent as written (FR-021 records "confirmed answer," FR-011 gates what counts as confirmed).

## Credential Secret Handling

- [x] CHK009 Does "never displayed again" (FR-017) explicitly extend to diagnostic output, error messages, and log files, or only to the normal settings-page UI? [Completeness, Spec §FR-017] — **Resolved**: FR-017 now names logs/diagnostic output explicitly.
- [x] CHK010 Are requirements defined for the system's behavior when the OS keychain itself is unavailable, locked, or denies access (as distinct from the credential simply not existing)? [Gap, Exception Flow] — **Resolved**: new edge case added.
- [x] CHK011 Is it specified, anywhere in the requirements, that a credential secret must never be written to the application's own log file even at a diagnostic/debug level? [Gap, Security] — **Resolved**: covered by the same FR-017 edit as CHK009.
- [x] CHK012 Are the delete-credential requirements (FR-018) explicit that deletion must remove the secret from wherever it's stored, not just remove it from any user-facing list? [Clarity, Spec §FR-018, data-model.md invariant] — reviewed, already explicit via the data-model.md delete invariant (keychain + settings row, both required).

## Native-Dependency Packaging Risk (llama-cpp-python, Playwright driver)

- [x] CHK013 Does the plan define a concrete, repeatable acceptance gate — for both new native dependencies, not just one — analogous to the existing smoke-test gate that caught the v0.4.0 tls_client incident? [Traceability, Plan §Constraints, Research §3, §4] — reviewed, already covered (research.md §3 and §4 each define their own smoke-test extension).
- [x] CHK014 Is "native lib successfully bundled" stated as a measurable, automatable pass/fail condition (build-time assertion + a real executed inference/launch) rather than an informal expectation? [Measurability, Research §3, §4] — reviewed, already covered.
- [x] CHK015 Is a fallback/contingency documented for the case where the pinned llama-cpp-python CPU-wheel index lacks a build for the exact pinned version at release time? [Gap, Research §3] — reviewed, already covered (compiler-toolchain fallback documented).
- [x] CHK016 Are the consequences specified if the one-time model or Chromium download is interrupted partway (partial/corrupt file), for both the CI build step and the end-user first-use download? [Edge Case, Gap] — **Resolved**: edge case broadened to cover interrupted downloads, not just insufficient disk space.

## Graceful Fallback on Sites the Classifier Can't Read

- [x] CHK017 Is "few/no confidently-classified fields" (the trigger for graceful fallback) quantified with an explicit threshold, or left entirely to implementation judgment? [Clarity, Spec §FR-009] — **Resolved**: FR-009 now defines the trigger as failing to recognize the core identity fields (name, email, resume upload).
- [x] CHK018 Are requirements defined for how the user is informed that a given job fell back to manual mode, so it's distinguishable from a successful autofill rather than silently identical? [Gap, Coverage] — **Resolved**: FR-009 now requires this visibly.
- [x] CHK019 Is the graceful-fallback behavior described consistently between User Story 2's acceptance scenario 3 and the Edge Cases section, or could they be read as two different behaviors (e.g., one implying a warning is shown, the other not mentioning one)? [Consistency, Spec §User Story 2, §Edge Cases] — **Resolved**: both now use the same threshold and visibility language.
- [x] CHK020 Is it explicit in the requirements that graceful fallback applies uniformly to every domain the classifier struggles with, and that no site-specific exception/allowlist is created by this phase (per Assumptions)? [Consistency, Spec §Assumptions] — reviewed, already explicit in Assumptions.

## Notes

- Check items off as completed: `[x]`
- These items test the *requirements'* completeness/clarity/consistency, not
  the eventual implementation. 18/20 resolved or reviewed-and-accepted
  directly in this pass (spec.md + research.md edited); 2 residual items
  (CHK002, CHK004) are accepted as implementation/testing-level concerns to
  carry into `tasks.md` rather than further spec changes — flag again in
  `/speckit.analyze` if that doesn't hold up.
