# Feature Specification: The Companion — the extension becomes the product

**Feature Branch**: `018-companion`
**Created**: 2026-07-29
**Status**: Draft
**Input**: User description: "did you analyse simplify / jobright.ai because the extension is not working well i want all the drafted answers on the extension and the extension is going to bottom of the page where i cannot see and when i click fill it is not filling please analyse and devolop and improve the extension and apply assist i want less of to and fro from the app and browser and want more polished inteface and professional and easy of applying" + "also analyse the functonality of the extension and make it easier and fast best for user"

## Context

v1.7.0 (017) fixed *what* Apply Assist writes: a refusal contract so it never
invents facts, answer-shape-must-fit-field, canonical synonym matching, a 37-column
profile, verified résumé attach, and an on-page answers panel.

The applicant could not use almost any of it, because the surface it renders
into is unreachable. This feature fixes the surface.

**The unexamined difference.** 017 was told to build "a floating button like
simplify or jobright.ai". That phrase was treated as a *visual* reference and no
analysis of those products was done. The substantive difference is not visual:
Simplify and Jobright are **extension-first** — the on-page widget drives the
application and the web dashboard is where you look afterwards. This product is
**app-first** — the app drives and the extension executes. Every complaint in
the input traces to that difference.

Competitive findings that inform the design:

- Simplify anchors a **small icon to the form**, not a large card; one primary
  action, always in the same place.
- Jobright is **one click from the posting**; its dashboard is consulted after
  the fact, never during.
- Their common weakness is **silent partial fills** — reviewers report fields
  left "empty, requiring manual entry anyway" with no explanation of what was
  skipped or why. 017's refusal contract already produces that explanation. It
  is this product's one genuine advantage over both, and it is currently
  invisible.

**Confirmed defects behind the report** (each verified in code, not inferred):

- Both floating widgets have rendered at the **bottom of the document**, not
  pinned to the viewport, since v1.0.0 — `all:initial` is declared last in the
  host's inline style, and because `all` is a shorthand for every property it
  resets the `position:fixed` declared before it. This is "the extension is
  going to bottom of the page where i cannot see."
- The badge's **"Apply with Apply Assist" is a dead button**: its handler reads
  a `posting` key that the detection code never sets, so it returns before
  sending anything. This is "when i click fill it is not filling."
- **Insert** and **Show me** never render on any answer, because the answer feed
  carries no field identifier.
- The panel lists **only questions the AI drafter touched** — everything filled
  from the profile or answer bank is absent, so the page cannot be where an
  application is reviewed.
- The panel **rebuilds every row on every scan (~2 s)**, destroying a half-typed
  answer before it can be saved.
- On a bare ATS application page with no job metadata, **no widget appears at
  all** — which is the page where it is needed most.
- There is **no Stop and no session control** on the page, and the app's own
  entry point navigates away from the job being read.

**Why the defects shipped**: 017's tests for these controls were
string-presence assertions on source files. A dead button passed a green suite.
This spec treats that as a first-class requirement, not a footnote.

## Clarifications

### Session 2026-07-29

- Q: Should the discovery badge and the fill panel become one widget? → A: Yes,
  one merged floating card — match score and sponsorship on top, one primary
  action, then live fill progress and every answer. (This is what 017's D4
  already decided; the code still ships two separate hosts.)
- Q: How much screen should the widget take by default? → A: It rests as a
  compact pill showing the essential state and expands on click. It
  auto-expands when a fill starts and when something first needs an answer, so
  an action is never missed.
- Q: Should the widget appear on a bare application form with no job metadata?
  → A: Yes — wherever the page has a fillable application form, offering "Fill
  this page" as the primary action.
- Q: Which answers should the panel list? → A: Everything, grouped and
  collapsible — needs-you first and open, then AI drafts to review, then fields
  filled from the profile (collapsed).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - I can see it, and it does something (Priority: P1)

The applicant opens a job posting. A companion appears **pinned to the corner of
the viewport**, visible without scrolling. They click its primary action and a
fill session actually starts. On a bare application URL with no job metadata,
the companion is still there, offering to fill the page.

**Why this priority**: Nothing else in the feature — or in 017 — is reachable
until this is true. These are three shipped defects that each independently
render the product unusable.

**Independent Test**: Load the real extension in a real browser on a tall,
hostile fixture page; assert the host's computed `position` is `fixed` and its
rectangle lies inside the viewport; click the primary action and assert the app
received the start message and opened a session.

**Acceptance Scenarios**:

1. **Given** a job posting 5000 px tall whose stylesheet declares
   `div { position: static !important }`, **When** the companion renders,
   **Then** it is pinned to the viewport corner and fully visible without
   scrolling.
