# Feature Specification: The Case File

**Feature Branch**: `022-the-case-file`
**Created**: 2026-08-03
**Status**: Draft
**Input**: User description: "can we do a full visual redesign into a more interactive smooth and make it more user frendly do not create and oush a version until i approve the design check where can i do improvements etc"

## User Scenarios & Testing *(mandatory)*

The applicant is a computer-engineering new grad on OPT who uses this app for
hours a day: scanning hundreds of postings, then filling real employer
applications with Apply Assist while the browser panel sits over the form.
Every scenario below is written from inside that daily use.

The audit behind these scenarios is recorded in
`docs/superpowers/specs/2026-08-03-feature-022-design.md` §2, with file:line
evidence for each finding.

### User Story 1 - Nothing renders as unfinished markup (Priority: P1)

The applicant opens Profile, Settings and the Apply Assist review list and sees
a designed interface rather than browser defaults: fields laid out in the
columns the markup already asks for, hints that read as hints, a real toggle,
and a review list with visible structure.

**Why this priority**: This is not polish. Roughly 35 class names are used in
the templates and defined in no stylesheet, so these screens currently fall back
to unstyled HTML. The Apply Assist review list is the screen used *during* a
live employer application — the highest-stakes surface in the product.

**Independent Test**: Walk all nine app screens and confirm no element renders
with browser-default styling; confirm the automated check reports zero class
names used in markup without a definition.

**Acceptance Scenarios**:

1. **Given** the Profile page, **When** it is opened at 1280px, **Then** the
   sections that declare a two-column grid render in two columns, and every
   field hint is visually distinct from the field label and from body text.
2. **Given** the Settings page, **When** the escort control is displayed,
   **Then** it renders as a switch, not as a default checkbox.
3. **Given** an Apply Assist session with reviewable answers, **When** the
   status panel renders, **Then** each answer shows its question, its reason
   and its state as distinguishable elements rather than run-together text.
4. **Given** any template in the app, **When** the design-system check runs,
   **Then** it reports zero class names that have no definition.

### User Story 2 - A score never hides how it was produced (Priority: P1)

Wherever the applicant sees a match score — feed, job page, dashboard, browser
panel — they can tell at a glance whether it is a keyword guess, an on-device
assessment, or a full analysis, without hovering or reading a tooltip.

**Why this priority**: The applicant decides which jobs to spend an hour
applying to based on this number. Provenance is currently a single `~` or `•`
character plus a `title` tooltip, which is invisible in normal use. Not
presenting a guess as a fact is the product's central commitment.

**Independent Test**: Seed three jobs scored by each method, then confirm all
four surfaces render three visibly different treatments with no pointer
interaction.

**Acceptance Scenarios**:

1. **Given** a job scored by keyword only, **When** its score is displayed
   anywhere, **Then** it renders in the provisional treatment.
2. **Given** a job scored by the on-device model, **When** its score is
   displayed, **Then** it renders in the confirmed treatment, visibly different
   from provisional.
3. **Given** a job scored by the cloud tier, **When** its score is displayed,
   **Then** it renders in the sealed treatment, visibly different from both.
4. **Given** any of the three, **When** a screen reader reads the score,
   **Then** the provenance is announced in text, not conveyed by colour alone.

### User Story 3 - The feed stays still while it is being read (Priority: P2)

The applicant scrolls the feed, hovers a row, reads a title. The list does not
jump, reset, or lose their place.

**Why this priority**: The feed currently replaces its entire table every five
seconds regardless of whether anything changed, discarding scroll position,
hover state and in-flight transitions twelve times a minute. This is the single
largest contributor to the app feeling unfinished in motion.

**Independent Test**: Open the feed, do not interact, and observe for one
minute: confirm no table replacement occurs while the underlying results are
unchanged, and that a genuine change still appears without a manual refresh.

**Acceptance Scenarios**:

1. **Given** an open feed whose results have not changed, **When** the refresh
   interval elapses, **Then** the displayed rows are not replaced.
2. **Given** an open feed, **When** a new job arrives, **Then** the new row
   appears without the applicant refreshing.
