---
description: "Task list for feature 017 — The Truthful Fill"
---

# Tasks: The Truthful Fill

**Input**: Design documents from `/specs/017-truthful-fill/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: REQUIRED. Constitution Principle V mandates pytest coverage for
deterministic engine logic before it is wired in, and this feature's whole
purpose is correctness — every defect becomes a failing test first (R24).

**Organization**: grouped by user story. Each story is independently
implementable, testable and shippable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete work)
- **[Story]**: the user story this serves

---

## Phase 1: Setup (shared fixtures)

**Purpose**: the observation surface every later test depends on.

- [ ] T001 Extend the practice fixture with the Akuna-shaped controls in `web/templates/practice_apply.html`: a React-select dropdown whose `<label>` is a 400-character acknowledgement and whose search `<input>` is nested inside `div.select__control`; a binding-exclusivity variant; a pronoun checkbox group in a `<fieldset><legend>`; a "please list their name" field; a "how your name is pronounced phonetically" field; a work-authorization expiry text field; a gender `<select>` worded `Man/Woman/Prefer not to say`; a location typeahead; a lone-`Name` variant
- [ ] T002 Extend the fixture beacon in `web/templates/practice_apply.html` and `web/main.py` (`/practice/fixture-state`) to report the résumé input's attached filename and size, the acknowledgement field's value, the pronoun group's checked members, and the "their name" / "phonetically" field values
- [ ] T003 [P] Create empty test modules `tests/test_vocab.py`, `tests/test_profile_answers.py`, `tests/test_field_shape.py`

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the pure primitives every user story consumes. No behaviour
changes yet — these modules are written and tested standalone, then wired in
per story.

- [ ] T004 [P] RED: canonical vocabulary tests in `tests/test_vocab.py` — table-driven over every family in data-model.md §8 (`Male→Man`, `Straight→Heterosexual`, `Y→Yes`, `Prefer not to say→Decline to self-identify`, `B.S.→Bachelor's`), plus the negative cases that must NOT match (`Male` must never resolve to `Woman`)
- [ ] T005 GREEN: implement `engine/autofill/vocab.py` — canonical values, synonym sets, `canonical(family, text)`, `family_for_tag(tag)`. Pure module, no imports beyond stdlib
- [ ] T006 [P] RED: shape-predicate tests in `tests/test_field_shape.py` covering every row of contracts/answer-resolution.md §2, including the four Akuna work-auth free-text questions rejecting a bare `Yes`, and a paragraph rejected for a choice control with unknown options
- [ ] T007 GREEN: implement `field_core.value_fits(descriptor, value) -> (bool, reason)` in `engine/autofill/field_core.py`, including the ancestry rule (an input nested in a choice widget is judged as a choice control)
- [ ] T008 [P] RED: resolver tests in `tests/test_profile_answers.py` — one case per tag in data-model.md §7, plus blank-stays-`None` and the three self-ID states
- [ ] T009 GREEN: implement `engine/autofill/profile_answers.py` (`PROFILE_ANSWER_TAGS`, `answer_for`). Operates on a plain profile dict so it is testable before the columns exist
- [ ] T010 Extend the serializer parity test in `tests/test_watcher.py` to assert `scanner.js` and `watcher.SERIALIZE_JS` produce identical logical fields for the T001 fixture, and fix the known selector drift (`fields.py:27-34` omits `[type=hidden]`; `scanner.js:13-21` omits `[type=reset]`)

**Checkpoint**: three new modules green in isolation; parity guard extended.

---

## Phase 3: US1 — Stop the harm (Priority: P1) 🎯 MVP

**Goal**: nothing false, nothing runaway, always stoppable.
**Independent test**: run against T001's fixture with an empty library — ungrounded questions stay empty and flagged, each question generates at most twice, and Stop stays reachable.

