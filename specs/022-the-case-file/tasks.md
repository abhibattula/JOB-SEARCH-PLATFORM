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

- [X] T001 Download Archivo Variable (wdth,wght; latin + latin-ext) and IBM Plex Mono 400/600 woff2 into `web/static/fonts/`, ~229 KB total *(FR-006)*
- [X] T002 [P] Vendor the OFL licence for each family into `web/static/fonts/`
- [X] T003 [P] Download Archivo TTF (regular + bold) into `assets/fonts/` for the PDF renderer *(FR-040)*
- [X] T004 Confirm `packaging/jobengine.spec` picks up `web/static/fonts/` with no spec change, and that `paths.resource_path("assets/fonts")` resolves the new TTFs
- [X] T004a **BASELINE, before any styling change** (SC-012, analysis O1): run the current build and record how many job rows are visible in one 1366×768 viewport at the default feed. T033 has nothing to compare against if this is not captured first. Write the number into `specs/022-the-case-file/baseline.txt` *(SC-012)*

## Phase 2: Foundational (BLOCKING — nothing below starts until this is green)

- [X] T005 Write `tests/test_design_system.py` implementing contract assertions T1–T7 from `contracts/design-tokens.md`, including in-test WCAG luminance arithmetic and an assertion that every font stack ends in a system fallback (FR-007). **Run it and watch T1 fail with ~35 undefined classes and T2 fail on raw hex** — that failure is the audit reproduced as a gate. *(FR-002, FR-005, FR-007, FR-009, SC-002, SC-007)*
- [X] T005a Implement T1 as a **shrinking allowlist** (analysis C1): the test carries the set of classes still known to be undefined and asserts that set never *grows*. Without this the suite is red from Phase 2 to Phase 6 and a genuinely new breakage cannot be told from the expected one. T056 empties the allowlist
- [X] T006 Write the nine-token block plus `-tint` companions in `web/static/styles.css` `:root`, preserving the existing `[data-theme]` / `prefers-color-scheme` cascade structure at `styles.css:70-119` *(FR-001)*
- [X] T007 Add the dark binding for every token; assert both themes declare the identical name set (T4) *(FR-001, FR-004, FR-005)*
- [X] T008 Add `@font-face` declarations with relative `url()` and a system fallback in every stack; retune the type scale to the new faces *(FR-006, FR-007, FR-008)*
- [X] T009 Add the global `@media (prefers-reduced-motion: reduce)` override that neutralises animation and transition app-wide (R8 — `styles.css:475-479` is currently ungated) *(FR-032, SC-009)*
- [X] T010 Delete the undefined `--bg` / `--border` references at `styles.css:563-564` and point `.autofill-controls` at real tokens (R10 — the dark-mode white bar) *(FR-014)*
- [X] T011 Run T005's test: T2–T7 must now pass. T1 still fails — that is expected until Phases 3–6 build the classes *(FR-002, FR-005)*

## Phase 3: US2 + US3 + US4 + the Feed's share of US1 → **APPROVAL GATE**

**Goal**: a complete, look-at-able Feed. **Independent test**: open the feed, see three provenance treatments, watch it stay still for a minute, resize to 1024px and see one nav row.

### Provenance stamp (US2, P1)

- [X] T012 [US2] Write `tests/test_provenance_stamp.py` asserting contract S1–S5 for all four `match_method` values, using `basic` / `local` / `llm` / absent — **watch it fail** *(FR-016, FR-019, SC-005)*
- [X] T013 [US2] Build the stamp component in `web/static/styles.css` at three sizes, with ring style (not colour) as the differentiator *(FR-015, FR-016, FR-019)*
- [X] T014 [US2] Render the stamp in `web/templates/partials/feed_table.html`, replacing the `~`/`•` prefix at lines 63-67; keep the explanatory `title` *(FR-015, FR-018)*
- [X] T015 [P] [US2] Render the `lg` stamp in `web/templates/job_detail.html` (replacing `.score-big` at lines 85-93) *(FR-018)*
- [X] T016 [P] [US2] Render the `sm` stamp in `web/templates/partials/dashboard.html` (replacing `.score-chip`) *(FR-018)*
- [X] T017 [US2] Add the visually-hidden provenance phrase for assistive technology (FR-017); confirm T012 green *(FR-017, SC-005)*

### Feed stays still (US3, P2)

- [X] T018 [US3] Write `tests/test_feed_fingerprint.py`: identical data → same fingerprint; each mutable field from `data-model.md` §4 → different fingerprint; note edit changes it; invisible field does not — **watch it fail** *(FR-027)*
- [X] T019 [US3] Implement the fingerprint helper over the rendered row tuple plus `total`, `page` and query signature *(FR-027)*
- [X] T020 [US3] Wire the `204 No Content` short-circuit into `feed_partial` (`web/main.py:705-728`) when the client's fingerprint matches *(FR-027)*
- [X] T021 [US3] Add a route test asserting first request 200, repeat request 204, and 200 again after a status change *(FR-028, FR-029, SC-003)*
- [X] T022 [US3] Confirm `pollingAllowed()` mid-edit suppression (`app.js:144`) still works alongside the 204 path *(FR-030)*

