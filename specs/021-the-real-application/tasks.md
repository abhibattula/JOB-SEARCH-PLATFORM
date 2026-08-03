# Tasks: The Real Application (v2.1.0)

**Feature**: `021-the-real-application` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**TDD is mandatory** (hybrid workflow): for every task that changes behaviour,
write the failing test first, watch it fail for the right reason, then write
the minimal code to pass. A task marked with a test file writes that test
first.

**[P]** = parallelisable (different files, no dependency on an incomplete task).

---

## Phase 1: Setup

- [ ] T001 Record pre-change gate counts and real-page evidence in `specs/021-the-real-application/baseline.txt` (unit + browser suite counts, the reported Filled 5 / Needs you 149 / Seen 156, the llama_cpp CPU-only backend finding)
- [ ] T002 Back up `data/jobs.db` to `data/backup/jobs-pre-2.1.0.db` before any migration runs
- [ ] T003 [P] Add `data/reports/` to `.gitignore` and confirm `data/` is already ignored

---

## Phase 2: Foundational (blocks US1 and US2)

**Workstream A — the capture. Nothing in US1/US2 is written until T012 lands.**

- [ ] T004 [P] Write `tests/test_page_report.py` refusal test: values, secrets, credentials and a full URL with query string never appear in the built report (fails — module absent)
- [ ] T005 [P] Write `tests/test_page_report.py` substance test: identity, shape, section and decision of every descriptor **do** appear, so refusal cannot pass on an empty builder
- [ ] T006 Create `engine/autofill/page_report.py` with a pure `build(descriptors, decisions, *, captured_at, ats, url_host, counts) -> dict` — no I/O, no `web/` import, `has_value` boolean only
- [ ] T007 Write the round-trip test: valid JSON, every `fields[]` entry carries the full key set even when empty
- [ ] T008 Add `POST /api/bridge/page-report` in `web/routes_bridge.py` writing `data/reports/page-<ISO>.json`, and a report list + download route in `web/routes_api.py`
- [ ] T009 Add "Save page report" to the companion panel in `extension/content/panel.js` and its message handler in `extension/content/main.js`
- [ ] T010 List page reports on `web/templates/diagnostics.html` with download links
- [ ] T011 Extend `tests/test_secret_hygiene.py` to assert no report can carry a secret, credential or pairing token
- [ ] T012 **Capture the applicant's real Intel Workday page** and record in `baseline.txt`: true per-scan field count, whether `_frame_seen` is summing stale frames, and section-detection coverage. **(A4)** This gates T028/T029 and the *validation* of T018 — it does **not** gate US1/US2, whose three causes are read from source and certain.

**Section context plumbing (contract), needed by both US1 and US2**

- [ ] T013 Write the parity test extension in `tests/test_extension_assets.py` for `section_label`/`section_index` across `scanner.js` and `watcher.py` (fails)
- [ ] T014 Write the protocol tolerance test: a descriptor carrying unknown keys does not cause `ext_protocol` to reject the whole fields message (the 020 `Literal` lesson), and one missing the new keys still validates
- [ ] T015 Extend `formContext()` in `extension/content/scanner.js` to resolve `section_label` (fieldset legend → automation-id section/panel → role=group/region → preceding heading → `""`) using `stripControls()`, and compute `section_index` per scan without stamping the DOM
- [ ] T016 Mirror the same resolution byte-for-byte into `SERIALIZE_JS` in `engine/autofill/watcher.py`
- [ ] T017 Add `section_label: str = ""` and `section_index: int = 0` to `Descriptor` in `engine/autofill/ext_protocol.py`, keeping `PROTOCOL_V` at 1

**Checkpoint**: the fixture below is buildable now; T012 refines it when the capture arrives.

