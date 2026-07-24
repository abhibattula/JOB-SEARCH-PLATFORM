# Feature Specification: The Refinements Release

**Feature Branch**: `013-refinements`  
**Created**: 2026-07-24  
**Status**: Draft  
**Input**: User description: "Fix + polish + performance pass after v1.2.0: (1) Apply Assist must fill in the user's default browser / connected companion, not Edge; (2) use the GPU when available + tune CPU threads + speed up resume extraction (no installer bloat); (3) human-readable dates '24 July 2026'; (4) visible sort arrows on Posted and Match; (5) a Back button on job detail; (6) a real app icon."

## Clarifications

### Session 2026-07-24

- Q: Exactly how should the human date read? → A: **"24 July 2026"** — title-case full month (day, full month name, year); not uppercase, not abbreviated.
- Q: Where should the new date format apply? → A: **Feed and job detail only** — other screens (tracker/pipeline, analytics, digests) keep their current date rendering for now.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Applications fill in the browser where I'm signed in (Priority: P1)

The user's everyday browser is Chrome, they installed the companion in Chrome,
and they're signed in to job sites there. When they run Apply Assist, the job
opens and fills **in Chrome** (via the connected companion) — or, if the
companion isn't connected, in their **default** browser — never in a different
browser (Edge) where they aren't signed in and the companion isn't watching.

**Why this priority**: This is a blocking bug — in v1.2.0 the fill opened in Edge
regardless of the user's default browser, so the companion never saw the page and
applications could not be completed. Nothing else in this release matters if the
core "fill in my own browser" promise is broken.

**Independent Test**: With the companion connected in the default browser, start
Apply Assist on a job and confirm the page opens and fills in that browser. With
the companion disconnected, confirm the assistant window opens in the OS default
browser (not a hardcoded other browser). Confirm "Open posting" opens in the
default browser too.

**Acceptance Scenarios**:

1. **Given** the companion is connected in the user's default browser, **When**
   Apply Assist starts on a saved job, **Then** the job opens and fills in that
   browser via the companion — not in a separate window in a different browser.
