# Tasks: The Experience Release (feature 014, v1.4.0)

**Input**: Design documents from `/specs/014-experience/`
**Prerequisites**: plan.md, spec.md, research.md (measured baseline), data-model.md, quickstart.md

**Tests**: deterministic web-layer changes (date reach, cache headers/versioning,
render hooks, lifespan bootstrap) get pytest coverage; UX/perf verified by the
**chrome-devtools before→after** gate + real-browser suite + frozen smoke.

**Organization**: WS-0 measure → US4 audit (early, clean base) → US1 look →
US2 fast → US3 palette → Verify/ship.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files). Repo: `web/`, `.github/`, `tests/`, `packaging/`.

---

## Phase 1: Setup + WS-0 Measure

- [x] T001 Bump version to **1.4.0** (`engine/__init__.py`, `packaging/windows.iss`);
  `check_version.py` OK; add `WHATS_NEW["1.4.0"]` stub in `web/main.py`.
- [x] T002 WS-0 baseline (chrome-devtools-mcp): with the app running, capture a
  performance trace (LCP/CLS) + Lighthouse a11y for **job detail, Apply Assist,
  Analytics, Profile** (feed already done: LCP 941ms / CLS 0.27 / a11y 100) and
  append the full before-table to `research.md`.

---

## Phase 2: US4 — Audit fixes (early; a clean, green base)

- [x] T003 Confirm CI is green on `main` post-v1.3.0; if `.github/workflows/ci.yml`
  still fails on Ubuntu, diagnose + fix the Linux-only failures until green.
- [x] T004 [P] Write failing test `tests/test_web.py::test_startup_bootstrap_runs`
  asserting the app's startup bootstrap still runs under the lifespan pattern
  (e.g. sponsorship/extension stamp side-effect observable), then migrate
  `web/main.py` `@app.on_event("startup")` → `lifespan=` async context manager.
  Make it green.
- [x] T005 [P] Quiet warnings: silence the Starlette/`httpx` TestClient +
  FastAPI deprecations at their source (or filter in `pytest.ini` with a
  documented reason); target a materially lower total than ~329. Assert no
  `DeprecationWarning` from our own modules via a `-W error::DeprecationWarning`
  scoped run or a small guard test.
- [x] T006 [P] Extend `humandate` to every screen: apply `| humandate` in
  tracker/pipeline (`partials/pipeline_board.html`, tracker rows), analytics
  (`analytics.html`), and digest/alert templates; add
  `tests/test_web.py::test_no_raw_iso_dates_on_key_pages` rendering each and
  asserting no `\d{4}-\d{2}-\d{2}` user-facing date remains.
- [x] T007 Static asset caching + versioning: in `web/main.py` serve
  `styles.css`/`app.js`/`palette.js`/favicon with a long `Cache-Control` and
  reference them as `/static/x?v={APP_VERSION}` in `base.html`; test asserts the
  header + versioned URL (addresses the Cache insight; safe because the version
  query busts on upgrade).

**Checkpoint**: green CI, no own-code deprecations, dates consistent, assets cached.

---

## Phase 3: US1 — The look (P1)

- [x] T008 [US1] Refresh the token layer in `web/static/styles.css` (`:root` +
  `[data-theme="dark"]`): re-tuned type scale/rhythm, spacing, **elevation/shadow
  tokens**, motion tokens, and palette — holding AA in both themes. Guided by the
  `frontend-design` skill. Components keep deriving from tokens (no raw hex).
- [x] T009 [US1] Shared components pass: unify card/table/badge/button/input/
  empty-state styling so they're consistent across pages; polish the shell + nav
  density in `base.html`; give the match score a clearer visual treatment and make
  sponsor/eligibility badges visually distinct.
- [x] T010 [US1] Analytics inline charts (`analytics.html`): dependency-free inline
  **SVG** for funnel, source breakdown, score-band distribution, callback rate —
  rendered from the existing analytics data, `dataviz`-styled, theme-aware via
  tokens, with `<title>`/aria labels + an accessible data table fallback.
- [x] T011 [P] [US1] Add `tests/test_web.py` assertions: every page returns 200 and
  carries the refreshed shell hooks; the analytics page contains the chart `<svg>`
  with accessible labels. (Visual correctness in both themes is verified by the
  chrome-devtools/manual gate in WS-D.)

**Checkpoint**: cohesive look on every page in both themes; Analytics is a dashboard.

