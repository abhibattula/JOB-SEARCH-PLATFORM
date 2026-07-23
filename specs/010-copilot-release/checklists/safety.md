# Checklist: Safety, Security & Resilience Requirements Quality (010)

**Purpose**: Unit-test the requirements writing in the six highest-risk
areas of The Copilot Release before implementation planning hardens them.
**Created**: 2026-07-23
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [bridge-protocol](../contracts/bridge-protocol.md)

## 1. Never-click / never-auto-submit / never-auto-login (two backends)

- [x] CHK001 - Is the never-click invariant stated as binding on BOTH fill backends (assistant window AND companion), not just the engine? [Consistency, Spec §FR-006, §FR-023; Contract §Invariants-1]
- [x] CHK002 - Do the requirements enumerate ALL forbidden interaction classes (apply, submit, next, login, navigation, arbitrary page controls) rather than just "submit"? [Completeness, Spec §US1-AS7, Contract §Invariants-1]
- [x] CHK003 - Is the ad-hoc "Fill this page" mode explicitly bound to every rule of queued fills (so the invariant can't be bypassed by the new entry point)? [Coverage, Spec §FR-004a]
- [x] CHK004 - Is the "custom dropdowns can't be set without clicking → needs-manual, never clicked" policy carried forward explicitly for the companion? [Consistency, Spec §Edge-Cases]
- [x] CHK005 - Is there a measurable, test-enforceable acceptance criterion for the invariant (zero exceptions across fixture + live gates)? [Measurability, Spec §SC-003]
- [x] CHK006 - Are overlay/panel interactions constrained so the progress UI itself can never interact with page controls? [Edge Case, Spec §FR-009]

## 2. Bridge security & password fill-and-forget

- [x] CHK007 - Is mutual authentication between app and companion required, with the threat ("no other local software can issue fill instructions or receive profile data") named? [Completeness, Spec §FR-002]
- [x] CHK008 - Are the data classes crossing the bridge enumerated (descriptors out, fill values in, secrets one-way), so review can detect scope creep? [Completeness, Contract §Commands/Events]
- [x] CHK009 - Is password handling specified end-to-end: never stored, never displayed, never logged companion-side, masked in all reports, never echoed back? [Completeness, Spec §FR-008; Contract §FillItem-secret]
- [x] CHK010 - Is the domain-matching precondition for sending credentials specified (registrable domain match on a currently-watched tab)? [Clarity, Contract §FillItem-secret; Spec §FR-008]
- [x] CHK011 - Is the companion's total durable-state surface bounded in writing (last-known-good port only; no secrets, profile data, or fill values)? [Completeness, data-model §Extension-side state]
- [x] CHK012 - Are failure semantics for authentication specified (wrong secret, superseded session, version mismatch — each with distinct close behavior)? [Coverage, Contract §Handshake]
- [x] CHK013 - Is the resume-file transfer specified with single-use, expiring access rather than an open file endpoint? [Edge Case, http-api §bridge/file]

## 3. AI draft safety

- [x] CHK014 - Is the grounding source set closed and enumerated (resume, profile, saved answers, job title/company/description — nothing else)? [Completeness, Spec §FR-011]
- [x] CHK015 - Is "never fabricated facts" made concrete with named examples (no invented employers, dates, credentials)? [Clarity, Spec §FR-011]
- [x] CHK016 - Is the sensitive-question exclusion specified fail-closed (an allowlist of AI-eligible question types, not a blocklist of forbidden ones)? [Clarity, plan §D8; Spec §FR-014]
- [x] CHK017 - Is the total-failure path specified as leave-untouched + needs-manual (never placeholder/junk fills)? [Exception Flow, Spec §FR-015, §US2-AS5]
- [x] CHK018 - Is 100% visible flagging of AI fills stated as measurable (on-page AND in-report, zero unflagged)? [Measurability, Spec §FR-012, §SC-005]
- [x] CHK019 - Are draft length/tone bounded with numbers so "concise" is verifiable? [Measurability, Spec §FR-011 (60–120 words), §SC-004]
- [x] CHK020 - Is the saved-answer-first ordering (bank match before AI) required, preventing AI drift on already-answered questions? [Consistency, Spec §US2-AS2, plan §D9]
- [x] CHK021 - Is the low-confidence/non-English behavior addressed (attempt, then untouched + needs-manual on thin output)? [Edge Case, Spec §Edge-Cases]

## 4. Consent semantics

- [x] CHK022 - Is "detected submission never changes status silently" stated with the affirmative mechanism (user-confirmable one-click advance)? [Clarity, Spec §FR-020, §US3-AS2]
- [x] CHK023 - Are auto-saved answers required to be visibly badged, editable, and deletable in Profile? [Completeness, Spec §FR-013]
- [x] CHK024 - Is the decline path specified (dismissing the confirmation changes nothing)? [Coverage, http-api §submission-confirm]
- [x] CHK025 - Is detection framed as best-effort with the cost of a miss explicitly zero (manual status change remains)? [Assumption, Spec §Assumptions]
- [x] CHK026 - Do the two draft-acceptance paths (explicit confirm vs detected submission) have consistent, non-conflicting outcomes in the answer bank? [Consistency, Spec §FR-013, data-model §answers]
- [x] CHK027 - Is tracker linkage for ad-hoc sessions user-confirmed rather than automatic? [Consistency, Spec §FR-004a]

## 5. MV3 resilience

- [x] CHK028 - Are re-scan/idempotency requirements specified such that repeated scans can never double-fill (authoritative ledger location named)? [Completeness, Contract §Invariants-5; plan §D5]
- [x] CHK029 - Are recovery requirements defined for background-process suspension/eviction mid-fill (automatic reconnection, harmless re-scan)? [Recovery, Spec §Edge-Cases; design doc §8]
- [x] CHK030 - Is extension reload/update mid-queue addressed (orphaned scripts stop, overlay removed, no double-fill)? [Recovery, Spec §Edge-Cases (stale folder), design doc §8]
- [x] CHK031 - Is the mid-queue disconnect flow specified with explicit user choice (wait vs switch) and a prohibition on silent backend swap? [Clarity, Spec §FR-005]
- [x] CHK032 - Is the multi-profile case bounded (one active session, newer supersedes, loser visibly disconnected)? [Edge Case, Spec §Edge-Cases]
- [x] CHK033 - Is stale-companion version handling specified (refuse session + tell user to reload; app keeps folder current)? [Edge Case, Spec §Edge-Cases, §FR-022]
- [x] CHK034 - Is the closed-tab-mid-fill case mapped onto existing interrupted/resume semantics? [Consistency, Spec §Edge-Cases]

## 6. Fallback parity

- [x] CHK035 - Is it required that extension-absent users retain the FULL v0.9.0 behavior (not a degraded subset)? [Completeness, Spec §FR-004, §FR-024]
- [x] CHK036 - Is the active mode always visible to the user, so fallback is never mistaken for the companion path? [Clarity, Spec §FR-004, §FR-018]
- [x] CHK037 - Is queue-mode stickiness specified (backend fixed for the run), preventing mixed-session state? [Consistency, Spec §FR-005]
- [x] CHK038 - Are the v0.9.0 capabilities that must remain unchanged enumerated (practice, import, offline-first, assistant window, activity feed)? [Completeness, Spec §FR-024]
- [x] CHK039 - Does the live-gate criterion compare companion fills against the v0.9.0 baseline on the same postings (parity measurable)? [Measurability, Spec §SC-002]
- [x] CHK040 - Is the non-Chrome-user experience explicitly scoped (loses nothing relative to v0.9.0)? [Assumption, Spec §Assumptions]

## Notes

- All 40 items PASS against the current spec/plan/contracts — the three
  clarify answers (ad-hoc mode, submission auto-save, draft shape) closed
  what would have been CHK003/CHK019/CHK026 gaps.
- Re-run this checklist mentally during /speckit-analyze; any item that
  stops passing after tasks.md generation is an analyze finding.