- [ ] T018 Build `tests/fixtures/ats_pages/workday_my_experience.html` (~150 fields, repeated work-history and education blocks, Workday-shaped `aria-haspopup=listbox` dropdowns, `data-automation-id` identity, unlabelled fields, and the exact labels the applicant reported: "Country/Region*", "State", "Country/Region Phone Code*", "Location", "I currently work here", "Overall Result (GPA)" ×2). **(A4)** Built from the mechanisms proven in R1 plus the applicant's own report; T012 validates and refines it rather than blocking it.

---

## Phase 3: US1 — Every question appears once, named, and grouped (P1)

**Goal**: the panel becomes readable on the real page.
**Independent test**: load the fixture, run a fill pass, assert one named row per distinct question grouped by section.

- [ ] T019 [P] [US1] Write `tests/test_page_answers.py` case: two descriptors, same question, same section → one row (fails today, two rows)
- [ ] T020 [P] [US1] Write the case: same question, **different** sections → two rows (guards over-collapsing)
- [ ] T021 [P] [US1] Write the case: a collapsed row retains every `je_idx` behind it
- [ ] T022 [US1] De-duplicate in `page_answers.build` by `(section_label, section_index, normalized question)`. **(A3)** `je_idx` MUST stay a **string** — `panel.js` uses it as one in five places (`:773,778,797,827,828`) and it feeds the `_RENDERED` digest. Add `je_idx_all: list[str]` alongside it and add that key to `_RENDERED`. Purely additive. Preserve today's answer-wins-over-skip precedence.
- [ ] T023 [P] [US1] Write `tests/test_ext_backend.py` case: a whitespace-only `label_text` yields no row (fails — currently a blank row)
- [ ] T024 [P] [US1] Write the case: label empty but `automation_id` present → row named from the humanized automation id
- [ ] T025 [US1] Add `.strip()` and the `automation_id` → `name` → `id` humanizing fallback to `question_of()` in `engine/autofill/ext_backend.py`; return `""` when all fail so `note_answer` skips it
- [ ] T026 [P] [US1] Write the pruning test: a `je_idx` absent from the last N scans of a document stops being reported outstanding (fails — `_page_entries` only clears at session start)
- [ ] T027 [US1] Prune stale entries from `_page_entries` in `ext_backend`, keyed by last-seen scan sequence per document
- [ ] T028 [P] [US1] Write the `_frame_seen` test for whatever T012 revealed — stale frame counts must not inflate `total_seen`
- [ ] T029 [US1] Fix `_frame_seen` accumulation in `ext_backend` per T028
- [ ] T030 [P] [US1] Write the panel test: rows render under section headings, and an undetermined section falls back to today's flat group
- [ ] T031 [US1] Group rows by section in `extension/content/panel.js`, keeping the existing patch-in-place reconcile and the focus guard intact
- [ ] T032 [US1] Make "Show me" cycle through every element behind a collapsed row in `panel.js`
- [ ] T033 [US1] Browser test in `tests/test_browser_controller.py` (or a new `-m browser` case) against `workday_my_experience.html`: no duplicate question within a section, no blank row, sections grouped
- [ ] T034 [US1] Measure `reconcile()` on the 150-field fixture; record in `baseline.txt`; must stay inside one animation frame

**Checkpoint**: US1 is independently shippable — the panel is readable even with nothing else done.

---

## Phase 4: US2 — Work history and education fill themselves (P1)

**Goal**: the biggest cut to the 149.
**Independent test**: two experience entries + one education entry against a form with two work blocks and one education block.