2. **Given** a recognised job posting, **When** the applicant clicks "Apply with
   Apply Assist", **Then** the app records the posting, starts a watched
   session on that tab, and the companion reflects the running session.
3. **Given** an application URL with no job metadata but a fillable form,
   **When** the page settles, **Then** the companion appears with "Fill this
   page" as its primary action, and clicking it starts an ad-hoc fill session.
4. **Given** the applicant clicks the primary action, **When** the app refuses
   (for example, another session is running), **Then** the companion says so in
   plain language instead of appearing to do nothing.

---

### User Story 2 - One companion, not two, and it looks like a product (Priority: P2)

The match score, the sponsorship grade, the fill progress, the answers and every
control live in **one** floating card. At rest it is a small pill; clicking it
expands the card; it collapses back. It never covers the field being filled.

**Why this priority**: Two cards in two corners is the "not polished,
unprofessional" report, and it is what 017's D4 already committed to and did not
deliver. It depends on P1 being visible at all.

**Independent Test**: On a scored posting, assert exactly one companion host
exists in the document, that it carries both the score state and the fill state,
and that collapse/expand toggles the card and survives a page mutation.

**Acceptance Scenarios**:

1. **Given** any page where the companion appears, **When** the document is
   inspected, **Then** exactly one companion host element exists.
2. **Given** the companion at rest, **When** it is displayed, **Then** it shows a
   compact pill carrying the current state (match score when idle on a posting,
   filled-of-seen while filling, a count when something needs the applicant).
3. **Given** the collapsed pill, **When** the applicant clicks it, **Then** the
   full card expands; clicking collapse returns it to the pill, and that choice
   persists for the tab.
4. **Given** a fill session starts, or the first question needs the applicant,
   **When** that happens, **Then** the card expands on its own.
5. **Given** a viewport shorter than the card, **When** the card is expanded,
   **Then** it stays inside the viewport and scrolls internally rather than
   overflowing the screen.

---

### User Story 3 - Every answer, readable, insertable, correctable (Priority: P3)

The companion lists every question the application asked: the ones needing the
applicant first, then AI drafts to review, then the fields filled from the
profile. Each answer can be copied, inserted into its field, or scrolled to. A
question the app declined to answer has an input; typing an answer saves it for
this field and every future application — and typing is never interrupted.

**Why this priority**: This is "i want all the drafted answers on the extension"
and the largest reduction in to-and-fro. It depends on a visible card (P1, P2).

**Independent Test**: Run a fill against a fixture form; assert profile-filled
fields, AI drafts and refusals all appear in their groups; click Insert and
assert the field receives the value; type into a needs-you input, let two scan
cycles pass, and assert the text is still there.

**Acceptance Scenarios**:

1. **Given** a completed fill pass, **When** the applicant expands the card,
   **Then** questions are grouped as needs-you (expanded), AI drafts, and
   filled-from-profile (collapsed), each showing its count.
2. **Given** any listed answer, **When** the applicant clicks Insert, **Then**
   that value is placed in that one field and nothing else on the page changes.
3. **Given** any listed answer, **When** the applicant clicks Show me, **Then**
   the page scrolls that field into view.
4. **Given** the applicant is typing into a needs-you input, **When** the page
   re-scans (up to every 2 s), **Then** the input keeps focus and keeps its text.
5. **Given** the applicant submits a typed answer, **When** the next scan runs,
   **Then** the field is filled with exactly that text, and the answer is stored
   as theirs — surviving a purge of model-written answers.
6. **Given** a scan whose answers are unchanged, **When** it completes, **Then**
   no answer payload is pushed to the page at all.

---

### User Story 4 - I never have to switch to the app mid-application (Priority: P4)

Stop, Fill again, and moving to the next queued job are all on the page. The
companion shows which job is running and how many remain. Starting Apply Assist
from a job in the app no longer navigates away from that job. A keyboard
shortcut toggles the companion and runs a fill.

**Why this priority**: This is "less to and fro". It is the last layer because
each control is only useful once the card is visible and populated.

**Independent Test**: With a two-job queue running, click Stop in the companion
and assert the app's session actually stopped; assert the app's job page starts
a session without navigating.

**Acceptance Scenarios**:

1. **Given** a running session, **When** the applicant clicks Stop in the
   companion, **Then** the app's queue stops and the companion says so.
2. **Given** a multi-job queue, **When** a job is done, **Then** the companion
   shows which job is current and how many remain, and offers to move on.
3. **Given** the app's job page, **When** the applicant starts Apply Assist,
   **Then** the session starts and status appears in place — the page does not
   navigate to the Apply Assist page.
