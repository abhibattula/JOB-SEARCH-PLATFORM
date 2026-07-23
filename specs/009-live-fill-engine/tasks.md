# Tasks: The Live Fill Engine (v0.9.0)

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/http-api.md
**Workflow**: hybrid — every deterministic-logic task follows superpowers TDD
(write test → watch it FAIL → implement → green). Browser-marked tests run
via `pytest -m browser` (excluded from the default fast suite).

**Total**: 27 tasks — Setup 1 · Foundational 4 · US1 7 · US2 4 · US3 7 ·
US4 2 · Polish/Ship 2.

## Phase 1: Setup

- [X] T001 Create pytest.ini (register `browser` marker; `addopts = -m "not browser"`); add an explicit `python -m pytest -m browser -q` step to both jobs in .github/workflows/release.yml (after the fast suite)

## Phase 2: Foundational (blocking)

- [X] T002 [test] Failing tests in tests/test_fields.py: raw-attribute descriptors classify — `first_name`/`last_name`/`given_name` name attrs, `family-name` autocomplete, `years_experience`, `how_did_you_hear`, `salary_expectations`, `cover_letter` (underscore/hyphen separators)
- [X] T003 Implement `[\s_-]*` separator fixes + synonyms in engine/autofill/fields.py (classify/match_option behavior otherwise preserved)
- [X] T004 [P] apply-URL resolution: failing tests in tests/test_apply_urls.py (lever→/apply idempotent, ashby→/application idempotent, greenhouse as-is, unknown as-is, query/fragment preserved) → implement engine/autofill/apply_urls.py; plus tests/test_sources.py ashby applyUrl-preference test → 1-line fix in engine/ingest/ashby.py
- [X] T005 [P] adapters: failing tests in tests/test_adapters.py (Greenhouse `first_name`/`job_application[...]`, Lever `name`/`urls[LinkedIn]`/`resume`, Ashby `_systemfield_*`, shared autocomplete map, `ats_from_url`, unknown→None) → implement engine/autofill/adapters.py

## Phase 3: US1 — Apply Assist actually fills (P1)

- [X] T006 [test] [US1] Failing tests in tests/test_worker.py (Playwright fully faked): commands processed in order; command preempts tick; tick runs only when a job is current; `_assert_worker_thread` raises off-thread; RESOLVE_PENDING ack ≤0.5s; thread survives CLOSE_PAGE/SHUTDOWN_CONTEXT
- [X] T007 [US1] Implement engine/autofill/worker.py (daemon thread, queue.Queue, tick scheduling via get-timeout=2.0s, command handlers)
- [X] T008 [test] [US1] Failing tests in tests/test_watcher.py (FakePage/FakeFrame/FakeLocator — FakeLocator.click raises): stamp-based addressing only; serialize+stamp in one eval; idempotent across ticks; focused-guard; just-before-write re-check; delayed appearance (tick1 empty → tick2 fills); multi-frame merge with MAX_FRAMES bound; re-render refill without duplicate report rows; 3-strike scan-failure tolerance; activity accounting; pending single-slot preserved
- [X] T009 [US1] Implement engine/autofill/watcher.py (tick: frame walk → serialize/stamp JS → adapter-then-generic classify → idempotent fill via `[data-je-idx]` locators reusing `_apply_field_value`/`_value_for_tag`/masked reporting)
- [X] T010 [test] [US1] Failing tests: browser_controller facade — state-machine tests retarget monkeypatch seam `_open_job`→`_dispatch` keeping every assertion; `queue_snapshot`/`status` expose `activity`; `rescan` returns `{forced: true}`; `resolve_pending` routes through the worker; `unrecognized` never produced; tests/test_routes_autofill.py contract updates
- [X] T011 [US1] Rewrite engine/autofill/browser_controller.py as the thread-safe facade (public API + 005-008 semantics preserved; delete `_wire_page_change`/one-shot `_open_job` internals) + web/routes_autofill.py activity/rescan changes
- [X] T012 [US1] web/templates/partials/autofill_status.html: live activity feed ("watching page — N seen · M filled"), waiting_for_form guidance callout, launch/nav/scan branches kept; template render tests first

## Phase 4: US2 — Proof on my machine (P2)

