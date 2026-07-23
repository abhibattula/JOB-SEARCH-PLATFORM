# Feature Specification: The Live Fill Engine

**Feature Branch**: `009-live-fill-engine`
**Created**: 2026-07-23
**Status**: Draft
**Input**: User description: "Rebuild Apply Assist from scratch as a live fill engine (it opens the browser but never fills anything — root causes confirmed), rebuild profile import from resume around an explicit review screen with background extraction (it silently did nothing), make the offline model the default AI tier, and add a bundled practice application that proves Apply Assist works on the user's machine."

Approved design doc: `docs/superpowers/specs/2026-07-23-feature-009-design.md`
(root causes confirmed by two 2026-07-23 code investigations with file:line
evidence, recorded in the design doc and plan).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apply Assist actually fills applications (Priority: P1)

The user starts Apply Assist on saved jobs. The browser opens each job at
the page where its application form actually lives. From that moment the
app continuously watches the open page and fills every empty field it
recognizes the instant that field exists — whether the form rendered late,
lives inside an embedded frame, appeared because the user clicked the
site's own Apply button, or belongs to the next page of a multi-step
application the user advanced to. The status panel shows live activity:
how many fields are visible, how many are filled, and what the app is
waiting for. The app never clicks anything.

**Why this priority**: This is the product's headline capability and it
has never worked on real job sites ("total waste" — user, on v0.8.0). Two
independent root causes each guaranteed zero fills; the rebuild removes
both plus every defect that blocked recovery.

**Independent Test**: Start a queue on one real Greenhouse, one Lever, one
Ashby, and one Indeed job. For each: the browser lands on the correct form
page (or the posting page with on-screen guidance), and recognized fields
visibly fill within a few seconds of the form appearing — including after
the user clicks the site's Apply button and after advancing to a second
form page.

**Acceptance Scenarios**:

1. **Given** a Lever or Ashby job, **When** the queue opens it, **Then**
   the browser lands on the application-form URL (not the description
   page) and fields fill once the form renders.
2. **Given** a form that renders slowly (script-driven), **When** it
   finishes rendering seconds after the page opens, **Then** the fields
   fill without any user action — no one-shot "couldn't read this page"
   dead end exists anymore.
3. **Given** an application form embedded inside a frame on a company
   careers page, **When** it appears, **Then** its fields fill the same as
   a top-level form.