- [ ] T011 [US1] RED: in `tests/test_ext_backend.py`, assert that completing one draft does NOT reset any other question's backoff — count generator invocations across a simulated multi-question scan loop
- [ ] T012 [US1] GREEN: remove the `drafter.reset_backoff_for_job(job_id)` call from the draft-completion push path in `engine/autofill/ext_backend.py:307`; keep it only on the explicit `fill_again` path
- [ ] T013 [US1] [P] RED: in `tests/test_drafter.py`, assert `MAX_ATTEMPTS_PER_QUESTION` and `MAX_DRAFTS_PER_JOB` are enforced and that exhaustion yields the non-retryable reasons `attempts_exhausted` / `job_budget_exhausted`
- [ ] T014 [US1] GREEN: implement the caps and the new reason vocabulary in `engine/autofill/drafter.py`; add both reasons to `_NEEDS_YOU_REASONS` and `_NEVER_RETRY_REASONS`
- [ ] T015 [US1] [P] RED: in `tests/test_answer_bank.py` and `tests/test_drafter.py`, assert the refusal contract — a `CANNOT_ANSWER` response becomes `(False, None, "cannot_answer")` and is never retried, and an empty response is a refusal rather than an endless retry
- [ ] T016 [US1] GREEN: add the refusal instruction and token to `answer_bank.suggest` in `engine/autofill/answer_bank.py`, and map it in `drafter._validate`
- [ ] T017 [US1] [P] RED: in `tests/test_answer_bank.py`, assert the factual prompt contains no company name, role title or job description, and that only the cover-letter prompt receives them
- [ ] T018 [US1] GREEN: split the prompt construction in `engine/autofill/answer_bank.py` per contracts/answer-resolution.md §3
- [ ] T019 [US1] [P] RED: in `tests/test_drafter.py`, assert no tag in the never-generated set ever reaches the generator, using the exact Akuna questions ("have you ever applied…", "do you have prior experience working at an options market making firm", "did you complete our online Options 101 Course", "do you have any offer deadlines", "do you live in New York or California")
- [ ] T020 [US1] GREEN: add the factual-history tags to `engine/autofill/fields.py` and the never-generated set in `engine/autofill/drafter.py`
- [ ] T021 [US1] [P] RED: in `tests/test_drafts.py` and `tests/test_db.py`, assert one `ai_drafts` row per `(job_id, question)` and that drafter records rehydrate for the active job after a restart
- [ ] T022 [US1] GREEN: add the unique index plus `attempts`/`reason`/`updated_at` columns in `engine/db.py`, convert `drafts.record` to an upsert in `engine/autofill/drafts.py`, and rehydrate `_records` on session start
- [ ] T023 [US1] [P] RED: in `tests/test_api.py`, assert the purge removes only `source IN ('ai','auto_saved')` rows and unconfirmed drafts, and never touches `user`/`confirmed` rows
- [ ] T024 [US1] GREEN: implement the purge endpoint in `web/routes_api.py` and the "Reset learned answers" control with its confirmation counts in `web/templates/partials/profile_answer_bank.html`
- [ ] T025 [US1] Make the status view always stoppable: move Stop/Done/Re-scan into a sticky region outside the polled swap target and bound the rendered draft list to 20 with a disclosure, in `web/templates/partials/autofill_status.html` and `web/templates/autofill.html`; assert the controls render above the report in `tests/test_web.py`
- [ ] T026 [US1] Sweep stale tests that pin the old drafting behaviour across `tests/test_drafter.py`, `tests/test_browser_controller.py`, `tests/test_routes_autofill.py`, `tests/test_web.py` and `tests/conftest.py` — the recurring 015/016 lesson, done deliberately rather than reactively

**Checkpoint**: US1 shippable on its own — the tool can no longer state something untrue or run away.

---

## Phase 4: US2 — Right answer in the right field (Priority: P2)

**Goal**: answers match the shape of the control.
**Independent test**: the T001 fixture receives a correctly shaped value or nothing in every field.

- [ ] T027 [US2] [P] RED: in `tests/test_extension_assets.py` and the parity test, assert an input nested inside a choice widget is not emitted as its own field and that a surviving nested input inherits `widget: "custom_combobox"`
- [ ] T028 [US2] GREEN: implement the ancestry de-duplication and widget inheritance in `extension/content/scanner.js` and the mirrored `SERIALIZE_JS` in `engine/autofill/watcher.py`, in lockstep
- [ ] T029 [US2] [P] RED: assert a checkbox set sharing a legend becomes ONE descriptor (`type: "checkbox_group"`, options from member labels, `je_idx` from the first member) and that selecting two members emits two existing `kind:"checkbox"` fill items
- [ ] T030 [US2] GREEN: implement checkbox grouping in both serializers and per-member emission in `engine/autofill/ext_backend.py`; no new `FillItem.kind`
- [ ] T031 [US2] [P] RED: in `tests/test_field_core.py` and `tests/test_drafter.py`, assert prose is refused for a choice control with unknown options and a bare `Yes` is refused for a descriptive free-text work-auth question
- [ ] T032 [US2] GREEN: wire `value_fits` into `field_core.decide` and `drafter._validate`
- [ ] T033 [US2] [P] RED: in `tests/test_fields.py`, assert "how your name is pronounced phonetically" is not a phone field, "please list their name" is not a name field, "Preferred Name" is `preferred_name`, and Lever's bare `name=` attribute still classifies as `full_name`
- [ ] T034 [US2] GREEN: word-bound `_PHONE_RE`, add the third-party disqualifier to the name patterns, and add `preferred_name` / `middle_name` tags ahead of `_FULL_NAME_RE` in `engine/autofill/fields.py`
- [ ] T035 [US2] [P] RED: in `tests/test_field_core.py`, assert `name_layout` across four shapes — First+Last, lone `Name`, `Name` + `Last name`, and `Name` + `Preferred Name`
- [ ] T036 [US2] GREEN: implement `field_core.name_layout(descriptors)` and apply it in both `engine/autofill/ext_backend.py` and `engine/autofill/watcher.py` before deciding
- [ ] T037 [US2] [P] Per-field status wording reflects the control type (no more "attach manually" for a dropdown) in `web/templates/partials/autofill_status.html`, asserted in `tests/test_web.py`
- [ ] T038 [US2] FR-048: the same question in two documents of one application is answered once and generated once — test in `tests/test_ext_backend.py`, implement in the drafter key/ledger path

