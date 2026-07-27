# Tasks: The Fill Release (feature 016, v1.6.0)

**Input**: Design documents from `/specs/016-fill/`
**Prerequisites**: plan.md, spec.md (amended per checklists/fill.md),
research.md (R1–R14), data-model.md, contracts/, quickstart.md,
constitution v1.1.4 (apply-opener clarification)

**Tests**: REQUIRED (constitution V + superpowers TDD) — every
deterministic engine change lands red→green; the fill path gets
real-browser E2E in BOTH browser families with a zero-submit assertion;
the frozen gate runs with AI isolation as the new default and gains a
tailor call.

**Organization**: Setup → Foundational (protocol + drafter + storage) →
US1 pipeline → US2 choice-aware → US3 on-page → US4 AI runtime →
Verify/docs/ship.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an
  incomplete task).

---

## Phase 1: Setup

- [x] T001 Bump version to **1.6.0** (`engine/__init__.py`,
  `packaging/windows.iss`, `extension/manifest.json`);
  `packaging/check_version.py` OK; add `WHATS_NEW["1.6.0"]` stub in
  `web/main.py`.

---

## Phase 2: Foundational (blocking prerequisites)

- [x] T002 [P] Protocol additions (additive, PROTOCOL_V stays 1) in
  `engine/autofill/ext_protocol.py`: `Descriptor.members`/`required`,
  `type "radio_group"`, `FillItem.kind "radio"`, flag `"needs_you"`,
  messages `rescan` (out) / `scan_error`, `child_tab` (in). Tests
  (`tests/test_ext_protocol.py`): new fields parse, OLD payloads without
  them still parse (`extra="ignore"` + defaults), PROTOCOL_V unchanged.
- [x] T003 `engine/autofill/drafter.py` (NEW, R2/R7) — TDD: write
  `tests/test_drafter.py` FIRST (one-draft-per-key under a 16-thread
  `ensure` hammer; bounded pool ≤2; backoff 30 s→×2→cap 600 s;
  `reset_backoff_for` re-arms once; sensitive tags → immediate
  `failed:sensitive`, model NEVER invoked; option post-validation
  (answer ∉ options → `failed:no_valid_option`); maxlength enforcement;
  `cache_version` bumps per completion; completion side-effect order per
  contracts/drafter-api.md §6), watch it fail, then implement.
- [x] T004 [P] Storage foundations — TDD: `answer_bank` additive columns
  `origin`/`job_id` (guarded ALTER in `engine/db.py` init), scoped
  save/lookup rules in `engine/autofill/answer_bank.py` (job-specific
  prose scoped; lookup for job B ignores other jobs' scoped rows;
  human saves unchanged); `load_h1b_employers()` memoized with
  invalidation on the sponsorship refresh write path. Tests:
  `tests/test_answer_bank.py`, `tests/test_db.py`.

**Checkpoint**: drafter proven under stress with stubs; protocol
backward-compatible; bank scoping in place. No behavior change visible
yet.

---

## Phase 3: US1 — The form I'm looking at gets filled, promptly (P1)

- [x] T005 [US1] Decide-fast loop + incremental fills (R1) — TDD FIRST in
  `tests/test_ext_backend.py`: (a) poisoned-executor guard — any model
  call reached from `handle_message` fails the test; (b) a `fields` batch
  containing knowns + one unknown dispatches the known fills even though
  the unknown's draft (slow stub) never completes; (c) heartbeat/`pong`
  processing stays fresh during a slow draft. Then rework
  `engine/autofill/ext_backend.py::_handle_fields`: decide via
  profile/bank/`drafter.answer_for` only; unknowns → `drafter.ensure`;
  dispatch fills incrementally; drafter completion → ledger clear +
  `rescan` push.
- [x] T006 [US1] Gate removal + activity log (R11) —
  `engine/autofill/browser_controller.py`: single-pending park →
  drafting/activity list (`current_job().activity` per data-model §9);
  retire `resolve_pending`; `rescan()` sends the nudge in extension mode;
  `web/routes_autofill.py`: confirm endpoints bank-only (sentinel guard
  kept), queue POST skips Playwright `preflight()` when
  `ext_backend.is_live()`. SWEEP (the stale-pin lesson): rewrite
  park/pending tests in `tests/test_browser_controller.py`,
  `tests/test_routes_autofill.py`, `tests/test_web.py`; replace
  `conftest.py`'s `_join_pending_drafts_for_tests` teardown with
  `drafter.reset_for_tests()`.
- [x] T007 [P] [US1] Ledger repair (R3) — TDD: `cache_version` stamps in
  `engine/autofill/field_core.py` decisions (terminal `no_match`/
  `needs_manual` retryable when the drafter has a newer answer);
  `_inflight` TTL 20 s + extension-path job outcomes
  (`launch_failed`/`scan_failed`) in `ext_backend.py`. Tests:
  `tests/test_field_core.py`, `tests/test_ext_backend.py`.
