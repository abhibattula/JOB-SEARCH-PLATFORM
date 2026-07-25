# Feature 014 "The Experience Release" (v1.4.0): measured audit fixes + a full visual/interaction redesign

## Context

The app is functionally deep (find → decide → discover → apply → track) but the
UI is a 007-era hand-rolled token system that hasn't had a holistic pass, and a
few real errors/tech-debt items have accumulated. The user wants a **full visual
redesign — more interactive and fast** — plus a sweep of **errors and
improvements**. Locked decisions (AskUserQuestion, 2026-07-24): **evolve the
current stack** (keep Jinja + HTMX + design tokens; NO framework/build step, so
$0 and constitution-compliant); ship **redesign + audit fixes together** as
v1.4.0; and do **measured research first** — use the newly installed
`chrome-devtools-mcp` (real LCP/CLS/TBT + a11y traces of the running app) and
`serena` (semantic code audit) to make the plan evidence-based, not guesswork.

> Plugin reality: `serena` + `chrome-devtools-mcp` require **`/reload-plugins`**
> (or a session restart) before their MCP tools are callable — they are installed
> but not yet loaded. The `typescript/csharp/php` LSPs do **not** apply to this
> Python + Jinja + vanilla-ES-module stack and are out of scope. The
> `frontend-design` and `dataviz` skills inform the design.

## Workstreams

### WS-0 — Measure the baseline (evidence, done FIRST during implementation)

- **chrome-devtools-mcp**: launch the running app, capture a performance trace +
  Core Web Vitals (LCP/CLS/TBT) and an **a11y audit** for the key pages (feed `/`,
  job detail, Apply Assist, Analytics, Profile). Record numbers as the baseline
  to beat. Repeat after the redesign for a before→after table.
- **serena**: semantic audit of `web/` + `engine/` — find dead/duplicated CSS
  classes, unused template partials, inconsistent components, and any risky
  patterns; feed the findings into WS-B/WS-C.
- Output: a short `specs/014-experience/research.md` "baseline metrics + audit
  findings" table that the redesign must improve on.

### WS-A — Fix the real errors / tech debt (the audit)

- **CI green on Linux**: `.github/workflows/ci.yml` runs full `pytest -q` on
  Ubuntu and has been red; the env-dependent `test_browser_channel.py` failures
  were one cause (fixed in v1.3.0 — confirm) — investigate + fix any remaining
  Linux-only failures so the badge is green.
- **Deprecations**: migrate the FastAPI `@app.on_event("startup")` in
  `web/main.py` to the lifespan-handler pattern; address the Starlette/`httpx`
  TestClient deprecation; quiet the ~329 suite warnings where cheap.
- **Date consistency**: extend the `humandate` filter (from 013) to the
  tracker/pipeline + analytics + digests so no screen shows raw `YYYY-MM-DD`.
- **Accessibility fixes** surfaced by the WS-0 a11y audit (contrast, focus rings,
  ARIA, tap-target sizes, keyboard traps).

### WS-B — Design-system refresh (the "look")

- **Aesthetic direction (locked):** *evolve the Instrument identity* — keep the
  distinctive engineering / "datasheet" (light) + "scope-screen" (dark)
  character that sets it apart from generic job tools, and modernize it (type,
  spacing, elevation, motion, re-tuned palette). Not a mainstream-SaaS pivot.
- Refresh `web/static/styles.css` token layer (the existing `:root` block):
  modernized **type scale + rhythm**, **spacing/rounding**, **elevation/shadow**,
  and a re-tuned palette that keeps AA contrast in both light ("datasheet") and
  dark ("scope screen") themes — driven by the `frontend-design` skill so it
  reads as intentional, not templated. Components keep flowing from tokens (no
  raw hex), so the refresh is centralized.
- Polish the shell: `web/templates/base.html` topbar/nav density, brand mark
  (reuse the new app icon), consistent card/table/badge components, empty states.
- **Analytics** (`analytics.html`) charts reworked via the `dataviz` skill (one
  coherent, accessible chart system; light/dark aware).

### WS-C — Interactivity + speed (the "more interactive and fast")

- **Motion**: adopt the **View Transitions API** for page/partial swaps (HTMX
  `hx-boost` + `transition:true` where supported; graceful no-JS fallback),
  subtle enter/hover/press micro-interactions, respecting
  `prefers-reduced-motion`.
- **Perceived speed**: **skeleton loaders** for the HTMX-loaded regions
  (`update-banner`, `whats-new`, feed refresh, autofill status) and **optimistic
  UI** on status actions (Save/Applied/Hide flip instantly, reconcile on
  response) — building on the existing `app.js` toast/loading pattern.
- **Keyboard & command**: j/k feed navigation, `/` to focus search, and a
  lightweight **command palette** (Ctrl/⌘-K) for jump-to-page/actions — vanilla
  JS, no dep.
- **Real speed**: cache-bust + long-cache static assets, defer/scope JS, trim CSS
  dead code (from serena), ensure the feed's first paint is server-rendered
  (it already is) — validated by re-running the WS-0 chrome-devtools trace
  (target: LCP under the baseline, CLS ~0).

### WS-D — Verify, docs, ship

- chrome-devtools before→after metrics table (LCP/CLS/TBT + a11y) must show
  improvement; full `pytest -q` ×2 + `-m browser` + `-m slow` green; frozen build
  + `smoke_test.py` PASS; manual walkthrough of every page in both themes.
- Docs: USER_MANUAL §18 (what changed visually), README screenshot refresh,
  WHATS_NEW 1.4.0. Version 1.4.0. Ship ritual → verify BOTH installers.

## Constitution guardrails

Stays inside the fixed stack (**Jinja + HTMX + vendored assets, no Node build,
no JS framework** — no amendment needed) · $0 · engine never imports web ·
offline-first · Apply Assist unchanged (never auto-submits). The redesign is
CSS/templates/vanilla-JS + View Transitions only.

## Verification

- WS-0 baseline vs WS-D re-measure (chrome-devtools-mcp): LCP/CLS/TBT improved,
  a11y issues resolved.
- Every page renders correctly in light + dark, keyboard-navigable, reduced-motion
  honored.
- Full test battery + frozen smoke green; both installers verified on the release.

## Process

New branch `014-experience` → design doc → full speckit chain (specify → clarify
→ plan → checklist → tasks → analyze, fix findings) → **WS-0 measure** → hybrid
`/speckit-implement` + superpowers TDD → docs → frozen smoke → ship v1.4.0.
Same pipeline as 010–013; ask before implementation.

## Non-goals

SPA/framework rewrite (chosen against) · a new brand identity beyond evolving the
current one · reworking the sort/query backends · code signing (needs a paid
cert — $0 constraint) · touching the fill/scoring engines.

## Immediate next step (unblocks the measured research)

Run **`/reload-plugins`** so `chrome-devtools-mcp` + `serena` tools load; then I
start the app and capture the WS-0 baseline (LCP/CLS/a11y + code audit) and fold
the real numbers into this plan before we implement.
