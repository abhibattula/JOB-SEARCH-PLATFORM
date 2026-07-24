# Tasks: The Refinements Release (feature 013, v1.3.0)

**Input**: Design documents from `/specs/013-refinements/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: REQUIRED for deterministic engine logic (Constitution V). Hybrid TDD:
red → green for `default_browser`, `humandate`, the model gpu/threads config, and
the extraction hash-skip. UI/template + packaging changes verified by static
asserts + the run-the-app manual gate.

**Organization**: by phase, then user story (US1 P1 browser, US2 P2 feed polish,
US3 P3 speed, US4 P3 icon).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete-task dependency)
- Repo root: `engine/`, `web/`, `packaging/`, `tests/`.

---

## Phase 1: Setup

- [x] T001 Bump version to **1.3.0**: `engine/__init__.py` `APP_VERSION`,
  `packaging/windows.iss` `MyAppVersion`; run `packaging/check_version.py` (expect
  OK). Add the `WHATS_NEW["1.3.0"]` stub in `web/main.py` (filled in T028).
- [x] T002 [P] Create empty test modules `tests/test_default_browser.py` and
  `tests/test_local_llm.py` with imports/markers, ready for red tests.

---

## Phase 2: Foundational (pure, TDD — blocks the user stories)

- [x] T003 [P] Write failing unit tests `tests/test_default_browser.py` for
  `engine.autofill.default_browser.default_channel_order`: ProgId `ChromeHTML`→
  order starts `chrome`; `MSEdgeHTM`→ starts `msedge`; `BraveHTML`→`chrome`;
  unknown/None ProgId → a sensible default order; the result always contains both
  `chrome` and `msedge` (deduped) so a fallback exists. Inject the ProgId read via
  a `read_progid` param/seam (no real registry). **Include a non-Windows case:
  with the platform simulated as non-`win32`, the module still imports and returns
  a valid default order** (guards the M1 portability finding).
- [x] T004 Implement `engine/autofill/default_browser.py`: `default_channel_order(
  read_progid=None) -> tuple[str,...]` (Windows registry `UserChoice\ProgId` map;
  macOS/Linux best-effort; default `("chrome","msedge")`); pure, engine-only.
  **`winreg` (and any Windows-only API) MUST be imported lazily inside a
  `sys.platform == "win32"` branch — never at module top level — so the module
  imports cleanly on macOS/Linux/CI (Principle IV: engine runs headless/cross-
  platform).** Make T003 green.
- [x] T005 [P] Write a failing test for the `humandate` Jinja filter (in
  `tests/test_api.py` or a new `tests/test_web.py`): `"2026-07-24"`→`"24 July
  2026"`; an ISO datetime → same; `None`/`""`/already-human input returned
  unchanged (no raise); day has no leading zero.
- [x] T006 Register `humandate` in `web/main.py`
  (`templates.env.filters["humandate"]`) — tolerant parse of date/datetime/None,
  format `%d %B %Y` with the leading zero stripped. Make T005 green.
- [x] T007 [P] Write failing tests `tests/test_local_llm.py`: `_load_model` passes
  `n_gpu_layers`/`n_threads` from env (`JOBS_GPU_LAYERS`, `JOBS_LLM_THREADS`) to
  `Llama` (monkeypatch `Llama` to capture kwargs); default `n_threads` =
  `os.cpu_count()`; **graceful fallback** — when constructing with GPU layers
  raises, it retries once with `n_gpu_layers=0` and succeeds.
- [x] T008 Implement the gpu/threads config + graceful CPU retry in
  `engine/local_llm.py::_load_model` (memoize the working config); apply the same
  `n_gpu_layers`/`n_threads` treatment to `engine/semantic.py`'s `Llama` load.
  Make T007 green. No behavior change on the CPU wheel (offload no-ops → retry 0).

**Checkpoint**: pure helpers green; nothing wired yet.

---

## Phase 3: US1 — Fill in the right browser (P1, the bug)

- [x] T009 [US1] Write failing tests `tests/test_browser_controller.py`:
  `_ensure_context`/`preflight` iterate the channels from
  `default_channel_order()` (default-first), not the hardcoded msedge-first tuple
  (monkeypatch `default_channel_order` + the Playwright launch seam to record the
  channel order tried); `_choose_backend` still returns `"extension"` when the
  companion is live and honors `AUTOFILL_BACKEND`.
- [x] T010 [US1] `engine/autofill/browser_controller.py`: replace
  `_CHANNELS = ("msedge","chrome")` with a call to
  `default_browser.default_channel_order()` used by `_ensure_context` (~L220) and
  `preflight` (~L248); in `_choose_backend` (~L116) prefer the companion when it
  has connected this session even if the heartbeat is briefly stale (widen the age
  at queue start) rather than launching a different browser. Make T009 green.
- [x] T011 [US1] Surface the active backend + browser in the Apply Assist status
  (render in `web/templates/partials/autofill_status.html`), FR-004: for the
  extension backend show **"Companion — your browser"** (no Playwright channel
  exists there); for the Playwright backend show **"Assistant window — <channel>"**
  using `_launched_channel`. So the user can see whether the fill is in their own
  browser or a separate window.
- [x] T012 [US1] Open postings via the OS default handler: in `web/routes_api.py`
  (~L41-43) use `os.startfile(url)` on Windows (fall back to `webbrowser.open`
  elsewhere / on failure); add/adjust the test in `tests/test_api.py` that the
  open endpoint uses the default-handler path on Windows.

**Checkpoint**: fills go to the companion/default browser; postings open in the
default browser; the active browser is visible.