- [x] T008 [P] [US1] Tab following (R4) — extension:
  `extension/background/tabs.js` + `service-worker.js` — `tabs.onCreated`
  + `openerTabId` → `child_tab` message; watched set persisted to
  `chrome.storage.session`; app: `ext_backend.py` watch transfer,
  `open_tab` ack 5 s + 1 retry + `pending_open` expiry → `launch_failed`
  + queue advance; wrong-tab drops counted. Tests: transfer/expiry units
  in `tests/test_ext_backend.py`; SW source assertions in
  `tests/test_extension_assets.py`.
- [x] T009 [P] [US1] Discovery decongestion (R5) —
  `extension/content/discovery.js` per-href score cache (re-arm on URL
  change); `ext_backend` score handler reads the memoized employer table
  (T004). Tests: asset assertion (no unconditional interval request) +
  handler unit.
- [x] T010 [P] [US1] Error surfacing (R1/R4) —
  `extension/background/service-worker.js` handles `error` (popup shows
  "busy — stop the queue first" via `extension/popup/popup.js`);
  `extension/content/main.js` reports `scan_error` instead of swallowing;
  `web/routes_bridge.py` doctor gains `dropped_fields`/`scan_errors`;
  Re-scan response gains `nudged`. Tests: `tests/test_routes_bridge.py`,
  `tests/test_extension_assets.py`.

**Checkpoint**: US1 independently testable — knowns fill promptly with a
slow draft in flight; drafts land by themselves; new tabs follow; errors
visible.

---

## Phase 4: US2 — Choice questions answered from the real options (P2)

