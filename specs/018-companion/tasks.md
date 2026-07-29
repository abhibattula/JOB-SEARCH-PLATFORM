# Tasks: The Companion — the extension becomes the product

**Feature**: 018-companion · **Target**: v1.8.0
**Input**: [spec.md](spec.md) · [plan.md](plan.md) · [research.md](research.md) ·
[data-model.md](data-model.md) · [contracts/](contracts/)

**Test policy** (Constitution V + the 017 lesson): tests are written **first**
and watched fail. Every interactive companion control is proved by a **click in
a real browser** — a string-presence assertion on a source file is never the
sole coverage for a control (FR-039).

---

## Phase 1: Setup — fixtures the tests need

- [ ] T001 [P] Create the hostile-CSS discovery fixture at `tests/fixtures/discovery_pages/hostile_css.html`: valid JSON-LD `JobPosting`, a 5000 px-tall body, and a stylesheet declaring `div { position: static !important; z-index: 0 !important; }` plus a high-`z-index` sticky page header
- [ ] T002 [P] Create the metadata-less application fixture at `tests/fixtures/discovery_pages/bare_application.html`: a realistic ATS application form (name, email, phone, résumé file input, two selects, a textarea) with **no** JSON-LD and no LinkedIn/Indeed markers
- [ ] T003 [P] Create the probe-negative fixture at `tests/fixtures/discovery_pages/search_only.html`: an ordinary page whose only inputs are a search box and a newsletter email field — the companion must NOT appear
- [ ] T004 [P] Extend `web/templates/practice_apply.html` with a question the app will decline (so a needs-you row exists to type into) and a `window.__jeTyping` beacon recording focus/value at each scan

---

## Phase 2: Foundational — blocking prerequisites

- [ ] T005 Merge the two `content_scripts` entries in `extension/manifest.json` into one, ordered `click_guard.js, scanner.js, filler.js, panel.js, discovery.js, opener.js, main.js`, so load order is explicit rather than dependent on cross-entry injection order (research R8)
- [ ] T006 Add `tests/integration/test_companion_widget.py` with the harness scaffolding copied from `tests/integration/test_discovery_badge.py` (`fixture_server`, `app_server`, real unpacked extension, `pairing.json` pointed at the live app), plus a `companion_host(page)` helper and a `shadow_click(page, control_id)` helper wrapping the `document.getElementById(host).shadowRoot.getElementById(id).click()` pattern

---

## Phase 3: US1 — I can see it, and it does something (P1)

**Goal**: the companion is pinned to the viewport, its primary action works, and
it appears on a bare application page.
**Independent test**: on the hostile fixture the host computes `position: fixed`
and sits on screen; clicking the primary action makes the app start a session.

### Tests first (RED)

- [ ] T007 [P] [US1] In `tests/integration/test_companion_widget.py`, assert on `hostile_css.html` that the companion host computes `position === "fixed"`, has a non-`auto` inset, and its `getBoundingClientRect()` intersects the viewport without scrolling — must FAIL against today's `all:initial` ordering
- [ ] T008 [P] [US1] Assert the host is still on screen after `window.scrollTo(0, document.body.scrollHeight)` on the same 5000 px fixture
- [ ] T009 [P] [US1] Assert clicking the primary action on a scored posting causes the app to record the job and start a watched session (poll `GET /api/autofill/status` for `queue_active` and a positive `current_job_id`) — must FAIL against the dead `current.posting` handler
- [ ] T010 [P] [US1] Assert the companion appears on `bare_application.html` with the primary action labelled "Fill this page", and that clicking it starts an ad-hoc session (`current_job_id == -2`)
- [ ] T011 [P] [US1] Assert **no** companion host exists on `search_only.html` after the poll interval — the probe heuristic must not fire on ordinary pages
- [ ] T012 [P] [US1] In `tests/test_extension_assets.py`, assert `jeScanner.probe` exists and that the `probe` function body contains neither `stamp(` nor `docToken(` — the probe must not mutate the page (research R7)
- [ ] T013 [P] [US1] Browser test: after the companion has rendered on `bare_application.html`, assert the document contains **no** `[data-je-idx]` and `<html>` has no `data-je-doc` — proving detection stamped nothing
- [ ] T014 [P] [US1] Browser test: when the app refuses the primary action (start a session, then click the primary action from a second tab), the companion shows the refusal text and re-enables its button — no silent no-op (FR-010)

