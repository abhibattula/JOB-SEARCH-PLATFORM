# Tasks: Apply Assist

**Input**: Design documents from `/specs/005-apply-assist/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-api.md, quickstart.md

**Tests**: Included and REQUIRED (not optional) — Constitution Principle V
("Tested Core Logic") mandates pytest coverage for deterministic engine
logic before it's wired into the pipeline, and this project's established
practice across features 001-004 is TDD throughout.

**Organization**: Tasks are grouped by user story (spec.md priorities
P1-P4), after a Milestone 0 bug-sweep gate (spec FR-020) and a Foundational
phase for infrastructure shared by 2+ stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4); Setup/
  Milestone-0/Foundational/Polish tasks carry no story label (cross-cutting)

---

## Phase 1: Setup

**Purpose**: Dependency and scaffolding groundwork; no behavior yet.

- [ ] T001 [P] Add pinned `llama-cpp-python`, `playwright`, and `keyring` to `requirements.txt`, with a comment noting `llama-cpp-python` needs `--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu` (research.md §3)
- [ ] T002 Create `engine/autofill/__init__.py` package
- [ ] T003 [P] Add `models/` and the Playwright browsers cache directory to `.gitignore` (research.md §3, §4 — these are fetched at build/first-use time, never committed)

---

## Phase 2: Milestone 0 — Bug Sweep (gates everything below)

**Purpose**: Re-verify the existing shipped app (v0.4.2) is clean before any
new code lands, per spec FR-020 / SC-008.

- [ ] T004 Run `python -m pytest -q` (full existing suite); confirm 0 failures as the recorded baseline
- [ ] T005 Fresh dev-mode `pyinstaller packaging/jobengine.spec` build + `packaging/smoke_test.py` run against it; confirm the v0.4.2-clean state holds under the current toolchain
- [ ] T006 Manual click-through of every existing page/action (feed, job detail, profile, analytics, settings, status/stage changes, resume upload + tailoring, refresh trigger); fix anything found here before proceeding to Phase 3

**Checkpoint**: Baseline confirmed clean — any later regression is attributable to new work in this feature.

---

## Phase 3: Foundational (Blocking Prerequisites)

**Purpose**: Infrastructure shared by 2+ user stories (data-model.md; the
field taxonomy backs both US2's fill logic and US3's reuse logic).

**⚠️ CRITICAL**: No US2/US3 work can begin until this phase is complete. US1 does not depend on this phase and may proceed in parallel with it.

- [ ] T007 Add `answer_bank` and `application_answers` tables (idempotent `CREATE TABLE IF NOT EXISTS`) and `user_profile.authorized_without_sponsorship` / `user_profile.visa_status` columns to `engine/db.py`, per data-model.md
- [ ] T008 [P] Test: `tests/test_db.py` — insert/query round trip for both new tables and the new `user_profile` columns; confirm `idx_answer_bank_norm` and the `application_answers(job_id)` index exist
- [ ] T009 [P] `engine/autofill/fields.py` — pure field-taxonomy classifier over plain-dict descriptors (`{tag, type, name, id, label_text, placeholder, aria_label, autocomplete}`), taxonomy per research.md §6 including the open/extensible `eeo_disclosure` category (spec FR-012); legally-sensitive tags matched before generic yes/no catch-alls; `login_*` tags require corroborating context
- [ ] T010 [P] Test: `tests/test_fields.py` — fixture-dict coverage of every taxonomy tag, explicit assertion that `work_authorization`/`sponsorship_requirement`/`eeo_disclosure` win over generic catch-alls, and that `login_email`/`login_password` require corroborating context (not just a bare `type=password`)

**Checkpoint**: Foundation ready — US2 and US3 implementation can now begin.

---

## Phase 4: User Story 1 - Works offline, no signup, out of the box (Priority: P1) 🎯 MVP

**Goal**: AI-quality scoring/tailoring/Q&A drafting with zero setup — no API key, no internet required for the AI itself.

**Independent Test**: Fresh install, no API key ever entered, no internet connection for scoring — resume upload produces AI-quality match scores, visibly labeled distinctly from both cloud-AI and basic-match results (spec Independent Test, US1).

### Tests for User Story 1

- [ ] T011 [P] [US1] Test: `tests/test_local_llm.py` — `available()` true/false paths, `chat()` behavior (mock `Llama`, no real model load in unit tests)
- [ ] T012 [P] [US1] Test: `tests/test_matcher.py` additions — tier-dispatch order (cloud → local → raise when neither available), `scoring_tier()` returns the right label per configured state

### Implementation for User Story 1

- [ ] T013 [US1] `engine/local_llm.py` — lazy module-level `Llama` singleton behind a lock, `available()` (resolves the bundled `.gguf` via `paths.resource_path()`), `chat(messages) -> str` (depends on T011 failing first)
- [ ] T014 [US1] `engine/matcher.py` — rename existing `_chat` body to `_chat_cloud`; add `_chat_local` (delegates to `engine/local_llm.py`); `_chat` becomes cloud → local → raise dispatcher; add `scoring_tier() -> "cloud"|"local"|"basic"` (depends on T012 failing first, T013)
- [ ] T015 [US1] `engine/pipeline.py::_score_new_jobs` — three-way branch on `matcher.scoring_tier()`, tagging `match_json.method` as `"llm"` / `"local"` / `"basic"` (depends on T014)
- [ ] T016 [US1] `engine/db.py::jobs_needing_score` — extend the existing basic→cloud upgrade-path SQL to a three-tier basic→local→cloud upgrade (depends on T015)
- [ ] T017 [US1] `web/templates` — add a distinct visual tag (e.g. `•` prefix) for `method="local"` scores, alongside the existing `~` basic-match prefix, so cloud/local/basic are never visually confused
- [ ] T018 [US1] [P] `packaging/fetch_model.py` — downloads the pinned Qwen2.5-1.5B-Instruct GGUF Q4_K_M revision from Hugging Face, verifies a hardcoded SHA256, writes to gitignored `models/` (research.md §1, §3)
- [ ] T019 [US1] `packaging/jobengine.spec` — bundle `llama_cpp`'s native lib via `collect_dynamic_libs("llama_cpp")` with a build-time assertion (mirrors the existing `tls_client` assertion pattern exactly), add the `.gguf` as a `datas` entry with a size-sanity assertion, add `"llama_cpp"` to `hiddenimports` (depends on T018)
- [ ] T020 [US1] `web/main.py` (or a small new diagnostics route module) — `GET /api/diagnostics/local-llm-selftest`, a thin route calling `local_llm.chat(...)` and returning `{"ok": bool, "reply": str}` (depends on T013)
- [ ] T021 [US1] `packaging/smoke_test.py` — call the new self-test route, assert HTTP 200 + non-empty reply; extend `FATAL_LOG_PATTERNS` with llama.cpp-specific failure substrings (depends on T019, T020)

**Checkpoint**: User Story 1 fully functional and testable independently — offline scoring works with zero setup, upgrades automatically when a cloud key is later added.

---

## Phase 5: User Story 2 - Apply Assist opens and pre-fills applications, human submits (Priority: P2)

**Goal**: A visible, dedicated browser window per shortlisted job, recognized fields pre-filled, human always clicks submit/login.

**Independent Test**: With ≥1 shortlisted job and a saved profile, starting Apply Assist opens that job's real application page in a dedicated visible browser window with recognized fields pre-filled, and no automated click ever lands on a submit or login button anywhere in the flow (spec Independent Test, US2).

### Tests for User Story 2

- [ ] T022 [P] [US2] Test: `tests/test_browser_controller.py` — queue start/current_job/advance/stop state machine, with Playwright fully mocked (no real browser in unit tests)
- [ ] T022a [P] [US2] Test: `tests/test_browser_controller.py` — explicit regression test for FR-008/FR-016 (analyze finding C1): with a mocked Playwright page, assert that no code path in `browser_controller.py` ever invokes a click (or equivalent) on an element classified as a submission or login-completion control, across every method (`start_queue`, `advance`, `stop_queue`, and the field-fill routine) — this is the single most safety-critical invariant in the feature and must be verified by a real failing-then-passing test, not left true only "by construction"
- [ ] T023 [P] [US2] Test: `tests/test_answer_bank.py` — `lookup()` exact-then-fuzzy match, `save()` only reachable via explicit confirmation call, `suggest()` reuses the `matcher._chat` tier dispatcher from US1 (mock `_chat`)

### Implementation for User Story 2

- [ ] T024 [US2] `engine/autofill/answer_bank.py` — `lookup()` (exact-normalized then `rapidfuzz` fuzzy), `save()`, `suggest()` (depends on T022/T023 failing first, and on US1's `matcher._chat` dispatcher)
- [ ] T025 [US2] `engine/autofill/browser_setup.py` — first-use Chromium install (`sys.executable -m playwright install chromium` as a subprocess), progress surfaced via a settings/status mechanism, `PLAYWRIGHT_BROWSERS_PATH` set to `paths.data_dir() / "browsers"` before any Playwright call
- [ ] T026 [US2] `engine/autofill/browser_controller.py` — Playwright lifecycle on its own dedicated background thread, `queue.Queue`-based command interface (FastAPI threads never touch Playwright objects directly), `launch_persistent_context(headless=False)` in a dedicated isolated profile (never the user's default browser, per clarify session), `start_queue(job_ids)`/`current_job()`/`advance()` (user-driven only, never automatic completion detection — spec clarify)/`stop_queue()`; serializes real DOM fields via JS eval and hands them to `fields.classify()`; graceful fallback per FR-009's core-identity-field threshold (name/email/resume-upload) — opens the tab for manual completion and still advances rather than failing (depends on T009, T024, T025)
- [ ] T027 [US2] `web/routes_autofill.py` — thin routes: `POST /api/autofill/setup`, `POST /api/autofill/queue`, `POST /api/autofill/next`, `POST /api/autofill/stop`, `GET /api/autofill/status`, `GET /partials/autofill/status` per contracts/http-api.md (depends on T026)
- [ ] T028 [US2] `web/templates/autofill.html` + `GET /autofill` page — job selection from existing shortlist/status, queue status display, "Done, next application" control (not automatic detection), visible indicator when a job fell back to manual mode (spec FR-009), Chromium first-use install progress (depends on T027)
- [ ] T029 [US2] [P] `packaging/jobengine.spec` — bundle Playwright's runtime driver files via `collect_data_files("playwright")` with a build-time assertion, add `"playwright.sync_api"` to `hiddenimports` (research.md §4 — do not trust Playwright's own PyInstaller hook)
- [ ] T030 [US2] `packaging/smoke_test.py` — add a diagnostic step that launches Chromium and navigates to `about:blank`, asserting success (depends on T029)

**Checkpoint**: User Story 2 fully functional and testable independently — queue opens real application pages, fills recognized fields, never auto-submits or auto-logs-in, degrades gracefully on unreadable sites (including Workday).

---

## Phase 6: User Story 3 - Reusable answer bank with review-before-use for sensitive questions (Priority: P3)

**Goal**: Answer once, reuse everywhere; a per-application record of exactly what was used where; legally-sensitive answers only ever come from a confirmed source.

**Independent Test**: Answer a work-authorization-style question once through the review flow; on a later, different job with the same or a very similarly worded question, the saved answer is applied automatically without being asked again, and no eligibility-related answer is ever visible as "filled" without having gone through a review step at least once (spec Independent Test, US3).

### Tests for User Story 3

- [ ] T031 [P] [US3] Test: `tests/test_answer_bank.py` additions — `application_answers` rows snapshot `answer_used` at write time and are unaffected by a later edit to the corresponding `answer_bank.answer`
- [ ] T032 [P] [US3] Test: fuzzy-match reuse across two differently-worded-but-equivalent questions succeeds, while two genuinely different questions (e.g. "authorized to work" vs. "require sponsorship") do NOT collapse into one answer-bank entry (spec edge case)

### Implementation for User Story 3

- [ ] T033 [US3] `engine/autofill/answer_bank.py::record_application_answer(job_id, question_raw, answer_bank_id, answer_used)` — the only write path into `application_answers` (depends on T031 failing first)
- [ ] T034 [US3] `web/routes_autofill.py::POST /api/autofill/answers/confirm` — the only write path into `answer_bank` (FR-011 invariant), wired to also call `record_application_answer` for the current job (depends on T033)
- [ ] T035 [US3] `web/templates/autofill.html` — pending-confirmation review UI: drafted answer visually marked "AI-drafted, unreviewed" distinct from a confirmed answer, edit-before-confirm control, queue stays paused if the user neither confirms nor dismisses (spec edge case) (depends on T034)
- [ ] T036 [US3] Profile page (`web/templates`) — add `authorized_without_sponsorship` / `visa_status` fields so `answer_bank.suggest()` drafts are grounded in facts the user actually provided

**Checkpoint**: User Story 3 fully functional and testable independently — answered-once questions are never re-asked; every sponsorship/work-authorization/EEO-disclosure answer used traces to a confirmed source; a per-application record exists.

---

## Phase 7: User Story 4 - Saved logins autofill without auto-login (Priority: P4)

**Goal**: Per-domain credentials fill recognized login fields; the human always clicks login; secrets are never re-displayed or logged.

**Independent Test**: Save a credential for a domain once; on a later visit to that domain's login page, the email/password fields are pre-filled and the login button is never clicked automatically; the saved password cannot be viewed again through any part of the app after saving (spec Independent Test, US4).

### Tests for User Story 4

- [ ] T037 [P] [US4] Test: `tests/test_credentials.py` — save/get/delete against a `keyring` in-memory test backend; confirm delete clears both the keychain entry and the `cred_email:{domain}` settings row (data-model.md invariant); confirm no code path returns a saved password from any "list" function

### Implementation for User Story 4

- [ ] T038 [US4] `engine/credentials.py` — explicit `keyring.set_keyring(...)` call at import time branching on `sys.platform` (does not rely on auto-selection, per research.md §8); `save(domain, email, password)`, `get(domain)`, `delete(domain)`, `list_domains()` (settings-table read only, never touches the vault) (depends on T037 failing first)
- [ ] T039 [US4] [P] `packaging/jobengine.spec` — conditional `keyring.backends.Windows` / `keyring.backends.macOS` hiddenimports, mirroring the existing `plyer.platforms.*` pattern
- [ ] T040 [US4] Settings page + routes — `POST /api/credentials`, `GET /api/credentials`, `DELETE /api/credentials/{domain}` per contracts/http-api.md; write-only UI reusing the `settings.py::mask_key` masking idiom for the displayed email hint; password never echoed in any response (depends on T038)
- [ ] T041 [US4] `engine/autofill/browser_controller.py` — wire `login_email`/`login_password` classified fields to `credentials.get(domain)`; login button is filled but never clicked, same as the submit-button rule (depends on T026, T038)

**Checkpoint**: User Story 4 fully functional and testable independently — saved logins autofill without auto-submission; secrets never resurface anywhere, including logs.

---

## Phase 8: Polish & Ship

**Purpose**: Cross-cutting wrap-up once all four stories are complete.

- [ ] T042 [P] Docs — README/USER_MANUAL/USER_GUIDE: new "Apply Assist" section, including the one-time ToS/anti-bot disclaimer text shown before first use (research.md risk note)
- [ ] T043 Bump `APP_VERSION` (`engine/__init__.py`), `packaging/windows.iss` (`MyAppVersion`), `packaging/jobengine.spec` (`CFBundleShortVersionString`) in lockstep, per this project's existing convention
- [ ] T044 Full verification pass: unit suite green ×2, live walkthrough of every item in `quickstart.md`'s verification checklist, frozen rebuild + `packaging/smoke_test.py` (both new diagnostics — local-llm-selftest and Chromium-launch — passing)
- [ ] T045 Tag the release; confirm both CI installers (`windows-installer`, `mac-dmg`) go green and the installer-size increase is the one the user already accepted

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Milestone 0 (Phase 2)**: No dependencies on Phase 1's content, but run after it for convenience; BLOCKS every phase below (spec FR-020 — must confirm a clean baseline before new work).
- **Foundational (Phase 3)**: Depends on Milestone 0 passing. BLOCKS US2 and US3 (both need `fields.py` and the new tables). Does NOT block US1.
- **US1 (Phase 4, P1)**: Depends on Milestone 0 only — may proceed in parallel with Phase 3.
- **US2 (Phase 5, P2)**: Depends on Foundational (Phase 3) and reuses US1's `matcher._chat` dispatcher (via `answer_bank.suggest()`), so US1 should land first or alongside.
- **US3 (Phase 6, P3)**: Depends on US2 (extends the confirm/pause flow US2 already establishes).
- **US4 (Phase 7, P4)**: Depends on Foundational (Phase 3) for the classifier's `login_*` tags and on US2 (Phase 5) for the browser controller it wires into. Independent of US3.
- **Polish (Phase 8)**: Depends on all four stories being complete.

### Within Each Story

- Tests MUST be written and FAIL before implementation (TDD, Constitution Principle V).
- Data/module layer before route layer before template/UI layer.
- Packaging changes for a story's native dependency land alongside that story's implementation, not deferred to Polish (each is its own tls_client-shaped risk — verify immediately, don't batch the risk).

### Parallel Opportunities

- T001, T003 (Setup) in parallel.
- T008, T009+T010 (Foundational tests/classifier) in parallel with each other; both block US2/US3 start.
- US1 (Phase 4) can be built in parallel with Foundational (Phase 3) by a second contributor, since it has no dependency on it.
- Within US1: T011+T012 in parallel; T018 (model fetch) in parallel with T013/T014 (code) since they're independent until T019 bundles them together.
- Within US2: T022+T023 in parallel; T029 (Playwright packaging) in parallel with T024-T028 (application logic) until T030 needs both.

---

## Parallel Example: User Story 1

```bash
# Tests together:
Task: "tests/test_local_llm.py - available()/chat() with mocked Llama"
Task: "tests/test_matcher.py additions - tier dispatch order"

