# Implementation Plan: The Case File

**Branch**: `022-the-case-file` | **Date**: 2026-08-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/022-the-case-file/spec.md`

## Summary

Replace the app's presentation layer with one design system — nine semantic
tokens, two vendored typefaces, and a provenance stamp — applied across all nine
app screens, the browser panel, and the generated PDFs. The work is as much
repair as redesign: roughly 35 class names are used in templates and defined in
no stylesheet, so screens including the live Apply Assist review list currently
render as unstyled HTML.

Three changes are behavioural rather than cosmetic and carry the bulk of the
"smoother" outcome: the feed stops replacing its rows when nothing changed
(a `204` short-circuit, not an animation), navigation becomes two rows that
cannot wrap, and the panel starts following the applicant's theme.

## Technical Context

**Language/Version**: Python 3.11+, plus hand-written CSS and vanilla ES5-compatible JS
**Primary Dependencies**: FastAPI + Jinja2 + HTMX (vendored), fpdf2 2.8.7. **No new runtime dependency.**
**Storage**: SQLite at `data/jobs.db`; two new preference rows via the existing `engine/settings.py` key/value store (`THEME` already exists; `FEED_DENSITY` is new)
**Testing**: pytest; real-browser suite under `tests/integration/` marked `-m browser`; packaged-build smoke via `packaging/smoke_test.py`
**Target Platform**: Windows and macOS desktop app (WebView2 / WKWebView shell) plus Chrome/Edge MV3 companion
**Project Type**: Desktop web application with a browser extension and a PDF renderer
**Performance Goals**: feed renders zero DOM replacements per minute while unchanged (from 12); nav occupies one row at ≥1024px; compact density shows at least as many jobs per screen as today
**Constraints**: fully offline — no network asset of any kind; $0 recurring; `engine/` never imports `web/`; no JS framework and no build step; `PROTOCOL_V` stays 1; ~229 KB of vendored fonts
**Scale/Scope**: 9 app screens, 11 partials, 1 stylesheet rewritten around a new token set, 1 extension panel, 1 PDF renderer, 49 functional requirements, 85 tasks

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Speed-to-Value First** | **PASS** | Justified by "help the user complete and submit applications faster": the Apply Assist review list — the screen used *during* a live application — currently renders unstyled, and provenance on the score that drives which jobs get an hour of effort is invisible without hovering. No deferred capability (auth/multi-user, hosted deployment, CLI/MCP) is built. No speculative abstraction: no CSS framework, no preprocessor, no component library. |
| **II. Zero-Subscription Cost** | **PASS** | Adds no dependency, paid or free. Typefaces are open-licensed (OFL), fetched once and vendored; the built app makes no network request for them. WCAG contrast checking is ~15 lines of arithmetic in the test rather than a package. |
| **III. API-First, Polite Ingestion** | **N/A → PASS** | This feature changes no ingestion path. No source is added, removed or re-rated; no request is made to any job board. The one-time font fetch is a development-time action against a public CDN, not part of the product. |
| **IV. Reusable Core, Thin Web Layer** | **PASS** | All changes are in `web/` (templates, stylesheet), `extension/`, and the presentation half of `engine/resume_pdf.py`. The only `engine/` writes are two `settings` reads and PDF typography. `engine/` gains no import from `web/`. The feed fingerprint lives in `web/main.py` because it is a transport concern, not business logic. |
| **V. Tested Core Logic** | **PASS** | The one piece of deterministic new logic — the feed fingerprint — gets tests before it is wired in (fingerprint stability, change detection, and the 204 path). The design system gets a mechanical gate (`tests/test_design_system.py`) that would have caught every finding in the audit. Presentation that cannot be asserted mechanically is verified in the visual pass and named as such, rather than covered by a string-presence assertion pretending to be a test. |

**Additional Constraints check**: stack unchanged (no Node, no JS framework);
privacy unchanged (no new data leaves the machine — the theme field travels only
over the existing local companion channel); recency rules untouched.

**Result: no violations. Complexity Tracking is empty.**

### Re-check after Phase 1 design

Re-evaluated against the generated artifacts: unchanged, still **PASS** on all
five. The design added no dependency, no engine→web import, and no new network
path. One item strengthened rather than weakened the gates — R2 replaced an
assumed provenance value (`cloud`) with the value actually stored (`llm`), which
removes a defect that would have shipped a stamp that never rendered.

## Project Structure

### Documentation (this feature)

```text
specs/022-the-case-file/
├── plan.md              # This file
├── spec.md              # 6 stories, 47 FRs, 12 success criteria
├── research.md          # Phase 0 — 10 decisions, all verified against code or network
├── data-model.md        # Phase 1 — tokens, semantic states, provenance, fingerprint
├── quickstart.md        # Phase 1 — how to run, see, and gate this
├── contracts/
│   ├── design-tokens.md      # the token contract every surface consumes
│   ├── provenance-stamp.md   # the one signature element, at three sizes
│   └── panel-theme.md        # the additive bridge field, PROTOCOL_V unchanged
└── checklists/
    ├── requirements.md       # spec quality (complete)
    └── design.md             # visual/a11y/regression checklist
