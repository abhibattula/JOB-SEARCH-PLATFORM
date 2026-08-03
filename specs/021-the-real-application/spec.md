# Feature Specification: The Real Application

**Feature Branch**: `021-the-real-application`
**Created**: 2026-08-02
**Status**: Draft
**Input**: User description: "how can we make the AI MODEL Faster / i did click apply with autofill this is the error i am seeing the questions repeated times even for same question that might be a drop down / i reccomend to add more questions in profile section / what all free apis can i add / the resume did not generate after i click generate a tailored resume / IF I FILL IT ON JOB APPLICATION IT SHOULD COLLECT THE ANSWERS AND SAVE IT FOR MODEL TRAINING OR PROFILE FOR REFERENCE / IT WOULD BE BETTER TO HAVE THE APPLY ASSIST EXTENSION TO MOVE IF IT DID STRUCK ON BOTTOM RIGHT I SHOULD HAVE AN OPTION TO DRAG AND PLACE IT AT OTHER PLACE"

Reported against v2.0.0 on a real Intel Corporation "RTL Design Engineer"
Workday application. The panel reported **Filled 5 · Needs you 149 · Seen
156**, most rows carrying no question text at all.

## Clarifications

### Session 2026-08-02

Resolved autonomously under the applicant's standing instruction to proceed
without further questions. Each answer is the one that follows from an
existing rule in this codebase; the rule is named so the choice is auditable.

- Q: What counts as "the applicant typed it" for a learned answer? → A: A
  field the app did **not** fill, observed empty on one scan and non-empty on
  a later scan of the same document. A value already present on first sight
  is the employer's own prefill or the browser's password manager, and is not
  the applicant's answer to learn. (Follows 019's existing
  `skipped_existing` distinction.)
- Q: An observed answer collides with an existing answer-bank row — the
  question column is unique. What wins? → A: An observed answer is written
  only when no row exists, or when the existing row's provenance is also
  `observed`. It **never** overwrites a row the applicant confirmed or the
  drafter had accepted. (Follows FR-019 and the existing provenance column.)
- Q: Once a cloud key is saved, which tier serves applicant-initiated work by
  default? → A: The cloud tier, because the applicant explicitly chose "free
  key + local fallback" this session. Bulk background work stays on-device
  regardless. The switch stays visible and reversible, and the on-device path
  is never removed.
- Q: How is a section index kept stable when the page re-renders? → A:
  Recomputed from the document on every scan (section label + ordinal among
  repeats), never stamped onto the element. A stamped index would drift on
  exactly the React remounts that caused the original flood.
- Q: Where does a page report go, and how long is it kept? → A: Written to
  `data/reports/` with a timestamped filename, listed on the Diagnostics
  page for download, and never auto-deleted — it is evidence, and `data/` is
  already gitignored and local-only.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every question appears once, named, and grouped (Priority: P1)

The applicant opens a real multi-section Workday application and presses
Apply with autofill. The panel lists each distinct question **once**, under
the section of the form it belongs to ("Work Experience 2", "Education 1"),
and every listed row names the question it is asking about. A field the app
cannot name is not listed at all, because a blank row is worse than no row.

**Why this priority**: At 149 rows, most of them blank and many of them the
same question repeated, the review surface is unusable — which makes the
whole Apply Assist feature unusable on the ATS the applicant most needs it
for. Nothing else in this release matters if the panel cannot be read.

**Independent Test**: Load the captured 150-field Workday fixture, run a
fill pass, and assert the rendered feed contains one row per distinct
question, each with non-empty question text, grouped by section.

**Acceptance Scenarios**:

1. **Given** a form where one question is served by two elements (a trigger
   button and its listbox), **When** the panel renders, **Then** exactly one
   row appears for that question, and its "Show me" reaches every element
   behind it.
2. **Given** a field whose label resolves to empty or whitespace, **When**
   the panel renders, **Then** the row is either named from the field's
   stable identifier or omitted — never rendered blank.
3. **Given** a multi-step wizard where the applicant advances three steps,
   **When** the panel renders on step three, **Then** it does not still list
   the fields of steps one and two as outstanding.
4. **Given** two sections each containing a "Start date", **When** the panel
   renders, **Then** both rows survive, distinguished by their section.

---

### User Story 2 - Work history and education fill themselves (Priority: P1)

The applicant's uploaded resume has already been parsed into structured
employment and education entries. When an application asks for employer,
job title, dates, school, degree, field of study or GPA, those fields fill
from that parsed history instead of being handed back as "needs you".

