# Quickstart: The Experience Release (feature 014, v1.4.0)

## Prerequisites

- App running locally (`python app.py` → 127.0.0.1:8000) with a populated feed.
- `/reload-plugins` done so `chrome-devtools-mcp` is available for measurement.

## Measure before → after (the core gate)

1. **Before** (captured in `research.md`): feed LCP 941 ms, **CLS 0.27**,
   Lighthouse a11y 100. Capture the same for job-detail / Apply Assist / Analytics
   / Profile at the start of implementation.
2. Implement WS-A…WS-C.
3. **After**: re-run the chrome-devtools performance trace + Lighthouse a11y on the
   same 5 pages. **Pass = CLS ≤ 0.1 on the feed, LCP ≤ baseline, a11y = 100 held**,
   recorded as a before→after table.

## Try each area

### Look (US1)
- Every page in **light and dark** looks cohesive: refreshed type/spacing/
  elevation, consistent cards/tables/badges, intentional empty states. No
  unstyled/mis-themed elements.
- **Analytics** shows real inline charts (funnel, sources, score-band, callback
  rate), theme-aware and labeled.

### Fast (US2)
- Reload the feed → the top regions show **skeletons** (no blank flash, no jump);
  measured **CLS drops to ~0**.
- Click **Save / Applied / Hide** on a job → it flips **instantly**, reconciling
  with the server (reverts + toasts on failure).
- Navigation feels smooth (**View Transitions**); enabling OS "reduce motion"
  removes the animation.

### Palette + keyboard (US3)
- Press **Ctrl/⌘-K** → a searchable palette opens (navigation + global actions:
  Refresh now, toggle theme, start Apply Assist); Escape closes; fully keyboard
  operable.
- In the feed, **j/k** move between jobs, Enter opens, **/** focuses search.

### Clean codebase (US4)
- CI test job is **green** on a clean checkout (incl. Linux).
- `pytest -q` shows **no deprecation warnings from our code** and a much lower
  total warning count.
- Every screen (tracker/pipeline, analytics, digests included) shows
  **human-readable dates**.

## Verification battery (before ship)

- chrome-devtools before→after table shows improvement (CLS headline) + a11y 100.
- `pytest -q` ×2 + `-m browser` + `-m slow` green; frozen build + `smoke_test.py`
  PASS; every page walked in both themes + keyboard-only.
- Ship v1.4.0 → verify BOTH installers (exe `MZ` / dmg `78 01`) + SHA-256.