### Implementation (GREEN)

- [ ] T015 [US1] Fix host positioning in `extension/content/discovery.js`: set `host.style.cssText = "all:initial"` **first**, then `setProperty` for `position: fixed`, `inset`, `z-index`, `display: block`, each with `"important"` (research R1)
- [ ] T016 [US1] Apply the identical positioning fix in `extension/content/overlay.js`
- [ ] T017 [US1] Fix `onApply()` in `extension/content/discovery.js` to read `current` directly instead of the non-existent `current.posting` (research R2)
- [ ] T018 [US1] Add `probe()` to `extension/content/scanner.js` — read-only, calling neither `stamp()` nor `docToken()` — returning `{fields, hasFile, hasEmail}` over the existing `FIELD_SELECTOR`, excluding `type=search` and fields whose `name`/`id` matches `^(q|s|search|query|keyword)`
- [ ] T019 [US1] Export `probe` from the `window.jeScanner` return object in `extension/content/scanner.js`
- [ ] T020 [US1] In `extension/content/discovery.js`, add the form-detection tick using `jeScanner.probe()` with the heuristic `fields >= 3 || (hasFile && fields >= 1) || (hasEmail && fields >= 3)`, producing `detection ∈ none|form|posting|posting+form`
- [ ] T021 [US1] Render the companion when `detection != "none"` even with no posting metadata, with "Fill this page" as the primary action sending the existing `fill_here` message
- [ ] T022 [US1] Report every primary-action outcome: disable → act → on success reflect the new session state, on refusal/failure restore the label and show the reason line

**Checkpoint**: T007–T014 green. The companion is visible and its primary action
works, on both a posting and a bare application form.

---

## Phase 4: US2 — One companion, and it looks like a product (P2)

**Goal**: one host, one card, pill at rest.
**Independent test**: exactly one companion host exists and carries both score
state and fill state; collapse/expand toggles and persists.

### Tests first (RED)

- [ ] T023 [P] [US2] Browser test: on a scored posting **and** during a fill, assert `document.querySelectorAll('[id$="-host"]')` yields exactly one Job Engine host (FR-004)
- [ ] T024 [P] [US2] Browser test: the merged host carries every `data-je-*` attribute the 012/016/017 suites assert — `jeScore`, `jeBand`, `jeCompany`, `jeSponsor`, `jeSaved`, `jeCollapsed`, `jeSeen`, `jeFilled`, `jeNeedsYou`, `jeAnswers` — plus the new `jeSession` and `jeDetection`
- [ ] T025 [P] [US2] Browser test: the companion rests collapsed; clicking it expands; clicking collapse returns it to the pill; `data-je-collapsed` mirrors the state
- [ ] T026 [P] [US2] Browser test: the collapsed pill shows the match score when idle on a posting, and `filled/seen` while filling
- [ ] T027 [P] [US2] Browser test: the card auto-expands when a session starts, and again when `needs_you` first becomes non-zero — but not again after the applicant collapses it
- [ ] T028 [P] [US2] Browser test: with the viewport resized to 500 px tall, the expanded card's rect stays within the viewport and its body scrolls internally
- [ ] T029 [P] [US2] In `tests/test_extension_assets.py`, assert `extension/content/panel.js` contains no `.click(` (the widget never clicks a page element) and that `overlay.js` no longer exists
- [ ] T030 [P] [US2] Browser test: no companion host is created inside a cross-origin sub-frame (fixture page embedding an iframe from the second fixture origin)

### Implementation (GREEN)