**Why this priority**: The repeated employer and education blocks are the
single largest share of the 149 outstanding fields, and the data to answer
them is already stored and unused. This is the biggest measurable reduction
available in this release.

**Independent Test**: With a profile holding two experience entries and one
education entry, run a fill pass over a form with two work-history blocks
and one education block, and assert each block fills from the matching
entry.

**Acceptance Scenarios**:

1. **Given** a profile with `experience[1].organization = "Acme"`, **When**
   the form's second work-history block asks for Company, **Then** it fills
   with "Acme".
2. **Given** a profile with only one experience entry, **When** the form
   offers three work-history blocks, **Then** blocks two and three are
   flagged for the applicant and **never** filled from entry one.
3. **Given** an education entry with no GPA, **When** the form asks for
   "Overall Result (GPA)", **Then** the field is flagged for the applicant
   rather than filled with any other number.
4. **Given** the applicant corrects a parsed employer in their profile,
   **When** the next fill pass runs, **Then** the corrected value is used.

---

### User Story 3 - Interactive AI is fast and never fails silently (Priority: P2)

The applicant presses "Tailor for this job" and either gets the result or
gets told plainly what went wrong. Work they are waiting on is never stuck
behind background scoring. If they choose to add a free cloud AI key, the
app tells them exactly what leaves the machine and then actually uses it.

**Why this priority**: A button that silently does nothing destroys trust in
every other AI surface in the app. And the fast tier already exists — it is
simply switched off in a way no one can discover.

**Independent Test**: Issue a tailoring request while a background AI pass
is running and assert it resolves inside its budget; separately, force an
empty response and assert a human-readable message appears.

**Acceptance Scenarios**:

1. **Given** a background AI pass is mid-job, **When** the applicant presses
   Tailor, **Then** the background pass stands down and the tailoring
   request is served next.
2. **Given** the tailoring request returns nothing at all, **When** the
   handler runs, **Then** a plain message is shown — never a silent no-op.
3. **Given** a saved cloud key and the interactive preference, **When** a
   tailoring request runs, **Then** it is served by the cloud tier; **and
   when** the network is unavailable, **Then** it falls back to the
   on-device model without the applicant doing anything.
4. **Given** no cloud key and no network, **When** any AI surface is used,
   **Then** the app still works on-device exactly as it does today.

---

### User Story 4 - The app learns the answers I type (Priority: P2)

When the applicant answers a question on the application page themselves,
the app remembers that answer and offers it the next time the same question
appears. Everything it has learned is listed in one place, editable and
deletable. Sensitive fields are never captured at all.

**Why this priority**: With this release still leaving some fields to the
applicant, each one they answer should be the last time they answer it.
This is what turns a one-off form-filling session into a profile that
improves.

**Independent Test**: Simulate the applicant typing into a field the app
declined, run the next scan, and assert the question and answer are stored
with `observed` provenance and offered on a second form.

**Acceptance Scenarios**:

1. **Given** the applicant types an answer into a field the app left alone,
   **When** the next scan observes it, **Then** the question and answer are
   stored and shown on the Learned answers page.
2. **Given** a field classified as a credential, self-identification, SSN,
   date of birth, government ID or bank detail, **When** the applicant fills
   it, **Then** nothing is stored, logged, or written to any report.
3. **Given** a learned answer, **When** the same question appears on another
   application, **Then** it is offered as the answer.
4. **Given** a learned answer that maps to a known profile fact, **When**
   the applicant views it, **Then** they are offered a one-click save to
   their profile — and it is **not** written without that click.
5. **Given** the applicant presses "Forget everything learned", **When** it
   completes, **Then** no observed answer remains.

---

### User Story 5 - The panel goes where I put it (Priority: P3)

The applicant drags the Apply Assist panel to a spot that does not cover the
form, and it stays there on this and every later application.

**Why this priority**: Small, self-contained, and a daily irritation — the
panel currently sits on top of the very controls being filled.

**Independent Test**: Drag the panel, reload the page, and assert it
restores to the dragged position; then restore a saved position that is
off-screen and assert it is clamped back into view.

**Acceptance Scenarios**:

1. **Given** the panel at its default corner, **When** the applicant drags
   it by its header, **Then** it follows the pointer and stays where it is
   released.
2. **Given** a position saved on a large monitor, **When** the panel is
   restored on a smaller viewport, **Then** it is clamped fully into view.
3. **Given** a page with hostile CSS, **When** the panel is positioned,
   **Then** its placement still wins.