```

### Source Code (repository root)

```text
web/
├── static/
│   ├── styles.css            # REWRITTEN around the nine tokens
│   ├── fonts/                # NEW — 6 woff2 (~229 KB) + OFL licences
│   ├── app.js                # density toggle wiring; existing module untouched
│   └── palette.js            # unchanged
├── templates/
│   ├── base.html             # two-tier tab nav, font preload
│   ├── feed.html · job_detail.html · profile.html · settings.html
│   ├── autofill.html · companion.html · diagnostics.html
│   ├── analytics.html · learned_answers.html
│   ├── practice_*.html       # UNTOUCHED — fixtures imitating third-party ATS
│   └── partials/             # all 11, incl. the unstyled autofill_status.html
└── main.py                   # feed fingerprint → 204; nav group context

extension/content/
└── panel.js                  # tokens replace the hardcoded GitHub-dark block

engine/
├── resume_pdf.py             # typographic hierarchy; DejaVu as fpdf2 fallback
├── settings.py               # (read-only use of the existing get/set)
└── autofill/ext_backend.py   # additive `theme` on overlay_state / watch_start

assets/fonts/                 # NEW — Archivo TTF for the PDF renderer

tests/
├── test_design_system.py     # NEW — the audit, as a gate
├── test_web.py · test_api.py · test_routes_autofill.py   # assertions re-read individually
└── integration/
    └── test_companion_widget.py   # panel theme + stamp, real browser
```

**Structure Decision**: no new top-level directory. The feature is presentational
and lands in the existing `web/`, `extension/content/`, and the rendering half of
`engine/`. Two new asset directories (`web/static/fonts/`, additions to
`assets/fonts/`) follow the paths the packaging spec and `paths.resource_path`
already resolve, so neither needs a packaging change.

## Phases

Phases are sequential. **Phase 1 ends at an approval gate** — the applicant sees
the Feed in light and dark with the stamp at all three provenance levels, and
approves or redirects before Phase 2 begins (SC-011).

Phase numbers match `tasks.md` exactly (analysis I1 — they previously did not).

| Phase | Content | Gate |
|---|---|---|
| **1** | Vendor fonts + licences; **capture the jobs-per-screen baseline before anything is restyled** | baseline recorded in `baseline.txt` |
| **2** | Write `test_design_system.py` **first** and watch it fail; then the token block, `@font-face`, the global reduced-motion override, the `--bg`/`--border` fix | the new test fails for the right reason (~35 undefined classes), then T2–T7 pass |
| **3** | Two-tier tab nav; the provenance stamp; the Feed (compact + comfortable, responsive fallback); the 204 fingerprint | **APPLICANT APPROVAL — screenshots, light and dark, all three stamps** |
| **4** | Job detail, Profile, Settings — including `.grid-2`, `.hint`, `.switch`, section indexes | allowlist shrinks; anchors still resolve |
| **5** | Apply Assist: the whole unstyled review vocabulary; ink/pencil/flag | allowlist shrinks; `test_routes_autofill` re-read individually |
| **6** | Companion, Diagnostics, Analytics, Learned answers | **zero undefined classes across the whole app** — allowlist empty |
| **7** | Extension panel tokens + theme + stamp | browser suite green; `PROTOCOL_V` still 1 |
| **8** | PDFs | ATS-safe, Unicode coverage intact |
| **9** | Docs, full verification set | all gates green — **held, no tag** |

## Risks

| Risk | Mitigation |
|---|---|
| Renaming classes breaks many of the 77 markup assertions in `test_api.py` | Clarified policy: re-read each break individually to decide whether test or markup was right; never blanket-update. Phased rollout keeps each break small and attributable. |
| The two-column Profile has never actually rendered, and its `id="field-*"` anchors are deep-linked from the panel | FR-024 pins anchor resolution; a test asserts every `field-*` anchor referenced anywhere still exists. |
| A 204 fingerprint that hashes too little serves stale rows; too much and it never fires | Fingerprint input is enumerated in `data-model.md` and tested in both directions — unchanged data yields 204, each mutable field yields a swap. |
| The stamp could read as decoration and lose the tooltip's information | FR-016/FR-017: non-colour differentiator plus text for assistive technology; the existing `title` explanation is kept, not replaced. |
| macOS catches what Windows passes (twice now, in 020) | Both-platform browser suite is a gate, not a note. |
| Fonts fail to load in the frozen shell | FR-007 system fallback in every stack, plus a frozen-smoke assertion that the app renders with fonts absent. |

## Complexity Tracking

> No Constitution Check violations. This section is intentionally empty.