4. **Given** a posting page whose form only appears after the user clicks
   the site's own Apply button, **When** the user clicks it, **Then** the
   revealed fields fill within a few seconds, and until then the panel
   shows guidance ("click the site's Apply button — fields fill the moment
   the form appears").
5. **Given** a multi-page application, **When** the user clicks the site's
   own Next and a new form page loads, **Then** the new page's fields fill
   — reliably, on every page (the old navigation-event mechanism that
   silently never worked is gone).
6. **Given** any field the user is actively typing in or has already
   filled, **Then** the app never overwrites it; **and** the app never
   clicks submit, login, next, apply, or any other control — ever.
7. **Given** the second, third, … job in a queue, or a re-scan, or
   confirming a drafted answer, **Then** these work as reliably as the
   first job (all browser work now lives on one dedicated worker;
   cross-thread breakage is structurally impossible).
8. **Given** a field whose label the app cannot answer, **Then** the
   existing pause-for-review flow (drafted answer, user confirms) still
   applies, and confirmed answers fill from the worker reliably.

---

### User Story 2 - Proof it works on my machine (Priority: P2)

From the Apply Assist page, the user clicks "Test Apply Assist". A
realistic practice application (bundled with the app, served locally)
opens in the browser and the user watches their own profile data fill in
live — name, email, phone, resume file, a work-authorization dropdown, a
custom question — including a section that renders late and a section
inside an embedded frame. No real job site is involved. Anywhere in the
app that needs the user's attention now scrolls into view and is
highlighted.

**Why this priority**: Trust. The user has been burned three releases in a
row; this makes "it works" verifiable in ten seconds on their own machine,
and the same practice pages become the automated browser-test suite that
prevents regression.

**Independent Test**: With a filled profile, click Test Apply Assist —
observe every practice field fill correctly (resume attached, dropdown
matched, delayed and framed sections included) and the activity feed
report matching counts.

**Acceptance Scenarios**:

1. **Given** a filled profile, **When** the user runs Test Apply Assist,
   **Then** the practice form's recognized fields fill with the user's
   real data within seconds, visibly.
2. **Given** the practice page's delayed-render and embedded-frame
   sections, **Then** both fill (proving the two historic root-cause
   classes are dead).
3. **Given** anything requiring user review (import conflicts, pending
   answers), **Then** it is scrolled into view and visually highlighted.

---

### User Story 3 - Profile import that visibly imports (Priority: P3)

The user uploads a resume (or clicks "Import from resume" for one already
uploaded). The page responds instantly; a progress banner shows extraction
happening in the background with stage-by-stage progress. When it
finishes, a review screen lists every profile field — name, email, phone,
links, skills, target titles, locations, and a resume-sections summary —
showing the current value beside the value found in the resume, with a
per-row choice (Keep / Use resume's / Merge). One click applies the
selections and the profile visibly updates. Nothing is ever changed
silently, and nothing fails silently.

**Why this priority**: The user uploaded a resume and "nothing happened" —
extraction was synchronous-and-frozen-looking, structurally broken on the
offline model, and its results invisible. The review screen makes every
outcome explicit.

**Independent Test**: Upload a resume on a machine with no cloud key:
progress banner appears immediately, advances through stages, and the
review screen lists all fields with sensible defaults; applying updates
the profile and shows a confirmation.

**Acceptance Scenarios**:

1. **Given** a resume upload, **When** the user submits, **Then** the page
   responds immediately and shows a live progress banner (stages, and
   part-counts for long resumes) — never a frozen window.
2. **Given** extraction on the offline model, **Then** it succeeds for
   normal multi-page resumes (the old version failed 100% of the time on
   the offline model due to a size limit) — long resumes are processed in
   parts, and one failed part costs only that part.
3. **Given** the review screen, **Then** every field appears — including
   unchanged ones marked "no change" — with defaults: blanks pre-set to
   apply, conflicts pre-set to keep, list fields pre-set to merge;
   sections the user hand-edited warn before replacement and default to
   keep.
4. **Given** the user applies selections, **Then** the profile updates,
   a confirmation toast appears, derived search terms refresh unless the
   user owns them, and applying sections counts as the explicit consent
   that replaces the old re-extract prompt.
5. **Given** any extraction failure, **Then** the banner states the real
   error and offers retry — never a silent no-op.
6. **Given** any import, **Then** work-authorization/visa fields are never
   imported (existing rule preserved).

---

### User Story 4 - Offline model first (Priority: P4)

By default the app's AI features (match scoring, tailoring, resume
extraction, answer drafting) run on the bundled offline model even when a
cloud key is saved. The cloud key serves as an automatic fallback when the
local model fails, and a Settings toggle flips the preference any time.

**Why this priority**: Explicit user preference ("I recommend using the
offline model") — privacy-first and $0, with the cloud as safety net.

**Independent Test**: With both a cloud key and the bundled model
available, run scoring/extraction and confirm the local tier served them;
untick the toggle and confirm the cloud tier takes over; simulate a local
failure and confirm automatic cloud fallback.

**Acceptance Scenarios**:

1. **Given** default settings with a cloud key saved, **When** any AI
   feature runs, **Then** the offline model serves it.
2. **Given** a local-model failure mid-call, **Then** the app falls
   through to the cloud key automatically (when present) instead of
   failing the feature.
3. **Given** the Settings toggle unticked, **Then** cloud is preferred
   again — no restart needed.

---

### Edge Cases

- Browser window closed mid-watch: existing interruption/resume behavior
  preserved; the worker survives and relaunches on Resume.
- A page with more than a bounded number of frames: only the first N
  frames are watched (bound documented); fields elsewhere are reported as
  not covered rather than hanging the watcher.
- Custom script-driven dropdown widgets that require clicks to open:
  cannot be filled without clicking (banned) — reported honestly as
  unmatched, never guessed, never clicked.
- A form that re-renders and wipes its own fields (framework re-mount):
  the watcher re-fills the newly-empty fields; the fill report does not
  duplicate rows for re-fills of the same field.
- The user types into a field the same moment the watcher would fill it:
  the focused-field guard plus a just-before-write re-check prevents any
  overwrite; worst case the watcher skips the field.
- Practice run with an empty profile: practice form fills whatever exists
  and the activity feed states which fields had no profile data — not an
  error.
- Import proposal outstanding when the app restarts: proposal is
  session-scoped and dropped; re-import is one click (documented).
- Import applied twice / stale proposal after profile edits: applying
  consumes the proposal; a new import is required for further changes.
- Resume with unparseable/scanned content: import fails with the real
  error shown in the banner; nothing changes.
- Offline model missing/corrupted on disk: preference falls through to
  cloud (when key present) or the basic tier, with the tier visible as
  today.

## Requirements *(mandatory)*

### Functional Requirements

**Live fill engine**

- **FR-001**: All browser automation MUST run on a single dedicated
  worker owned by the app for the whole session; user actions (start,
  next, stop, re-scan, resume, confirm answer) MUST return immediately
  and never perform browser work on a request thread.
- **FR-002**: Each queued job MUST open at its best-known application-form
  URL: Lever postings at their apply page, Ashby postings at their
  application page (also captured at ingest going forward), Greenhouse
  postings as-is, all others at the posting page.
- **FR-003**: While a job is current, the app MUST repeatedly scan the
  open page — including embedded frames, up to a documented bound — and
  fill any empty, recognized, non-focused field, at an interval of a few
  seconds, until the user advances or stops. There MUST be no terminal
  "couldn't read this page" state while a job is current.
- **FR-004**: Field addressing MUST NOT be constructed from raw page
  attribute values; elements MUST be addressed via stamps applied during
  scanning, immune to special characters in names/ids.
- **FR-005**: Field recognition MUST use per-ATS deterministic mappings
  (Greenhouse, Lever, Ashby native forms) first, falling back to the
  generic classifier, whose word-separator handling MUST match raw
  attribute styles (e.g. `first_name`).
- **FR-006**: The fill pass MUST preserve all existing guarantees: never
  click any control; never overwrite a non-empty field; never touch the
  field the user is focused on, with a just-before-write re-check; never
  fill sensitive/unrecognized questions without the existing confirm-first
  flow; passwords masked at record time; per-field fill report without
  duplicate rows for re-filled fields.
- **FR-007**: The status panel MUST show live activity: phase, fields
  seen, fields filled, and contextual guidance (e.g. "click the site's
  Apply button — fields fill the moment the form appears"); launch and
  navigation failures keep their distinct visible reasons.
- **FR-008**: Queue semantics from prior releases MUST be preserved:
  manual advance only, interruption detection and resume, batch summary,
  reason-class outcomes for launch/navigation failures.

**Practice application & attention polish**

- **FR-009**: The app MUST bundle a realistic practice application page,
  served locally, reachable via a "Test Apply Assist" action, exercising
  at minimum: text identity fields, resume file upload, an
  option-matching dropdown, a custom question, a delayed-render section,
  and an embedded-frame section — filled with the user's real profile
  data through the normal engine.
- **FR-010**: The practice pages MUST double as an automated real-browser
  regression suite that runs before any release.
- **FR-011**: UI elements requiring user attention (review screens,
  conflicts, pending answers) MUST scroll into view and be visually
  highlighted when they appear.

**Profile import**

- **FR-012**: Resume upload MUST return immediately; extraction MUST run
  in the background with visible stage progress (and part-counts for long
  resumes), and failures MUST be shown with their real error and a retry.
- **FR-013**: Extraction MUST succeed on the offline model for normal
  multi-page resumes: long inputs are processed in bounded parts and
  merged; a failed part degrades that part only. No single request to the
  local model may exceed its context capacity.
- **FR-014**: Import MUST produce a review proposal listing every profile
  field (identity, skills, target titles, locations, resume-sections
  summary) as current-value vs resume-value with per-row Keep / Use
  resume's / Merge choices and the stated defaults (blank→apply,
  conflict→keep, lists→merge, user-edited sections→keep with warning).
  Nothing may change without the user applying the proposal.
- **FR-015**: Applying a proposal MUST update the profile in one action
  with visible confirmation, count as explicit consent for replacing
  user-edited sections, refresh derived search terms unless user-owned,
  and never import work-authorization/visa fields.
- **FR-016**: An "Import from resume" action MUST re-run import any time
  without re-uploading; the profile save endpoint MUST no longer perform
  any AI work inline.

**Offline-first**

- **FR-017**: A persistent preference (default ON) MUST make the offline
  model serve all AI features even when a cloud key exists, with
  automatic fall-through to the cloud key on local failure, and a
  Settings toggle to flip it without restart.

### Key Entities

- **Watch activity**: per-session live state — phase, fields seen/filled,
  message, last scan time, current URL.
- **Field stamp**: scan-time element address (frame, index) — the only
  way fill actions locate elements.
- **Import proposal**: session-scoped extraction result — per-field
  current/proposed/default triples plus sections summary and tier used.
- **Practice application**: bundled local page set exercising the
  documented field classes.
- **AI-tier preference**: the offline-first setting.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the release live gate (one real Greenhouse, Lever,
  Ashby, and Indeed/Workable posting each), 100% of the postings reach a
  correct form page and every recognized empty field fills within ~2 scan
  intervals of the form (or a newly revealed/next page) appearing —
  including at least one iframe-embedded and one multi-page case.
- **SC-002**: The practice run fills all its recognized fields — delayed
  and framed sections included — within 10 seconds of the form
  appearing, on the user's machine, from a cold start.
- **SC-003**: Zero clicks are ever issued by the app on any page
  (invariant-tested at unit and browser-fixture level, verified on the
  live gate).
- **SC-004**: Resume upload responds in under 2 seconds with visible
  progress; on the offline model, a 3-page resume produces a review
  proposal with populated sections (≥1 experience entry) — a case that
  failed 100% of the time in v0.8.0.
- **SC-005**: Every profile change from import is attributable to an
  explicit user choice on the review screen (zero silent mutations by
  design and by test).
- **SC-006**: With default settings and a saved cloud key, AI calls are
  served by the offline model; flipping the toggle switches tiers without
  restart.

## Assumptions

- Watching is bounded per tick (frames and evaluation budget), so
  steady-state CPU stays modest; exact cadence is an implementation
  choice around a few seconds.
- The import proposal is session-scoped (lost on app restart) — same
  model as the Apply Assist queue; re-import is cheap.
- Custom click-to-open dropdown widgets remain unfillable by rule (never
  click); they are reported unmatched.
- The practice application represents common ATS field patterns; it is a
  fidelity aid and regression suite, not a guarantee for every site.
- Offline-first may be slower per call than the cloud; the user explicitly
  accepts this default and can flip the toggle.
- Prior features' behavior not named here (credentials, tailored PDFs,
  answer bank, delisting, watchlist, self-update) is preserved unchanged.
