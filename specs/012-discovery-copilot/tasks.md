# Tasks: The Discovery Copilot (feature 012, v1.2.0)

**Input**: Design documents from `/specs/012-discovery-copilot/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/discovery-bridge.md, quickstart.md

**Tests**: REQUIRED. Per Constitution Principle V, deterministic engine logic and
the bridge trust boundary MUST have pytest coverage before wiring. Hybrid TDD:
red (failing test) → green (implementation) for every engine/protocol unit.

**Organization**: by phase, then by user story (US1 P1, US2 P2, US3 P3). Each
user story is an independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1 / US2 / US3 for story-phase tasks; Setup/Foundational/Polish carry none

## Path Conventions

Repo root: `engine/`, `web/`, `extension/`, `tests/`, `packaging/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: constitution note + test scaffolding so the rest is TDD-ready.

- [x] T001 Add a one-line Principle-III note to `.specify/memory/constitution.md` (PATCH bump 1.1.2 → 1.1.3 + Sync Impact Report entry): the companion MAY read the current page's public job metadata to render a local-only, READ-ONLY discovery overlay — a bounded read-only addition, not a relaxation of the no-click/no-submit/no-bulk-scrape rules.
- [x] T002 [P] Create the discovery fixtures directory `tests/fixtures/discovery_pages/` with three pages: `jsonld_jobposting.html` (schema.org JobPosting JSON-LD with title/hiringOrganization.name/description), `linkedin_jobs_view.html` (LinkedIn `/jobs/view` DOM shape, no clean JSON-LD), `indeed_viewjob.html` (Indeed job-page DOM shape). Each also exposes its detected title/company in the DOM so a test can assert extraction.
- [x] T003 [P] Create empty test modules `tests/test_discovery.py` and `tests/integration/test_discovery_badge.py` with the standard imports/markers (`pytestmark = pytest.mark.browser` for the integration one), ready for red tests.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the engine + bridge plumbing every user story depends on. All TDD.

- [x] T004 [P] Write failing unit test `tests/test_discovery.py::test_get_job_by_url` for a new `db.get_job_by_url(url)` (returns the job dict incl. id for a known url; None otherwise).
- [x] T005 Implement `engine/db.py::get_job_by_url(url) -> dict | None` (SELECT on the existing `jobs.url UNIQUE`; reuse `_row_to_job`/`get_job` shape or a minimal id+status row). Make T004 green.
- [x] T006 [P] Write failing unit test `tests/test_discovery.py::test_grade_company_parity` asserting a new `sponsorship.grade_company(name, employers=None)` returns the same grade/cap_exempt/approvals that the `apply_to_companies` path produces for identical seeded employer records (graded company, unknown company, cap-exempt name).
- [x] T007 Refactor `engine/sponsorship.py`: extract the per-company grading block (~lines 177-200) into `grade_company(name, employers=None) -> dict` (loads `db.load_h1b_employers()` when `employers is None`; returns `{sponsor_grade, cap_exempt, approvals, has_sponsor_data}`), and call it from `apply_to_companies`. Make T006 green; keep existing sponsorship tests passing.
- [x] T008 [P] Write failing unit tests `tests/test_discovery.py` for `discovery.score_page(title, company, description)`: (a) real score+band from a seeded profile+JD; (b) sponsor grade via already-graded company (fast path); (c) on-demand grade for a company only in USCIS records; (d) unknown company → sponsor_grade None + has_sponsor_data False; (e) no resume → needs_resume True + match_score None; (f) already_saved reflects `get_job_by_url`.
- [x] T009 Implement `engine/discovery.py::score_page(...)` (pure; imports only `db`/`basic_match`/`sponsorship`): profile via `db.get_profile()`; match via `basic_match.score(resume_text, title, description, extra_skills=set(profile.get("skills") or []))`; **band via fixed cutoffs — "strong" ≥ 80, "good" ≥ 60, else "fair"; "none" when needs_resume** (per data-model.md; a `_band(score)` helper with a unit test on the boundaries 80/60); sponsorship via two-tier `db.get_company_by_name` → `sponsorship.grade_company`; `already_saved` via `db.get_job_by_url`. Make T008 green. (Add a T008 boundary case asserting 80→strong, 79→good, 60→good, 59→fair.)
- [x] T010 [P] Write failing tests (`tests/test_ext_backend.py` or `tests/test_ext_protocol.py`) that `ext_protocol.parse_inbound` accepts a valid `score_request` and `save_job`, rejects oversize (>1MB) and unknown-type, and that both new models ignore extra keys.
- [x] T011 Add `ScoreRequest` and `SaveJob` `_Strict` models to `engine/autofill/ext_protocol.py` and register them in `_INBOUND`. Make T010 green. (Outbound `score_result`/`save_result` use existing `outbound()` — no model needed.)
- [x] T012 [P] Write failing tests `tests/test_ext_backend.py`: `_handle_score_request` emits a `score_result` with the documented fields via an injected `send`; `_handle_save_job` upserts (`source="manual"`, then status `saved`) and emits `save_result` with `already` False then True on repeat of the SAME url; **plus a cross-source case — a job pre-existing under a different source/url with matching (company,title,location) → save reports `already=True`, `job_id` may be null, no duplicate row, no error**. BOTH paths with **no `_watch` session set**, asserting `ext_backend._watch` stays untouched (independence regression guard).
- [x] T013 Implement `engine/autofill/ext_backend.py`: `_handle_score_request(msg)` (truncate description; call `discovery.score_page`; `send(_outbound("score_result", tab_id=msg.tab_id, **result))`) and `_handle_save_job(msg)` (`status = db.upsert_job({...,"source":"manual"})`; then resolve the row via `db.get_job_by_url(msg.url)` — **when it resolves, `db.set_status(id,"saved")` and report `already = status != "inserted"`; when it does NOT resolve (a cross-source `"skipped"` dup kept under a different URL), skip the status write and still report `already=True` with `job_id=null`** — never error, never a duplicate; `send(_outbound("save_result", status=status, job_id=id_or_null, already=...))`); dispatch both from `handle_message`. Read nothing from `_watch`/`bc._state`. Make T012 green (include the cross-source-skip case). Prefer stateless handlers (no `reset_for_tests` change).
- [x] T014 Route the two outbound types in `extension/background/service-worker.js` `state.onMessage`: `case "score_result"` / `case "save_result"` → `toContent(msg.tab_id, {type, ...}, 0)` (top frame). No inbound SW change (existing `relayFromContent` forwards `{_je,payload}` and stamps `tab_id`).