3. **Given** the applicant is scrolled halfway down the feed, **When** a
   refresh cycle elapses, **Then** scroll position and hover state are retained.
4. **Given** the system reports a preference for reduced motion, **When** any
   screen loads, **Then** no entrance animation, shimmer or transition plays.

### User Story 4 - The applicant can always tell where they are (Priority: P2)

Navigation shows four stable groups; the current group and current view are both
visible; the bar does not wrap or reflow at any window size the app is used at.

**Why this priority**: Fourteen links currently sit in one wrapping bar with no
visible grouping — the group labels exist in the stylesheet but the markup only
exposes them to screen readers, so sighted use gets an undifferentiated list
that becomes two rows on a laptop.

**Independent Test**: Load every screen at 1280px and at 1024px and confirm the
top navigation row occupies a single line, with the active group and active view
both indicated.

**Acceptance Scenarios**:

1. **Given** any screen at 1024px or wider, **When** it renders, **Then** the
   primary navigation row occupies exactly one line.
2. **Given** the applicant is on any view, **When** the navigation renders,
   **Then** both its group and the view itself are marked as current.
3. **Given** a viewport too narrow for the second-row views, **When** it
   renders, **Then** those views scroll horizontally rather than wrapping.
4. **Given** Profile or Settings, **When** the page is longer than the
   viewport, **Then** a section index lets the applicant jump between sections.

### User Story 5 - The browser panel belongs to the same product (Priority: P3)

The Apply Assist panel that sits over an employer's form uses the same colours,
type and score treatment as the app, and follows the applicant's light/dark
choice.

**Why this priority**: The panel is a separate hardcoded dark design that
ignores the theme setting. It is where the applicant spends the actual
application, so the mismatch is felt at the worst moment — but it is behind the
app screens because a mismatched panel still works.

**Independent Test**: Set the app to light, open the panel on a form, confirm it
renders light and shows the same score treatment as the app; repeat for dark.

**Acceptance Scenarios**:

1. **Given** the app theme is light, **When** the panel is opened, **Then** it
   renders in the light theme.
2. **Given** the app theme is dark, **When** the panel is opened, **Then** it
   renders in the dark theme.
3. **Given** no theme preference has been expressed, **When** the panel is
   opened, **Then** it follows the operating system preference.
4. **Given** a panel from a version that predates this change, **When** it
   connects, **Then** it continues to work unchanged.
5. **Given** the panel is displayed, **When** the applicant drags it, **Then**
   it moves and its position persists exactly as before this change.

### User Story 6 - What reaches an employer looks considered (Priority: P3)

The generated resume and cover-letter PDFs have clear typographic hierarchy and
consistent spacing, while remaining machine-readable by applicant tracking
systems.

**Why this priority**: These are the only artifacts an employer actually
receives. They are behind the screens because they are already correct in
content — only their presentation is unconsidered.

**Independent Test**: Generate both PDFs, confirm hierarchy is legible, then
confirm text is selectable, layout is single-column, and no table or image is
present.

**Acceptance Scenarios**:

1. **Given** a completed profile, **When** a resume PDF is generated, **Then**
   name, section headings and body text are distinguishable by size and weight.
2. **Given** any generated PDF, **When** it is inspected, **Then** all text is
   selectable and the layout is a single column.
3. **Given** resume text containing accented or non-Latin characters, **When**
   the PDF is generated, **Then** every character renders rather than falling
   back to a placeholder glyph.

### Edge Cases

- A bundled font file fails to load: text renders in the system fallback and
  the page remains fully usable.
- The applicant's operating system requests reduced motion: no entrance
  animation, shimmer, view transition or hover transition plays anywhere.
- A saved panel position from a large monitor is restored on a small laptop:
  the panel is clamped into the viewport rather than stranded off-screen.
- The feed is open when the applicant is mid-edit in a notes field: refresh
  remains suppressed exactly as it is today.
- A job has no score at all: the score position renders an explicit "not scored
  yet" state rather than an empty or misleading stamp.
- The applicant is offline: every screen renders identically, since no asset is
  fetched from a network.
