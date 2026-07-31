# Checklist: Escort Safety & Click Policy — Requirements Quality

**Purpose**: Unit-test the 019 requirements for the safety-critical domain:
progression clicks vs final-class, credential secrecy, CAPTCHA pause,
LinkedIn exclusion. Author-side gate before `/speckit-tasks`.
**Created**: 2026-07-31
**Feature**: [spec.md](../spec.md) · plan/research/contracts under
`specs/019-door-to-door/`

## Click Taxonomy — Completeness & Precedence

- [x] CHK001 - Are the permitted click kinds enumerated exhaustively (open
  apply, wizard advance, sign-in) with no open-ended language? [Completeness,
  Spec §FR-022/023/016, Constitution v1.2.0]
- [x] CHK002 - Is the final-class (never-click) list exhaustive and phrased
  to cover paraphrases ("any phrasing")? [Completeness, Spec §FR-025,
  Contracts escort-ui "Click-safety copy"]
- [x] CHK003 - Is precedence stated for a control matching both an allowlist
  and final-class (final-class wins, refuse)? [Consistency, Spec §FR-024,
  Edge Cases "mislabelled final control"]
- [x] CHK004 - Is the one-shot unit defined precisely (rendered document +
  field set, explicitly NOT the page address)? [Clarity, Spec §FR-026,
  Edge Cases "same address" case]
- [x] CHK005 - Is the advance cap quantified (12) with specified at-cap
  behavior (pause to human)? [Measurability, Spec §FR-027]
- [x] CHK006 - Are ALL advance preconditions enumerated (required fields
  decided, none in flight, zero needs-attention, no focused input, quiet
  period)? [Completeness, Spec §FR-023]
- [x] CHK007 - Is behavior defined when a complete step has NO discoverable
  progression control? [Gap → RESOLVED: FR-024 now requires a "your turn"
  pause]
- [x] CHK008 - Is the sign-in click's arming condition stated as state-gated
  (only after the system's own credential fills, exact frame, never
  text-inferred)? [Clarity, Spec §FR-016]
- [x] CHK009 - Is retry behavior after a failed sign-in bounded (one click
  per rendered document; error pauses to human)? [Edge Case, Spec §FR-016,
  US3-AS6]
- [x] CHK010 - Are requirements consistent between the fill path's click
  protections (unchanged) and the new progression clicks (new module)?
  [Consistency, Spec §FR-012 vs §FR-024; research R20/R21]
- [x] CHK011 - Is every automated click required to be observable
  (recorded kind/target/step/outcome)? [Measurability, Spec §FR-031,
  Data-model "Progression Click Record"]
- [x] CHK012 - Is attribution specified so app-initiated advances are never
  counted as user submissions? [Completeness, Spec §FR-032]

## Credential Secrecy — Completeness & Verifiability

- [x] CHK013 - Is the exhaustive never-stored list for secrets specified
  (database, extension storage, logs, reports, diagnostics, on-page answer
  list)? [Completeness, Spec §FR-018, Contracts escort-protocol
  "Secret-safety invariants"]
- [x] CHK014 - Is "write-only after saving" defined for saved logins?
  [Clarity, Spec §FR-018, Key Entities "Saved Login"]
- [x] CHK015 - Is the save-from-page flow's secrecy specified end to end
  (payload redacted from logging, ack carries no secret, input cleared)?
  [Completeness, Contracts escort-protocol §credential_save, escort-ui rules]
- [x] CHK016 - Is post-save behavior defined (sign-in proceeds without
  re-asking)? [Gap → RESOLVED: FR-017 extended]
- [x] CHK017 - Is the generated-password flow's save timing specified (at
  fill time, idempotent overwrite) with rationale for the failure case?
  [Clarity, Spec §FR-021, research R18, Edge Cases "account already exists"]
- [x] CHK018 - Are browser-password-manager-prefilled credentials' status
  defined (count as satisfied, not stuck)? [Edge Case, Spec §FR-019]
- [x] CHK019 - Can secret-hygiene compliance be objectively verified (an
  instrumented full-run grep is a stated success criterion)? [Measurability,
  Spec §SC-009]
- [x] CHK020 - Is the create-account click unambiguously assigned to the
  human with the system's hand-off prompt specified? [Clarity, Spec §FR-021,
  US3-AS5]

## CAPTCHA & Pauses — Coverage

- [x] CHK021 - Is "never interact" with bot-checks stated absolutely (no
  exception paths anywhere in spec/plan)? [Consistency, Spec §FR-028,
  Assumptions; Constitution v1.2.0]
- [x] CHK022 - Is resume-after-CAPTCHA defined with an observable trigger
  (signal clears and the page moves on)? [Clarity, Spec §FR-028]
- [x] CHK023 - Is precedence defined when CAPTCHA appears after a step was
  judged complete but before the click (detection outranks completeness)?
  [Edge Case, Spec Edge Cases]
- [x] CHK024 - Are ALL pause states enumerated with their triggers and exit
  conditions (needs-you, CAPTCHA, cap, ready-for-review, no-control)?
  [Completeness, Spec §FR-024/027/028/029/030, Data-model state diagram]
- [x] CHK025 - Is "typing wins" specified (focused input blocks advancing)?
  [Edge Case, Spec §FR-023, Edge Cases]

## LinkedIn & Domain Boundaries

- [x] CHK026 - Is the LinkedIn exclusion absolute (no click kinds exempted)
  while filling remains available? [Completeness, Spec §FR-033, US4-AS7]
- [x] CHK027 - Is the unsupported-ATS boundary defined (generic fallback
  only, iCIMS named)? [Clarity, Spec Assumptions]
- [x] CHK028 - Is frame targeting specified so sign-in/advance act only in
  the frame the system itself filled? [Coverage, Spec Edge Cases
  "multiple frames", Contracts escort-protocol §advance_step]

## Degradation & Compatibility

- [x] CHK029 - Is escort behavior against a version-mismatched companion
  defined (never arms; fill-only until reload; state says so)? [Gap →
  RESOLVED: FR-035 extended]
- [x] CHK030 - Is the escort-off/paused behavior pinned to an existing known
  behavior (exactly fill-only v1.8.0)? [Measurability, Spec §FR-034, SC via
  quickstart §5]
- [x] CHK031 - Is worker-restart survival specified for arming state AND the
  advance cap (cap cannot reset by worker death)? [Edge Case, Spec §FR-006,
  Edge Cases]

## Notes

- Three genuine gaps surfaced while drafting; each was resolved by a spec
  edit in the same commit (CHK007 → FR-024, CHK016 → FR-017, CHK029 →
  FR-035). No open items remain.
- Deliberately deferred to plan-level artifacts (recorded in the clarify
  report): quiet-period duration (research R19, ~2 s) and the concrete
  Workday identifier list (research R8). Neither weakens a safety
  requirement.
