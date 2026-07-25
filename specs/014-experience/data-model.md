# Phase 1 Data Model: The Experience Release

**No database schema change, no migration.** This is a presentation +
interactivity + internal-quality release. The "entities" are front-end/config
artifacts, not persisted data.

## Design artifacts (not persisted)

### Design token set (`web/static/styles.css` `:root` + `[data-theme]`)
The single source of visual truth every component derives from.

| Group | Tokens (evolved) |
|-------|------------------|
| color | surfaces, ink/muted, line, accent(+tint), status lamps (ok/warn/danger), draft — re-tuned, AA in both themes |
| type | `--sans`/`--mono`, `--fs-*` scale (re-rhythmed), weights, line-heights |
| space | `--s1..s6` spacing scale (rhythm) |
| shape | `--r-*` radii, new `--shadow-*` elevation tokens |
| motion | new `--ease-*`, `--dur-*` tokens; all uses gated by `prefers-reduced-motion` |

Components keep flowing from tokens (no raw hex) — the refresh is centralized.

### Component inventory (must be consistent across all pages)
card · table · badge (status/sponsor/grade) · button (primary/ghost/danger) ·
input/select · empty-state · **skeleton** (new) · **command palette** (new) ·
**inline chart** (new: bar/funnel/distribution).

### Baseline metrics record (`research.md`)
Per key page: LCP, CLS, Lighthouse a11y — the pre-redesign numbers the release
must beat (feed baseline: LCP 941 ms, **CLS 0.27**, a11y 100).

## Reused server data (unchanged shapes)

- Feed/job rows, tracker stages, and the **analytics** aggregates already produced
  by `engine/` + `web/` are rendered as-is; the redesign only changes how they are
  presented (e.g., analytics numbers → inline SVG charts). No new fields, no query
  changes (reworking the sort/query backend is a non-goal).
- Dates: the stored `posted_date`/`first_seen`/stage timestamps are unchanged; the
  `humandate` filter (013) is simply applied on more screens.

## Front-end state (ephemeral, in-page)

- **Optimistic status**: on Save/Applied/Hide, the row reflects the new state
  immediately and reconciles with the server response (revert + toast on failure).
  No new persistence — the server remains the source of truth.
- **Command palette**: transient open/closed + query state in `palette.js`; no
  storage. Theme preference continues to use the existing settings mechanism.