4. **Given** any page, **When** the applicant presses the companion's keyboard
   shortcut, **Then** the card toggles; a second shortcut runs a fill on the
   current page.
5. **Given** the app refuses an action, **When** that happens, **Then** the
   refusal text appears in the companion, not only in the toolbar popup.

---

### Edge Cases

- **Page CSS actively fights the widget** (`position`, `display`, `z-index`, or
  `transform` forced with `!important` on all `div`s): the companion must stay
  pinned and visible.
- **Page has no `<body>` yet** when the companion first tries to mount.
- **Same-document (SPA) navigation** to a different posting: the companion must
  reset score, answers and dismissal state rather than showing the last job's.
- **Two frames both claim the top frame** — the companion is top-frame only;
  cross-origin iframes fill their own documents but must not mount a companion.
- **Answers exceed the message budget**: the page shows what fits and says so;
  the app's own view stays complete.
- **The applicant dismisses the companion**, then a fill starts: a dismissal
  must not silently hide a running session's needs-you list.
- **A needs-you input is focused when its own row's answer changes server-side**:
  the applicant's typing wins.
- **The extension is reloaded mid-session** (orphaned frame): the companion tears
  down cleanly instead of throwing on every scan.
- **The app is not running / not paired**: the companion must say which, not
  present dead controls.
- **A field's element disappears** between the answer feed and an Insert click.

## Requirements *(mandatory)*

### Functional Requirements

**Visibility and mounting**

- **FR-001**: The companion MUST be pinned to the browser viewport, in a fixed
  corner, regardless of page scroll position or document height.
- **FR-002**: The companion's positioning MUST survive hostile page stylesheets,
  including declarations marked `!important` on generic element selectors.
- **FR-003**: The companion MUST render inside a shadow root so page styles
  cannot alter it and its styles cannot leak onto the page.
- **FR-004**: Exactly ONE companion host element MUST exist per top-level
  document; cross-origin sub-frames MUST NOT mount one.
- **FR-005**: The companion MUST appear on a page that has a fillable
  application form, whether or not job-posting metadata is detectable.
- **FR-006**: The companion MUST mount safely before `<body>` exists and MUST
  tear down cleanly when the extension is reloaded.

**Primary action**

- **FR-007**: The companion MUST expose exactly one primary action whose label
  and behaviour follow the current state: start Apply Assist for a detected
  posting; fill this page when only a form is detected; Stop while running; Fill
  again when a pass has completed.
- **FR-008**: Clicking the primary action on a detected posting MUST cause the
  app to record that posting and start a watched, job-linked fill session on
  that tab.
- **FR-009**: Clicking the primary action on a metadata-less application form
  MUST start an ad-hoc fill session for that tab.
- **FR-010**: Every companion control MUST report the outcome of the action it
  triggered — success, refusal with a reason, or failure — and MUST NEVER appear
  to have done nothing.
- **FR-011**: The companion MUST NOT click, type into, submit, or otherwise
  mutate any element belonging to the page, other than placing a value into a
  field the applicant explicitly chose. It never performs a submit or a login.

**Presentation**

- **FR-012**: The companion MUST rest in a compact collapsed form showing the
  most relevant current state, and expand to the full card on click.
- **FR-013**: The companion MUST expand on its own when a fill session starts
  and when a question first needs the applicant.
- **FR-014**: The collapse/expand choice MUST persist for the tab across
  re-renders and same-document navigations.
- **FR-015**: The expanded card MUST stay within the viewport and scroll
  internally rather than overflowing or covering the whole form.
- **FR-016**: The companion MUST present match score, sponsorship signal, and
  save state (today's badge) and fill progress and answers (today's panel) in
  one card.
- **FR-017**: The companion MUST expose its state on the host element in the
  light DOM so it is observable without piercing the shadow root.
- **FR-018**: The companion MUST be operable by keyboard, with visible focus,
  and MUST respect a reduced-motion preference.

**Answers**

- **FR-019**: The answer feed sent to the page MUST include every field the
  application asked for that the app made a decision about — those filled from
  the profile or answer bank, those drafted by the AI, and those declined —
  not only the AI drafter's records.
- **FR-020**: Every entry in the answer feed MUST carry an identifier for the
  field it belongs to, so it can be inserted and scrolled to.
- **FR-021**: The companion MUST group answers as needs-you, AI drafts, and
  filled-from-profile, each collapsible, with needs-you expanded by default.
- **FR-022**: Each answer MUST offer Copy, Insert into its own field, and Show
  me (scroll to the field).