4. **Given** the applicant chooses "Reset position", **When** it completes,
   **Then** the panel returns to its default corner.

---

### User Story 6 - More of my facts, and more jobs (Priority: P3)

The profile holds every fact the applicant is repeatedly asked for, the
panel links straight to the field that is missing rather than just naming
it, and the feed draws on more free job boards.

**Why this priority**: Additive breadth. Valuable, but worth nothing until
the panel is readable and the history fills.

**Independent Test**: Assert each new profile field round-trips and is
reachable from the panel's "add it to your profile" link; assert each new
ingest source parses a recorded board response into jobs.

**Acceptance Scenarios**:

1. **Given** a needs-you row whose reason is a missing profile fact, **When**
   the applicant follows its link, **Then** the profile opens focused on
   exactly that field.
2. **Given** a phone country code field, **When** a fill pass runs, **Then**
   it fills from the profile rather than being handed back.
3. **Given** a new source's board response, **When** ingestion runs, **Then**
   its jobs enter the feed with company, title, URL and posted date.
4. **Given** one source fails, **When** ingestion runs, **Then** every other
   source still completes.

---

### Edge Cases

- A question that legitimately appears twice in different sections (two
  "Start date" fields) must **not** be collapsed into one row.
- A field whose label changes as its value changes must not create a second
  row on every scan.
- A form with more sections than the applicant has history entries must
  flag the surplus, never recycle an earlier entry.
- An education entry with no GPA, or an employment entry with no end date
  because it is current, must be handled without inventing a value.
- The cloud tier's free daily request budget must not be consumed by bulk
  background work.
- A cloud request that is rate-limited or times out must fall back rather
  than surface an error.
- An observed answer for a question the app already has a confirmed answer
  for must not silently overwrite the confirmed one.
- A page report must remain safe to share: shape only, never values.
- The panel must remain draggable when the page is scrolled, zoomed, or
  inside a right-to-left layout.

## Requirements *(mandatory)*

### Functional Requirements

**Diagnosis and evidence**

- **FR-001**: The companion MUST be able to write a page report describing
  every field it saw — identity, role, widget, visibility, requiredness, and
  the decision and reason each one received.
- **FR-002**: A page report MUST NOT contain any field value, any secret,
  or any credential, and MUST be safe to share unmodified. Reports MUST be
  written to the local data directory with a timestamped name, listed for
  download in the app, and never auto-deleted.
- **FR-003**: The test suite MUST include a fixture representative of a real
  multi-section Workday application (~150 fields), built from a real capture.

**The review surface**

- **FR-004**: The panel MUST render exactly one row per distinct question
  within a section, regardless of how many elements serve that question.
- **FR-005**: A collapsed row MUST retain access to every element behind it,
  so "Show me" can reach each one.
- **FR-006**: The panel MUST NOT render a row whose question text is empty
  or whitespace.
- **FR-007**: A question MUST be resolved from the field's label, and where
  that fails, from its stable automation identifier, name or id, humanized.
- **FR-008**: Each field MUST report the form section it belongs to, and the
  panel MUST group rows by that section.
- **FR-009**: Fields no longer present in the document MUST stop being
  reported as outstanding.
- **FR-010**: Two fields sharing a question but belonging to different
  sections MUST remain distinct rows.

**Work history and education**

- **FR-011**: The fill layer MUST answer employer, job title, employment
  start, employment end, currently-employed, job location, school, degree,
  field of study, GPA and graduation date from the applicant's stored
  structured history.
- **FR-012**: A history value MUST be selected by the section index of the
  field, so the second work-history block uses the second employment entry.
  That index MUST be recomputed from the document on every scan, never
  stamped onto an element, so it survives a re-render.
- **FR-013**: When no history entry exists for a section, the fill layer
  MUST flag the field for the applicant and MUST NOT substitute a value from
  any other entry.
- **FR-014**: The applicant MUST be able to view and correct their parsed
  employment and education entries before they are used.

**Learning**

- **FR-015**: When the applicant fills a field the app declined, the app
  MUST record the question and the answer. A field MUST qualify only when
  the app did not fill it and it was observed empty on an earlier scan of
  the same document — a value already present on first sight is the
  employer's prefill, not the applicant's answer.
- **FR-016**: A recorded answer MUST be distinguishable by provenance from
  one the applicant confirmed and one the AI drafted.
- **FR-017**: The app MUST NOT record an answer for a field classified as a
  credential, secret, voluntary self-identification, national identifier,
  date of birth, government identifier or financial detail.
