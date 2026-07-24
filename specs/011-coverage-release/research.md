# Research: The Coverage Release (011)

All decisions resolved 2026-07-24 (design pass + two clarify answers). No
NEEDS CLARIFICATION remain.

## D1. The safe-click boundary (the crux)

- **Decision**: introduce a shared submit **denylist**. The companion/watcher
  may click ONLY an element it is setting a value on (a field's dropdown
  control or its option, a typeahead suggestion). Every click is gated by
  `is_denylisted(text, type, role)`; a true verdict aborts the click and
  records `needs_manual`. Terms: apply, submit, next, continue, save, finish,
  review & submit, login, sign in, sign up, register, create account,
  pay/checkout — matched case-insensitively on normalized text.
- **Scope (clarify Q1)**: the verdict is computed from the clicked element's
  OWN text/type/role plus the concatenated text/role of elements it CONTAINS,
  and never its ancestors. Rationale: every option sits inside the form that
  holds Submit; matching ancestors would block the whole feature. Matching
  self+descendants still refuses an actual `<button type=submit>` or a `<div>`
  wrapping one.
- **Rationale**: within Principle III's wording ("the human performs the
  final submit/login action"); clicking a dropdown to choose a value is
  neither submit/login nor bot-protection bypass.
- **Alternatives rejected**: keep absolute zero-click (custom dropdowns stay
  manual — the very gap this release exists to close); allowlist specific
  ATS widgets only (brittle, misses the long tail).

## D2. One denylist, two languages

- **Decision**: `engine/autofill/click_guard.py` is the source of truth;
  `extension/content/click_guard.js` mirrors the same term list. A test
  (`test_extension_assets.py`) asserts the two lists are term-for-term
  identical so they cannot drift.
- **Rationale**: the extension runs in the page (JS, can't import Python);
  the Playwright watcher runs in Python. Both need the guard at the moment of
  clicking. A parity test is cheaper and safer than a build-time codegen.

## D3. Recognizing custom widgets

- **Decision**: scanner/`SERIALIZE_JS` classify a field's `widget` as
  `native_select` (a real `<select>`), `custom_combobox` (`[role=combobox]`,
  `[role=listbox]`, `[aria-haspopup=listbox]`, or a React-Select control
  `[class*="-control"]` within a select-ish container), `typeahead` (a text
  input with `role=combobox`/`aria-autocomplete=list` or a known
  location/school field), else `""`. Descriptor also carries `automation_id`
  (Workday's `data-automation-id`), the widget's displayed value, and any
  readable options.
- **Rationale**: `field_core` must know which fill technique to emit; native
  selects keep their exact current path (zero regression).
- **Alternatives rejected**: infer widget type in JS and fill there (would
  duplicate classification into JS — violates "app is the brain").

## D4. Filling a custom dropdown / typeahead (~1.5s budget, clarify Q2)

- **Decision (combobox)**: safeClick the control → wait ≤1.5s (MutationObserver
  + short poll) for an options list → match an option by normalized label
  (reuse `fields.match_option` semantics) → safeClick it → recheck the
  widget's displayed value changed → dispatch input/change. Any miss/timeout
  → send Escape to close the popup, report `needs_manual` (never a wrong
  option, never left open).
- **Decision (typeahead)**: native-set the input value → wait ≤1.5s for a
  suggestion list → safeClick the matching suggestion; no match → clear/leave
  and report `needs_manual`.
- **Rationale**: 1.5s covers typical React-Select/Workday popups and debounced
  typeaheads without stalling a broken widget across a many-field form; it
  mirrors the existing ~2s watch cadence.

## D5. Backend parity (companion + Playwright fallback)

- **Decision**: `watcher.py` gains the same combobox/typeahead fill via
  Playwright locators, every `.click()` preceded by `click_guard.is_denylisted`.
  Both backends consume the same `field_core` decision and the same denylist.
- **Rationale**: FR-011 — a user without the companion must not lose the new
  coverage. The shared `field_core` + `click_guard` make parity structural,
  not duplicated logic.

## D6. Workday / iCIMS / Taleo adapters

- **Decision (Workday)**: host detect `*.myworkdayjobs.com` /
  `*.wd{N}.myworkdayjobs.com`; field map keyed on `data-automation-id`
  (stable across tenants): `legalNameSection_firstName/_lastName`, `email`,
  `phone-number`, `addressSection_*`, the source/how-heard combo, work-auth
  combos. Location/school are typeaheads (D4). Multi-page wizard: the watcher
  already re-scans each frame every tick; the USER clicks Workday's own
  Next/Continue (denylisted for the app), the new page fills as it appears.
- **Decision (iCIMS/Taleo)**: host maps + legacy field-name patterns; iCIMS
  iframes already covered by `all_frames:true`.
- **Rationale**: `data-automation-id` is the one reliable Workday handle;
  where a tenant deviates, fields degrade to generic label classification,
  then to `needs_manual` — never wrong.

## D7. Constitution clarification

- **Decision**: append one sentence to Principle III — the automation may
  click a field's own input widget to set a value; submit/apply/next/login
  controls remain never-clicked; the human still performs the final submit/
  login. Governance note bumps to v1.1.2 (clarification, not a principle
  change).
- **Rationale**: the safety-model boundary must be documented, not implicit.

## D8. Test strategy

- **Decision**: `test_click_guard.py` allow/deny matrix (incl. submit-styled-
  as-option, wrapper-div-with-submit, disabled-next); `test_extension_assets`
  parity + reframed only-clicks-through-guard; field_core widget-kind tests;
  adapters tests; and real-browser (`-m browser`, `--load-extension`)
  integration that FILLS a custom dropdown + Workday-style page + typeahead
  and proves a submit-styled-option is never clicked. Playwright-path parity
  test for the same widgets. Existing 8 extension tests + idle-recovery stay
  green.
- **Rationale**: the submit-never-clicked guarantee (SC-003) is the highest-
  stakes property; it gets both a unit matrix and a real-browser proof.