- [ ] T035 [P] [US2] Write `tests/test_history_answers.py`: section index 1 returns `experience[1]` (fails — module absent)
- [ ] T036 [P] [US2] Write the **critical** case: index 2 with only 2 entries returns `None`, never entry 0 or 1
- [ ] T037 [P] [US2] Write the case: an entry with an empty GPA returns `None` for `edu_gpa`, never a value from another entry
- [ ] T038 [US2] Create `engine/autofill/history_answers.py` — pure, `value_for(tag, section_index, resume_sections) -> str | None`
- [ ] T039 [P] [US2] Add `location` and `is_current` to `ExperienceEntry` and `field_of_study`, `gpa` to `EducationEntry` in `engine/resume_extract.py`, all defaulting empty
- [ ] T040 [US2] Write the back-compatibility test: a v2.0.0 `resume_sections` blob still validates against the extended models
- [ ] T041 [P] [US2] Add `exp_employer`, `exp_title`, `exp_start`, `exp_end`, `exp_current`, `exp_location`, `edu_school`, `edu_degree`, `edu_field`, `edu_gpa`, `edu_start`, `edu_end` to `engine/autofill/vocab.py` with their question patterns
- [ ] T042 [US2] Write the classification test: "Overall Result (GPA)", "I currently work here", "Company", "School or University" classify to the right tags
- [ ] T043 [US2] Route history tags through `field_core.decide` in `engine/autofill/field_core.py`, passing `section_index` from the descriptor
- [ ] T044 [US2] Write the end-to-end fill test against `workday_my_experience.html`: block 2 gets entry 2, block 3 (no entry) is left for the applicant
- [ ] T045 [US2] Add the work-history / education editor to `web/templates/profile.html` with save routes in `web/routes_api.py`
- [ ] T046 [US2] Write the test that a profile correction is the value used on the next pass
- [ ] T047 [US2] Re-capture the real page and record the new needs-you count against 149 in `baseline.txt` (SC-002: ≥60% reduction)

---

## Phase 5: US3 — Interactive AI is fast and never fails silently (P2)

- [ ] T048 [P] [US3] Write `tests/test_upgrade.py` case: an applicant-initiated request during an active upgrade pass is served next (fails — stand-down is fill-session only)
- [ ] T049 [US3] Add an interactive-request gate to `engine/upgrade.py` and widen `_wait_out_any_session` to honour it
- [ ] T050 [US3] Write the starvation test: a tailoring request during a background pass resolves inside its budget and `inference.max_observed_concurrency()` stays 1
- [ ] T051 [P] [US3] Write the browser test: an empty/dropped tailoring response shows a message rather than nothing (fails — `JSON.parse("")` throws)
- [ ] T052 [US3] Guard the `hx-on::after-request` handler in `web/templates/job_detail.html` with a fallback message for empty and non-JSON responses
- [ ] T053 [P] [US3] Write `tests/test_matcher.py` cases for purpose-aware tier: interactive prefers cloud when a key exists; bulk stays local even then
- [ ] T054 [US3] Make `scoring_tier()` purpose-aware in `engine/matcher.py` and add the `AI_INTERACTIVE_TIER` setting; keep `PREFER_LOCAL_LLM` honoured for bulk only. **(A2)** MUST be a **keyword-only `purpose` parameter defaulting to today's exact behaviour** — `scoring_tier()` is called zero-arg by `profile_import.py:149`, `resume_extract.py:250`, `upgrade.py:236` and `matcher._chat`, and asserted in `test_matcher.py:100-116,224-238` and `test_inference.py:231`. Those assertions must pass unchanged.
- [ ] T055 [US3] Write the fallback test: a cloud failure, timeout or rate-limit falls through to on-device with no applicant action
- [ ] T056 [US3] Write the offline test: with no key and no network every AI surface behaves exactly as v2.0.0
- [ ] T057 [US3] Rewrite the AI section of `web/templates/settings.html` to state plainly what leaves the machine under each choice
- [ ] T058 [US3] Stream tailoring output in `engine/local_llm.py` + `engine/tailor.py`, rendering progressively in `job_detail.html`
- [ ] T059 [US3] Cut the cover-letter token budget in `engine/tailor.py`; record the before/after generation time in `baseline.txt`
- [ ] T060 [US3] **Measure** KV-cache quantization (`type_k`/`type_v`) and a right-sized `n_ctx` in `engine/local_llm.py`; adopt only if measurably faster, otherwise record as a dead end in `baseline.txt`. **(A9)** Any such setting MUST go through the existing `_load_model` retry so a build that rejects it falls back rather than breaking all on-device AI.
- [ ] T061 [US3] Measure a tailoring request on each tier and record the multiple (SC-006: ≥10x)

