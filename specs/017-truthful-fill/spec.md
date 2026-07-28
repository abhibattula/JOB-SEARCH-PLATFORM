# Feature Specification: The Truthful Fill — right answer, right field, or nothing

**Feature Branch**: `017-truthful-fill`
**Created**: 2026-07-28
**Status**: Draft
**Input**: User description: "now it fills the application i have few improvements … an feature to add apply with apply assist … i am unable to see the drafted responses … a floating button like simplify or jobright.ai … i want the apply assist to fill more like attach resume also select my location … i want the profile page to be more elobrate having more questions … it should select male/man/hetrosexual/straight since all applications will not have same terminology similarly for name/first name … for this question this is a drop down menu and the user has to select yes instead of this the apply assist is writing paragraphs there … see how it did fetch the questions … if i want to stop the apply assist in app it will not allow me to scroll up"

## Context

v1.6.0 made Apply Assist fill real application forms. A live run against
Akuna Capital's Greenhouse application (2026-07-28, 91 fields seen, 26 filled,
170 AI drafts) showed that filling works but **what** it fills is frequently
wrong, sometimes invented, and could not be stopped mid-run. That run is the
primary evidence for this feature.

Observed in that single run:

- Invented claims about the applicant: interning at the target company,
  completing the company's own course, holding an offer deadline, living in a
  state they do not live in.
- Right-sounding field, wrong value: the phone number placed in "write out how
  your name is pronounced phonetically"; "Yes" placed in four free-text
  work-authorization questions that ask for a date or a description; the
  applicant's own name placed in "if you heard about us through an employee,
  please list **their** name".
- Multi-sentence paragraphs typed into dropdowns, including a binding
  acknowledgement dropdown whose only valid answers are Yes and No.
- A pronoun checkbox group treated as five separate essay questions.
- A draft-review list showing 170 entries — 10–15 differently-worded answers
  per question — which grew the page beyond the point where **Stop** could be
  reached. These are *historical* rows accumulated by earlier runs and earlier
  app versions against the same saved job, re-rendered in full every three
  seconds; the current run's own activity list correctly shows each question
  once. The defect is that the review surface does not reflect the current
  run and is unbounded, not that answers are regenerated.

## Clarifications

### Session 2026-07-28

- Q: Should voluntary self-identification (gender, race/ethnicity, veteran,
  disability, orientation) be auto-answered? → A: Yes — filled from values the
  user stores once, mapped onto each form's wording. The AI never generates
  them; blank stays blank; "Prefer not to say" is a storable value.
- Q: Which resume file should be attached? → A: The tailored PDF when one
  exists for that job, otherwise the master resume; the on-page panel names the
  file it attached.
- Q: How elaborate should the profile become? → A: Every field a large
  application asks for, plus a library of common questions the user pre-answers
  once so they never reach the AI drafter.
- Q: Where should the on-page launcher live? → A: The existing match-score
  badge becomes the launcher; one floating widget, not two.
- Q: How should acknowledgement/consent dropdowns be handled? → A: Split by
  consequence. Routine consents (background check, drug test, terms, accuracy
  certifications) auto-answer from the library. Commitments that give something
  up (exclusivity, "top preference", "will not be considered for other roles",
  non-compete) are never answered for the user — they are left unfilled,
  highlighted, and shown with their full question text.
- Q: Which resume file should be attached when the applicant never ran Tailor
  for that job? → A: The tailored document only when tailoring was actually run
  for that job; otherwise the applicant's own uploaded resume. An
  app-generated rendering must never replace the uploaded document on a job the
  applicant did not tailor.
- Q: What happens to questions the system refuses to answer? → A: The on-page
  panel lists each one with an input. What the applicant types fills the field
  immediately and is saved to their answer library, so the same question
  auto-fills on every future application — the library grows as they apply.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Nothing false, nothing runaway, always stoppable (Priority: P1)

The applicant starts Apply Assist on a long application. Every answer it
produces is traceable to their own profile or resume; anything it cannot ground
is left for them rather than invented. Each question is attempted a bounded
number of times, so the app stays responsive. At any moment they can reach
Stop.

**Why this priority**: Until this holds, the tool is actively harmful — it
writes false statements onto real job applications and cannot be halted. Every
other improvement is worth less than removing that risk.