- [ ] T011 [US2] Scanner grouping (R6) — parity test FIRST
  (`tests/integration/test_pairing_e2e.py::test_serializer_parity`,
  browser marker: same fixture HTML through `extension/content/scanner.js`
  and `engine/autofill/watcher.py`'s serializer → same logical fields).
  Then implement in BOTH: radio groups (name/radiogroup/fieldset; question
  = legend/group label; options = member labels; `je_idx` = first member;
  `members[]`), `required` capture, checkbox-group legend context (NOT
  merged).
- [ ] T012 [US2] Constrained drafting (R7) — TDD: `engine/qa.py::draft`
  and `engine/autofill/answer_bank.py::suggest` receive descriptor ctx
  (type/options/maxlength) via the drafter; pick-one JSON prompt for
  option fields; combobox ≤4-word label; profile-fact yes/no short-circuit
  (no model call — assert via poisoned stub); prose obeys maxlength.
  Tests: `tests/test_qa.py`, `tests/test_answer_bank.py`,
  `tests/test_drafter.py`.
- [ ] T013 [US2] Filler upgrades + version gate (R8) —
  `extension/content/filler.js`: real radio branch (check matched member
  + events), normalized select match (option text from app-side
  `match_option`), combobox harvest widened (listbox `li`, open-listbox
  option classes), honest outcomes; `engine/autofill/watcher.py`: radio
  branch via Playwright `check()` on the member. App-side gate in
  `ext_backend.py`: new kinds only when hello version == APP_VERSION,
  else `needs_you` flag. Tests: `tests/test_extension_assets.py` source
  assertions + gate unit + E2E DOM assertions (T022).
- [ ] T014 [P] [US2] Fixture upgrades (R14) —
  `web/templates/practice_apply.html` + E2E fixture pages: radio yes/no
  group, custom combobox, maxlength field, EEO-style question, an
  apply-opener variant page, a new-tab opener variant, and a server-side
  submit-click log endpoint. Update `tests/test_web.py` practice asserts.

**Checkpoint**: US2 independently testable on the practice form — selects/
radios/comboboxes correct, EEO blank + flagged, honest outcomes.

---

## Phase 5: US3 — Everything happens on the page (P3)

- [ ] T015 [US3] Apply-opener (R9, constitution v1.1.4) —
  `extension/content/opener.js` (NEW): per-ATS allowlist
  (Greenhouse/Lever/Ashby selectors), structural guards (never
  `type=submit`, not inside a form with filled inputs), one-shot per
  `(doc, href)`, queue-driven watched tabs only; wired from
  `extension/content/main.js`; registered in `extension/manifest.json`
  `content_scripts` (load order: before main.js);
  `engine/autofill/adapters.py` carries the selector registry (single
  source, asset-parity-tested).
  `extension/content/click_guard.js` UNTOUCHED. Tests: asset parity +
  guard-untouched assertions; E2E opener case in T022.
- [ ] T016 [US3] On-page panel (R10) — `extension/content/overlay.js`:
  shadow-DOM panel (status, filled/needs-you counters, per-field list
  with jump-to, Fill again, review-and-submit note);
  `extension/content/main.js` handles `rescan`; Fill again → bridge
  message → app clears non-`skipped_existing` ledger entries +
  `drafter.reset_backoff_for(page questions)` + rescan nudge. Tests:
  asset assertions + `ext_backend` fill-again unit.
- [ ] T017 [P] [US3] Highlights (R10) — `extension/content/filler.js`
  renders `ai_draft`/`needs_you` flags as outline + badge keyed by
  `je_idx`; input listener clears; reapplied across rescans while the
  flag holds. Tests: asset assertions + E2E visibility check (T022).
- [ ] T018 [US3] App UI rework (R11) —
  `web/templates/partials/autofill_status.html`: blocking review box →
  passive activity log (drafting/drafted/filled/needs-you, links to the
  bank); `web/templates/autofill.html` presentation; 015 fill-path
  disclosure preserved. SWEEP: `tests/test_web.py` pending-panel asserts
  rewritten to activity-log asserts.

**Checkpoint**: US3 independently testable — opener clicks once, panel
live, highlights clear on edit, user values sacred, zero submit clicks.

---

## Phase 6: US4 — AI can fail without taking the app down (P4)

- [ ] T019 [US4] Isolation default ON (R12) — `engine/inference.py`:
  `_subprocess_enabled()` true unless `JOBS_AI_SUBPROCESS == "0"`.
  Tests (`tests/test_inference.py`): default-ON semantics, `"0"` opt-out,
  `set_executors_for_tests` still bypasses the child; fault containment
  on the DEFAULT path (echo seam: kill child mid-call → clean
  RuntimeError, restart counted, next call works).
- [ ] T020 [P] [US4] Generation bounds + load hygiene (R13) —
  `engine/local_llm.py`: `max_tokens` per purpose in the chat payload
  (json≈1536, draft≈512, prose≈768); `engine/semantic.py`:
  `_load_attempted` guard + embedder `n_batch=256`. Tests:
  `tests/test_matcher.py` stub signature, payload assertions, one-shot
  load attempt.
- [ ] T021 [US4] Tailor hardening (R13) — `engine/tailor.py`: combined
  prompt ≤6k chars, `timeout_s=300`, 1 local attempt (cloud fallthrough
  unchanged); `web/routes_api.py`: 502 carries a human-readable reason;
  `web/templates/job_detail.html`: in-progress state ("can take a few
  minutes") + rendered failure. Tests: `tests/test_tailor.py` (NEW):
  cap, timeout passed, single attempt, persist-on-success (stub), 502
  payload; template assertions in `tests/test_web.py`.

**Checkpoint**: US4 independently testable — induced fault never closes
the app; tailor bounded and honest.

---

## Phase 7: Verification, docs, ship

- [ ] T022 E2E (R14) — extend
  `tests/integration/test_pairing_e2e.py` (BOTH browser families,
  existing real-uvicorn + Playwright harness): apply-opener fixture
  (form appears only after the click), new-tab transfer variant,
  radio/select/combobox DOM-verified fills, EEO blank + flagged, panel
  present, highlights until edit, ZERO submit clicks (server-side click
  log), serializer parity (T011's test goes green here if deferred).
- [ ] T023 Full battery (default isolation ON) — `pytest -q` ×2,
  `-m browser`, `-m slow`, frozen build + `packaging/smoke_test.py`
  (extended: runs under default isolation + tailor smoke call + existing
  015 stamp/doctor gates). Cross-platform sweep: grep for stale pinned
  asserts (the 013/015 lesson — version pins, platform-conditional
  asserts) BEFORE tagging; fix all fallout.
- [ ] T024 Docs + memory — `docs/USER_MANUAL.md` §20 (fill-first flow,
  panel, highlights, apply-opener, sensitive policy, tailor states,
  isolation default), `README.md` companion section, `WHATS_NEW["1.6.0"]`
  final copy; auto-memory updates (job-engine status, apply-assist
  rebuild lessons).
- [ ] T025 Ship v1.6.0 — merge `016-fill`→`main`, mirror
  `main:001-ai-job-engine`, keep the feature branch, tag `v1.6.0`
  (triggers "Release installers"), watch BOTH jobs, verify BOTH
  installers (magic bytes 4d5a/7801 + SHA-256 release-body vs stored
  digests), release notes.

---

## Dependencies

- Phase 2 blocks everything: T003 (drafter) blocks T005/T006/T012/T016;
  T002 (protocol) blocks T005/T008/T013/T016; T004 blocks T005/T012.
- US1 (T005–T010) blocks US3's panel/fill-again (T016) and E2E (T022).
- US2's T011 blocks T013; T014 blocks T022.
- US4 (T019–T021) is independent after Setup — parallelizable with
  US2/US3.
- T022–T025 strictly last, in order.

## Implementation strategy

MVP = Phase 1–3 (US1): a connected companion fills known fields promptly
and drafts land by themselves — visible value on day one. Then US2
(choice correctness), US3 (on-page experience), US4 (containment), then
verify/ship. Each phase ends green before the next starts.