---

## Phase 6: US4 — The app learns the answers I type (P2)

- [ ] T062 [P] [US4] Write `tests/test_observed_answers.py` refusal cases: credential, `selfid_*`, SSN, date of birth, government id and bank detail store **nothing** (fails — module absent)
- [ ] T063 [P] [US4] Write the paired substance case: an ordinary question **does** store, so refusal cannot pass on a no-op
- [ ] T064 [P] [US4] Write the predicate cases: a value present on first sight is **not** captured; empty-then-filled **is**; a value the app filled is not
- [ ] T065 [US4] Add the "seen empty" bit to the per-document ledger and an `observed` outcome in `engine/autofill/field_core.py`
- [ ] T066 [US4] Add `answer_bank.record_observed()` in `engine/autofill/answer_bank.py` with the deny-list applied **before** any copy or log. **(A1)** It MUST NOT delegate to `save_with_provenance` — that function's `ON CONFLICT … DO UPDATE SET` is **unconditional** (`answer_bank.py:109`) and would destroy confirmed answers. Write a guarded upsert (`WHERE answer_bank.source IN ('observed','model')` on the conflict branch) inside one transaction. Do not change `save_with_provenance`; its other callers rely on overwriting.
- [ ] T067 [US4] Write the provenance write-rule tests: no row → insert; `observed` → update; `user`/`confirmed`/`auto_saved` → no write; `model` → overwrite
- [ ] T068 [US4] Route observed answers from `_handle_fields` in `engine/autofill/ext_backend.py`
- [ ] T069 [US4] Write the reuse test: a learned answer is offered for the same question on a different application
- [ ] T070 [US4] Create `web/templates/learned_answers.html` + routes: list, edit, delete, and "forget everything learned"
- [ ] T071 [US4] Write the test that "forget everything learned" removes only `observed` rows
- [ ] T072 [US4] Add one-click "Save to profile" for observed answers whose tag is a known profile fact — and the test that the profile is **never** written without it
- [ ] T073 [US4] Extend `tests/test_secret_hygiene.py`: a denied value appears in no log, report, diagnostic or row

---

## Phase 7: US5 — The panel goes where I put it (P3)

- [ ] T074 [P] [US5] Write the browser test: dragging the header moves the panel and it stays on release (fails — no drag)
- [ ] T075 [US5] Add header drag in `extension/content/panel.js`, writing `right`/`bottom` offsets with `setProperty(..., "important")`
- [ ] T076 [P] [US5] Write the persistence test: the position restores after a reload
- [ ] T077 [US5] Persist `je_panel_pos` in `chrome.storage.local` and restore on build
- [ ] T078 [P] [US5] Write the clamp test: a position saved off-screen restores fully inside the viewport
- [ ] T079 [US5] Clamp on restore and on viewport resize in `panel.js`
- [ ] T080 [US5] Write the hostile-CSS test (`div{position:static!important}`) — placement still wins; add "Reset position" and its test
- [ ] T081 [US5] Add the drag affordance (cursor, hit area) to `extension/content/overlay.css`

---

## Phase 8: US6 — More of my facts, and more jobs (P3)