- **FR-023**: Insert MUST place the value into exactly one field and MUST NOT
  alter any other element.
- **FR-024**: Each declined question MUST show why it was declined, in plain
  language, and MUST offer an input to answer it.
- **FR-025**: An answer typed in the companion MUST be stored as the applicant's
  own — never model-written — so it fills future applications and survives a
  purge of model-written answers.
- **FR-026**: Re-rendering the answer list MUST preserve focus and in-progress
  text in any input the applicant is using.
- **FR-027**: The app MUST NOT push an answer payload when the answers have not
  changed since the last push.
- **FR-028**: Answer text MUST be rendered as text, never as markup.
- **FR-029**: When the answer list exceeds the message budget, the companion
  MUST show what fits and state that the app holds the complete list.

**Session control**

- **FR-030**: The applicant MUST be able to stop a running session from the
  companion.
- **FR-031**: The applicant MUST be able to re-run a fill pass from the
  companion.
- **FR-032**: For a multi-job queue, the companion MUST show the current job and
  the number remaining, and MUST let the applicant move to the next job.
- **FR-033**: App-side refusals and errors MUST surface in the companion.
- **FR-034**: Starting Apply Assist from a job in the app MUST NOT navigate away
  from that job; status MUST appear in place.
- **FR-035**: The extension MUST offer keyboard commands to toggle the companion
  and to fill the current page.

**Compatibility and safety**

- **FR-036**: The wire protocol version MUST remain unchanged; all new message
  fields MUST be additive and optional, and an older companion MUST NOT
  mis-handle them.
- **FR-037**: Secrets MUST NOT appear in the companion, in any message it
  receives, or in any log or diagnostic.
- **FR-038**: The applicant MUST perform every submit, login, and wizard step;
  nothing in this feature may perform one.

**Verification**

- **FR-039**: Every interactive companion control MUST be covered by a test that
  clicks it in a real browser and asserts the observable effect. A test that
  only asserts a string appears in a source file MUST NOT be the sole coverage
  for any control.
- **FR-040**: The companion's pinned positioning MUST be covered by a test that
  asserts computed style and on-screen position against a hostile page.

### Key Entities

- **Companion**: the single on-page widget. State: collapsed/expanded,
  detection state (posting / form-only / none), session state (idle / starting /
  filling / stopped / done), and the counts it displays.
- **Page answer**: one question the application asked, as shown on the page —
  the question text, the answer text, the field identifier, its group
  (needs-you / draft / profile), and, when declined, the reason. Derived from
  the app's existing per-field decisions plus the drafter's records; adds no new
  stored data.
- **Session control action**: a request from the page to stop, re-run, or
  advance the app's existing fill queue. Carries no new capability.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every page where it appears, the companion is visible without
  scrolling — measured as the host rectangle intersecting the viewport on 100 %
  of tested pages, including a hostile-CSS page and a 5000 px document.
- **SC-002**: 100 % of the companion's interactive controls produce their stated
  effect when clicked in a real browser, verified by automated tests.
- **SC-003**: An applicant can start a fill, review every answer, correct a
  declined question, and stop the session **without leaving the browser tab** —
  zero switches to the app required for a single application.
- **SC-004**: Text typed into a needs-you input survives at least three
  consecutive page-scan cycles with no loss of characters or focus.
- **SC-005**: Every field the application asked for that the app decided about
  appears in the companion's list — no decided field is missing.
- **SC-006**: Exactly one companion host element exists per document.
- **SC-007**: Scans that change no answers push no answer payload, measured as a
  reduction in repeated identical pushes to zero.
- **SC-008**: The full existing test battery passes twice, plus the browser suite
  and the offline-model gates, before release.

## Assumptions

- The applicant uses a Chromium browser with the companion loaded and paired to
  the local app; this feature does not change pairing.
- The engine keeps ownership of the profile, answer bank, drafter, vocabulary
  and matching. The companion remains a thin client — no answering logic moves
  into the extension.
- 017's answer semantics are correct and unchanged: the refusal contract, the
  never-generated tags, answer-shape-must-fit-field, and the binding/routine
  acknowledgement split all stay exactly as they are. This feature changes only
  what reaches the page and how it is presented.
- The existing real-browser harness (real unpacked extension, real Chromium,
  live app, real WebSocket bridge, shadow-root driving) is the basis for the new
  interaction tests; no new test infrastructure is required.
- The existing `fill_here`, `apply_here`, `fill_again` and `answers` messages are
  reused; only genuinely new capabilities (session control) add a message type,
  additively.
- "Polished" is scoped to the on-page companion and the one app entry point it
  replaces; the app's own pages are not redesigned.