### Navigation (US4, P2)

- [X] T023 [US4] Write a test asserting the primary row renders four groups, the active group and active view are both marked current, and no `flex-wrap` is applied to the primary row — **watch it fail** *(FR-020, FR-022, SC-004)*
- [X] T024 [US4] Rebuild the nav in `web/templates/base.html:17-43` as two tiers, promoting the four existing `aria-label` groups to visible tabs *(FR-020)*
- [X] T025 [US4] Style the index tabs — active tab drops its bottom rule and merges into the page surface; second row scrolls horizontally when narrow *(FR-021)*
- [X] T026 [US4] Add `main.py` context for which group is active, so the second row renders that group's views *(FR-022)*

### Feed styling and density (US1 share, P1)

- [X] T027 Write a test asserting `data-density` renders from `settings.get("FEED_DENSITY")`, defaults to `compact`, and that compact emits one row element per job — **watch it fail** *(FR-026, FR-026a)*
- [X] T028 Restyle the feed table on the new tokens: sponsorship and grade as quiet marks, `.is-new` tint, flags
- [X] T029 Implement compact (one line per job) and comfortable (two lines) as CSS over one template, keyed by `data-density` *(FR-026a, FR-026b)*
- [X] T030 Add the density toggle to the feed toolbar in `web/templates/feed.html`, persisting via `settings.set` *(FR-026)*
- [X] T031 Add the stacked-record fallback below the table's minimum width (FR-025) *(FR-025)*
- [X] T032 Define `.export-link` and `.pager`, and put `.skeleton` to work on the first feed paint and the next-actions list (FR-031) *(FR-031)*
- [X] T033 **Count jobs visible per screen at compact density and compare against v2.1.0** — SC-012 is a measurement, not an assumption *(FR-026a, SC-012)*

### GATE

- [X] T034 Run the app, capture the Feed in light and dark at all three provenance levels plus the unscored state
- [X] T035 **Send screenshots to the applicant. STOP. Do not begin Phase 4 until they approve or redirect** (SC-011, CHK061–CHK062) *(SC-011)*

---

## Phase 4: US1 — job detail, Profile, Settings

- [X] T036 Write a test asserting every `id="field-*"` anchor referenced anywhere in the app or extension still exists in `profile.html` (FR-024) — **watch it pass now, so it guards the relayout** *(FR-024)*
- [X] T037 [US1] Define `.grid-2` and `.hint` so Profile's five sections lay out in two columns with distinguishable hints (`profile.html:54,103,157,203,272`) *(FR-010, FR-011)*
- [X] T038 [US1] Add the sticky section index to `web/templates/profile.html` (FR-023) *(FR-023)*
- [X] T039 [P] [US1] Define `.switch` and restyle the escort control (`settings.html:186`) *(FR-012)*
- [X] T040 [P] [US1] Add the section index to `web/templates/settings.html`; give the 021 AI-tier choice its due weight *(FR-023)*
- [X] T041 [P] [US1] Define `.jd` and `.job-url`; restyle `web/templates/job_detail.html` on the new tokens
- [X] T042 [US1] Render tailored output in `--pencil` until accepted (semantic state contract) *(FR-003)*
- [X] T043 [US1] Re-run `test_design_system.py`; these three templates must contribute zero undefined classes

## Phase 5: US1 — Apply Assist (the largest single repair)