- [X] T013 [test] [US2] Failing tests in tests/test_api.py + test_routes_autofill.py: `GET /practice/apply` + `/practice/frame` render (identity fields, select, file input, delayed-section script, iframe src); `POST /api/autofill/practice` starts a practice queue (409 when active)
- [X] T014 [US2] Implement web/templates/practice_apply.html + practice_frame.html, `/practice/*` routes in web/main.py, `OPEN_PRACTICE` worker path (no DB row), "Test Apply Assist" button on autofill.html
- [X] T015 [US2] Attention polish: `window.reveal(el)` (scrollIntoView + flash class) in web/static/app.js + styles.css; applied to pending-answer block, import region, update banner; template hooks
- [X] T016 [US2] Real-browser fixture suite (`@pytest.mark.browser`): tests/fixtures/ats_pages/{greenhouse_delayed,greenhouse_iframe_host,greenhouse_embed_frame,lever_apply,ashby_application,posting_with_apply_button,typing_race}.html + ThreadingHTTPServer harness + tests/integration/test_autofill_fixture_pages.py (poll queue_snapshot → assert real DOM values; the TEST clicks the Apply button / types during the race; headless via AUTOFILL_HEADLESS=1 honored in `_ensure_context`; skip cleanly when no channel launches)

## Phase 5: US3 — Profile import that imports (P3)

- [X] T017 [test] [US3] Failing tests: tests/test_local_llm.py asserts `Llama(..., n_ctx=8192)`; tests/test_resume_extract.py `_split_chunks` (blank-line boundaries, ~5000 target, no mid-line splits) + `_merge` (ordered concat, casefold dedupe, contact first-non-empty + regex overlay, all-failed→None, one-failed→partial) + local-tier dispatch sends every prompt ≤6000 chars
- [X] T018 [US3] Implement chunked map-reduce local path in engine/resume_extract.py (`extract(text, on_progress=None)`) + n_ctx=8192 in engine/local_llm.py
- [X] T019 [test] [US3] Failing tests in tests/test_profile_import.py (`background=False`): state transitions incl. failed(error); stage/chunk progress; proposal matrix (blank→apply, conflict→keep, identical→"none", lists→merge, edited-sections→keep+warning, `has_differences`, visa fields absent); apply decisions (one save_profile, merge semantics, sections consent sets/clears `sections_edited_at`, search-terms re-derivation unless user-owned, proposal consumed)
- [X] T020 [US3] Implement engine/profile_import.py (updates.py-pattern state machine + proposal builder + apply)
- [X] T021 [test] [US3] Failing route tests in tests/test_api.py: slim `POST /api/profile` (monkeypatch extract/extract_skills to raise — must not be called inline; auto-starts import on upload), `POST /api/profile/import` (+409s), `GET status/proposal` (404 until ready), `POST apply`, `/api/profile/reextract` delegates
- [X] T022 [US3] Implement route changes in web/routes_api.py + `GET /partials/profile/import` in web/main.py; retire PENDING_IDENTITY_CONFLICTS generation (endpoint kept for compat)
- [X] T023 [US3] Templates: partials/import_progress.html (incl. failed state showing the real error with a Retry button per FR-012) + import_review.html (full table, compact zero-diff confirmation with expandable view) + profile.html `#import-region` polling wiring + apply JS + toasts; render tests first

## Phase 6: US4 — Offline model first (P4)

- [X] T024 [test] [US4] Failing tests in tests/test_matcher.py + test_settings.py: `PREFER_LOCAL_LLM` default "1"; `scoring_tier()` → local when model available even with key; toggle off → cloud; local-tier exception falls through to cloud when key present (else re-raises); settings page shows the checkbox
- [X] T025 [US4] Implement in engine/matcher.py (+settings.py default, settings.html checkbox, GET/POST /api/settings plumbing)

## Phase 7: Polish & Ship

- [x] T026 Offline-tier gate: slow test (skipif model absent) — real chunked extraction of a bundled 3-page fixture resume text on the local model returns sections with ≥1 experience entry; plus packaging/smoke_test.py additions (status.activity, import status idle, /practice/apply 200)
- [x] T027 Final gate, in order: docs (README/USER_MANUAL/USER_GUIDE — live watcher, practice run, import review, offline-first); version 0.9.0 (engine/__init__.py, windows.iss, jobengine.spec) + What's New entry; full pytest ×2 AND `pytest -m browser` green; frozen build + smoke; live gate per quickstart (real Greenhouse/Lever/Ashby/Indeed); merge → mirror `001-ai-job-engine` → tag v0.9.0 → both installers verified on the Release page

## Dependencies

- T001 → all test tasks. T002-T005 (Foundational) → US1.
- US1: T006→T007→T008→T009→T010→T011→T012 (worker before watcher before
  facade; T004/T005 feed T009/T011).
- US2: T013-T015 after T011 (practice queues through the facade); T016
  after T012 (asserts activity) — T016 is the release gatekeeper for US1+US2.
- US3: T017→T018 ∥ T019→T020 → T021→T022→T023 (extraction and state
  machine independent until routes).
- US4: independent; before T026 (gate runs with the default preference).
- T026 → T027.

## Implementation strategy

MVP = Foundational + US1 + the T016 fixture suite (the engine provably
fills). Then US2 (visible proof), US3, US4, ship. Full suite green after
every task; browser suite green before any merge.