- [ ] T031 [US2] Create `extension/content/panel.js` — single host `je-companion-host`, open shadow root, the corrected positioning from T015, mounting to `document.body || document.documentElement`, guarded to `window === window.top`
- [ ] T032 [US2] Implement the card structure per `contracts/companion-ui.md` §3: header (state dot, collapse, dismiss), score block, primary + secondary actions, progress row, notice line, answer groups, and the unchanged "You click apply / submit — never us."
- [ ] T033 [US2] Implement the collapsed pill and its content rules, plus the auto-expand rules and the per-tab in-memory collapse state (research R9 — not `storage.session`, which excludes content scripts)
- [ ] T034 [US2] Implement the primary-action state machine from `data-model.md` §2 (`idle|starting|filling|stopped|done` × `detection`) as a pure function so it is unit-testable
- [ ] T035 [US2] Implement the light-DOM `data-je-*` mirror on the merged host
- [ ] T036 [US2] Style pass: spacing scale, one accent, legible contrast on light and dark boards, visible focus ring, `prefers-reduced-motion`, `max-height` clamped to the viewport with an internally scrolling body
- [ ] T037 [US2] Expose `window.jeOverlay` from `panel.js` as a facade with the exact 017 surface (`show`, `hide`, `update`, `note`, `setAnswers`, `onAnswer`, `onInsert`, `onJump`, `onFillAgain`) delegating to the panel, and `window.jePanel` for the new surface (`setPosting`, `setScore`, `setSession`, `notice`)
- [ ] T038 [US2] Rewrite `extension/content/discovery.js` rendering to call `window.jePanel` instead of owning a host; keep **all** detection, scoring, save and dismiss logic unchanged
- [ ] T039 [US2] Delete `extension/content/overlay.js` and remove it from `extension/manifest.json`
- [ ] T040 [US2] Retarget the US1 tests (T007–T014) and `tests/integration/test_discovery_badge.py` onto `je-companion-host`
- [ ] T041 [P] [US2] Add `tests/test_panel_state.py` covering the T034 state machine table-driven across every `session` × `detection` combination
- [ ] T041a [US2] Tear down cleanly on an orphaned frame (extension reloaded): `panel.js` removes its host and stops its ticks when `chrome.runtime.sendMessage` throws, matching `main.js`'s existing `teardown()` (FR-006); browser test reloads the extension mid-session and asserts no console error storm and no orphan host
- [ ] T041b [P] [US2] Browser test: every companion control is reachable by keyboard (Tab order covers primary, save, collapse, dismiss and each group header) and `:focus-visible` renders a ring (FR-018)

**Checkpoint**: one companion, polished, behaving as a pill-to-card.

---

## Phase 5: US3 — Every answer, readable, insertable, correctable (P3)

**Goal**: the page lists every decided field, each insertable, and typing is
never destroyed.
**Independent test**: a profile-filled field appears with a working `je_idx`;
typed text survives three scan cycles.

### Tests first (RED)

- [ ] T042 [P] [US3] Create `tests/test_page_answers.py`: `build()` groups a skip-with-needs-you reason as `needs_you`, an `ai_draft` decision as `draft`, and any other filled decision as `profile`; ordering is needs-you → draft → profile, document order within a group
- [ ] T043 [P] [US3] In `tests/test_page_answers.py`, assert every item carries `key` and `je_idx`, and that a field decided as `secret` is excluded entirely (FR-037)
- [ ] T044 [P] [US3] In `tests/test_page_answers.py`, assert the digest is stable for identical input, differs when any rendered field changes, and is order-sensitive
- [ ] T045 [P] [US3] In `tests/test_ext_backend.py`, assert the `answers` payload for a job includes a field filled from the profile (not only drafter records) — must FAIL today (research R5)
- [ ] T046 [P] [US3] In `tests/test_ext_backend.py`, assert a second identical `fields` message pushes **no** `answers` message (FR-027)
- [ ] T047 [P] [US3] In `tests/test_ext_backend.py`, assert `answers` IS re-sent after `answer_question`, after `fill_again`, and on session start even when the digest is unchanged
- [ ] T048 [P] [US3] Browser test: after a fill on `practice_apply.html`, every rendered answer row exposes Copy, and rows with a `je_idx` also expose Insert and Show me — must FAIL today (research R4)
- [ ] T049 [P] [US3] Browser test: clicking Insert places the answer in exactly that field, and a sentinel value in a neighbouring field is unchanged
- [ ] T050 [P] [US3] Browser test: clicking Show me scrolls the field into view (its rect enters the viewport)
- [ ] T051 [P] [US3] Browser test: type 12 characters into a needs-you input, wait through ≥3 scan cycles (>6 s), assert the value and `shadowRoot.activeElement` are unchanged — must FAIL today (research R6)
- [ ] T052 [P] [US3] Browser test: submitting a typed answer fills that field on the next scan with exactly the typed text, and the app stores it with source `user`
- [ ] T053 [P] [US3] Browser test: groups render with counts, needs-you expanded and the other two collapsed, and each header toggles
- [ ] T054 [P] [US3] In `tests/test_extension_assets.py`, extend the 017 no-`innerHTML` guard to the new renderer in `panel.js`