- [ ] T082 [P] [US6] Write the round-trip tests for `phone_country_code`, `address_line2`, `work_auth_expiry`, `security_clearance`, `drivers_licence`
- [ ] T083 [US6] Add those facts to `engine/db.py` profile columns, `profile_answers._DIRECT` and `web/templates/profile.html`
- [ ] T084 [US6] Write the test that a `profile_fact_missing` row carries a deep link to the exact profile field
- [ ] T085 [US6] Emit the profile field anchor in `page_answers.build` and render it as a link in `panel.js`
- [ ] T086 [P] [US6] Write recorded-response parse tests for `recruitee`, `teamtailor`, `personio`, `breezy`, `jazzhr` (fixtures under `tests/fixtures/boards/`)
- [ ] T087 [US6] Create `engine/ingest/{recruitee,teamtailor,personio,breezy,jazzhr}.py` on the `base.py` pattern and register them in `engine/ingest/__init__.py`
- [ ] T088 [US6] Add them to `FULL_BOARD_SOURCES` in `engine/pipeline.py` and write the delisting test
- [ ] T089 [P] [US6] Create `engine/ingest/{adzuna,themuse}.py` behind an optional free key, added to `SCRAPED_SOURCES`
- [ ] T090 [US6] Write the isolation test: an induced failure in one source leaves every other source's results intact
- [ ] T091 [US6] Write the politeness test: every new source routes through `base.py`'s per-domain rate limiter

---

## Phase 8b: Remediation from `/speckit.analyze` (do these with their phase)

These close findings A1, A5–A10. A1, A2, A3, A4 and A9 are already folded into
the tasks above. See [analysis.md](./analysis.md).

- [ ] T106 [US2] **(A5)** Extend the extraction schema in `_SYSTEM` (`engine/resume_extract.py:85`) to emit `location` and `is_current` for experience and `field_of_study` and `gpa` for education — otherwise T039's new fields are never populated and US2 fills nothing from a fresh resume. Re-measure the assembled prompt against the documented safe band (a >6k-char prompt failed silently 100% of the time) and record the length in `baseline.txt`
- [ ] T107 [US2] **(A5)** Add a deterministic, zero-AI fallback for `is_current` (empty/"Present"/"Current" end date) and `gpa` (pattern match in `details`), so the new fields work on the basic tier — mirroring the existing `_EMAIL_RE`/`_PHONE_RE` contact fallback
- [ ] T108 [US4] **(A6)** Write the failing test first: an **unclassified free-text** question the applicant answers by hand is captured. `field_core.decide` returns a plain `skip` (not `settle`) when `tag == "free_text_unknown"` (`field_core.py:287-290`), so a predicate keyed only on the settle path misses every essay answer — the class the applicant most wants learned. Then make the predicate cover both branches
- [ ] T109 [US3] **(A7)** Add an explicit unknown-model / auth-failure path to `engine/matcher._chat_cloud`: name the problem (retired model id, bad key, rate limit) and fall back on-device. A cloud misconfiguration must never read as "the AI is broken" — that is the exact silent-failure class FR-022 exists to remove
- [ ] T110 [US1] **(A8)** Surface `MAX_PAGE_ENTRIES` truncation through the existing `truncated` channel in `page_answers`/`panel.js` instead of dropping entries silently at `ext_backend.py:775`; write the test that a page exceeding the cap says so
- [ ] T111 [US1] **(A10)** Pin the pruning window at **3 consecutive scans** in `engine/autofill/ext_backend.py` and test that a field missing from exactly one scan (a re-render) is **not** evicted
- [ ] T112 **(A2)** Run `tests/test_matcher.py` and `tests/test_inference.py` unchanged after T054 — all eight existing `scoring_tier()` assertions must still pass, proving the zero-arg contract held

---

## Phase 9: Polish, docs and ship

