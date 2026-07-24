# Tasks: The Copilot Release (v1.0.0)

**Input**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: REQUIRED for engine/ logic (constitution Principle V) — TDD
throughout (superpowers red→green), matching the 009 hybrid pattern.
**Organization**: Setup → Foundational (blocking) → US1 (P1 companion) →
US2 (P2 AI drafts) → US3 (P3 UI overhaul) → Polish/Ship.

## Phase 1: Setup

- [x] T001 Extension scaffolding: create `extension/` (manifest.json MV3 — storage/tabs/alarms, host_permissions http://127.0.0.1/*, content_scripts <all_urls> all_frames:true run_at document_idle, minimum_chrome_version 116; empty module files background/{service-worker,socket,protocol,tabs,badge}.js, content/{main,scanner,filler,overlay}.js, content/overlay.css, popup/{popup.html,popup.js}); gitignore `extension/pairing.json`; Chrome loads it unpacked without errors
- [x] T002 [P] DB migrations (additive, in `engine/db.py` _MIGRATIONS): answers.provenance/drafted_at/source_job_id; jobs (applications) follow_up_at/notes; new table ai_drafts; settings key bridge_secret generated on first init_db; tests in `tests/test_db.py` extend the migration + concurrent-init suites
- [x] T003 [P] Protocol schemas `engine/autofill/ext_protocol.py` (pydantic envelope v1 + every message/FillItem/Descriptor from contracts/bridge-protocol.md, 1MB bound, strict validation) with `tests/test_ext_protocol.py` round-trip + malformed/oversized rejection tests

## Phase 2: Foundational (blocking prerequisites)

- [x] T004 Extract `engine/autofill/field_core.py` from `watcher._process_field` (sacred-non-empty, focused-guard, classify → adapters-then-generic, option matching, ledger bookkeeping, outcome vocabulary) with `tests/test_field_core.py`; `watcher.py` delegates to it; ALL existing 009 watcher/browser tests stay green unchanged
- [x] T005 `scripts/stamp_extension.py` (materialize repo `extension/` → `<data_dir>/extension/`, write pairing.json {port, secret, app_id}; idempotent, version-stamped) + `desktop.py` calls it after port bind + dev-mode equivalent in `web/main.py` startup; unit tests for stamping in `tests/test_stamp_extension.py`
- [x] T006 Bridge server `web/routes_bridge.py`: `WS /ws/ext` (hello auth vs bridge_secret → 4401, version gate → 4426, single-session supersede → 4409, ping/pong, registers send-callable with ext_backend), `GET /api/bridge/info`, `GET /api/bridge/file/<token>` one-time 60s resume fetch; wired in `web/main.py`; `tests/test_routes_bridge.py` (starlette WS test client: auth, supersede, token single-use)

## Phase 3: US1 — Companion fills in the user's Chrome (P1) 🎯 MVP

- [x] T007 [US1] `engine/autofill/ext_backend.py` TDD (`tests/test_ext_backend.py` with fake sender): session state {connected, version, last_seen}, command translation (OPEN_JOB→open_tab+watch_start, CLOSE_PAGE→close_tab, FORCE_TICK→no-op safe), inbound `fields`→field_core decisions→`fill` batches followed by an `overlay_state` push (app-computed seen/filled/drafts summary to the top frame), `fill_result`→existing `_record`, `page_event` handling (nav/tab_closed→interrupted, frame_gone→ignore [ledger keys die with the doc token], submit_detected→pending next-action), credential gate: `kind:"secret"` items only when the sending frame's registrable domain matches the credential entry (frame URL from the `fields` event, not the job URL), secret-redaction assertions (no secret in any report/snapshot/log record)
- [x] T008 [US1] `browser_controller.py` backend routing: `_state.backend` chosen at start_queue (extension iff heartbeat <10s, AUTOFILL_BACKEND=auto|extension|playwright override), sticky per queue; disconnect mid-queue → interrupted + resume offers wait/switch; status payload adds `backend` + `extension {connected, version, last_seen}`; extend `tests/test_browser_controller.py` (TestFacade010) + `tests/test_routes_autofill.py`
- [x] T009 [P] [US1] Service worker JS: `background/socket.js` (pairing.json fetch each attempt, backoff 1s→30s, 20s ping, chrome.alarms watchdog), `background/service-worker.js` + `tabs.js` (open/close/track, sender.frameId routing) + `badge.js` (green/gray) + `protocol.js` (envelope validation, logging helper that structurally drops fill values)
- [x] T010 [P] [US1] Content scripts: `content/scanner.js` (SERIALIZE_JS-parity descriptors, DOM-attribute stamps + doc token, MutationObserver 500ms debounce + 2s safety poll + post-fill rescan), `content/filler.js` (native-setter + input/change events, just-before-write recheck, select/checkbox, DataTransfer file attach, kind:secret fill-and-forget, NO .click() anywhere), `content/main.js` (port lifecycle, orphan detection)
- [x] T011 [P] [US1] Overlay `content/overlay.js/.css`: top-frame closed-shadow-DOM slide-in panel (connected state, seen/filled counts from `overlay_state`, per-field outcome chips, ai_draft flag styling, "you click submit" reminder, zero page-interacting controls) + `popup/popup.html/js` (status, "Fill this page" button → `fill_here`, recovery pairing input)
- [x] T012 [US1] Ad-hoc mode: `fill_here` → job-less session in browser_controller/ext_backend (tab-keyed report, refuse when queue job actively filling), `POST /api/autofill/adhoc/link` (link URL→existing job by URL match or create on confirm); tests in test_ext_backend + test_routes_autofill
- [x] T013 [US1] New fixtures `tests/fixtures/ats_pages/`: react_controlled.html (echo-mirror asserts native-setter path; plain .value= must fail), react_select_dropdown.html (custom combobox → needs_manual, no click), file_upload_input.html (DataTransfer attach echo), essay_question.html (free-text for US2 reuse)
- [x] T014 [US1] Extension integration suite `tests/integration/test_extension_fixture_pages.py` (browser-marked): launch_persistent_context --load-extension with test-stamped pairing.json against real app on ephemeral port; cover delayed-render fill, iframe host cross-frame fill, typing-race (never overwritten), apply-reveal pickup, react_controlled, react_select needs_manual, file attach, SW-kill + reconnect mid-queue (no double-fill), ad-hoc fill_here flow
- [x] T015 [US1] Companion walkthrough page `/companion` (`web/templates/companion.html` + route in `web/main.py`): step-by-step unpacked install with copyable extension path, live connection check via status poll, SmartScreen/dev-mode-nag documentation; frozen-path aware (data-dir path when frozen)

**Checkpoint US1**: full suite + browser suite green; companion fills all
fixture pages in a real Chromium with the real extension; fallback path
(extension absent) runs the 009 engine untouched.

## Phase 4: US2 — Grounded AI drafts (P2)

- [x] T016 [US2] `engine/qa.py` TDD (`tests/test_qa.py`): AI-eligible tag allowlist (free-text question tags only; work-auth/visa/EEO structurally excluded — fail-closed test), grounding assembly (resume sections + profile + nearest saved answers + job title/company/description excerpt), concise 60–120w output (maxlength-aware scaling), grammar-constrained local JSON via matcher._chat tier fall-through, explicit refusal on thin grounding → None (caller leaves field untouched → needs_manual), prompt-size bound test
- [x] T017 [US2] Draft lifecycle: ai_drafts table CRUD in `engine/db.py` + `engine/answers.py` provenance (user/confirmed/auto_saved, saved-answer-match-first unchanged); field_core integration — unmatched free-text with qa-eligible tag → generate → fill with `flag: "ai_draft"` → record outcome `ai_draft` (terminal); works on BOTH backends (extension flag chip; Playwright report only); tests in test_field_core + test_answers
- [x] T018 [US2] Draft review UI + API: `GET /api/autofill/drafts`, `POST /api/autofill/drafts/{id}` (confirm w/ optional edit → answers provenance confirmed + re-fill if still draft-valued; discard), drafts list partial on the Apply Assist screen with reveal(); tests in `tests/test_routes_autofill.py` (Test010Drafts)
- [x] T019 [US2] Submission confirm + auto-save: `page_event submit_detected` → pending next-action; `POST /api/jobs/{id}/submission-confirm` (true → status applied + final on-page draft texts saved provenance auto_saved [captured from last fields scan]; false → dismiss); Profile answers section shows auto-saved badge + edit/delete; tests in test_api + test_ext_backend
- [x] T020 [US2] Practice essay loop: essay question in `web/templates/practice_apply.html` + practice-mode qa stub path; extension integration test: draft filled + flagged on practice page, confirm via API, re-run → bank hit no flag; offline gate `tests/test_offline_gate.py::test_real_local_model_drafts_grounded_answer` (slow-marked: real model, real resume fixture, asserts grounded non-empty ≤150w draft + refusal on empty grounding)

**Checkpoint US2**: draft → flag → confirm/auto-save → reuse proven on
fixtures + practice + real local model.

## Phase 5: US3 — UI overhaul (P3)

- [x] T021 [US3] Design-token layer in `web/static/styles.css`: CSS custom properties (type scale, color roles, spacing, radii, shadows) for light + dark; use frontend-design skill for the identity; existing pages keep rendering (both-themes test suite stays green)
- [x] T022 [US3] Home dashboard: `/` route → `web/templates/home.html` (top 5 matches with scores, stage stats, next-actions list); feed remains at `/feed` (nav updated); `GET /api/next-actions` (draft_review/follow_up/import_ready/submission_confirm derived) in `web/routes_api.py`; tests in `tests/test_api.py` (Test010NextActions) + `tests/test_web.py` route/render tests
- [x] T023 [US3] Apply Assist screen rework `web/templates/autofill.html` + partials: connection card (extension state, /companion link, backend mode indicator), queue with 009 activity feed, drafts review list, practice button; tests: test_routes_autofill payload assertions + template render
- [x] T024 [US3] Tracker board polish — the applied view's `view=board` mode (rendered via feed.html/applied templates in `web/main.py`, no board.html exists): notes + follow-up date per application (`POST /api/jobs/{id}/follow-up`), due follow-ups → next-actions, submission-confirm chip on affected cards; tests in test_api (Test010FollowUps)
- [ ] T025 [US3] Global identity sweep: remaining templates (feed, profile, settings, analytics, practice, companion) restyled on tokens; a11y preserved (existing aria-live/focus/theme tests green; add axe-style checks where cheap)

**Checkpoint US3**: every page coherent in both themes; dashboards live.

## Phase 6: Polish, packaging, ship

- [ ] T026 Packaging: `packaging/jobengine.spec` bundles `extension/` (datas + build-time assert on manifest presence); `packaging/windows.iss` unchanged paths verified; `packaging/smoke_test.py` additions (extension assets stamped + pairing.json present, /api/bridge/info answers, /companion 200, /api/next-actions 200); version 1.0.0 in engine/__init__.py + windows.iss + jobengine.spec; What's New entry in web/main.py
- [ ] T027 Docs: README.md, docs/USER_MANUAL.md (§ companion install + AI drafts + dashboard), docs/USER_GUIDE.md, quickstart walkthrough screenshots-by-text; SmartScreen note; CLAUDE.md already points at 010
- [ ] T028 Final gate, in order: full pytest ×2 AND `pytest -m browser` (both engines' suites) AND slow gates green → frozen build + extended smoke → scripted live gate (extension on real Greenhouse/Lever/Ashby postings, parity vs 0.9.0 counts) + manual checklist per quickstart → merge → mirror `001-ai-job-engine` → tag v1.0.0 → verify BOTH installers on the Release page

## Dependencies

- Setup (T001-T003) → everything.
- T004 (field_core) blocks T007/T017; T005/T006 block T007-T015.
- US1 core chain: T007→T008; T009/T010/T011 [P] after T003; T012 after
  T007/T011; T013 [P] anytime; T14 after T007-T013; T015 [P] after T005.
- US2 after US1 checkpoint (needs fill+flag surfaces): T016 [P-able with
  late US1], T017 after T004+T016; T018/T019 after T017; T020 last.
- US3 after US2 (drafts list/next-actions feed the new screens); T021
  first within US3; T022-T025 parallelizable after T021.
- T026-T028 strictly last.

## Implementation strategy

MVP = Phase 1+2+US1 (companion filling with fallback — independently
shippable). US2 layers drafting onto the same fill pipeline. US3 reskins
on top of stable payloads. One release at the end (user's mega-release
choice) but each checkpoint leaves the app runnable and fully tested.