- A companion older than this release connects: it receives no field it cannot
  ignore, and continues to fill normally.
- The window is narrower than the feed table's minimum: rows render as stacked
  records rather than overflowing horizontally.

## Requirements *(mandatory)*

### Functional Requirements

**Design system**

- **FR-001**: The app MUST define a single set of design tokens covering
  surfaces, text, rules, and the four semantic states, and every component MUST
  derive its colour from that set.
- **FR-002**: No colour literal MAY appear outside the token definitions, in
  either the app stylesheet or the browser panel.
- **FR-003**: The four semantic states MUST be: confirmed-by-the-applicant,
  drafted-by-the-AI, needs-the-applicant, and done — and each MUST render
  consistently everywhere it appears.
- **FR-004**: The system MUST provide a light and a dark theme; an explicit
  choice MUST win over the operating system preference, and the operating
  system preference MUST apply only when no explicit choice is set.
- **FR-005**: Every foreground/background token pairing MUST meet WCAG 2.1 AA
  contrast in both themes.
- **FR-006**: Typefaces MUST be served from files bundled with the application;
  no asset MAY be requested from a network at any time.
- **FR-007**: Each bundled typeface MUST declare a system fallback so that a
  missing font file degrades presentation without breaking layout.
- **FR-008**: A monospaced face MUST be used for machine-produced values —
  scores, identifiers, dates, counts, versions, file paths and form field names
  — and MUST NOT be used for prose, headings, labels or controls.

**Completeness**

- **FR-009**: Every class name used in any app template MUST resolve to a
  definition in the stylesheet.
- **FR-010**: The Profile page's declared two-column sections MUST render as two
  columns at desktop widths and collapse to one column when too narrow.
- **FR-011**: Field hints MUST be visually distinct from field labels and from
  body text.
- **FR-012**: The escort control on Settings MUST render as a switch.
- **FR-013**: The Apply Assist review list MUST render each answer's question,
  reason and state as visually distinct elements.
- **FR-014**: The sticky Apply Assist control bar MUST use theme tokens, so it
  is legible in both themes.

**Provenance**

- **FR-015**: A match score MUST render in a treatment determined by how it was
  produced: keyword-only, on-device, or full analysis.
- **FR-016**: The three treatments MUST be distinguishable without pointer
  interaction and without relying on colour alone.
- **FR-017**: The score's provenance MUST be available to assistive technology
  as text.
- **FR-018**: The same three treatments MUST be used in the feed, on the job
  page, on the dashboard and in the browser panel.
- **FR-019**: A job with no score MUST render an explicit unscored state rather
  than an empty or ambiguous stamp.

**Navigation and layout**

- **FR-020**: Primary navigation MUST present four groups on a single row that
  does not wrap at 1024px or wider.
- **FR-021**: The views belonging to the current group MUST be presented on a
  second row, scrolling horizontally when the viewport is too narrow.
- **FR-022**: Both the active group and the active view MUST be marked as
  current, programmatically and visually.
- **FR-023**: The Profile and Settings pages MUST provide a section index that
  navigates between their sections.
- **FR-024**: Existing in-page anchors that other surfaces link to MUST continue
  to resolve.
- **FR-025**: The feed MUST render as stacked records rather than a horizontally
  overflowing table when the viewport is too narrow for its columns.
- **FR-026**: The applicant MUST be able to choose a comfortable or compact feed
  density, and that choice MUST persist across restarts.

**Motion and responsiveness**

- **FR-027**: The feed MUST NOT replace its rendered rows when the underlying
  results are unchanged.
- **FR-028**: A genuine change to the results MUST still appear without a manual
  refresh.
- **FR-029**: Scroll position and hover state MUST survive a refresh cycle.
- **FR-030**: Refresh MUST remain suppressed while the applicant is mid-edit, as
  it is today.
- **FR-031**: Genuinely asynchronous content MUST show a placeholder that
  reserves its space, rather than causing a layout shift on arrival.
- **FR-032**: Every animation and transition MUST be disabled when the system
  requests reduced motion.