**Checkpoint**: US1 + US2 — the fill is truthful and correctly shaped.

---

## Phase 5: US3 — Profile depth and the resolver (Priority: P3)

**Goal**: the profile can answer a real application.

- [ ] T039 [US3] [P] RED: in `tests/test_db.py`, a table-driven test asserting every `_PROFILE_COLUMNS` entry saves and reloads unchanged — which also fails today for `target_titles`
- [ ] T040 [US3] GREEN: add the columns from data-model.md §1 to `_MIGRATIONS` and `_PROFILE_COLUMNS` in `engine/db.py`, including `target_titles`
- [ ] T041 [US3] Wire `profile_answers.answer_for` into `browser_controller._value_for_tag` ahead of the answer-bank path and fold `qa.PROFILE_FACT_TAGS` / `qa.profile_fact_answer` into it; update `tests/test_browser_controller.py`
- [ ] T042 [US3] [P] RED: in `tests/test_fields.py` and `tests/test_adapters.py`, assert the location tag family classifies and that Greenhouse `candidate-location` / Ashby `_systemfield_location` map to `location_full` rather than `free_text_unknown`
- [ ] T043 [US3] GREEN: add the location tags in `engine/autofill/fields.py` and remap in `engine/autofill/adapters.py`
- [ ] T044 [US3] [P] RED: assert every library tag resolves from the profile with no generator call
- [ ] T045 [US3] GREEN: add the library tags to `engine/autofill/fields.py` and resolve them in `engine/autofill/profile_answers.py`
- [ ] T046 [US3] Profile UI sections (Identity, Address, Work authorization detail, Preferences, Experience, Links, Voluntary self-identification, Answer library) in `web/templates/profile.html` and the matching optional form fields in `web/routes_api.py`; assert the round trip through the route in `tests/test_api.py`

**Checkpoint**: refusals decay — the profile answers what it can.

---

## Phase 6: US4 — Say it the way the form says it (Priority: P4)

- [ ] T047 [US4] [P] RED: in `tests/test_fields.py`, assert `match_option` selects `Man` for a stored `Male`, `Heterosexual` for `Straight`, and a decline option for `Prefer not to say` — and that work-authorization matching strictness is unchanged
- [ ] T048 [US4] GREEN: add the canonical fourth pass and the optional `tag` parameter to `fields.match_option`
- [ ] T049 [US4] [P] RED: assert a bare "Gender" label classifies as `selfid_gender` (not `free_text_unknown`), that `criminal_history` and `references` now have producers, that stored self-ID fills, and that blank stays blank
- [ ] T050 [US4] GREEN: split `_EEO_RE` into the self-ID producer tags and add the missing producers in `engine/autofill/fields.py`; resolve them in `profile_answers.py`; keep them all in the never-generated set
- [ ] T051 [US4] [P] RED: assert routine acknowledgements resolve from the library and the Akuna exclusivity acknowledgement is never answered by any path
- [ ] T052 [US4] GREEN: implement the `acknowledgement` tag and its binding/routine sub-classification in `engine/autofill/fields.py`

**Checkpoint**: stored values reach forms regardless of wording.

---

## Phase 7: US5 — Attach the real résumé (Priority: P5)

