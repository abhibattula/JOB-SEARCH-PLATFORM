# Feature Specification: The Experience Release

**Feature Branch**: `014-experience`  
**Created**: 2026-07-24  
**Status**: Draft  
**Input**: User description: "A full visual + interaction redesign of the web UI (evolving the existing engineering-instrument identity, same stack, no framework) PLUS a sweep of accumulated errors/tech-debt, shipped together. Measure a real performance + accessibility baseline first and improve on it."

## Clarifications

### Session 2026-07-24

- Q: The Analytics page is text/numbers only today — how far should the viz rework go? → A: **Add lightweight, dependency-free inline charts** (funnel, source breakdown, score-band distribution, callback rate) styled via the dataviz method, light/dark-aware and accessible — no charting library, no build step.
- Q: How broad should the command palette be this release? → A: **Navigation + global actions only** (jump to any page/view + global actions like Refresh now, toggle theme, start Apply Assist) — not per-job/context actions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A cohesive, modern, accessible interface (Priority: P1)

Every screen looks like one intentional, polished product — consistent
typography, spacing, cards, tables, badges, and empty states — in both the light
("datasheet") and dark ("scope-screen") themes. Text meets accessibility contrast
standards, every interactive element is reachable and operable by keyboard with a
visible focus indicator, and nothing looks broken or half-styled.

**Why this priority**: The look-and-feel is what the user experiences on every
visit; a coherent, accessible redesign is the core of this release and the
foundation everything else sits on.

**Independent Test**: Walk every page in both themes and confirm consistent,
polished styling and correct rendering; run an accessibility check and confirm
contrast, focus, ARIA, and tap-target issues are resolved; navigate the whole app
using only the keyboard.

**Acceptance Scenarios**:

1. **Given** any page, **When** viewed in light and in dark theme, **Then** it
   renders with consistent, intentional styling (type, spacing, color, components)
   and no unstyled/broken elements in either theme.
2. **Given** any page, **When** its text and controls are checked for contrast,
   **Then** all text and meaningful UI meets AA contrast in both themes.
3. **Given** any page, **When** the user navigates with the keyboard only,
   **Then** every interactive element is reachable and operable, with a clearly
   visible focus indicator and no keyboard traps.
4. **Given** the shared components (cards, tables, badges, buttons, empty states),
   **When** they appear on different pages, **Then** they look and behave
   consistently everywhere.

---

### User Story 2 - It feels fast and responsive (Priority: P2)

The app feels quick: actions give instant visual feedback, content areas show a
loading placeholder instead of a blank flash while they fetch, page and section
transitions are smooth, and measured load performance is better than before.

**Why this priority**: Perceived and real speed strongly shape how good the
product feels; this is the second pillar of the redesign after the look.

**Independent Test**: Compare measured Core Web Vitals (largest-content load,
layout stability, main-thread responsiveness) on the key pages before vs. after,
and confirm improvement; observe skeleton placeholders on data-loading regions and
instant status changes (Save/Applied/Hide) that reconcile with the server.

**Acceptance Scenarios**:

1. **Given** the key pages, **When** their load performance is measured after the
   redesign, **Then** the largest-content load time and layout-stability and
   responsiveness metrics are the same or better than the recorded baseline.
2. **Given** a region that loads data after the page appears, **When** it is
   fetching, **Then** a skeleton/placeholder is shown rather than empty space or a
   content jump.
3. **Given** a job's status action (Save / Applied / Hide), **When** the user
   clicks it, **Then** the UI updates immediately and reconciles with the server
   result, showing an error and reverting only if the server rejects it.
4. **Given** motion/transitions, **When** the user has "reduce motion" enabled,
   **Then** animations are minimized or removed.

---

### User Story 3 - Get anywhere fast (keyboard + command palette) (Priority: P3)

A power user can jump to any page or run common actions without the mouse: a
command palette (opened with Ctrl/Cmd-K) offers quick navigation and actions, and
common lists support keyboard navigation.

**Why this priority**: A meaningful interactivity upgrade that speeds daily use,
but the product is fully usable without it, so it's P3.

**Independent Test**: Open the command palette with the keyboard shortcut, search
for a destination/action, and execute it; navigate the feed list with the
keyboard.

**Acceptance Scenarios**:

1. **Given** any page, **When** the user presses the command-palette shortcut,
   **Then** a searchable palette opens listing navigation destinations and common
   actions, operable entirely by keyboard and dismissable with Escape.
2. **Given** the feed, **When** the user uses the list-navigation keys, **Then**
   focus moves between jobs and the focused job can be opened from the keyboard.

---

### User Story 4 - A clean, trustworthy codebase (Priority: P3)

The project's automated checks pass, deprecation warnings are gone, test output is
quiet, and dates read consistently in human form on every screen — so the product
is reliable and maintainable and nothing shows raw machine formatting.

**Why this priority**: Reliability/maintainability underpins everything but isn't
directly user-visible except through consistency and trust, so P3.

**Independent Test**: The continuous-integration checks pass on a clean checkout;
the test run reports no deprecation warnings from our code and a much lower total
warning count; every screen shows human-readable dates.

**Acceptance Scenarios**:

1. **Given** a clean checkout, **When** the continuous-integration test job runs,
   **Then** it passes (green), including on Linux.
2. **Given** the test suite, **When** it runs, **Then** it emits no
   deprecation warnings originating from our own code, and the overall warning
   count is materially reduced.