### Implementation (GREEN)

- [ ] T055 [US3] Create `engine/autofill/page_answers.py` — pure: `build(decisions, drafter_records)`, `group_for(...)`, `digest(items)`, `PAGE_ANSWER_GROUPS`. No I/O, no `web/` import
- [ ] T056 [US3] In `engine/autofill/ext_backend.py`, accumulate each field decision during `_handle_fields` (keyed by `field_core.key(raw)`, carrying `raw["je_idx"]`) and hand the accumulation to `page_answers.build`
- [ ] T057 [US3] Replace the `drafter.answers_for_page(job_id)` call in `_handle_fields` with the assembled index, merging drafter records for questions the drafter owns
- [ ] T058 [US3] Add per-tab digest tracking in `ext_backend` and skip the `answers` send when unchanged; force a send on session start, `fill_again`, and `answer_question`
- [ ] T059 [US3] Extend the `answers` outbound payload with `key`, `je_idx` and `group` per `contracts/bridge-protocol-additions.md` §1, keeping `question`/`answer`/`state`/`reason`/`askable` unchanged
- [ ] T060 [US3] Implement grouped, collapsible answer rendering in `extension/content/panel.js` with per-group counts and the default expansion rules
- [ ] T061 [US3] Implement keyed reconciliation in `panel.js`: match rows by `key`, patch in place, create only new keys, remove only vanished keys
- [ ] T062 [US3] Never touch a row containing `root.activeElement` — using the **shadow root's** `activeElement`, since `document.activeElement` returns the host when focus is inside an open shadow root (research R6)
- [ ] T063 [US3] Render Copy always, and Insert / Show me whenever `je_idx` is present; keep answer text going in via `textContent`
- [ ] T064 [US3] Keep the truncation notice wired to the `truncated` flag (FR-029)

**Checkpoint**: the panel is a complete, usable review surface.

---

## Phase 6: US4 — Full control without the app (P4)

**Goal**: Stop, Fill again, Next, live status and keyboard, all on the page; the
app stops navigating away.

### Tests first (RED)

- [ ] T065 [P] [US4] In `tests/test_ext_protocol.py`, assert `SessionControl` validates `{tab_id, action}` for `stop` and `next`, rejects an unknown action, and that `PROTOCOL_V` is still `1`
- [ ] T066 [P] [US4] In `tests/test_ext_protocol.py`, assert a 017-era `answers`/`overlay_state` payload still validates with the new optional fields absent
- [ ] T067 [P] [US4] In `tests/test_ext_backend.py`, assert `session_control{stop}` calls `browser_controller.stop_queue()` only when `tab_id` matches the watched tab, and `{next}` calls `advance()`
- [ ] T068 [P] [US4] Browser test: with a session running, clicking Stop in the companion leaves `GET /api/autofill/status` reporting `queue_active` false
- [ ] T069 [P] [US4] Browser test: an app-side `error` message (start a second session while one runs) appears in the companion's notice line (FR-033)
- [ ] T070 [P] [US4] In `tests/test_web.py`, assert `web/templates/job_detail.html` does not navigate to `/autofill` on success and renders status in place
- [ ] T071 [P] [US4] In `tests/test_extension_assets.py`, assert `extension/manifest.json` declares both `commands` with suggested keys and that the service worker registers `chrome.commands.onCommand`

### Implementation (GREEN)