- **FR-018**: The applicant MUST be able to see, edit and delete every
  recorded answer, and to delete all of them at once.
- **FR-019**: A recorded answer MUST be written only when no answer exists
  for that question, or when the existing one is itself a recorded answer.
  It MUST NOT overwrite an answer the applicant confirmed or the drafter had
  accepted.
- **FR-020**: A recorded answer that maps to a known profile fact MUST be
  offered for one-click saving to the profile, and MUST NOT be written to
  the profile automatically.

**Responsiveness and honesty**

- **FR-021**: Background AI work MUST stand down for any applicant-initiated
  AI request, not only for an active fill session.
- **FR-022**: An applicant-initiated AI request that returns nothing MUST
  produce a human-readable message.
- **FR-023**: The app MUST let the applicant choose which tier serves
  applicant-initiated AI work, and MUST state plainly what leaves the
  machine under each choice. Once a cloud key is saved the cloud tier MUST
  be the default for that work, and the choice MUST remain visible and
  reversible.
- **FR-024**: Bulk background AI work MUST NOT consume the cloud tier's free
  daily request budget.
- **FR-025**: A cloud request that fails, times out or is rate-limited MUST
  fall back to the on-device model without applicant action.
- **FR-026**: The app MUST remain fully functional with no network and no
  cloud key.

**Placement**

- **FR-027**: The applicant MUST be able to drag the panel and have its
  position persist across pages and sessions.
- **FR-028**: A restored position MUST be clamped fully within the current
  viewport.
- **FR-029**: The panel's placement MUST survive hostile page stylesheets.
- **FR-030**: The applicant MUST be able to reset the panel to its default
  position.

**Breadth**

- **FR-031**: The profile MUST hold phone country code, second address line,
  work-authorization expiry, security clearance and driving licence status.
- **FR-032**: A needs-you row caused by a missing profile fact MUST link to
  that exact profile field.
- **FR-033**: The system MUST ingest from additional free job board APIs,
  each obeying the existing politeness limits, and a failure in one MUST NOT
  abort the others.

### Key Entities

- **Page report**: a shareable, value-free description of one application
  page — every field's identity, shape, section, visibility and the decision
  it received.
- **Form section**: the named region of a form a field belongs to, plus its
  index among repeats of that region.
- **History entry**: one parsed employment or education record — employer or
  institution, title or degree, start, end, and whether it is current.
- **Observed answer**: a question and answer captured from what the applicant
  typed on a real application, carrying its provenance and source job.
- **AI tier preference**: which tier serves applicant-initiated work, held
  separately from what serves bulk background work.
- **Panel placement**: the applicant's chosen position for the companion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the captured Workday application, the panel lists no
  duplicate question within a section and no row without question text.
- **SC-002**: On that same application, the count of fields left to the
  applicant falls by at least 60% against the recorded baseline of 149.
- **SC-003**: Every field the app fills on that application is correct — no
  value is taken from a history entry that does not belong to that section.
- **SC-004**: An applicant-initiated AI request issued while background AI
  work is running completes within its stated budget, every time.
- **SC-005**: No applicant-initiated AI request can fail without showing the
  applicant a message.
- **SC-006**: With the cloud tier selected, a tailoring request completes at
  least 10x faster than the recorded on-device time.
- **SC-007**: No value from a sensitive field ever appears in storage, a
  log, a report or a diagnostic — asserted in both directions.
- **SC-008**: The panel restores to its saved position, fully on-screen, on
  every page tested including hostile-CSS pages.
- **SC-009**: Every new job source yields parseable jobs from a recorded
  response, and an induced failure in one leaves the others unaffected.
- **SC-010**: The unit and browser suites both exceed their v2.0.0 counts
  (1731 and 104), with none lost.

## Assumptions

- The applicant's resume has been uploaded and parsed; work-history filling
  degrades to today's behaviour when it has not.
- Section grouping is heuristic and ATS-specific; where a section cannot be
  determined the panel degrades to today's flat list rather than grouping
  wrongly.
- The free cloud tier remains free and keyless-to-obtain; the on-device
  model remains the default until the applicant chooses otherwise.
- "Model training" in the applicant's request means reuse of their own
  answers on later applications, not any retraining of model weights, which
  is out of scope and not possible at $0.
- New job sources expose public JSON board endpoints; none require payment,
  a credit card, or bot-protection bypass.
- Two Workday fixtures existing at 9 and 2 fields is why this class of
  failure was never caught; the new fixture is built from a real capture
  rather than authored from imagination.