**Checkpoint**: engine + bridge fully unit-tested and green; no UI yet.

---

## Phase 3: User Story 1 — See my match + sponsorship on any job I browse (P1)

**Goal**: a badge auto-appears on a detected posting showing score + sponsorship.
**Independent test**: open the JSON-LD/LinkedIn/Indeed fixtures with the app up →
badge shows the right score and company; no badge on a non-posting page.

- [x] T015 [US1] Create `extension/content/discovery.js` (classic script, top-frame guard `window===window.top`): detection = JSON-LD `JobPosting` (direct or `@graph`) reading title/hiringOrganization.name/description **and `jobLocation` opportunistically (else "")**; fallbacks for `linkedin.com/jobs/view` and `indeed.com` (`/viewjob`,`/jobs`) DOM; debounced re-detect on load + URL-change (history/poll). On detect, `chrome.runtime.sendMessage({_je:true, payload:{type:"score_request", url, title, company, description}})` (carry `location` on the later `save_job`). NO page clicks/mutations. Truncate description before sending.
- [x] T016 [US1] In `discovery.js`, render the closed-shadow-DOM badge on `score_result` only: own host `je-discovery-badge-host`, fixed bottom-right, showing company · title, match number with band color, and a sponsor pill (grade A–F / "cap-exempt likely" / "H-1B: unknown"); handle `needs_resume` → "add your resume" prompt. Listen for `score_result`/`save_result` via `chrome.runtime.onMessage`.
- [x] T017 [US1] Register `content/discovery.js` in `extension/manifest.json` `content_scripts.js` (after `overlay.js`); bump manifest `version` to `1.2.0`.
- [x] T018 [P] [US1] Write `tests/test_extension_assets.py` static assertions: `discovery.js` exists and is listed in the manifest; it references the JSON-LD selector and the linkedin/indeed host checks; it uses `attachShadow({mode:"closed"})`; it performs NO page `.click()`/`.value=`/`dispatchEvent(...submit...)` on page elements (read-only proof). Assert manifest version `1.2.0` **and that `host_permissions` is unchanged (still only `http://127.0.0.1/*`) — discovery adds no new host / off-machine reach (FR-012/SC-007), and no new permissions or stored secret (FR-015).**
- [x] T019 [US1] Write real-browser test `tests/integration/test_discovery_badge.py::test_badge_renders_score` (`-m browser`, `launch_persistent_context` channel=msedge/chrome, real uvicorn + stamped pairing, seeded profile+graded company): open each of the three fixtures → assert the badge host exists and shows a numeric score and the correct company; open a non-posting fixture/page → assert no badge host.

**Checkpoint**: US1 demonstrable — the badge scores real pages in a real browser.

---

## Phase 4: User Story 2 — Save a job to the engine in one click (P2)

**Goal**: Save button captures the posting into the feed/tracker as saved, dedup-safe.
**Independent test**: click Save on a fixture → job persisted (`source="manual"`,
status `saved`); reopen → "Already saved"; no duplicate.

- [x] T020 [US2] Add the **Save to Job Engine** button to the badge in `extension/content/discovery.js`: on click, `sendMessage({_je:true, payload:{type:"save_job", url, title, company, description, location}})`; on `save_result` set the button to "Saved ✓"; if `already_saved`/`already` render the "Already saved" state on open.
- [x] T021 [US2] Extend `tests/integration/test_discovery_badge.py::test_save_persists_and_dedups` (`-m browser`): click Save on a fixture → assert the job appears via the app (DB/query) with correct title/company/url and status `saved`; trigger Save/reload again → assert no duplicate and the badge shows "Already saved".
- [x] T022 [P] [US2] Add a unit test `tests/test_ext_backend.py::test_save_job_marks_saved_and_dedups` covering the handler-level dedup + status `saved` + `already` flag transitions (fast, non-browser complement to T021).