**Independent Test**: Run a fill against a fixture containing questions the
profile cannot answer ("have you applied here before", "did you complete our
course", "do you have offer deadlines"). Assert no text is produced for them,
each is flagged for the user, the generator is invoked at most the capped
number of times per question, and Stop is reachable without scrolling.

**Acceptance Scenarios**:

1. **Given** a question with no grounding in the profile or resume, **When**
   the drafter runs, **Then** it produces no answer and the question is marked
   as needing the user.
2. **Given** one draft completes, **When** other questions for the same job are
   in retry backoff, **Then** their backoff is not reset and they are not
   regenerated.
3. **Given** a question has failed its capped number of attempts, **When** the
   page is scanned again, **Then** no further generation is attempted and the
   question is marked as needing the user.
4. **Given** a form with 90+ fields and many drafts, **When** the status view
   refreshes, **Then** Stop/Done/Re-scan remain visible and the scroll position
   is preserved.
5. **Given** the app restarts mid-session, **When** the same job is scanned
   again, **Then** already-answered questions are not regenerated.
6. **Given** previously auto-saved AI answers exist, **When** the user chooses
   to reset learned answers, **Then** those answers are removed and no longer
   fill future applications.

---

### User Story 2 - The right answer in the right field (Priority: P2)

Answers match the shape of the control they go into. A yes/no fact only ever
reaches a yes/no choice; a paragraph never reaches a dropdown; a question about
someone else's name never receives the applicant's name.

**Why this priority**: These are the visible wrong-value defects on every real
application; they make a submitted application look careless or dishonest.

**Independent Test**: Run against a fixture reproducing the Akuna form shapes —
a React-select dropdown with a long label and a nested search input, a
work-authorization expiry text field, a "list their name" field, a
name-pronunciation field — and assert each receives either a correctly shaped
answer or nothing.

**Acceptance Scenarios**:

1. **Given** a dropdown whose options are not readable until opened, **When**
   the system has only a multi-sentence answer, **Then** nothing is typed and
   the field is flagged.
2. **Given** a free-text field asking when work authorization expires, **When**
   the profile holds no expiry date, **Then** the field is left empty and
   flagged — never filled with "Yes".
3. **Given** a label containing "phonetically", **When** fields are classified,
   **Then** it is not treated as a phone field.
4. **Given** a label asking for a third party's name, **When** fields are
   classified, **Then** the applicant's own name is not filled.
5. **Given** a document with separate first and last name fields plus a generic
   "Name" field, **When** fields are classified, **Then** the generic field is
   treated as the first name.
6. **Given** a checkbox set sharing one group question, **When** it is
   answered, **Then** it is treated as one multi-select question rather than
   one open question per checkbox.

---

### User Story 3 - A profile that can answer a real application (Priority: P3)

The applicant fills out an elaborate profile once — legal and preferred names,
full address and current location, work-authorization detail, education and
graduation dates, preferences, links, voluntary self-identification, and a
library of common application questions. Apply Assist answers from it.

**Why this priority**: It is the supply of truth that makes US1's refusal
policy productive rather than merely safe — the more the profile knows, the
less is left for the user.

**Independent Test**: Populate every new profile field, run against a fixture
asking for each, and assert each is filled from the stored value with no model
call.

**Acceptance Scenarios**:

1. **Given** a stored current location and country, **When** a form asks for
   location and country, **Then** both fill from the profile.
2. **Given** a pre-answered common question, **When** a form asks it in
   different wording, **Then** it fills from the stored answer without a model
   call.
3. **Given** a profile field left blank, **When** a form asks for it, **Then**
   the field is left untouched and flagged, not guessed.

---

### User Story 4 - Say it the way the form says it (Priority: P4)

Stored values are matched onto whatever wording each form uses — Male or Man,
Straight or Heterosexual, Yes or "Yes, I am authorized", Prefer not to say or
"Decline to self-identify".

**Why this priority**: Without it, US3's stored values sit unused on forms that
phrase their options differently, which is the reported symptom.

**Independent Test**: Table-driven matching over the synonym families, plus a
fixture whose gender select offers "Man/Woman/Prefer not to say".

**Acceptance Scenarios**:

1. **Given** a stored self-identification, **When** the form's option wording
   differs, **Then** the equivalent option is selected.
2. **Given** no equivalent option exists, **When** matching fails, **Then** the
   field is left unfilled and flagged — never approximated.
3. **Given** a work-authorization dropdown, **When** matching runs, **Then**
   its existing strictness is unchanged.
4. **Given** a binding acknowledgement (exclusivity, "top preference"),
   **When** it is encountered, **Then** no answer is selected and the full
   question text is surfaced for the user.

---

### User Story 5 - Attach the real resume (Priority: P5)

When a form asks for a resume, the applicant's actual resume file is attached —
the tailored version when one exists for that job, otherwise the master — under
its real filename.

**Why this priority**: An application with a missing or corrupt attachment is
rejected outright, and today the attachment can silently be the wrong bytes.

**Independent Test**: Fixture file input reports the attached file's name and
size; assert it matches the chosen source file exactly.

**Acceptance Scenarios**:

1. **Given** the applicant ran Tailor for this job, **When** a resume upload is
   filled, **Then** the tailored document is attached and named in the panel.
2. **Given** the applicant never tailored this job, **When** a resume upload is
   filled, **Then** their own uploaded resume is attached — not an
   application-generated rendering.
2. **Given** the file cannot be retrieved or is not a valid document, **When**
   attachment is attempted, **Then** nothing is attached and the field is
   flagged — never a placeholder or an error page.
3. **Given** a cover-letter file upload, **When** it is filled, **Then** a
   rendered cover-letter document is attached, never drafted prose.

---

### User Story 6 - See and act on the drafted answers, on the page (Priority: P6)

While reviewing the application in the browser, the applicant opens a panel
listing every question with the answer text, copies any of them, inserts one
into its field, and jumps to anything still needing them.

**Why this priority**: The user reported being unable to see drafted responses
at all; this closes that gap where the work happens.

**Independent Test**: Assert the panel lists question/answer pairs including
ones that were not filled, and that copy and jump-to-field work.

**Acceptance Scenarios**:

1. **Given** an answer was drafted but not filled, **When** the panel is
   opened, **Then** its full text is shown and can be copied.
2. **Given** a field needs the user, **When** they select it in the panel,
   **Then** the page scrolls to that field.
3. **Given** a draft completes in the background, **When** it becomes
   available, **Then** the page re-scans promptly rather than waiting for the
   next poll.
4. **Given** a question the system declined to answer, **When** the applicant
   types an answer in the panel, **Then** the field is filled with it and the
   answer is saved to their library.
5. **Given** an answer was captured that way on a previous application,
   **When** the same question appears on a new application, **Then** it fills
   without asking again.

---

### User Story 7 - Apply with Apply Assist, in one click (Priority: P7)

From a job in the app — or from the floating badge on a posting in the browser
— the applicant starts an Apply Assist session for that job directly.

**Why this priority**: Valuable but purely a convenience; every prior story
must hold first or one click just produces wrong answers faster.

**Independent Test**: From a job page, one action starts a session for that job
and the browser tab begins filling.

**Acceptance Scenarios**:

1. **Given** a job open in the app, **When** the applicant chooses Apply with
   Apply Assist, **Then** a session starts for that job without visiting the
   queue page.
2. **Given** a job posting open in the browser, **When** the applicant uses the
   floating badge, **Then** the posting is saved and a session starts for it.

---

### Edge Cases

- A dropdown whose options load after the first scan: the field must not be
  treated as free text in the meantime.
- A question that is both sensitive and a choice (e.g. a gender dropdown):
  answered only from stored self-identification, never generated.
- A form with two documents (page plus embedded frame) containing the same
  question: one answer, not two independent drafts.
- A question whose label exceeds several hundred characters: length must not
  cause it to be treated as an essay prompt.
- A profile value that matches no option on the form: unfilled and flagged.
- The companion running an older version than the app: new field kinds are
  withheld rather than mis-filled.
- The app restarting mid-session: no re-drafting of already-answered questions.
- A resume file that has been moved or deleted since upload: reported, not
  silently skipped.

## Requirements *(mandatory)*

### Functional Requirements — truthfulness and containment

- **FR-001**: Completing one draft MUST NOT reset the retry backoff of any
  other question.
- **FR-002**: Each question MUST have a bounded number of generation attempts;
  on exhaustion it MUST be marked as needing the user.
- **FR-003**: Each job MUST have a bounded total number of generated drafts per
  session.
- **FR-004**: An application restart MUST NOT cause already-answered questions
  to be regenerated.
- **FR-005**: At most one stored draft MUST be retained per (job, question).
- **FR-006**: The drafting path MUST be able to refuse. When an answer is not
  grounded in the profile or resume, the system MUST produce no answer and MUST
  mark the question as needing the user.
- **FR-007**: Prompts for factual questions MUST NOT include the target
  company's or role's text; company context is confined to cover-letter
  drafting.
- **FR-008**: Factual-history questions — prior application to this employer,
  prior employment at a named type of firm, completion of a named course,
  existing offer deadlines, state of residence — MUST NOT be AI-answered.
- **FR-009**: Stop, Done and Re-scan MUST remain reachable regardless of how
  many fields or drafts are present.
- **FR-010**: The status view MUST preserve the user's scroll position across
  refreshes and MUST bound the number of drafts rendered at once.
- **FR-011**: Users MUST be able to purge AI-origin saved answers and stale
  drafts.

### Functional Requirements — answer shape

- **FR-012**: An answer MUST only be written to a field whose shape accepts it.
  A yes/no fact MUST only fill a choice control offering yes/no; prose MUST
  never be written to a choice control, including one whose options are not
  yet readable.
- **FR-013**: A control nested inside a choice widget MUST NOT be treated as an
  independent question.
- **FR-014**: A set of checkboxes sharing one group question MUST be treated as
  a single multi-select question.
- **FR-015**: Field classification MUST match on word boundaries, so a label
  containing "phonetically" is not classified as a phone field.
- **FR-016**: Name classification MUST distinguish the applicant's own name
  from a third party's, and MUST distinguish preferred and middle names from
  the legal full name.
- **FR-017**: When a document contains a distinct last-name field, a generic
  "Name" field MUST be treated as the first name.
- **FR-018**: Per-field status wording MUST reflect the field's actual type.

### Functional Requirements — profile and resolution

- **FR-019**: The profile MUST store identity (including preferred and middle
  name and pronouns), full address and current location, work-authorization
  detail (type, expiry, extension options, future sponsorship need),
  preferences (desired salary, earliest start, notice, relocation, remote,
  travel), experience facts (years, current employer and title, highest
  education, graduation month and year, GPA), links, and voluntary
  self-identification.
- **FR-020**: A single resolver MUST map a classified question to its profile
  value, consulted before the answer bank and before any generation.
- **FR-021**: Location questions — city, state, postal code, country, full
  location — MUST be answered from the profile.
- **FR-022**: Pre-answered common questions MUST be resolved by question
  classification rather than by fuzzy matching of question text.
- **FR-023**: A blank profile value MUST leave the field untouched and flagged,
  never guessed.

### Functional Requirements — terminology

- **FR-024**: Stored values MUST be matched onto a form's own option wording
  through canonical equivalents (e.g. Male/Man, Straight/Heterosexual,
  Yes/"Yes, I am authorized", Prefer not to say/"Decline to self-identify").
- **FR-025**: The existing matching strictness for work-authorization and
  sponsorship questions MUST NOT be loosened.
- **FR-026**: Self-identification questions MUST be answered only from stored
  self-identification values and MUST never be generated.
- **FR-027**: Acknowledgement and consent questions MUST be classified and
  split: routine consents resolve from stored answers; binding commitments MUST
  NOT be answered for the user and MUST be surfaced with their full text.
- **FR-028**: When no equivalent option exists, the field MUST be left unfilled
  and flagged.

### Functional Requirements — attachments

- **FR-029**: Resume file retrieval MUST reach the local application, never the
  job board's origin.
- **FR-030**: Retrieved file content MUST be verified as a plausible document
  of the expected size before attachment; otherwise nothing is attached and the
  field is flagged.
- **FR-031**: Files MUST be attached under their real filename.
- **FR-032**: The tailored document MUST be attached only when tailoring was
  actually performed for that job; otherwise the applicant's own uploaded
  resume MUST be attached. An application-generated rendering MUST NOT replace
  the uploaded document on a job the applicant did not tailor. The attached
  filename MUST be shown to the user.
- **FR-033**: A cover-letter file upload MUST receive a rendered cover-letter
  document, never drafted prose.

### Functional Requirements — on-page review and entry

- **FR-034**: The page MUST receive the full answer text for every question,
  including questions that were not filled.
- **FR-035**: The on-page panel MUST list question and answer pairs with a copy
  action and an action to insert one answer into its field.
- **FR-036**: The panel MUST let the user jump to any field needing them.
- **FR-037**: A background draft becoming available MUST prompt a prompt
  re-scan rather than waiting for the periodic poll.
- **FR-038**: The existing floating badge MUST act as the launcher for the
  panel and MUST be able to start a session for the posting being viewed.
- **FR-039**: The badge MUST continue to mutate nothing on the page.
- **FR-040**: A job in the app MUST offer a single action that starts an Apply
  Assist session for that job.
- **FR-041**: The in-app draft review surface MUST reflect the same answers the
  page shows.

### Functional Requirements — cross-cutting invariants

- **FR-042**: Wire-protocol changes MUST be additive; the protocol version is
  retained and older companions degrade safely rather than mis-filling.
- **FR-043**: The system MUST NOT submit an application, log in, register, pay,
  or advance a multi-step wizard; the human performs every such action.
- **FR-044**: The system MUST NOT agree to any binding commitment on the user's
  behalf.

### Functional Requirements — answer capture and coverage

- **FR-045**: For every question the system declines to answer, the panel MUST
  offer the applicant an input; the value they enter MUST fill that field
  immediately and MUST be saved to their answer library so the same question is
  answered without asking on future applications.
- **FR-046**: An answer captured this way MUST be recorded as the applicant's
  own, not as generated, so a later purge of AI-origin answers does not remove
  it.
- **FR-047**: When a fill runs without the companion (the assistant-window
  fallback, which has no on-page panel), the application view MUST surface the
  same answers, refusals and capture inputs, so the applicant is never left
  without access to them.
- **FR-048**: The same question appearing in more than one document of one
  application (a page and an embedded frame) MUST be answered once and MUST NOT
  cause more than one generation.
- **FR-049**: If the set of answers sent to the page must be shortened for
  transport, the applicant MUST be told that not all answers are shown on the
  page, and the application view MUST remain complete.

### Key Entities

- **Profile**: the single stored record of the applicant — identity, contact,
  address and current location, work-authorization detail, preferences,
  experience facts, links, and voluntary self-identification. Blank means
  "unknown"; "Prefer not to say" is a distinct stored value.
- **Answer**: a question paired with a value, its origin (profile, stored
  answer, generated, refused) and its state (filled, needs the user, no
  matching option).
- **Draft record**: one per job and question, carrying attempt count, outcome
  and refusal reason; bounded in attempts and retained singly.
- **Field descriptor**: one logical question on a page — including a merged
  radio or checkbox group and a choice widget with its nested controls treated
  as one.
- **Answer library**: the set of common application questions the user
  pre-answers once, resolved by classification.
- **Attachment**: a file chosen for an upload field, with its real name and
  verified content.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fixture reproducing the reported form, **zero** fields
  receive an answer whose shape does not fit the control — no prose in a
  dropdown, no yes/no in a free-text date question.
- **SC-002**: A full pass over a 90-field form produces **at most one**
  generation per unique question, and no question exceeds its attempt cap.
- **SC-003**: For questions with no grounding in the profile or resume, the
  system produces an answer in **0%** of cases and flags them in 100%.
- **SC-004**: Stop is reachable in one interaction at any point during a run,
  on a form of any size.
- **SC-005**: The attached file is byte-identical to the chosen source file in
  100% of successful attachments; a failed retrieval attaches nothing.
- **SC-006**: Every drafted answer, filled or not, can be read and copied
  without leaving the application page.
- **SC-007**: Starting a fill for a specific job takes one action from that
  job.
- **SC-008**: Self-identification and location questions fill from stored
  values across differing option wordings on the fixture set.
- **SC-009**: The tool performs **zero** submit, login, or wizard-advance
  clicks across the whole test suite.
- **SC-010**: A question answered once by the applicant in the panel fills
  automatically the next time it appears, with no model call and no prompt.
- **SC-011**: On a job the applicant never tailored, the attached file is their
  uploaded resume in 100% of attachments.

## Assumptions

- The applicant's own machine, single user, offline-first; all profile and
  resume data stays local.
- Greenhouse, Lever and Ashby remain the primary targets; other boards degrade
  gracefully through the generic classifier.
- The companion extension and the app ship as one version; version mismatch is
  already surfaced and new field kinds are withheld on mismatch.
- The 016 fill-first model is retained: fields fill immediately and the user
  corrects in place; no in-app approval gate is reintroduced.
- Voluntary self-identification is stored only because the user chooses to
  enter it; it is never inferred from the resume or any other source.
- The constitution is unchanged by this feature. Attaching the applicant's own
  file to a file input is field-filling under the existing rules, and the
  floating launcher only messages the local app. This feature supersedes
  feature 016's requirement that self-identification questions are never
  answered, replacing it with "never generated".
- Existing storage, the answer bank, the background drafter and the companion
  bridge are extended, not replaced.
