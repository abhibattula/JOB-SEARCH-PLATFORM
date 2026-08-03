# Tasks: The Case File

**Feature**: `specs/022-the-case-file/` · **Branch**: `022-the-case-file`
**Input**: [plan.md](./plan.md) · [spec.md](./spec.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/)

Tests are **required**, not optional: Constitution Principle V, and the
applicant asked for a TDD hybrid. Every task that changes behaviour is preceded
by a test task that must be watched failing first.

## Delivery order, and why it deviates from strict priority

Strict P1-first ordering would build US1 (nothing unstyled) across all nine
screens before touching the Feed. That cannot work here: **SC-011 requires an
approval gate on a complete, look-at-able Feed** before the other eight screens
are touched. Phase 3 is therefore a vertical slice — the Feed's share of US1,
plus all of US2, US3 and US4 — and Phases 4–6 finish US1 screen by screen.

---

## Phase 1: Setup

- [ ] T001 Download Archivo Variable (wdth,wght; latin + latin-ext) and IBM Plex Mono 400/600 woff2 into `web/static/fonts/`, ~229 KB total
- [ ] T002 [P] Vendor the OFL licence for each family into `web/static/fonts/`
- [ ] T003 [P] Download Archivo TTF (regular + bold) into `assets/fonts/` for the PDF renderer
- [ ] T004 Confirm `packaging/jobengine.spec` picks up `web/static/fonts/` with no spec change, and that `paths.resource_path("assets/fonts")` resolves the new TTFs

## Phase 2: Foundational (BLOCKING — nothing below starts until this is green)

- [ ] T005 Write `tests/test_design_system.py` implementing contract assertions T1–T7 from `contracts/design-tokens.md`, including in-test WCAG luminance arithmetic. **Run it and watch T1 fail with ~35 undefined classes and T2 fail on raw hex** — that failure is the audit reproduced as a gate
- [ ] T006 Write the nine-token block plus `-tint` companions in `web/static/styles.css` `:root`, preserving the existing `[data-theme]` / `prefers-color-scheme` cascade structure at `styles.css:70-119`
- [ ] T007 Add the dark binding for every token; assert both themes declare the identical name set (T4)
- [ ] T008 Add `@font-face` declarations with relative `url()` and a system fallback in every stack; retune the type scale to the new faces
- [ ] T009 Add the global `@media (prefers-reduced-motion: reduce)` override that neutralises animation and transition app-wide (R8 — `styles.css:475-479` is currently ungated)
- [ ] T010 Delete the undefined `--bg` / `--border` references at `styles.css:563-564` and point `.autofill-controls` at real tokens (R10 — the dark-mode white bar)
- [ ] T011 Run T005's test: T2–T7 must now pass. T1 still fails — that is expected until Phases 3–6 build the classes

## Phase 3: US2 + US3 + US4 + the Feed's share of US1 → **APPROVAL GATE**

**Goal**: a complete, look-at-able Feed. **Independent test**: open the feed, see three provenance treatments, watch it stay still for a minute, resize to 1024px and see one nav row.

### Provenance stamp (US2, P1)

- [ ] T012 [US2] Write `tests/test_provenance_stamp.py` asserting contract S1–S5 for all four `match_method` values, using `basic` / `local` / `llm` / absent — **watch it fail**
- [ ] T013 [US2] Build the stamp component in `web/static/styles.css` at three sizes, with ring style (not colour) as the differentiator
- [ ] T014 [US2] Render the stamp in `web/templates/partials/feed_table.html`, replacing the `~`/`•` prefix at lines 63-67; keep the explanatory `title`
- [ ] T015 [P] [US2] Render the `lg` stamp in `web/templates/job_detail.html` (replacing `.score-big` at lines 85-93)
- [ ] T016 [P] [US2] Render the `sm` stamp in `web/templates/partials/dashboard.html` (replacing `.score-chip`)
- [ ] T017 [US2] Add the visually-hidden provenance phrase for assistive technology (FR-017); confirm T012 green

### Feed stays still (US3, P2)

- [ ] T018 [US3] Write `tests/test_feed_fingerprint.py`: identical data → same fingerprint; each mutable field from `data-model.md` §4 → different fingerprint; note edit changes it; invisible field does not — **watch it fail**
- [ ] T019 [US3] Implement the fingerprint helper over the rendered row tuple plus `total`, `page` and query signature
- [ ] T020 [US3] Wire the `204 No Content` short-circuit into `feed_partial` (`web/main.py:705-728`) when the client's fingerprint matches
- [ ] T021 [US3] Add a route test asserting first request 200, repeat request 204, and 200 again after a status change
- [ ] T022 [US3] Confirm `pollingAllowed()` mid-edit suppression (`app.js:144`) still works alongside the 204 path

