# Correctness Checklist: The Real Application

**Purpose**: The panel-readability and history-filling logic is where this
feature can silently do the wrong thing. These items are the acceptance
conditions for Workstreams A–C.
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md) · [contracts/section_context.md](../contracts/section_context.md)

## Evidence before code

- [ ] CHK101 A real page report has been captured from the applicant's Workday application *(theirs to do — the capture tool ships in this release)*
- [X] CHK102 The `Seen 156` question is settled — **by construction**, not by the capture. `_frame_seen` provably retained dead frames forever, and the report now carries both `counts.seen` (live frames) and `counts_reported.seen_all_frames`, so CHK101 will show the gap rather than merely suggest it
- [X] CHK103 The Workday fixture is built from the **mechanisms proven in R1** plus the exact labels the applicant reported — not authored from imagination. CHK101 refines it
- [ ] CHK104 Section-detection coverage on the real capture is measured and recorded, not asserted
- [X] CHK105 No de-duplication rule rests on a guessed field count. Per analysis A4 the gate was re-scoped: R1's three causes are read from source and certain, so only CHK104 and the `_frame_seen` magnitude ever needed the capture

## Panel rendering

- [X] CHK106 One row per distinct question within a section
- [X] CHK107 Two sections asking the same question produce two rows
- [X] CHK108 No row renders with empty or whitespace question text
- [X] CHK109 A question resolves from label, then automation id, then name, then id — and the row is omitted when all fail
- [X] CHK110 A collapsed row's "Show me" reaches every element behind it
- [X] CHK111 Fields absent from the document stop being reported as outstanding
- [X] CHK112 Advancing a wizard step does not leave the prior step's fields listed
- [ ] CHK113 `reconcile()` on the 150-field fixture stays within one animation frame
- [X] CHK114 A row holding the applicant's focus is still never rebuilt under their typing

## Section context

- [X] CHK115 `section_index` is recomputed per scan and never written to the DOM
- [X] CHK116 `section_label: ""` degrades to today's flat grouping, never a guess
- [X] CHK117 Section text uses `stripControls()`, so a container cannot pick up a control's own rendered text
- [X] CHK118 `scanner.js` and `watcher.py SERIALIZE_JS` produce byte-identical descriptors, asserted by the extended parity test
- [X] CHK119 `PROTOCOL_V` is still 1, new keys are optional with defaults, and an older companion still works
- [X] CHK120 A newer companion sending unknown keys does not cause the app to reject the whole message

## History filling

- [X] CHK121 Work-history block *n* fills from employment entry *n*
- [X] CHK122 Education block *n* fills from education entry *n*
- [X] CHK123 More blocks than entries leaves the surplus for the applicant
- [X] CHK124 An empty field in an entry is flagged, never borrowed from another entry
- [X] CHK125 A profile correction is the value that gets typed on the next pass
- [X] CHK126 New `ExperienceEntry`/`EducationEntry` fields default empty, so v2.0.0 profiles stay valid
- [X] CHK127 `is_current` drives "I currently work here" and an empty end date does not

## Regression safety

- [ ] CHK128 Unit and browser suite counts both exceed v2.0.0's 1731 and 104, none lost
- [ ] CHK129 The browser suite has been run on Windows **and** macOS before the tag
- [ ] CHK130 The frozen smoke passes against the packaged build
- [X] CHK131 Rich-text cover letters still fill (020's fix is not regressed by the new selector work)
- [X] CHK132 `stripControls` still strips rich-text editors — the bug macOS caught in 020

## Notes

CHK105 is the load-bearing item. This project has had three approved plan
claims overturned by measurement; writing B against an imagined page would be
the fourth.
