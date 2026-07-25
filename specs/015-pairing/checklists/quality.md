# Requirements-Quality Checklist: The Pairing Release (highest-risk areas)

**Purpose**: Unit-test the REQUIREMENTS (spec.md) for completeness, clarity,
consistency, and measurability in the seven highest-risk areas before task
generation. Tests the writing, not the implementation.
**Created**: 2026-07-25
**Feature**: [spec.md](../spec.md) · plan/research: R1–R13

## 1. Inference serialization (US1)

- [x] CHK001 - Does "all on-device AI" enumerate every caller path (drafting,
  suggestions, scoring, tailoring, profile import, embeddings) so "all" is
  verifiable rather than assumed? [Completeness, Spec §FR-001]
- [x] CHK002 - Is behavior under saturation (more simultaneous AI requests
  than the system will hold) explicitly specified as a clean failure rather
  than unbounded waiting? [Gap → fixed, Spec §FR-001a]
- [x] CHK003 - Are time budgets specified with an exceed-behavior that callers
  already tolerate, and is the "never a hang" outcome measurable?
  [Clarity/Measurability, Spec §FR-004]
- [x] CHK004 - Is the no-generation-behind-status rule stated as an observable
  bound (status refresh latency during generation) rather than an internal
  design rule? [Measurability, Spec §FR-002, SC-002]
- [x] CHK005 - Is the "park immediately, draft in background" pause behavior
  specified so the pending question's lifecycle (parked → drafting → drafted)
  is unambiguous? [Clarity, Spec §FR-003]
- [x] CHK006 - Are concurrent-failure interactions addressed (AI busy/timeout
  during a fill session → field outcome, session continues)? [Coverage,
  Spec §FR-004, Edge Cases]

## 2. Subprocess spike (D1)

- [x] CHK007 - Are GO/NO-GO criteria objective and binary (named gates on
  named platforms), with the decision owner unambiguous? [Measurability,
  Spec §FR-006]
- [x] CHK008 - Is the NO-GO release state fully specified as acceptable
  (serialized owner only), so the release definition does not depend on the
  spike's outcome? [Completeness, Spec §FR-006, Assumptions]
- [x] CHK009 - Are the spike-conditional requirements/criteria explicitly
  marked so they cannot be misread as unconditional ship-blockers?
  [Consistency, Spec §FR-006, SC-011]

## 3. Pairing observability (US2)

- [x] CHK010 - Is every evidenced silent-failure mode mapped to a specified
  visible state on a specified surface: stamp failure → same-session banner
  (FR-008) + doctor (FR-014); wrong folder → popup reason (FR-011) + wizard
  troubleshooting (FR-010) + edge case; stale pairing → popup reason +
  rejected-attempt counters; version mismatch → popup reason + counters; app
  not running → popup reason? [Coverage, Spec §FR-008–FR-014, Edge Cases]
- [x] CHK011 - Is "pairing preparation" specified with a verification step
  (read-back) and a recorded outcome, so success is a checked fact rather
  than an assumption? [Completeness, Spec §FR-007]
- [x] CHK012 - Is the dependency-minimalism requirement for pairing
  preparation stated with an enforcement mechanism (automated guard), so the
  shipped failure class is structurally excluded? [Measurability, Spec §FR-009]
- [x] CHK013 - Are the wizard's per-step verification states specified
  (prepared → installed/authenticating → connected with browser + version),
  including what each failed step tells the user? [Completeness, Spec §FR-010]
- [x] CHK014 - Is the popup's non-dead-control rule universal (every
  disconnected state names a reason and offers retry; Fill explains instead
  of no-op)? [Coverage, Spec §FR-011, SC-007]
- [x] CHK015 - Is the diagnostics (doctor) content list complete enough to
  reconstruct the whole chain without logs (preparation outcome, freshness,
  port match, connection + browser + heartbeat, rejection kinds, OS default,
  preference)? [Completeness, Spec §FR-014]
- [x] CHK016 - Does the spec forbid sensitive pairing material (the secret)
  from appearing in any diagnostic surface? [Gap → fixed, Spec §FR-014]

## 4. Fill-path disclosure — D2 (US2)

- [x] CHK017 - Is the no-companion start behavior unambiguous: proceed +
  persistent prominent notice naming the actual path + connect link, never a
  blocking step? [Clarity, Spec §FR-012]
- [x] CHK018 - Is the disclosure requirement stated for BOTH paths (companion
  with browser name; assistant window with browser + signed-out), at all
  times during a session? [Completeness, Spec §FR-013]
- [x] CHK019 - Are mid-queue transitions specified (companion connects
  mid-queue → sticky path + truthful indicator; extension removed/browser
  closed mid-queue → interrupted handling + indicator updates)? [Coverage,
  Edge Cases]
- [x] CHK020 - Do D2 requirements avoid conflicting with the existing
  sticky-per-run backend rule? [Consistency, Spec Edge Cases, Assumptions]

## 5. Browser preference — D3 (US3)

- [x] CHK021 - Is the precedence chain complete and total (connected
  companion > preference > OS default), with each hop's condition stated?
  [Completeness, Spec §FR-016–FR-018]
- [x] CHK022 - Is the preferred-browser-missing fallback specified with a
  user-visible note (no silent substitution)? [Coverage, Spec §FR-017]
- [x] CHK023 - Are mismatch-surfacing conditions exact, including that
  Auto cannot mismatch by definition, and is the one-click OS-settings action
  scoped to Windows? [Clarity → fixed, Spec §FR-019]
- [x] CHK024 - Is the default value (Chrome) traceable to a recorded decision
  (D3) rather than implicit? [Traceability, Spec Clarifications]

## 6. Rough edges (US4)

- [x] CHK025 - Is the sentinel rule for answer confirmation measurable
  (success + reusable answer + NO per-application snapshot for non-tracked
  sessions)? [Measurability, Spec §FR-020, SC-008]
- [x] CHK026 - Are all three evidenced updater failure paths specified with
  outcomes (empty/incomplete download → pre-verification rejection with clear
  message; locked cleanup → deferred, never a crash; retention → current +
  at most newest previous)? [Completeness, Spec §FR-021, FR-022, SC-009]

## 7. Constitution invariants

- [x] CHK027 - Do the requirements keep every invariant explicit where this
  feature touches it: $0 (no store, stdlib-only additions), offline-first,
  engine-never-imports-web, never auto-submit (fill core untouched), secrets
  fill-and-forget extended to diagnostics? [Consistency, Spec Assumptions +
  §FR-014; Plan Constitution Check]
- [x] CHK028 - Is the fill core's untouched status bounded precisely (only
  value-resolution blocking behavior changes), so scope creep into the proven
  subsystem is detectable? [Scope, Spec Assumptions]

## Validation notes (initial run → fixes applied)

Initial evaluation found 4 items failing against spec.md as first written;
the spec was amended the same session and all items now pass:

- CHK001 FAIL → FR-001 now enumerates the caller paths explicitly.
- CHK002 FAIL → new FR-001a: saturation is an immediate clean failure, never
  unbounded waiting.
- CHK016 FAIL → FR-014 now forbids the pairing secret on any diagnostic
  surface.
- CHK023 PARTIAL → FR-019 now states Auto cannot mismatch and scopes the
  one-click action to Windows.

Result: 28/28 PASS after amendments. No unresolved ambiguities carried into
task generation.