3. **Given** any screen that shows a date (feed, job detail, tracker/pipeline,
   analytics, digests), **When** it renders, **Then** the date is human-readable
   (e.g., "24 July 2026"), never raw "YYYY-MM-DD".

---

### Edge Cases

- **Reduced motion**: users who prefer reduced motion get minimal/no animation.
- **Theme switching**: toggling light/dark re-renders everything correctly with no
  leftover mis-themed elements.
- **Slow/failed data loads**: skeletons resolve to content or a clear error; an
  optimistic status action that the server rejects reverts and explains.
- **No-JS / JS still loading**: core content is server-rendered and readable;
  enhancements (transitions, palette, optimistic UI) layer on and degrade
  gracefully.
- **Small windows / narrow widths**: the shell, tables, and charts remain usable
  and non-overflowing.
- **Empty states**: every list/section has an intentional empty state, not a blank
  area.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every page MUST present a cohesive, intentional visual design driven
  by one shared design-token system, in both the light and dark themes, with no
  unstyled or inconsistent components.
- **FR-002**: All text and meaningful interactive elements MUST meet AA contrast in
  both themes.
- **FR-003**: Every interactive element MUST be keyboard-reachable and operable
  with a visible focus indicator and no keyboard traps.
- **FR-004**: Shared components (cards, tables, badges, buttons, inputs, empty
  states) MUST be visually and behaviorally consistent across all pages.
- **FR-005**: The Analytics page MUST present the funnel, source breakdown,
  score-band distribution, and callback rate as **dependency-free inline charts**
  forming one coherent, accessible chart system correct in both light and dark
  themes (no charting library, no build step).
- **FR-006**: Data regions that load after initial render MUST show a
  skeleton/placeholder while loading, avoiding blank flashes and content jumps.
- **FR-007**: Job status actions (Save / Applied / Hide) MUST update the UI
  immediately (optimistic) and reconcile with the server, reverting with an error
  message if the server rejects the change.
- **FR-008**: Page and section transitions MUST be smooth and MUST be minimized or
  disabled when the user prefers reduced motion.
- **FR-009**: The app MUST provide a command palette (opened by a keyboard
  shortcut) covering **navigation destinations and global actions** (e.g., Refresh
  now, toggle theme, start Apply Assist) — not per-job/context actions this
  release — fully keyboard-operable and dismissable, plus keyboard navigation of
  the feed list.
- **FR-010**: Measured load performance (largest-content load, layout stability,
  main-thread responsiveness) on the key pages MUST be equal to or better than the
  recorded pre-redesign baseline.
- **FR-011**: The continuous-integration test job MUST pass on a clean checkout,
  including on Linux.
- **FR-012**: The test suite MUST emit no deprecation warnings from our own code
  and MUST have a materially reduced total warning count.
- **FR-013**: Every user-facing date on every screen MUST render in the
  human-readable form; none may show raw "YYYY-MM-DD".
- **FR-014**: All existing functionality (feed, filters, scoring, sponsorship,
  Apply Assist, discovery badge, tracker, profile, settings) MUST continue to work
  unchanged; this release changes presentation, interactivity, and internal
  quality only.
- **FR-015**: The redesign MUST stay within the existing delivery model — no new
  paid dependency, works offline, and no change to Apply Assist's behavior (it
  still never auto-submits).

### Key Entities *(include if feature involves data)*

- **Design token set**: the single source of visual truth (color, type scale,
  spacing, elevation, radius, motion) that every component derives from, defined
  once per theme.
- **Baseline metrics record**: the measured pre-redesign performance + a11y
  findings per key page, used as the bar the redesign must beat.
- **Component inventory**: the shared UI components (card, table, badge, button,
  input, empty state, chart, skeleton, palette) that must be consistent everywhere.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the measured key pages, the largest-content load time is **≤ the
  recorded baseline** (target: a noticeable improvement), and layout-stability and
  responsiveness metrics are the same or better.
- **SC-002**: 100% of text/meaningful UI meets AA contrast in both themes (zero
  contrast failures in the audit).
- **SC-003**: 100% of interactive elements are keyboard-operable with a visible
  focus indicator; zero keyboard traps.
- **SC-004**: Every page renders correctly in both light and dark themes (zero
  mis-themed/unstyled elements), verified across all pages.
- **SC-005**: The continuous-integration job passes on a clean checkout (green),
  including Linux.
- **SC-006**: Zero deprecation warnings from our own code in the test run, and the
  total warning count is reduced by a clear margin from the current ~329.
- **SC-007**: 100% of user-facing dates render human-readable across all screens.
- **SC-008**: The full existing test battery + frozen smoke test stay green (no
  functional regressions).
- **SC-009**: Status actions reflect on screen in under ~100 ms (optimistic),
  independent of server round-trip.

## Assumptions

- The current stack is kept: server-rendered templates + HTMX + a design-token CSS
  system + vanilla JS — no JS framework and no build step (a project constraint).
- The visual identity is *evolved*, not replaced: the engineering-instrument /
  datasheet + scope-screen character is retained and modernized.
- "Key pages" for measurement = the feed, a job detail page, Apply Assist,
  Analytics, and Profile (the most-used screens).
- The performance/accessibility baseline is captured with browser dev tooling
  before any redesign work and re-measured after.
- Enhancements (transitions, optimistic UI, command palette) are progressive: core
  content is server-rendered and remains usable if scripting is unavailable.
- No engine/business-logic or Apply Assist behavior changes; this is a
  presentation + interactivity + internal-quality release.
