# Tasks: The Coverage Release (v1.1.0)

**Input**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: REQUIRED for engine/ logic (constitution Principle V) — TDD
throughout (superpowers red→green), matching 009/010.
**Organization**: Setup → Foundational (the shared guard + widget protocol)
→ US1 (custom dropdowns) → US2 (Workday) → US3 (iCIMS/Taleo) → US4 (parity,
proven within the above) → Polish/Ship.

## Phase 1: Setup

- [ ] T001 Constitution clarification: append one sentence to Principle III in `.specify/memory/constitution.md` (the automation may click a field's own input widget to set a value; submit/apply/next/login controls remain never-clicked; the human still performs the final submit/login) + Sync Impact note → v1.1.2. No template changes needed.
- [ ] T002 [P] `engine/autofill/ext_protocol.py`: `FillItem.kind` += `combobox`, `typeahead`; `Descriptor` += `widget` (native_select|custom_combobox|typeahead|""), `automation_id`. Extend `tests/test_ext_protocol.py` (new kinds accepted, widget/automation_id round-trip, unknown widget rejected).

## Phase 2: Foundational (blocking — the shared safety + decision core)

- [ ] T003 `engine/autofill/click_guard.py` (NEW) TDD (`tests/test_click_guard.py`): `SUBMIT_DENY_PATTERNS` + `is_denylisted(text, type, role)`; matrix — deny (submit/apply/next/continue/save/finish/review-and-submit/login/sign in/register/create account/pay/checkout, `type=submit`, `role=button` w/ those labels, disabled Next), allow (option labels: "Yes"/"No"/"Authorized to work"/country/"LinkedIn"/a person's name/"United States"), and the scoping rule: a verdict from element text+descendants only — a submit button INSIDE the tested subtree denies, a submit in an ANCESTOR does not (caller passes only self+descendants).
- [ ] T004 `engine/autofill/field_core.py` widget-aware `decide()`: the `options` branch splits by `descriptor["widget"]` → native → `select` (unchanged), custom_combobox → `combobox`, typeahead → `typeahead`; `fields.match_option` still gates (no match → `no_match`); sensitive tags unchanged. Extend `tests/test_field_core.py` (each widget → correct kind; no-match still no_match; native select path byte-identical).

## Phase 3: US1 — Custom dropdowns & typeaheads fill (P1) 🎯 MVP

- [ ] T005 [US1] `fields.py` classifier patterns for combo/typeahead labels (work-auth, sponsorship, EEO, how-heard, years-experience, location, school) so unmapped custom widgets still classify by label/aria; tests in `tests/test_fields.py`/`test_adapters.py`.
- [ ] T006 [US1] Watcher serialization (`engine/autofill/watcher.py` `SERIALIZE_JS`) + `extension/content/scanner.js` (PARITY): serialize custom widgets — detect `[role=combobox]`/`[role=listbox]`/`[aria-haspopup=listbox]`/React-Select control/Workday combo; emit `widget`, `automation_id`, displayed `value`, readable `options`. Native `<select>` keeps `widget:"native_select"`. Extend `tests/test_watcher.py` (FakeFrame serializes widget fields).
- [ ] T007 [P] [US1] `extension/content/click_guard.js` (NEW) — the denylist mirrored from `click_guard.py`; `extension/manifest.json` loads it before `filler.js`. `tests/test_extension_assets.py`: assert JS & Python term lists are identical; reframe `test_filler_never_clicks` → `test_filler_only_clicks_through_guard` (every `.click(` in filler.js is a `safeClick(`; `click_guard.js` imported/used).
- [ ] T008 [US1] `extension/content/filler.js`: `safeClick(el)` (the ONLY click path; throws/aborts on `isDenylisted`), `fillCombobox` (safeClick control → MutationObserver wait ≤1.5s → match option by normalized label → safeClick → recheck displayed value changed → input/change; miss/timeout → Escape + report needs_manual), `fillTypeahead` (native-set → wait ≤1.5s → safeClick matching suggestion). Wired into the `fill` handler by kind.
- [ ] T009 [US1] `engine/autofill/ext_backend.py`: emit `combobox`/`typeahead` fill items from field_core decisions (option_label for combobox); report/ledger shapes unchanged. Extend `tests/test_ext_backend.py` (a custom_combobox descriptor → a combobox fill item with option_label; a needs_manual on fill_result settles).
- [ ] T010 [US1] `engine/autofill/watcher.py` Playwright executor PARITY: combobox/typeahead fill via locators, every `.click()` preceded by `click_guard.is_denylisted` refusal; ~1.5s waits; recheck. Extend `tests/test_watcher.py` (FakeLocator combobox path fills; a denylisted control raises/records needs_manual, never clicks).
- [ ] T011 [US1] New fixtures `tests/fixtures/ats_pages/`: make `react_select_dropdown.html` fillable (open→options→pick, echo the chosen value); `typeahead.html` (type→suggestions→pick, echo); `submit_styled_as_option.html` (an "option" that is actually a submit button + a real Submit near the options — echo `__submitted` on any submit). Each mirrors DOM values to `/echo`.
- [ ] T012 [US1] Extension integration (`tests/integration/test_extension_fixture_pages.py`, browser): custom dropdown fills to the saved value (echo); no-match dropdown left + needs_manual; typeahead fills; **submit_styled_as_option never echoes `__submitted`** (denylist proof in a real browser); non-empty combo sacred. Existing 8 + idle-recovery stay green.

**Checkpoint US1**: full suite + browser suite green; custom dropdowns +
typeaheads fill in a real browser AND via Playwright; submit never clicked;
practice page combo fills.

## Phase 4: US2 — Workday applications fill (P2)

- [ ] T013 [US2] `engine/autofill/adapters.py`: Workday host detect (`*.myworkdayjobs.com`, `*.wd{N}.myworkdayjobs.com`) + `data-automation-id` field map (legalName first/last, email, phone-number, addressSection_*, source/how-heard, work-auth); classify uses `automation_id` first, then generic label. Tests in `tests/test_adapters.py` (Workday descriptors → correct tags).
- [ ] T014 [US2] Fixture `tests/fixtures/ats_pages/workday_style.html`: data-automation-id identity/contact fields + one custom combo + one school typeahead + a "Next" button that must never be clicked (echo `__submitted` if it is); integration test fills the fields + combo + typeahead, and asserts Next is never clicked. Multi-page not required in the fixture (watcher re-scan already covered by delayed-render tests); a doc note covers the live multi-page gate.

## Phase 5: US3 — iCIMS / Taleo fill (P2)

- [ ] T015 [US3] `engine/autofill/adapters.py`: iCIMS + Taleo host maps + legacy field-name patterns; tests in `tests/test_adapters.py`. Fixtures `icims_style.html` + `taleo_style.html`; integration test fills standard identity/contact fields on each.

## Phase 6: Polish, packaging, ship

- [ ] T016 US4 parity is proven inside T012/T014/T015 (each new ability tested in the extension AND, for combobox, in the Playwright watcher). Add one explicit `tests/test_watcher.py` parity assertion that the watcher fills the same react-select fixture shape the extension does. `web/templates/practice_apply.html`: add a custom dropdown (work-auth) so the on-machine demo shows the new fill; `packaging/smoke_test.py` asserts `extension/content/click_guard.js` present in the stamped data-dir copy.
- [ ] T017 Packaging + version 1.1.0: `packaging/jobengine.spec` build-time assert `extension/content/click_guard.js` exists; version bump (engine/__init__.py, windows.iss, jobengine.spec) + check_version green; What's New 1.1.0 entry in web/main.py.
- [ ] T018 Docs: README known-limitations (custom dropdowns + Workday now fill; safety line "clicks fields to set values, never submit/login"), USER_MANUAL §15 The Coverage Release, USER_GUIDE (custom dropdowns/Workday note). CLAUDE.md already points at 011.
- [ ] T019 Final gate, in order: full pytest ×2 AND `pytest -m browser` AND `-m slow` green → frozen build + extended smoke → live gate per quickstart (a real Workday posting + a custom-dropdown Greenhouse/Lever/Ashby posting; submit/Next never clicked by the app) → merge → mirror `001-ai-job-engine` → tag v1.1.0 → verify BOTH installers on the Release page. Update memory after ship.

## Dependencies

- Setup (T001-T002) → everything. T003 (click_guard) + T004 (field_core)
  block all fill work. T006 (serialization) blocks T008/T010. T007
  (JS guard + reframed asset test) blocks T008. T009/T010 after T004+T006.
  T011 before T012. US2/US3 after US1 checkpoint (reuse the widget path).
  T016-T019 last.

## Implementation strategy

MVP = Phase 1+2+US1 (custom dropdowns/typeaheads fill everywhere, safely,
both backends — independently shippable value). US2/US3 are adapters layered
on the same widget path. One release at the end (matches 010); each
checkpoint leaves the app runnable and fully tested.
