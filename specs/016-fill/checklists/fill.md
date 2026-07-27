# Requirements Quality Checklist: The Fill Release (016)

**Purpose**: "Unit tests for English" — validate the requirements for the
highest-risk areas before implementation
**Created**: 2026-07-27
**Feature**: [spec.md](../spec.md) · plan/research/data-model/contracts in
this directory's parent

## Bridge responsiveness & incremental fills (RC1)

- [x] CHK001 Is "never blocked by drafting" stated as a testable rule
  (no model call reachable from message handling) rather than a vague
  performance wish? [Clarity, Spec §FR-001; plan Performance Goals]
- [x] CHK002 Are freshness and dispatch targets quantified (status < 5 s,
  known fields < 2 s) and repeated identically in Success Criteria?
  [Measurability, Spec §FR-001/§FR-002/§SC-002]
- [x] CHK003 Is "incremental" defined against the observed failure
  (batch-until-whole-form-decided) so the regression is unambiguous?
  [Clarity, Spec §FR-002; research R1]
- [x] CHK004 Is discovery/badge interference with fills bounded by an
  explicit requirement, not left as an implementation nicety?
  [Completeness, Spec §FR-007]

## Drafter semantics (RC1 loop-kill)

- [x] CHK005 Is "one draft per unique question per session" scoped with a
  defined key (job + normalized question) somewhere authoritative?
  [Clarity, Spec §FR-003; data-model §2]
- [x] CHK006 Are failure retries bounded with named backoff behavior and a
  user-initiated reset path? [Completeness, Spec §FR-003, Edge Cases;
  Clarifications]
- [x] CHK007 Is the no-user-action path for a completed draft (reach page
  + auto-save + flagged) fully specified including its bank origin
  marking? [Completeness, Spec §FR-004/§FR-018]
- [x] CHK008 Is cross-job reuse of auto-saved answers explicitly scoped
  (job-specific prose never reused; factual answers reused)?
  [Consistency, Spec §FR-004 + Clarifications]
- [x] CHK009 Is duplicate-question-on-one-form behavior specified (both
  fields served by one draft)? [Edge Case, Spec Edge Cases]

## Choice-aware answering (RC2)

- [x] CHK010 Are ALL choice control classes given a specified capture
  behavior: native select, radio group, custom combobox, checkbox group,
  single checkbox? [Coverage, Spec §FR-010, Edge Cases]
- [x] CHK011 Is radio-group identity across rescans addressed (stable
  grouping) rather than assumed? [Clarity, Spec §FR-010 "stable identity";
  data-model §1]
- [x] CHK012 Is the option-constraint rule hard (validated, else unfilled
  + flagged) with no prose fallback? [Clarity, Spec §FR-011]
- [x] CHK013 Is the custom-combobox mechanism specified end-to-end (short
  label drafted → harvested options matched at fill time → no-match
  outcome)? [Completeness, Spec §FR-011; research R7/R8]
- [x] CHK014 Are profile-fact yes/no questions required to bypass AI
  entirely? [Completeness, Spec §FR-012]
- [x] CHK015 Is "honest outcomes" concrete (never report filled when the
  page did not change — the observed radio lie)? [Measurability,
  Spec §FR-014]
- [x] CHK016 Is both-paths parity (companion scanner vs assistant-window
  scanner) a stated requirement, not an implementation hope?
  [Consistency, Spec §FR-010 "both capture paths"]

## Sensitive questions (gate replacement)

- [x] CHK017 Is the sensitive class list enumerated (EEO/demographic,
  disability, veteran, criminal history, references) rather than "etc."?
  [Completeness, Spec §FR-013]
- [x] CHK018 Is the sensitive guarantee testable as a zero-count (SC:
  auto-answered zero times)? [Measurability, Spec §SC-006]
- [x] CHK019 Is the sensitive rule enforced at a specified layer (drafter
  denylist) so no future caller can bypass it? [Consistency, plan/
  research R7; contracts drafter-api §4]

## Apply-opener safety (D1 / constitution v1.1.4)

- [x] CHK020 Is the opener bounded by ALL of: recognized-board allowlist,
  queue-driven watch only, one-shot per page state, never type=submit?
  [Completeness, Spec §FR-016; research R9]