- [ ] T053 [US5] [P] RED: in `tests/test_extension_assets.py`, assert `filler.js` no longer calls `fetch` directly and that a non-PDF or empty body results in no attachment; assert the service worker resolves the path against `http://127.0.0.1:<port>`
- [ ] T054 [US5] GREEN: implement the `fetch_file` message in `extension/background/service-worker.js` and rewrite `attachFile` in `extension/content/filler.js` to build the `File` from the returned bytes after verification
- [ ] T055 [US5] [P] RED: in `tests/test_ext_protocol.py`, assert `filename`/`mime` are additive and that a payload without them still parses
- [ ] T056 [US5] GREEN: add the fields to `FillItem` in `engine/autofill/ext_protocol.py` and populate them in `engine/autofill/ext_backend.py`
- [ ] T057 [US5] [P] RED: in `tests/test_browser_controller.py`, assert the tailored PDF is chosen only when the job carries a non-empty `tailor_json`, and the uploaded résumé otherwise
- [ ] T058 [US5] GREEN: change `_resume_file_for_job` in `engine/autofill/browser_controller.py` accordingly
- [ ] T059 [US5] A `cover_letter` file input receives a rendered, cached cover-letter PDF (reusing `resume_pdf.render_cover_letter`) or needs-you — never drafted prose; test in `tests/test_browser_controller.py`

**Checkpoint**: what goes out is what the applicant chose.

---

## Phase 8: US6 — See and act on the drafts (Priority: P6)

- [ ] T060 [US6] [P] RED: in `tests/test_ext_protocol.py` and `tests/test_ext_backend.py`, assert the `answers` message shape from contracts/bridge-protocol-additions.md §1, that credentials never appear in it, and that truncation is disclosed (FR-049)
- [ ] T061 [US6] GREEN: add a full-text accessor beside `drafter.list_for_job` and emit `answers` from `engine/autofill/ext_backend.py`
- [ ] T062 [US6] [P] RED: assert a `rescan` round-trip triggers exactly one immediate scan and mutates no drafter state
- [ ] T063 [US6] GREEN: implement the `rescan` case in `extension/background/service-worker.js` and the handler in `extension/content/main.js`
- [ ] T064 [US6] Panel rewrite in `extension/content/overlay.js`: open shadow root with `dataset` mirrors, answers list with Copy and Insert, needs-you jump-to-field, retained Fill again and the "you click apply / submit" line; update the static guards in `tests/test_extension_assets.py`
- [ ] T065 [US6] [P] RED: assert a panel-captured answer is stored with `source = 'user'`, fills its field, and auto-fills the same question on a later job without a generator call (SC-010)
- [ ] T066 [US6] GREEN: implement the `answer_question` inbound message in `engine/autofill/ext_protocol.py` and `engine/autofill/ext_backend.py`, the capture input in `extension/content/overlay.js`, and the bank write
- [ ] T067 [US6] FR-047: the assistant-window fallback surfaces the same answers, refusals and capture inputs in `web/templates/partials/autofill_status.html`; test in `tests/test_web.py`

**Checkpoint**: the applicant can see, copy and correct everything on the page.

---

## Phase 9: US7 — Apply with Apply Assist (Priority: P7)

- [ ] T068 [US7] [P] RED: in `tests/test_routes_autofill.py`, assert a single-job start saves the job if needed and starts a session without the queue page
- [ ] T069 [US7] GREEN: add the primary "Apply with Apply Assist" action to `web/templates/job_detail.html` and the feed row actions in `web/templates/partials/feed_table.html`
- [ ] T070 [US7] [P] RED: in `tests/test_ext_backend.py`, assert `apply_here` upserts the posting and starts a NON-ad-hoc watch on that tab (so the apply-opener arms)
- [ ] T071 [US7] GREEN: implement the `apply_here` inbound message and the badge button in `extension/content/discovery.js`, keeping the read-only guard intact
- [ ] T072 [US7] R23: pin the in-app draft-review surface's actual data source with a test, then converge it on the same feed the page uses, in `web/templates/partials/autofill_status.html` and `web/routes_autofill.py`

---

## Phase 10: Polish and ship

- [ ] T073 Extend `tests/integration/test_pairing_e2e.py` to assert, on the T001 fixture: the acknowledgement dropdown receives no text and is flagged; the pronoun group is one question; the "their name" and "phonetically" fields are untouched; self-ID and location fill from the profile; the attached file matches the source by name and size; the panel lists answers with Copy; and **zero** submit clicks
- [ ] T074 [P] Update `USER_MANUAL.md`, `README.md` and `WHATS_NEW["1.7.0"]` in `web/main.py` — including the new Profile sections, the answer library, the purge action, and what Apply Assist will now refuse to answer and why
- [ ] T075 Full battery ×2 plus the `browser` and `slow` markers, then `python packaging/smoke_test.py` on the frozen build with `JOBS_AI_SUBPROCESS` at its default
- [ ] T076 Ship v1.7.0: merge to `main`, mirror to `001-ai-job-engine`, tag, wait for the Release installers workflow, and verify **both** artifacts by magic bytes and SHA-256 against the release body; on any job failure delete the release and tag, fix, and re-tag

