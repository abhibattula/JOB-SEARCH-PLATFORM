# Phase 0 Research: The Experience Release — measured baseline + decisions

## WS-0 baseline (measured with chrome-devtools-mcp, 2026-07-24)

App run locally (`python app.py`, 127.0.0.1:8000), populated feed. Desktop.

### Feed `/` (the primary page)

| Metric | Baseline | Verdict |
|--------|----------|---------|
| **LCP** | **941 ms** (TTFB 562 ms + render delay 380 ms) | OK locally; render delay improvable |
| **CLS** | **0.27 → 0.00** ✅ | FIXED (T012: banners rendered server-side inline, no post-load injection) |
| Lighthouse **Accessibility** | **100** | already excellent — must be held |
| Lighthouse Best Practices | 100 | hold |
| Lighthouse SEO | 90 | minor (3 fails, low priority for a local app) |

**Key insights (actionable):**
- **CLS 0.27** — the two top HTMX regions in `base.html` (`#update-banner`,
  `#whats-new-region`, both `hx-trigger="load"`) render **empty**, then inject
  content and shove the page down. This is the biggest single UX defect and maps
  directly to WS-C (reserve space / skeletons). Target: CLS ≤ 0.1.
- **Cache** insight — static assets (`styles.css`, `htmx.min.js`, `app.js`,
  favicon) are served without a long cache lifetime → slower repeat visits. Add
  long-cache headers + a version query so updates still bust the cache.
- **RenderBlocking** — `styles.css` blocks first render (small at localhost, but
  the CSS refresh should keep it lean).
- a11y is already 100 on the feed — the risk is **regressing** it with the new
  interactive pieces (command palette, skeletons, optimistic UI), so a11y
  verification must run on every touched page after the redesign.

> Baselines for job-detail / Apply Assist / Analytics / Profile are captured the
> same way at the start of implementation (WS-0 task) and re-measured at the end
> for a before→after table; the feed CLS 0.27 already anchors the perf goal.

### T019 before→after (re-measured with chrome-devtools-mcp, 2026-07-24, end of implementation)

| Page | CLS before→after | LCP | a11y before→after | Notes |
|---|---|---|---|---|
| Feed `/` | **0.27 → 0.00** ✅ | 921 ms (≤ 941 ms baseline) ✅ | 100 → 100 ✅ | banners now server-side inline (T012) |
| Job detail `/jobs/{id}` | n/a | — | 100 → **96 → 100** ✅ | fixed: inline prose link relied on color only (WCAG 1.4.1) → `p a` underline |
| Apply Assist `/autofill` | n/a | — | 100 → **93 → 100** ✅ | fixed: per-job checkbox unlabeled when queue non-empty → `aria-label` (baseline missed it: empty queue) |
| Analytics `/analytics` | n/a | — | 100 → 100 ✅ | new inline-SVG dashboard kept a11y (role=img + `<title>` + aria-label + data-table fallback) |
| Profile `/profile` | n/a | — | 100 → 100 ✅ | refreshed tokens held AA |

**Outcome**: CLS headline fixed at the source (0.27 → 0.00), LCP held under baseline,
Lighthouse a11y = **100 on all five key pages** after fixing the two regressions the
new/data-dependent content surfaced. Best Practices 100 across the board; SEO 90
(unchanged, low priority for a local desktop app). Guard tests added in
`tests/test_web.py` (`test_autofill_job_checkbox_has_accessible_label`,
`test_prose_links_have_non_color_cue`).

## Visual assessment (from a full-page screenshot of the current feed)

The current "datasheet" is functional but flat: dense small type, tight rows,
minimal hierarchy, the match score is a bare number, sponsor/eligibility badges
read similarly, and the top dashboard row (Top matches / Your applications / Next
actions) is text-heavy. It's a *power tool* — the redesign must **keep the
density** while adding a clear type hierarchy, spacing rhythm, elevation, a
visual match indicator, and distinct status/badge treatments. Identity stays
"instrument/datasheet + scope-screen" (locked), modernized.

## Code-level audit findings (read-only search; serena reserved for impl)

- **CLS source**: `web/templates/base.html` L42-43 — the two load-triggered
  banner regions with no reserved height.
- **Deprecation**: `web/main.py` has 1 × `@app.on_event("startup")` → migrate to
  the `lifespan=` context-manager pattern; also the Starlette/`httpx` TestClient
  deprecation surfaces in tests (~329 total warnings) — quiet where cheap.
- **CI**: `.github/workflows/ci.yml` runs full `pytest -q` on Ubuntu; the
  env-dependent `test_browser_channel.py` failures (fixed in v1.3.0) were one
  cause — confirm CI is green on `main` now and fix any residual Linux-only
  failures.
- **Date consistency**: the `humandate` filter (013) is applied on feed + job
  detail only; tracker/pipeline, analytics, and digests still render raw ISO —
  extend the filter across them.
- **Analytics** (`analytics.html`): text/numbers only, **no charts, no charting
  lib** — the rework *adds* dependency-free inline SVG charts (clarified).
- **Assets**: no `web/static/*.min.css`, no cache headers, no version-busting.

## Decisions

- **D1 — Evolve the token system, don't rewrite** (`web/static/styles.css`
  `:root`): keep the token architecture (every component already flows from
  tokens, no raw hex), re-tune type scale / spacing / elevation / palette per the
  `frontend-design` skill, in both themes, holding AA + the Lighthouse a11y 100.
- **D2 — Motion via the View Transitions API + CSS**, layered progressively:
  HTMX `hx-boost` with view-transition on swaps where supported; pure-CSS
  micro-interactions; all gated behind `prefers-reduced-motion`. No JS framework.
- **D3 — Perceived speed**: skeleton placeholders for every `hx-trigger="load"`
  region (fixes CLS at the source) + optimistic status flips in `app.js` building
  on the existing toast/loading pattern; reconcile/revert on server response.
- **D4 — Command palette + keyboard nav**: a small vanilla-JS module
  (`web/static/palette.js`), Ctrl/⌘-K, navigation + global actions only
  (clarified); j/k feed nav + `/` search focus. ARIA dialog semantics; Escape to
  close; focus trap only while open (not a page-wide trap).
- **D5 — Analytics charts**: dependency-free **inline SVG** rendered server-side
  from the existing analytics data, styled by the `dataviz` method, theme-aware
  via tokens, with accessible labels/`<title>`/data tables.
- **D6 — Perf plumbing**: long-cache headers + `?v={APP_VERSION}` on static
  assets; keep CSS lean; ensure the shell reserves space so CLS ~0.
- **D7 — Tech-debt**: FastAPI lifespan migration; CI green; warning cleanup;
  `humandate` everywhere.

## Testing strategy

- **Before→after metrics** (chrome-devtools-mcp) on the 5 key pages: LCP/CLS +
  Lighthouse a11y — must improve (CLS the headline) and hold a11y = 100.
- **Rendering/asset tests** (pytest): every page returns 200 and includes the
  new shell/skeleton/palette hooks; `humandate` reaches tracker/analytics/digests;
  static assets carry cache headers + versioned URLs; no raw ISO dates in rendered
  key pages.
- **Regression**: full `pytest -q` ×2 + `-m browser` + `-m slow` green; frozen
  smoke PASS; every page walked in both themes + keyboard-only.