- [X] T044 [US1] Write a test asserting the review list renders question, reason and state as separable elements (FR-013) — **watch it fail** *(FR-013)*
- [X] T045 [US1] Define the whole unstyled review vocabulary in `styles.css`: `.answers-review`, `.answer-list`, `.answer-item`, `.q`, `.why`, `.answer-capture`, `.fill-coverage`, `.activity-log`, `.autofill-activity`, `.autofill-active`, `.fill-where`, `.fill-where-warning`, `.saved` (analysis C2 added the last three) *(FR-013)*
- [X] T046 [US1] Map filled / drafted / needs-you onto ink / pencil / flag per the semantic-state contract, matching `FillItem.flag` values *(FR-003)*
- [X] T047 [US1] Define `.autofill-page` and `.autofill-job-check` in `web/templates/autofill.html`
- [X] T048 [US1] Verify the 017 sticky controls still stick, now on real tokens (T010's fix) *(FR-014)*
- [X] T049 [US1] Re-read every assertion in `tests/test_routes_autofill.py` broken by the restyle, individually, deciding each time whether the test or the markup was right

## Phase 6: US1 — remaining screens

- [X] T050 [P] [US1] Define `.lead`, `.stamp-problem`, `.browser-mismatch` for `companion.html`; keep the 019 ok/bad/warn wizard states distinct (CHK042)
- [X] T051 [P] [US1] Restyle `diagnostics.html` on the new tokens
- [X] T052 [P] [US1] Restyle `analytics.html`; confirm `.chart-svg` follows the tokens for free
- [X] T053 [P] [US1] Define `.reset-learned`, `.answer-bank-delete`, `.eeo-answer-input` for `learned_answers.html` and `partials/profile_answer_bank.html`
- [X] T054 [P] [US1] Define `.board-followup`, `.fu-date`, `.fu-notes`, `.fu-save` in `partials/pipeline_board.html` and `.import-decision` in `partials/import_review.html`
- [X] T055 [US1] Restyle `partials/whats_new.html` and `partials/update_banner.html`; define `.whats-new` and `.update-banner` rather than leaving them riding on `.mission-panel`; confirm they still render server-side with no layout shift *(FR-042)*
- [X] T055a [US1] Define the classes no other task claimed (analysis C2): `.profile` (used ×4 across `profile.html`, `settings.html`, `diagnostics.html`, `learned_answers.html`) and `.unclean-banner` (`base.html:53`) *(FR-009)*
- [X] T056 [US1] **`test_design_system.py` T1 must now pass: zero undefined classes across the whole app** — SC-001 *(FR-009, SC-001)*
- [X] T057 [US1] Confirm the three practice-sandbox templates are untouched (FR-047, CHK008) *(FR-047)*

## Phase 7: US5 — the extension panel

- [X] T058 [US5] Write tests for contract P1–P6 in `tests/test_ext_protocol.py` and `tests/integration/test_companion_widget.py` — **watch them fail** *(FR-036, SC-006)*
- [X] T059 [US5] Add the additive `theme` field to `watch_start` and `overlay_state` in `engine/autofill/ext_backend.py`, sourced from `settings.get("THEME")` and normalised as `web/main.py:112-119` does *(FR-034, FR-035)*
- [X] T060 [US5] Replace the hardcoded GitHub-dark block at `extension/content/panel.js:255-360` with the injected token set *(FR-002, FR-033, SC-002)*
- [X] T061 [US5] Implement the panel's theme resolution order: field → `prefers-color-scheme` → light *(FR-034, SC-006)*
- [X] T062 [US5] Render the `panel`-size provenance stamp in the panel's score circle *(FR-018, FR-033)*
- [X] T063 [US5] Assert `PROTOCOL_V` is still 1 and no secret travels on a theme-carrying message (P1, P2) *(FR-035, FR-036, FR-046)*
- [X] T064 [US5] Run the 021 drag, persistence and clamping browser tests unchanged — they must pass without modification (FR-037) *(FR-037)*

## Phase 8: US6 — generated PDFs

- [ ] T065 [US6] Write a test asserting single column, selectable text, no table or image, and that an accented name renders without a placeholder glyph — **watch the glyph assertion fail if the fallback is not wired** *(FR-039, FR-040, SC-008)*
- [ ] T066 [US6] Register Archivo TTF for name and headings in `engine/resume_pdf.py`, keeping DejaVu for body
- [ ] T067 [US6] Wire `set_fallback_fonts()` with DejaVu so Unicode coverage survives (R6) *(FR-040)*
- [ ] T068 [US6] Rework hierarchy and spacing: name, section rules, body metrics *(FR-038)*
- [ ] T069 [US6] Apply the same treatment to the cover letter; confirm both remain ATS-safe *(FR-039, SC-008)*

## Phase 9: Verification, documentation, and the held gate

- [ ] T070 Run the full unit battery twice; the second run catches order dependence. **Name the preservation guarantees explicitly** (analysis G2) so they cannot silently lose coverage if this task is ever narrowed: prose links keep a non-colour cue (`test_web.py:100`), banners render server-side (`:77`), assets stay version-stamped (`:178`), the command palette stays keyboard-reachable (`:64`), form controls keep accessible labels (`:88`) *(FR-041, FR-043, FR-044, FR-045, SC-010)*
- [ ] T071 Run the browser suite on Windows
- [ ] T072 Run the browser suite on macOS — a gate, not a note (020's tag was cut twice because macOS caught what Windows passed)
- [ ] T073 Run `tests/test_secret_hygiene.py`; confirm no restyled surface exposes a secret (FR-046) *(FR-046)*
- [ ] T074 Run `packaging/check_version.py` **first**, then `packaging/smoke_test.py` on the frozen build
- [ ] T075 Verify no network request for any asset, with the machine actually disconnected (CHK059) *(FR-006)*
- [ ] T076 Walk all nine screens in light and dark; work the `checklists/design.md` items, recording judgements for CHK011, CHK028, CHK033
- [ ] T077 [P] Update `docs/USER_MANUAL.md` with the design system, the provenance stamp, density, and the navigation change
- [ ] T078 [P] Update `docs/USER_GUIDE.md` for the new navigation and the stamp
- [ ] T079 [P] Update `README.md`
- [ ] T080 [P] Add the `WHATS_NEW` entry for this release
- [ ] T081 **HELD: no tag, no release, no version pushed until the applicant says go** (SC-011) *(SC-011)*

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