- [ ] T092 [P] Update `docs/USER_MANUAL.md`: page reports, learned answers, the history editor, the AI tier choice, dragging the panel, the new sources
- [ ] T093 [P] Update `README.md` feature list and the AI tier explanation
- [ ] T094 [P] Add `WHATS_NEW["2.1.0"]` entries in `web/main.py`
- [ ] T095 [P] Update `docs/` architecture notes for `history_answers.py` and `page_report.py`
- [ ] T096 Work the `checklists/safety.md` items and tick each with its evidence
- [ ] T097 Work the `checklists/correctness.md` items and tick each with its evidence
- [ ] T098 Version bump to 2.1.0 everywhere it is asserted (app, extension manifest, packaging, the version test)
- [ ] T099 Full unit battery ×2 — counts must exceed 1731, none lost
- [ ] T100 Browser suite **alone**, not in background — count must exceed 104
- [ ] T101 Frozen build + `packaging/smoke_test.py`
- [ ] T102 Browser suite **on macOS** — the 020 lesson; a Windows-only pass is not a pass
- [ ] T103 Manual quickstart §4–§9 on the installed build
- [ ] T104 Manual quickstart §10 — the automation line, **including 019's outstanding T076**
- [ ] T105 Tag `v2.1.0`; verify **both** installers by magic bytes + SHA-256 against the release body

---

## Dependencies

```
Phase 1 (T001-T003)
   └─> Phase 2 Foundational (T004-T018)
          T012 (real capture) ──gates──> T018 (fixture) ──gates──> US1, US2
          T013-T017 (section contract) ──gates──> US1 grouping, US2 indexing
   └─> Phase 3 US1 (T019-T034)
          └─> Phase 4 US2 (T035-T047)     [needs section_index from US1]
   └─> Phase 5 US3 (T048-T061)            [independent]
   └─> Phase 6 US4 (T062-T073)            [independent]
   └─> Phase 7 US5 (T074-T081)            [independent]
   └─> Phase 8 US6 (T082-T091)            [independent]
   └─> Phase 9 (T092-T105)                [needs all]
```

## Parallel opportunities

- All of Phase 2's test-writing (T004, T005) before T006.
- US3, US4, US5 and US6 are mutually independent and independent of A→B→C.
  Once Phase 2 lands, four workstreams can proceed at once.
- Within US6, the five keyless sources (T086/T087) are independent of each
  other and of the profile facts (T082-T085).
- All of Phase 9's documentation (T092-T095) in parallel.

## Implementation strategy

**MVP is US1 alone.** A readable panel is shippable on its own and is the
difference between Apply Assist being usable and unusable on Workday.

**Then US2**, which is the largest measurable reduction in work left to the
applicant.

US3–US6 are additive and can land in any order after that.

## Independent test criteria

| Story | Independently testable by |
|---|---|
| US1 | Load `workday_my_experience.html`, run a fill pass, assert one named row per distinct question grouped by section |
| US2 | Two experience + one education entry against a form with two work blocks and one education block |
| US3 | Issue a tailoring request during a background AI pass; force an empty response |
| US4 | Simulate typing into a declined field; assert storage and the deny-list, both directions |
| US5 | Drag, reload, resize small, hostile CSS, reset |
| US6 | Round-trip each new profile fact; parse each source's recorded response; induce one source failure |

**Total: 112 tasks** — 3 setup, 15 foundational, 16 US1, 13 US2, 14 US3,
12 US4, 8 US5, 10 US6, 7 analysis remediation, 14 polish/ship.

## Analysis remediation index

| Finding | Severity | Closed by |
|---|---|---|
| A1 `save_with_provenance` overwrites unconditionally | CRITICAL | T066 (rewritten) |
| A2 `scoring_tier()` zero-arg contract | CRITICAL | T054 (rewritten), T112 |
| A3 `je_idx` must stay a string | CRITICAL | T022 (rewritten) |
| A4 manual capture serialised all of P1 | HIGH | T012, T018 (re-scoped) |
| A5 extraction prompt pins the old schema | HIGH | T106, T107 |
| A6 free-text skip branch missed by capture | HIGH | T108 |
| A7 retired cloud model id reads as "AI broken" | MEDIUM | T109 |
| A8 silent `MAX_PAGE_ENTRIES` truncation | MEDIUM | T110 |
| A9 KV quantization can break model load | MEDIUM | T060 (rewritten) |
| A10 pruning window N unfixed | LOW | T111 |