### Navigation (US4, P2)

- [ ] T023 [US4] Write a test asserting the primary row renders four groups, the active group and active view are both marked current, and no `flex-wrap` is applied to the primary row — **watch it fail**
- [ ] T024 [US4] Rebuild the nav in `web/templates/base.html:17-43` as two tiers, promoting the four existing `aria-label` groups to visible tabs
- [ ] T025 [US4] Style the index tabs — active tab drops its bottom rule and merges into the page surface; second row scrolls horizontally when narrow
- [ ] T026 [US4] Add `main.py` context for which group is active, so the second row renders that group's views

### Feed styling and density (US1 share, P1)

- [ ] T027 Write a test asserting `data-density` renders from `settings.get("FEED_DENSITY")`, defaults to `compact`, and that compact emits one row element per job — **watch it fail**
- [ ] T028 Restyle the feed table on the new tokens: sponsorship and grade as quiet marks, `.is-new` tint, flags
- [ ] T029 Implement compact (one line per job) and comfortable (two lines) as CSS over one template, keyed by `data-density`
- [ ] T030 Add the density toggle to the feed toolbar in `web/templates/feed.html`, persisting via `settings.set`
- [ ] T031 Add the stacked-record fallback below the table's minimum width (FR-025)
- [ ] T032 Define `.export-link` and `.pager`, and put `.skeleton` to work on the first feed paint and the next-actions list (FR-031)
- [ ] T033 **Count jobs visible per screen at compact density and compare against v2.1.0** — SC-012 is a measurement, not an assumption

### GATE

- [ ] T034 Run the app, capture the Feed in light and dark at all three provenance levels plus the unscored state
- [ ] T035 **Send screenshots to the applicant. STOP. Do not begin Phase 4 until they approve or redirect** (SC-011, CHK061–CHK062)

---

## Phase 4: US1 — job detail, Profile, Settings

- [ ] T036 Write a test asserting every `id="field-*"` anchor referenced anywhere in the app or extension still exists in `profile.html` (FR-024) — **watch it pass now, so it guards the relayout**
- [ ] T037 [US1] Define `.grid-2` and `.hint` so Profile's five sections lay out in two columns with distinguishable hints (`profile.html:54,103,157,203,272`)
- [ ] T038 [US1] Add the sticky section index to `web/templates/profile.html` (FR-023)
- [ ] T039 [P] [US1] Define `.switch` and restyle the escort control (`settings.html:186`)
- [ ] T040 [P] [US1] Add the section index to `web/templates/settings.html`; give the 021 AI-tier choice its due weight
- [ ] T041 [P] [US1] Define `.jd` and `.job-url`; restyle `web/templates/job_detail.html` on the new tokens
- [ ] T042 [US1] Render tailored output in `--pencil` until accepted (semantic state contract)
- [ ] T043 [US1] Re-run `test_design_system.py`; these three templates must contribute zero undefined classes

## Phase 5: US1 — Apply Assist (the largest single repair)

