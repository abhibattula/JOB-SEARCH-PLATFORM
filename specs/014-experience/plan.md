# Implementation Plan: The Experience Release

**Branch**: `014-experience` | **Date**: 2026-07-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/014-experience/spec.md`

## Summary

A full visual + interaction redesign of the web UI (evolving the existing
instrument/datasheet identity, same stack — Jinja + HTMX + design tokens + vanilla
JS, **no framework, no build step**) shipped together with a sweep of real
errors/tech-debt. A **measured** release: the chrome-devtools baseline already
found the headline defect — **feed CLS = 0.27 (poor)**, caused by the two top
`hx-trigger="load"` banners injecting content post-load — plus static assets
without cache headers, while Lighthouse **a11y is already 100** (to be held).
Work: refresh the token system + shared components, add motion (View Transitions),
skeletons + optimistic UI (fixing CLS at the source), a command palette +
keyboard nav, dependency-free inline Analytics charts, and the audit fixes (CI
green, FastAPI lifespan, warning cleanup, `humandate` everywhere).

## Technical Context

**Language/Version**: Python 3.11+ (thin web layer); Jinja2 templates; vanilla ES
modules; **no JS framework, no Node build** (constitution constraint).
**Primary Dependencies**: FastAPI + Jinja2 + HTMX (vendored). New: none (inline
SVG charts, CSS View Transitions, a small vanilla `palette.js`). **Storage**: none
changed. **Testing**: pytest (render/asset assertions) + **chrome-devtools-mcp**
before→after metrics (LCP/CLS + Lighthouse a11y) + real-browser suite + frozen
smoke. **Target Platform**: desktop web-app (pywebview shell + browser).
**Performance Goals**: **CLS ≤ 0.1** (from 0.27), LCP ≤ baseline, a11y = 100 held,
status actions reflect < ~100 ms. **Constraints**: $0, offline, engine never
imports web, no new dependency/build step, Apply Assist behavior unchanged.

## Constitution Check

*GATE: evaluated against constitution v1.1.3. Re-checked after Phase 1.*

- **I. Speed-to-Value** — PASS. A better, faster, more usable UI helps the user
  work the pipeline faster; fixes real defects (CLS) and tech-debt (CI/deprecs).
  No deferred capability built.
- **II. Zero-Subscription Cost** — PASS. No new dependency; inline SVG + CSS +
  vanilla JS; installer unchanged.
- **III. no-bot-bypass / no auto-submit** — PASS. UI-only; Apply Assist untouched.
- **IV. Reusable Core, Thin Web Layer** — PASS. All changes are in `web/`
  (templates, static, one lifespan tweak in `web/main.py`) + CI/tests; the
  `engine/` core is not touched and still never imports web.
- **V. Tested Core Logic** — PASS. No engine logic changes; new deterministic
  bits (date filter reach, cache-header/versioning, render hooks) get pytest
  coverage; UX/perf verified by the chrome-devtools before→after gate.

Stack stays inside the fixed "Jinja + HTMX + vendored assets, no build" rule — **no
constitution amendment needed**. No violations → Complexity Tracking omitted.

## Project Structure

### Documentation (this feature)

```text
specs/014-experience/
├── plan.md ├── research.md (baseline metrics + audit) ├── data-model.md
├── quickstart.md ├── checklists/requirements.md └── tasks.md (/speckit.tasks)
```
(No contracts/ — no new external interface.)

### Source Code (repository root)

```text
web/
├── static/
│   ├── styles.css        # EDIT — refresh token layer + components + motion + skeletons + palette/chart styles
│   ├── app.js            # EDIT — optimistic status actions, view-transition hooks (progressive)
│   └── palette.js        # NEW — command palette (Ctrl/⌘-K) + keyboard nav (nav + global actions)
├── main.py               # EDIT — FastAPI on_event→lifespan; long-cache + versioned static; humandate already registered
├── templates/
│   ├── base.html         # EDIT — shell/nav polish; reserve space + skeletons for the load-triggered regions (CLS fix); load palette.js; favicon/version asset URLs
│   ├── partials/*.html   # EDIT — cards/tables/badges/empty-states consistency; skeleton partials; humandate in tracker/pipeline/digests
│   ├── analytics.html    # EDIT — inline SVG charts (funnel, sources, score-band, callback rate) via dataviz method
│   └── (feed/job_detail/profile/settings/autofill/companion) # EDIT — apply refreshed components; humandate everywhere
.github/workflows/ci.yml  # EDIT if needed — make the Linux test job green
tests/
├── test_web.py           # EDIT — humandate reach; render hooks (skeletons, palette, chart svg); cache headers/versioned assets; no raw ISO on key pages
├── test_api.py           # EDIT — optimistic status endpoints still behave; lifespan startup still runs bootstrap
└── test_packaging/smoke  # smoke_test.py already checks the shell; extend for versioned static if cheap
packaging/smoke_test.py   # EDIT — assert the redesigned shell + static versioning serve in the frozen build
```

**Structure Decision**: everything lives in `web/` + CI/tests + docs. One new
static file (`palette.js`). No DB change, no dependency, no contracts.

## Phasing (maps to user stories + measurement)

- **WS-0 Measure (first)**: capture LCP/CLS + Lighthouse a11y for the 5 key pages
  (feed done: CLS 0.27) → `research.md` before-table.
- **US4 Audit fixes (do early — unblocks a clean base)**: CI green; FastAPI
  lifespan; warning cleanup; `humandate` everywhere; static cache+versioning.
- **US1 Look (P1)**: token refresh + shared components + shell/nav + empty states +
  Analytics inline charts; both themes, hold a11y = 100.
- **US2 Fast (P2)**: skeletons for load-regions (**CLS fix**) + optimistic status +
  View Transitions (reduced-motion honored).
- **US3 Palette (P3)**: `palette.js` command palette + keyboard nav.
- **WS-D Verify/ship**: re-measure (before→after table must improve), full test
  battery + frozen smoke, docs, v1.4.0 ship + verify BOTH installers.

## Complexity Tracking

No constitution violations — intentionally empty.