---

## Dependencies

- **Setup (T001–T003)** → everything (the fixture is the observation surface).
- **Foundational (T004–T010)** → all user stories.
- **US1 (T011–T026)** — no dependency on other stories. **This is the MVP.**
- **US2 (T027–T038)** — depends on T007 (`value_fits`) and T010 (parity guard).
- **US3 (T039–T046)** — depends on T009 (resolver). US2 stops the wrong value; US3 supplies the right one, so US2 is shippable before US3 lands.
- **US4 (T047–T052)** — depends on T005 (`vocab`) and T040 (self-ID columns).
- **US5 (T053–T059)** — independent of US2–US4; may be built in parallel with them.
- **US6 (T060–T067)** — depends on US1's reason vocabulary for `state`/`reason`.
- **US7 (T068–T072)** — depends on US6's panel for the badge launcher.
- **Polish (T073–T076)** — last.

## Parallel opportunities

- T004, T006, T008 (three independent RED suites) run together.
- Within each story, the `[P]` RED tasks are independent of one another.
- US5 (T053–T059) touches the file transport only and can proceed alongside
  US2–US4.
- T074 (docs) can be drafted while T073 runs.

## Traceability

Every requirement maps to at least one task; every success criterion maps to a
verifying task.

| Requirement | Tasks | | Requirement | Tasks |
|---|---|---|---|---|
| FR-001 | T011, T012 | | FR-026 | T049, T050 |
| FR-002 | T013, T014 | | FR-027 | T051, T052 |
| FR-003 | T013, T014 | | FR-028 | T031, T047 |
| FR-004 | T021, T022 | | FR-029 | T053, T054 |
| FR-005 | T021, T022 | | FR-030 | T053, T054 |
| FR-006 | T015, T016 | | FR-031 | T055, T056 |
| FR-007 | T017, T018 | | FR-032 | T057, T058 |
| FR-008 | T019, T020 | | FR-033 | T059 |
| FR-009 | T025 | | FR-034 | T060, T061 |
| FR-010 | T025 | | FR-035 | T064 |
| FR-011 | T023, T024 | | FR-036 | T064 |
| FR-012 | T031, T032 | | FR-037 | T062, T063 |
| FR-013 | T027, T028 | | FR-038 | T070, T071 |
| FR-014 | T029, T030 | | FR-039 | T071 |
| FR-015 | T033, T034 | | FR-040 | T068, T069 |
| FR-016 | T033, T034 | | FR-041 | T072 |
| FR-017 | T035, T036 | | FR-042 | T055, T060 |
| FR-018 | T037 | | FR-043 | T073 |
| FR-019 | T039, T040, T046 | | FR-044 | T051, T052, T073 |
| FR-020 | T041 | | FR-045 | T065, T066 |
| FR-021 | T042, T043 | | FR-046 | T065, T066 |
| FR-022 | T044, T045 | | FR-047 | T067 |
| FR-023 | T008, T009 | | FR-048 | T038 |
| FR-024 | T047, T048 | | FR-049 | T060 |
| FR-025 | T047 | | | |

| Success criterion | Verified by |
|---|---|
| SC-001 no wrong-shape value | T031, T073 |
| SC-002 one generation per question | T011, T013 |
| SC-003 0% invention, 100% flagged | T015, T019 |
| SC-004 Stop always reachable | T025 |
| SC-005 attachment byte-identical | T053, T073 |
| SC-006 every answer readable and copyable | T064 |
| SC-007 one-action start | T068 |
| SC-008 stored values match form wording | T047, T049 |
| SC-009 zero submit clicks | T073 |
| SC-010 answered once, remembered | T065 |
| SC-011 untailored job attaches the upload | T057 |

Tasks with no requirement mapping are infrastructure and are intentional:
T001–T003 (fixtures), T010 (parity guard), T026 (stale-test sweep),
T074–T076 (docs, verification, ship).

## Implementation strategy

**MVP = Phase 1 + Phase 2 + US1.** That alone removes the ability to state
something untrue on an application, ends the regeneration storm, and makes the
run stoppable — the three things that make the current build unsafe to use.
Each later phase is a self-contained increment that can be shipped or deferred
without leaving the product in a broken state.