- [ ] T072 [US4] Add the `SessionControl` model to `engine/autofill/ext_protocol.py` and register it in `_INBOUND`
- [ ] T073 [US4] Add `_handle_session_control` to `engine/autofill/ext_backend.py`, dispatching in `handle_message`, guarded on the watched tab, delegating to `browser_controller.stop_queue()` / `advance()`
- [ ] T074 [US4] Add optional `session`, `current_job_id` and `remaining` to the `overlay_state.summary` payload in `ext_backend._handle_fields`
- [ ] T075 [US4] Forward `error` messages to the watched tab's top frame in `extension/background/service-worker.js`, in addition to today's `storage.session` mirror for the popup
- [ ] T076 [US4] Wire Stop / Fill again / Next in `extension/content/panel.js` to `session_control` and the existing `fill_again`, and render current job + remaining
- [ ] T077 [US4] Add the `commands` block to `extension/manifest.json` — toggle companion (`Alt+J`), fill current page (`Alt+Shift+J`)
- [ ] T078 [US4] Handle `chrome.commands.onCommand` in `extension/background/service-worker.js`, messaging the active tab's top frame
- [ ] T079 [US4] Handle the two command messages in `extension/content/main.js` (toggle the panel; run a fill on this page)
- [ ] T080 [US4] Rewrite the `job_detail.html` success path to render status in place, with a link to the Apply Assist page instead of a redirect
- [ ] T081 [US4] Update `extension/popup/popup.js` so "Fill this page" reflects the companion's state rather than duplicating it

**Checkpoint**: a full application needs zero switches to the app.

---

## Phase 7: Polish, docs and release

- [ ] T082 [P] Retire the string-presence badge guards in `tests/test_extension_assets.py::TestBadgeLauncher017`, keeping only negative invariants (no `.click(` on page elements, no `innerHTML` for answers); note in the docstring that interaction coverage now lives in `tests/integration/test_companion_widget.py`
- [ ] T083 [P] Assert zero submit clicks across every fixture in the browser suite (carry forward the 016/017 guard onto the new fixtures)
- [ ] T084 [P] Work through `checklists/companion.md` and tick every box, fixing what fails
- [ ] T085 [P] Update `docs/USER_MANUAL.md`: the companion replaces the two-widget flow; the pill, the groups, Insert / Show me, on-page Stop, keyboard shortcuts
- [ ] T086 [P] Update `README.md`'s Apply Assist section for the extension-first flow
- [ ] T087 [P] Add `WHATS_NEW["1.8.0"]` naming the four fixed defects in plain language
- [ ] T088 Bump the version to `1.8.0` everywhere `packaging/check_version.py` checks — including `extension/manifest.json` and `packaging/windows.iss` (edit byte-safely: that file is not UTF-8 clean)
- [ ] T089 Run the full battery twice: `python -m pytest -q` ×2
- [ ] T090 Run `python -m pytest -m browser -q` and the offline-model gates
- [ ] T091 Run the frozen smoke (`packaging/smoke_test.py`) with `JOBS_AI_SUBPROCESS` default on
- [ ] T092 Manual end-to-end per `quickstart.md` §5 against a real Greenhouse posting **and** its bare `…/application` URL
- [ ] T093 Tag `v1.8.0`, wait for the release build, and verify **both** installers by magic bytes and SHA-256 against the release body

---

## Dependencies

```
Phase 1 (T001–T004)  ─┐
Phase 2 (T005–T006)  ─┴─→ US1 (T007–T022)
                            └─→ US2 (T023–T041)
                                  ├─→ US3 (T042–T064)
                                  └─→ US4 (T065–T081)
                                        └─→ Phase 7 (T082–T093)
```

- **US1** needs the fixtures (Phase 1) and the harness (T006).
- **US2** depends on US1 only for its tests to have something to retarget
  (T040); the panel itself could be built in parallel, but sequencing avoids
  writing the positioning fix twice.
- **US3** and **US4** are independent of each other and may proceed in parallel
  once US2 lands — US3 touches `page_answers.py` + the panel's answer list, US4
  touches the protocol + the panel's controls.
- **Phase 7** requires everything.

## Parallel opportunities

- T001–T004 are four independent files.
- Every `[P]` test task within a phase writes to a different test file or an
  independent test class.
- T042–T044 (`test_page_answers.py`) are independent of T045–T047
  (`test_ext_backend.py`) and of the browser tests T048–T054.
- T085–T087 are three independent docs.

## MVP scope

**US1 alone is a shippable fix.** It turns a product whose on-page surface is
unreachable and whose launcher does nothing into one where both work. US2–US4
are what make it good.