---

## Phase 4: US2 — Fast + responsive (P2)

- [x] T012 [US2] **Fix the CLS 0.27 at the source.** The `#update-banner` +
  `#whats-new-region` regions cause the shift by rendering EMPTY then injecting
  content on `hx-trigger="load"`; they are also usually empty (no pending update /
  no unseen version), so a naive fixed `min-height` would just trade the shift for
  a permanent dead gap. Instead **render both regions server-side inline** in the
  initial HTML — both states are cheaply known at render time (whats-new from
  settings; update status from the cached last-check result) — so there is no
  empty→filled injection and no reserved gap. Use skeletons ONLY for genuinely
  async, content-bearing loads (feed refresh, autofill status). A `.skeleton`
  component in `styles.css`. Re-measure in T015 → **CLS ≤ 0.1**.
- [x] T013 [US2] Optimistic status in `web/static/app.js`: Save/Applied/Hide flip
  the row immediately, then reconcile with the server (revert + error toast on
  failure), building on the existing toast/loading pattern. Keep the server as
  source of truth.
- [x] T014 [US2] Motion: adopt the **View Transitions API** for HTMX-boosted page/
  partial swaps + subtle CSS micro-interactions (hover/press/enter), ALL gated
  behind `@media (prefers-reduced-motion: reduce)`. Progressive — no-JS content
  unaffected.
- [ ] T015 [US2] Re-measure CLS on the feed with chrome-devtools; iterate until
  **CLS ≤ 0.1** (record the new number). Add a note to research.md.

**Checkpoint**: feels instant; CLS fixed at the source; reduced-motion honored.

---

## Phase 5: US3 — Command palette + keyboard (P3)

- [x] T016 [US3] `web/static/palette.js` (NEW, vanilla): Ctrl/⌘-K opens an ARIA
  dialog listing **navigation destinations + global actions** (Refresh now, toggle
  theme, start Apply Assist); type-to-filter, arrow/Enter to run, Escape to close,
  focus trapped only while open. Loaded from `base.html` (deferred).
- [x] T017 [US3] Feed keyboard nav in `app.js`: j/k move focus between job rows,
  Enter opens the focused job, `/` focuses the search/filter — no library.
- [x] T018 [P] [US3] `tests/test_extension_assets.py`-style static assert (or
  `test_web`): `palette.js` exists, is referenced in `base.html`, uses
  `role="dialog"`/Escape handling, and the shortcut is registered.

**Checkpoint**: jump anywhere by keyboard; palette is accessible.

---

## Phase 6: WS-D — Verify, docs, ship

- [x] T019 Re-measure ALL five key pages (chrome-devtools before→after table in
  research.md): CLS ≤ 0.1 (feed), LCP ≤ baseline, **Lighthouse a11y = 100 held**
  on every page; fix any a11y regressions from the new interactive pieces.
- [ ] T020 [P] Docs: USER_MANUAL §18 (visual/interaction changes + command
  palette/shortcuts), README (refreshed screenshots), `WHATS_NEW["1.4.0"]` filled.
- [ ] T021 Full battery: `pytest -q` ×2 + `-m browser` + `-m slow` green; manual
  walkthrough of every page in **light + dark** + **keyboard-only**; fix findings.
- [ ] T022 Frozen build + `packaging/smoke_test.py` PASS (redesigned shell +
  versioned static serve); then ship: merge `014-experience` → `main`, mirror
  `main:001-ai-job-engine`, tag `v1.4.0`; verify BOTH installers (exe `MZ` /
  dmg `78 01`) + SHA-256.

---

## Dependencies & Execution Order

- Setup+WS-0 (T001-T002) first. US4 audit (T003-T007) early — a clean base.
- US1 (T008-T011): T008 tokens → T009 components → T010 charts; T011 [P].
- US2 (T012-T015): T012 skeletons is the CLS fix; T015 re-measures.
- US3 (T016-T018) after the shell (base.html) settles.
- WS-D (T019-T022): T019/T021 gate T022 (ship).

## Parallel Opportunities

- T004/T005/T006 (distinct concerns) in parallel; T011/T018 test asserts; T020 docs.

## Implementation Strategy (MVP first)

MVP = Setup + US4 (clean base) + US1 (the look) + the T012 CLS fix — already a
huge visible upgrade. US2 polish, US3 palette, then the measured verify + ship.