---

## Phase 4: US2 — Human dates + sort arrows + Back (P2)

- [x] T013 [P] [US2] Apply `| humandate` in
  `web/templates/partials/feed_table.html` (the Posted cell L45 and the `seen ~`
  first_seen L44) and `web/templates/job_detail.html` (posted line L9), preserving
  the `posted_approx` "seen ~" marker.
- [x] T014 [P] [US2] Persistent sort arrows in `feed_table.html` headers (L23,25):
  render a faint `⇅` when inactive and `▾` when active on BOTH Posted and Match;
  add a `.sort` style in the existing token CSS (`web/static/styles.css`). Keep the
  existing `replace_query(sort=…)` links (no new sort backend).
- [x] T015 [US2] Add a `← Back` control to `job_detail.html` header:
  `history.back()` when `document.referrer && history.length>1`, else `href="/"`;
  add a `.back` style.
- [x] T016 [P] [US2] Add a static/render assertion (in `tests/test_api.py`) that a
  rendered feed shows the human date form and both sortable headers carry a sort
  link + indicator, and that the job-detail page contains a Back control.

**Checkpoint**: the feed reads in plain English, sorting is discoverable, Back works.

---

## Phase 5: US3 — Faster resume extraction (P3)

- [x] T017 [US3] Write a failing test (`tests/test_profile_import.py` or
  `tests/test_resume.py`) that re-importing the SAME resume text skips the
  extraction call (the model/extractor is not invoked the second time).
- [x] T018 [US3] Add the resume-text hash guard to `engine/profile_import.py`:
  store the last successfully-extracted resume hash; on a new import with an
  identical hash, skip the extraction call and reuse the prior result. Make T017
  green. (The gpu/threads speedup from T008 already applies.)

**Checkpoint**: unchanged re-imports are instant; new resumes extract (faster).

---

## Phase 6: US4 — App icon (P3)

- [x] T019 [US4] Add `packaging/make_icon.py` (Pillow) that renders one source
  mark → `packaging/icon.ico` (16/32/48/64/128/256), `packaging/icon.icns`, and
  `web/static/favicon.ico`; run it and **commit the generated assets**.
- [x] T020 [US4] Wire the icon into packaging: `packaging/jobengine.spec` — EXE
  `icon=<icon.ico>`, `BUNDLE icon=<icon.icns>`, and set
  `CFBundleShortVersionString` from `engine.APP_VERSION`; `packaging/windows.iss`
  — `SetupIconFile`, `UninstallDisplayIcon={app}\{#MyAppExeName}`, and
  `IconFilename` on the `[Icons]` shortcuts.
- [x] - [x] T021 [US4] Add the favicon link to `web/templates/base.html`
  (`<link rel="icon" href="/static/favicon.ico">`); confirm `/static` serves it.
- [x] - [x] T022 [P] [US4] Add an asset test (`tests/test_packaging.py` or extend
  `tests/test_extension_assets.py`): `packaging/icon.ico`, `icon.icns`,
  `web/static/favicon.ico` exist; `windows.iss` references `SetupIconFile`; the
  spec sets a non-None EXE icon.
- [x] - [x] T023 [US4] Extend `packaging/smoke_test.py` to assert the shipped app dir
  contains the favicon (and the frozen exe was built with an icon, if cheaply
  checkable) + version 1.3.0.

**Checkpoint**: the app has an icon on window/taskbar, installer/shortcuts, and tab.

---

## Phase 7: Polish, Docs & Ship

- [x] - [x] T024 [P] Docs — README (browser note: fills in your default browser /
  companion; GPU opt-in one-liner), `USER_GUIDE` (dates/sort/Back), `USER_MANUAL`
  new §17 (browser routing fix, GPU/threads + how to enable NVIDIA GPU, dates,
  icon), Settings page GPU note.
- [x] - [x] T025 Fill `WHATS_NEW["1.3.0"]` in `web/main.py` (browser fix, faster AI,
  human dates, sort arrows, Back, icon).
- [x] - [x] T026 Verification battery: `pytest -q` ×2 + `-m browser` + `-m slow` all
  green; fix any regression before proceeding.
- [ ] T027 Frozen build + `packaging/smoke_test.py` PASS; manual live gate from
  quickstart.md — a real application fills in Chrome via the companion; feed shows
  human dates + arrows; Back works; icon on all surfaces.
- [ ] T028 Ship: merge `013-refinements` → `main`, mirror `main:001-ai-job-engine`,
  keep the branch, tag `v1.3.0`; verify BOTH installers (exe `MZ`/dmg `78 01`) +
  SHA-256 on the Release page.

---

## Dependencies & Execution Order

- Setup (T001-T002) → Foundational (T003-T008) blocks all stories.
- TDD pairs: T003→T004, T005→T006, T007→T008, T009→T010, T017→T018.
- US1 (T009-T012) depends on `default_browser` (T004). US2 (T013-T016) depends on
  the `humandate` filter (T006). US3 (T017-T018) is independent. US4 (T019-T023)
  is independent (T019 assets before T020-T023 wiring).
- Polish/Ship (T024-T028) last; T026 gates T027 gates T028.

## Parallel Opportunities

- T003/T005/T007 (red tests) in parallel; then implement T004/T006/T008.
- T013/T014 (feed template edits are adjacent — coordinate) and T022/T024 docs in
  parallel.

## Implementation Strategy (MVP first)

MVP = Setup + Foundational + **US1** (the blocking browser fix) — that alone is
worth shipping. US2/US3/US4 are the polish/perf increments. Ship only after the
full battery (T026-T028).