# Model fetch alongside code (independent until packaging step):
Task: "packaging/fetch_model.py - download+verify pinned model"
Task: "engine/local_llm.py - Llama singleton, available(), chat()"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup → Milestone 0 → (Foundational may run in parallel, not required for US1)
2. Phase 4: User Story 1
3. **STOP and VALIDATE**: no API key, no internet — scoring works, visibly tiered
4. This alone already ships real value (removes the biggest existing setup-friction point)

### Incremental Delivery

1. Setup + Milestone 0 + Foundational → base ready
2. Add US1 → validate independently → ships local AI
3. Add US2 → validate independently → ships the core apply-co-pilot flow
4. Add US3 → validate independently → ships answer reuse + audit record
5. Add US4 → validate independently → ships saved-login autofill
6. Polish → docs, version bump, full verification, tag

---

## Notes

- [P] tasks touch different files with no dependency on each other.
- Every native-dependency packaging task (T019, T029, T039) gets its own
  build-time assertion AND its own `smoke_test.py` extension in the same
  phase it's introduced — never batched into Polish — per the v0.4.0
  tls_client lesson (`specs/004-get-hired/patch-0.4.1.md`).
- One residual risk accepted at checklist time (`checklists/safety.md`
  CHK002) remains implementation-level, not a requirements gap: T026 should
  avoid auto-filling a page's last remaining required field on a form
  suspected of JS auto-submit-on-completion behavior. CHK004 (an
  after-the-fact way to verify no submit/login click ever occurred) is now
  addressed directly by T022a, added during `/speckit.analyze` (finding C1)
  rather than left as a manual-verification-only concern.
- `/speckit.analyze` (2026-07-20) also resolved: FR-008's "Next"/"Continue"
  allowance narrowed to match what's actually built (T026 automates no
  button clicks at all — intra-form page navigation stays manual this
  phase); the `eeo_disclosure` category broadened across SC-005/data-model.md
  for consistency with FR-012; a quickstart.md verification item added for
  FR-004 (model updates ride Check-for-Updates, no separate downloader).