2. **Given** the companion is not connected, **When** Apply Assist starts,
   **Then** the assistant window opens in the user's **OS default** browser
   (falling back to another installed browser only if the default can't launch).
3. **Given** the user clicks "Open posting" on a job, **When** the link opens,
   **Then** it opens in the OS default browser handler.
4. **Given** the assistant window ends up in a different browser than the
   companion, **When** Apply Assist is running, **Then** the active
   backend/browser is shown to the user so any mismatch is visible, not silent.

---

### User Story 2 - A feed I can read and navigate comfortably (Priority: P2)

Dates read as "24 July 2026" instead of "2026-07-24"; the columns that can be
sorted (Posted date, Match score) show a clear, always-visible arrow the user can
click; and opening a job then wanting to go back is one obvious click.

**Why this priority**: These are daily-friction items that make the product feel
finished. They don't block the core loop (US1) but directly improve everyday use.

**Independent Test**: Load the feed and confirm dates render as "24 July 2026";
confirm both Posted and Match headers show a clickable sort indicator (not only
the active one); open a job and confirm a Back control returns to the feed.

**Acceptance Scenarios**:

1. **Given** the feed (and any job's detail page), **When** dates are shown,
   **Then** they render as "24 July 2026", and a date the source didn't provide is
   still clearly marked approximate.
2. **Given** the feed table, **When** it renders, **Then** both the Posted and
   Match columns show a persistent, clickable sort indicator; clicking it sorts by
   that column and the active column's indicator reflects the current sort.
3. **Given** a job detail page reached from the feed, **When** the user clicks
   **Back**, **Then** they return to the feed as they left it (filters/scroll
   preserved); reached by a direct link with no history, Back still lands on the
   feed.

---

### User Story 3 - Faster on-device AI (Priority: P3)

Scoring, drafting, and especially **resume extraction** run noticeably faster:
the offline AI uses the machine's GPU when the installed AI runtime supports it,
and always uses all CPU cores otherwise. Nothing breaks on a machine with no GPU.

**Why this priority**: Speed improves the experience (resume import feels slow
today) but the app already works; this is an optimization, so P3.

**Independent Test**: On a machine/runtime with GPU support, confirm the model
loads with GPU offload and inference is faster; on a CPU-only setup, confirm it
still loads and runs (graceful fallback) and uses all cores. Confirm resume
extraction completes faster than before with CPU tuning.

**Acceptance Scenarios**:

1. **Given** an AI runtime that supports GPU offload, **When** the offline model
   loads, **Then** it offloads to the GPU and inference is faster; **Given** a
   CPU-only runtime, **When** the model loads, **Then** it loads and runs on CPU
   with no error and using all available cores.
2. **Given** the same resume, **When** the user imports it, **Then** structured
   extraction completes faster than in v1.2.0, and re-importing the unchanged
   resume does not redo the work.
3. **Given** a machine with no GPU, **When** any AI feature runs, **Then**
   behavior and results are unchanged from before (offline-first still holds).

---

### User Story 4 - A recognizable app (Priority: P3)

The program has its own icon — on the application window, the taskbar, the
installer and its shortcuts, and as the browser tab favicon — instead of a blank
/ generic placeholder.

**Why this priority**: Polish and trust; not functional, so P3.

**Independent Test**: Launch the app and confirm the window/taskbar show the
icon; run the installer and confirm its icon and the created shortcuts show it;
open the app in a browser and confirm the tab shows the favicon.

**Acceptance Scenarios**:

1. **Given** the installed app, **When** it runs, **Then** the window and taskbar
   show the app icon.
2. **Given** the installer, **When** viewed/run, **Then** the setup file and the
   desktop/start-menu shortcuts show the app icon.
3. **Given** the app open in a browser tab, **When** the tab renders, **Then** the
   favicon is the app icon.

---

### Edge Cases

- **Default browser is Edge**: if Edge genuinely is the default, the assistant
  window uses Edge — the fix is "use the default," not "always Chrome".
- **Default browser is one that can't be automated** (e.g., Firefox for the
  automation path): fall back to the best available automatable browser and make
  the choice visible.
- **Companion connected but heartbeat briefly stale**: still prefer the companion
  (the user's real browser) rather than launching a different browser mid-session.
- **No GPU / CPU-only AI runtime**: GPU offload is skipped silently; everything
  works on CPU (this is the default installer path).
- **GPU present but the runtime/driver fails to initialize**: fall back to CPU
  automatically without surfacing an error to the user.
- **Missing/undetectable OS default browser**: fall back to a sensible install
  order without crashing.
- **Date value is absent or already human-formatted**: rendering must not crash;
  absent source dates remain marked approximate.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the companion is connected, Apply Assist MUST fill in that
  (the user's own) browser and MUST NOT open the job in a different browser.
- **FR-002**: When the companion is not connected, Apply Assist's assistant
  window MUST open in the user's **OS default browser** when it can be automated,
  falling back to another installed automatable browser only if the default
  cannot launch.
- **FR-003**: "Open posting" (and equivalent external-link opens) MUST use the
  OS default browser handler.
- **FR-004**: The active fill backend and the browser actually in use MUST be
  visible to the user during an Apply Assist session.
- **FR-005**: The offline AI MUST use GPU offload when the installed AI runtime
  supports it, and MUST fall back to CPU automatically (no error) when it does
  not, or when GPU initialization fails.
- **FR-006**: The offline AI MUST use all available CPU cores by default (tunable),
  improving CPU-path speed with no user action.
- **FR-007**: Resume extraction MUST be faster than v1.2.0 for the same input, and
  MUST NOT redo extraction for an unchanged resume.
- **FR-008**: The installer size and the default (CPU) AI behavior MUST be
  unchanged; GPU support MUST be opt-in for NVIDIA users via a single documented
  step, never a required larger download.
- **FR-009**: Dates shown in the **feed and on the job detail page** MUST render
  in the human-readable form **"24 July 2026"** (day, title-case full month,
  year); dates the source did not provide MUST remain marked approximate. Other
  screens keep their current date rendering (out of scope this release).
- **FR-010**: The feed's sortable columns (Posted, Match) MUST each show a
  persistent, clickable sort indicator; the active column's indicator MUST reflect
  the current sort.
- **FR-011**: The job detail page MUST provide a Back control that returns to the
  previous view (preserving the feed's filters/scroll when applicable) and lands
  on the feed when there is no prior history.
- **FR-012**: The application MUST present a branded icon on the app window, the
  taskbar, the installer and its shortcuts, and as the browser favicon.
- **FR-013**: All changes MUST preserve the constitution invariants: $0, offline
  works without a GPU, the engine core never depends on the web layer, and Apply
  Assist never auto-submits.

### Key Entities *(include if feature involves data)*

- **Default browser choice**: the ordered list of browsers Apply Assist will try
  for the assistant window, derived from the OS default; transient, computed at
  launch.
- **AI runtime configuration**: how the offline model is loaded — GPU offload
  amount and CPU thread count — derived from the machine and optional overrides.
- **App icon asset**: the single branded mark, in the formats each surface needs
  (window/taskbar, installer, favicon).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the companion connected in the default browser, 100% of Apply
  Assist sessions fill in that browser (0% open a different browser).
- **SC-002**: With the companion disconnected, the assistant window opens in the
  OS default browser in 100% of cases where that browser is automatable.
- **SC-003**: Resume extraction for a typical 1–2 page resume completes at least
  30% faster than v1.2.0 on the same CPU-only machine (thread tuning), and re-
  importing an unchanged resume does zero extraction work.
- **SC-004**: On a GPU-capable runtime, offline inference latency is materially
  lower than CPU-only for the same task; on a CPU-only machine, results and
  success rate are identical to v1.2.0 (no regression).
- **SC-005**: 100% of user-facing dates in the feed and job detail render in the
  human-readable form; none show the raw "YYYY-MM-DD".
- **SC-006**: Both sortable columns show a clickable sort indicator and sorting by
  each works, verified in the rendered feed.
- **SC-007**: From a job opened via the feed, Back returns to the feed in one
  click in 100% of cases (and never dead-ends when opened directly).
- **SC-008**: The app icon is present on the window, installer, shortcuts, and
  favicon (all four surfaces).

## Assumptions

- The user runs the packaged app (installer), whose bundled AI is a CPU build;
  GPU benefit for such users comes from opting into a GPU AI runtime, documented
  as one step. Source/advanced users benefit automatically if their runtime has
  GPU support. CPU thread tuning helps everyone with no action.
- "Default browser" is determined from the OS's registered handler for web links;
  on platforms where this can't be read, a sensible fixed order is used.
- The feed already supports sorting by date and by score via its existing view
  controls; this feature only makes the affordance visible and persistent, not a
  new sort backend.
- The date display change is presentation-only; stored dates are unchanged.
- The icon is a simple app mark (not a full brand identity), reused across all
  surfaces from one source image.
- Apply Assist continues to fill only in the user's own/default browser and never
  auto-submits.