**Browser panel**

- **FR-033**: The panel MUST use the same tokens, type and score treatment as
  the app.
- **FR-034**: The panel MUST follow the applicant's explicit theme choice, and
  the operating system preference when none is set.
- **FR-035**: Any information added to the app-to-panel protocol MUST be
  additive, and the protocol version MUST remain unchanged.
- **FR-036**: A panel from an earlier release MUST continue to function when it
  connects.
- **FR-037**: Panel dragging, position persistence and viewport clamping MUST
  behave exactly as they do today.

**Generated documents**

- **FR-038**: Generated PDFs MUST present a clear hierarchy between the
  applicant's name, section headings, and body text.
- **FR-039**: Generated PDFs MUST remain single-column with selectable text, and
  MUST contain no table, image or repeating header region.
- **FR-040**: Generated PDFs MUST render accented and non-Latin characters
  rather than substituting a placeholder glyph.

**Preservation**

- **FR-041**: Links within prose MUST retain a non-colour cue.
- **FR-042**: Banners MUST continue to render with the page rather than being
  injected after load.
- **FR-043**: Static assets MUST remain version-stamped for cache correctness.
- **FR-044**: The command palette MUST remain present and reachable by keyboard.
- **FR-045**: Every form control MUST retain an accessible label.
- **FR-046**: No credential, pairing secret or other sensitive value MAY become
  visible through any new or restyled surface.
- **FR-047**: The practice sandbox pages MUST NOT be restyled, since their
  markup deliberately imitates third-party application forms under test.

### Key Entities

- **Design token**: a named value for a surface, text colour, rule, spacing
  step, radius, shadow or motion duration. Has a light value and a dark value.
- **Semantic state**: one of confirmed, drafted, needs-you, done. Applies to a
  score, a filled field, an answer, or a status indicator.
- **Provenance**: how a score was produced — keyword-only, on-device, or full
  analysis. Already carried on each job as its scoring method.
- **Feed fingerprint**: a value derived from the currently rendered results,
  used to decide whether a refresh needs to change anything.
- **Density preference**: comfortable or compact, stored per installation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero class names used in app templates lack a definition
  (currently roughly 35).
- **SC-002**: Zero colour literals appear outside the token definitions, in the
  app and in the browser panel.
- **SC-003**: With the feed open and unchanged for 60 seconds, the rendered rows
  are replaced zero times (currently 12).
- **SC-004**: Primary navigation occupies one row at both 1280px and 1024px
  (currently wraps to two).
- **SC-005**: All three score provenances are distinguishable at a glance, with
  no pointer interaction, on all four surfaces that display a score.
- **SC-006**: The browser panel matches the app's theme in 100% of theme
  combinations tested (currently 0%).
- **SC-007**: Every foreground/background token pairing meets WCAG 2.1 AA in
  both themes.
- **SC-008**: Both generated PDFs remain single-column with fully selectable
  text and no placeholder glyphs.
- **SC-009**: With reduced motion requested, zero animations play.
- **SC-010**: The full existing verification set passes: unit battery twice,
  real-browser suite on both Windows and macOS, secret-hygiene suite, and the
  packaged-build smoke test.
- **SC-011**: The applicant approves the built result before any version is
  created.

## Assumptions

- The nine app screens are Feed, job detail, Profile, Settings, Apply Assist,
  Companion, Diagnostics, Analytics and Learned answers.
- Dark mode remains a derived remapping of the same token names rather than a
  separately art-directed theme; it is verified but not redesigned. This was
  explicitly chosen when scope was set.
- The three practice-sandbox pages are excluded because they are test fixtures
  imitating third-party forms.
- Bundled typefaces are open-licensed, and their licence files ship alongside
  them.
- The applicant runs the app on Windows; macOS is verified by the automated
  suite rather than by hand.
- "Full analysis" provenance corresponds to any scoring method that is neither
  keyword-only nor on-device.
- No change is made to what the engine ingests, scores, drafts or fills; this
  feature changes presentation only.
- No version is tagged, built for release, or pushed until the applicant
  approves the built result.