- [ ] T044 [US1] Write a test asserting the review list renders question, reason and state as separable elements (FR-013) — **watch it fail**
- [ ] T045 [US1] Define the whole unstyled review vocabulary in `styles.css`: `.answers-review`, `.answer-list`, `.answer-item`, `.q`, `.why`, `.answer-capture`, `.fill-coverage`, `.activity-log`, `.autofill-active`, `.fill-where`, `.fill-where-warning`
- [ ] T046 [US1] Map filled / drafted / needs-you onto ink / pencil / flag per the semantic-state contract, matching `FillItem.flag` values
- [ ] T047 [US1] Define `.autofill-page` and `.autofill-job-check` in `web/templates/autofill.html`
- [ ] T048 [US1] Verify the 017 sticky controls still stick, now on real tokens (T010's fix)
- [ ] T049 [US1] Re-read every assertion in `tests/test_routes_autofill.py` broken by the restyle, individually, deciding each time whether the test or the markup was right

## Phase 6: US1 — remaining screens

- [ ] T050 [P] [US1] Define `.lead`, `.stamp-problem`, `.browser-mismatch` for `companion.html`; keep the 019 ok/bad/warn wizard states distinct (CHK042)
- [ ] T051 [P] [US1] Restyle `diagnostics.html` on the new tokens
- [ ] T052 [P] [US1] Restyle `analytics.html`; confirm `.chart-svg` follows the tokens for free
- [ ] T053 [P] [US1] Define `.reset-learned`, `.answer-bank-delete`, `.eeo-answer-input` for `learned_answers.html` and `partials/profile_answer_bank.html`
- [ ] T054 [P] [US1] Define `.board-followup`, `.fu-date`, `.fu-notes`, `.fu-save` in `partials/pipeline_board.html` and `.import-decision` in `partials/import_review.html`
- [ ] T055 [US1] Restyle `partials/whats_new.html` and `partials/update_banner.html`; confirm they still render server-side with no layout shift (FR-042)
- [ ] T056 [US1] **`test_design_system.py` T1 must now pass: zero undefined classes across the whole app** — SC-001
- [ ] T057 [US1] Confirm the three practice-sandbox templates are untouched (FR-047, CHK008)

## Phase 7: US5 — the extension panel

- [ ] T058 [US5] Write tests for contract P1–P6 in `tests/test_ext_protocol.py` and `tests/integration/test_companion_widget.py` — **watch them fail**
- [ ] T059 [US5] Add the additive `theme` field to `watch_start` and `overlay_state` in `engine/autofill/ext_backend.py`, sourced from `settings.get("THEME")` and normalised as `web/main.py:112-119` does
- [ ] T060 [US5] Replace the hardcoded GitHub-dark block at `extension/content/panel.js:255-360` with the injected token set
- [ ] T061 [US5] Implement the panel's theme resolution order: field → `prefers-color-scheme` → light
- [ ] T062 [US5] Render the `panel`-size provenance stamp in the panel's score circle
- [ ] T063 [US5] Assert `PROTOCOL_V` is still 1 and no secret travels on a theme-carrying message (P1, P2)
- [ ] T064 [US5] Run the 021 drag, persistence and clamping browser tests unchanged — they must pass without modification (FR-037)

## Phase 8: US6 — generated PDFs

- [ ] T065 [US6] Write a test asserting single column, selectable text, no table or image, and that an accented name renders without a placeholder glyph — **watch the glyph assertion fail if the fallback is not wired**
- [ ] T066 [US6] Register Archivo TTF for name and headings in `engine/resume_pdf.py`, keeping DejaVu for body
- [ ] T067 [US6] Wire `set_fallback_fonts()` with DejaVu so Unicode coverage survives (R6)
- [ ] T068 [US6] Rework hierarchy and spacing: name, section rules, body metrics
- [ ] T069 [US6] Apply the same treatment to the cover letter; confirm both remain ATS-safe

## Phase 9: Verification, documentation, and the held gate

- [ ] T070 Run the full unit battery twice; the second run catches order dependence
- [ ] T071 Run the browser suite on Windows
- [ ] T072 Run the browser suite on macOS — a gate, not a note (020's tag was cut twice because macOS caught what Windows passed)
- [ ] T073 Run `tests/test_secret_hygiene.py`; confirm no restyled surface exposes a secret (FR-046)
- [ ] T074 Run `packaging/check_version.py` **first**, then `packaging/smoke_test.py` on the frozen build
- [ ] T075 Verify no network request for any asset, with the machine actually disconnected (CHK059)
- [ ] T076 Walk all nine screens in light and dark; work the `checklists/design.md` items, recording judgements for CHK011, CHK028, CHK033
- [ ] T077 [P] Update `docs/USER_MANUAL.md` with the design system, the provenance stamp, density, and the navigation change
- [ ] T078 [P] Update `docs/USER_GUIDE.md` for the new navigation and the stamp
- [ ] T079 [P] Update `README.md`
- [ ] T080 [P] Add the `WHATS_NEW` entry for this release
- [ ] T081 **HELD: no tag, no release, no version pushed until the applicant says go** (SC-011)

---

## Dependencies

```
Phase 1 (setup) → Phase 2 (foundational, BLOCKING)
                       ↓
                  Phase 3 → ***APPROVAL GATE (T035)***
                       ↓
        ┌──────────────┼──────────────┬──────────┐
     Phase 4        Phase 5        Phase 6    Phase 7 ─┐
   (detail/         (Apply         (rest)     (panel)  │
    profile/         Assist)                           │
    settings)                                       Phase 8
        └──────────────┴──────────────┴──────────────┬─┘
                                                  Phase 9
```

- **T005 before T006**: the test is written and watched failing before the token block exists.
- **T035 blocks everything in Phases 4–8.** This is the applicant's gate.
- **T056 requires Phases 4, 5 and 6 complete** — zero undefined classes is cumulative.
- Phase 7 depends only on Phase 2 (tokens) and could run parallel to 4–6; it is placed after so the panel copies a settled token set.

## Parallel opportunities

- T002, T003 alongside T001
- T015, T016 alongside each other (different templates)
- T039, T040, T041 alongside each other
- T050–T054 all alongside each other (all different templates)
- T077–T080 alongside each other

## Task count

81 tasks. 9 are test-first tasks that must be watched failing (T005, T012,
T018, T023, T027, T036, T044, T058, T065). 3 require a real measurement rather
than an assertion (T033 job count, T072 macOS, T075 offline).