- [x] CHK021 Is the fill-path click rule explicitly UNCHANGED (apply still
  denied during filling) so the two paths cannot blur? [Consistency,
  constitution v1.1.4; research R9]
- [x] CHK022 Is the never-submit guarantee expressed as an asserted zero
  in verification (not just prose)? [Measurability, Spec §SC-004]
- [x] CHK023 Is unrecognized-board behavior specified (no click; human
  opens; everything else works)? [Edge Case, Spec Edge Cases +
  Assumptions]

## On-page experience (D2/D3)

- [x] CHK024 Are the panel's required contents enumerated (status,
  progress counts, per-field list, Fill again, review-and-submit note)?
  [Completeness, Spec §FR-017]
- [x] CHK025 Is the highlight lifecycle fully specified (applied when,
  keyed how, cleared by user edit, survives rescans)? [Completeness,
  Spec §FR-018; data-model §5]
- [x] CHK026 Are Fill-again semantics precise about what it may and may
  not touch (retryable fields yes; user-typed values never; backoff
  reset once)? [Clarity, Spec §FR-017 + Clarifications + Edge Cases]
- [x] CHK027 Is the fallback (assistant-window) parity decision recorded
  so the panel/highlight scope is unambiguous? [Consistency,
  Clarifications + Assumptions]
- [x] CHK028 Is the never-auto-replace-accepted-drafts rule stated (user
  edits sacred; later "better" drafts don't overwrite)? [Consistency,
  design doc Non-goals; Spec Edge Cases "never overwritten"]

## Gate removal blast radius (RC3)

- [x] CHK029 Is the post-removal role of the confirm endpoints specified
  (bank curation only, sentinel guard retained, no fill side effects)?
  [Completeness, Spec §FR-019; contracts http-api]
- [x] CHK030 Is the replacement surface (passive activity log incl.
  drafting states) specified with its content? [Completeness,
  Spec §FR-019; data-model §9]
- [x] CHK031 Is the test-sweep obligation (rewrite all pending/confirm
  flow tests) captured as scope, given the project's 4× stale-pin
  history? [Completeness, plan Project Structure SWEEP entries;
  research R11]

## Tab following & operational traps (RC4)

- [x] CHK032 Is the watch model decided and stated (singular target,
  transfers to newest child, old tab intentionally stops)? [Clarity,
  research R4; Spec §FR-005]
- [x] CHK033 Are worker-restart survival and open-failure behavior
  (ack timeout, retry, visible outcome, queue advance) specified with
  bounds? [Completeness, Spec §FR-005/§FR-006; research R4]
- [x] CHK034 Is every silent error in the evidence mapped to a visible
  surface (busy error, scan exception, wrong-tab drops, dead re-scan,
  preflight skip)? [Coverage, Spec §FR-008/§FR-009; contracts]

## AI runtime & tailor (RC5)

- [x] CHK035 Is the isolation default flip stated with its escape hatch
  and its test consequences (battery runs in default mode)?
  [Completeness, Spec §FR-020; research R12]
- [x] CHK036 Are generation bounds required universally (every generation
  has output limit + time budget), with tailor's prompt band named?
  [Completeness, Spec §FR-021]
- [x] CHK037 Is tailor's user-visible contract complete (progress state,
  clean failure, persistence on success — currently 0 rows ever)?
  [Completeness, Spec §FR-022/§SC-005]
- [x] CHK038 Is version-skew degradation specified (new fill kinds
  withheld from old companions; flagged not mis-filled)? [Edge Case,
  Spec §FR-015]

## Cross-cutting invariants

- [x] CHK039 Do the constitution invariants appear as requirements-level
  constraints ($0, offline, engine-never-imports-web, secrets never in
  diagnostics, protocol additive-only)? [Consistency, plan Constitution
  Check; contracts]
- [x] CHK040 Is queue advancement in fill-first mode specified (advances
  only on user action or open-failure — never auto-advances on fill
  completion, since filling ≠ submitting)? [Gap → FIXED: added to Spec
  Edge Cases during this checklist's evaluation]

## Notes

- CHK040 initially FAILED — the spec never said when a job leaves the
  queue under fill-first. Fixed in spec.md (Edge Cases): the queue holds
  the current job until the user advances/stops (or the open fails);
  fill completion never auto-advances and never implies submission.
- All other items passed against the spec + plan artifacts as written.