**Checkpoint**: US1 + US2 = browse, score, and capture — the core loop ships value.

---

## Phase 5: User Story 3 — Stay out of the way, always (P3)

**Goal**: dismissable/collapsible, non-overlapping, read-only, non-interfering.
**Independent test**: dismiss/collapse work; no page action taken; an Apply Assist
fill runs unaffected while the badge is present.

- [x] T023 [US3] Add collapse (to a minimal re-expandable pill) and per-URL dismiss (✕) controls to the badge in `extension/content/discovery.js`; ensure fixed bottom-right placement with safe margins so it never overlaps page controls; re-detect/re-render on in-place navigation resets the dismissed state for a NEW url only.
- [x] T024 [US3] Write `tests/integration/test_discovery_badge.py::test_badge_dismiss_collapse_and_readonly` (`-m browser`): dismiss removes the badge; collapse toggles the minimal state; assert (via a page-side sentinel / mutation counter injected by the fixture) that discovery performed zero page mutations/clicks.
- [x] T025 [US3] Write `tests/integration/test_discovery_badge.py::test_no_interference_with_fill` (`-m browser`): with the discovery badge present, run an existing Apply-Assist-style fill flow on a form fixture and assert fills still complete (reuse an existing fill fixture); assert discovery messages never entered a fill report / changed `bc._state` (unit-level assert acceptable if browser-level is impractical).

**Checkpoint**: all three stories complete; trust + coexistence proven.

---

## Phase 6: Polish, Docs & Ship

- [x] T026 [P] Update `web/main.py` `WHATS_NEW` with a **1.2.0** entry (Discovery badge: browse any job site → match + H-1B sponsorship + one-click Save).
- [x] T027 [P] Companion page copy: add the discovery-badge blurb to the companion template ("Browse any job site — the badge shows your match + H-1B sponsorship; one click saves it") using existing partials/helpers.
- [x] T028 [P] Docs: README (new "Discovery badge" capability + read-only/local-only note + reload-extension reminder), `USER_MANUAL` new §, `USER_GUIDE` quick walkthrough. Keep the never-submit/read-only framing consistent with 011.
- [x] T029 Version bump to **1.2.0** across the gated files (`engine` APP_VERSION, `packaging/windows.iss`, manifest — per `packaging/check_version.py`); run `check_version.py`.
- [x] T030 Extend `packaging/smoke_test.py` to assert `extension/content/discovery.js` is bundled in the frozen build and the shipped manifest version is `1.2.0`.
- [x] T031 Verification battery: `pytest -q` ×2, `pytest -q -m browser`, `pytest -q -m slow` all green; fix any regressions before proceeding.
- [ ] T032 Frozen build + `packaging/smoke_test.py` PASS; then the manual live gate from quickstart.md on a real LinkedIn + Indeed + Greenhouse/JSON-LD posting (badge shows score, Save lands in feed, badge read-only).
- [ ] T033 Ship: merge `012-discovery-copilot` → `main`, mirror `main:001-ai-job-engine`, keep the feature branch, tag `v1.2.0`; verify BOTH installers (exe `MZ`/dmg) + SHA-256 lines on the Release page.

---

## Dependencies & Execution Order

- **Setup (T001-T003)** → **Foundational (T004-T014)** blocks all user stories.
- Within Foundational, TDD pairs run in order: T004→T005, T006→T007, T008→T009,
  T010→T011, T012→T013; T014 after T011/T013. `[P]` marks the independent red-test
  authoring tasks (different files).
- **US1 (T015-T019)** depends on Foundational (needs score_result plumbing).
- **US2 (T020-T022)** depends on US1 (badge must exist) + Foundational (save handler).
- **US3 (T023-T025)** depends on US1 (badge) and is independent of US2.
- **Polish/Ship (T026-T033)** after all stories; T031 gates T032 gates T033.

## Parallel Opportunities

- T002/T003 (fixtures + empty test modules) in parallel.
- The red-test authoring tasks T004/T006/T008/T010/T012 are `[P]` (distinct test
  functions/files) — write them as a batch, then implement T005/T007/T009/T011/T013.
- T026/T027/T028 docs in parallel.

## Implementation Strategy (MVP first)

MVP = Setup + Foundational + **US1** (browse → see your match + sponsorship). That
alone is demonstrable value. US2 (save) is the high-value follow-on; US3 hardens
trust/coexistence. Ship only after the full verification battery (T031-T033).

## Independent Test Criteria (per story)

- **US1**: badge renders the correct score+company on JSON-LD/LinkedIn/Indeed
  fixtures; no badge on non-postings.
- **US2**: Save persists `source="manual"`/status `saved`, dedups, shows
  already-saved.
- **US3**: dismiss/collapse work; zero page actions; Apply Assist unaffected.
