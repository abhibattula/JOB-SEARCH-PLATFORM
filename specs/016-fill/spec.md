# Feature Specification: The Fill Release — Apply Assist fills for real, on the page

**Feature Branch**: `016-fill`
**Created**: 2026-07-27
**Status**: Draft
**Input**: Approved design doc `docs/superpowers/specs/2026-07-27-feature-016-design.md`
(root-caused from the user's first real v1.5.0 run: nothing fills after
clicking Apply on Greenhouse; dropdown/yes-no questions get prose drafts;
approving answers in the app never reaches the page; popup fill silently
no-ops; "Tailor for this job" hard-crashes the app). Locked decisions
(2026-07-27): D1 auto-click form-OPENING Apply controls (final submit stays
human-only, constitution v1.1.4); D2 fill-first with on-page highlights, no
blocking approval gate; D3 injected on-page status panel.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The form I'm looking at gets filled, promptly (Priority: P1)

The user queues a job with the companion connected. The job opens in their
preferred browser, the application form is detected — including when it only
appears after an Apply click, and when it opens in a new tab — and every
field the assistant already knows (name, email, phone, links, saved answers)
fills within seconds. Questions the assistant has to think about are drafted
in the background and land on the page by themselves when ready. Nothing the
assistant is thinking about ever delays or blocks the fills it has already
decided, and the app's status stays live throughout.

**Why this priority**: This is the headline failure — in v1.5.0 the user
watched a connected companion fill nothing at all. Without this, no other
improvement is visible.

**Independent Test**: Queue a fixture job with the companion connected;
verify known fields fill within seconds while a deliberately slow draft is
in flight, the drafted answer lands later without user action, and a form
revealed after navigation or in a child tab still gets filled.

**Acceptance Scenarios**:

1. **Given** a queued job whose form is visible and the companion connected,
   **When** the page is scanned, **Then** all profile/known fields are
   filled within 2 seconds of detection, before any AI drafting completes.
2. **Given** an unknown free-text question on the form, **When** the
   background draft completes, **Then** the answer appears in the field
   without any user action, and it was drafted at most once for that
   question this session.
3. **Given** the application form opens in a new tab (embedded job board),
   **When** the new tab loads, **Then** filling continues in the new tab.
4. **Given** the companion is mid-queue, **When** the user presses the
   popup's fill button, **Then** they see a clear "busy" explanation instead
   of a silent no-op.
5. **Given** a job link that fails to open, **When** the failure occurs,
   **Then** the queue advances with a visible failure outcome instead of
   hanging.

---

### User Story 2 - Choice questions answered from the real options (Priority: P2)

Dropdowns, radio groups, and yes/no questions are answered with one of the
field's actual options — never an essay. Yes/no facts the profile already
knows (work authorization, sponsorship, relocation) are answered from the
profile without AI. Sensitive questions (EEO/demographics, disability,
veteran status, criminal history, references) are never auto-answered: they
are left blank and visibly flagged for the human.

**Why this priority**: The second-loudest failure — the app drafted
descriptive paragraphs for dropdown menus, which can never be filled and
poison the review flow.

**Independent Test**: Scan a fixture form containing a native select, a
radio yes/no group, a custom combobox, and an EEO question; verify each
select/radio is set to a real option, the combobox receives a short matched
option, the EEO question stays blank and flagged, and every reported
outcome matches what is actually on the page.

**Acceptance Scenarios**:

1. **Given** a work-authorization dropdown with options including "Yes, I am
   authorized", **When** the field is processed, **Then** the selected value
   is one of the field's real options, chosen consistently with the profile.
2. **Given** a yes/no radio group whose group question is in the group
   label, **When** the field is processed, **Then** the correct radio is
   actually checked on the page and the reported outcome says so.
3. **Given** a custom dropdown widget whose options only appear on click,
   **When** the field is processed, **Then** the assistant's short answer is
   matched against the harvested options; if none match, the field stays
   empty and is flagged.
4. **Given** an EEO/demographic question of any control type, **When** the
   form is processed, **Then** the field is left untouched and flagged for
   the human.
5. **Given** an older companion that predates choice filling, **When** a
   choice fill would be sent, **Then** it is withheld and the field flagged
   (never silently mis-filled).

---

### User Story 3 - Everything happens on the page (Priority: P3)

The user's whole review loop lives on the job page: on a recognized job
board the assistant opens the application form itself (clicking only a
form-opening Apply control — never anything that submits); a compact on-page
panel shows connection status, progress, and per-field results; AI-drafted
and needs-attention fields carry a visible highlight until the user edits
them; corrections are typed directly into the form; a "Fill again" action
re-fills without ever overwriting anything the user typed. The app window is
no longer required mid-application, and no approval step blocks filling.

**Why this priority**: The user's explicit direction — eliminate the
app↔browser round-trip; they correct on the page and submit themselves.

**Independent Test**: Open a fixture posting where the form only appears
after the Apply control is clicked; verify the assistant opens it once,
the panel appears with live counts, drafted fields are highlighted until
edited, Fill-again preserves a user-typed value, and the fixture's submit
control records zero automated clicks.

**Acceptance Scenarios**:

1. **Given** a queued recognized job posting with no visible form, **When**
   the page is processed, **Then** the form-opening Apply control is clicked
   exactly once, the revealed form fills, and no submit/login/next/pay
   control is ever clicked.
2. **Given** fills in progress, **When** the user looks at the page, **Then**
   the panel shows connection status, filled count, and needs-attention
   count, with a per-field list.
3. **Given** an AI-drafted answer in a field, **When** the user edits that
   field, **Then** its highlight clears; until then it remains visibly
   marked.
4. **Given** a field the user corrected by hand, **When** Fill-again runs,
   **Then** the user's value is preserved.
5. **Given** the app's Apply Assist page during a companion fill, **When**
   the user checks it, **Then** they see a passive activity log (including
   drafting-in-progress items) and are never required to approve anything
   for filling to proceed.

---

### User Story 4 - AI can fail without taking the app down (Priority: P4)

Heavy AI work — tailoring above all — runs isolated from the app by
default, with explicit output and time limits. A fault in the AI runtime
restarts the AI, not the app; the user sees an honest progress state and, on
failure, a clear error instead of a vanished application. Tailoring, which
has never once completed on the user's machine, completes or fails cleanly.

**Why this priority**: A hard crash is the worst experience in the app, but
it is independent of the fill pipeline and testable on its own.

**Independent Test**: With isolation on, induce an AI-runtime fault during a
tailor request; verify the app stays up, the restart is counted and
surfaced, and the request returns a clean failure; verify a normal tailor
completes and persists in the packaged build.

**Acceptance Scenarios**:

1. **Given** AI isolation on by default, **When** the AI runtime dies
   mid-generation, **Then** the app remains responsive, the failure is
   reported to the caller, and the restart appears in diagnostics.
2. **Given** a tailor request, **When** it runs, **Then** the user sees an
   honest in-progress state ("can take a few minutes") and either a
   persisted result or a rendered failure message — never a dead app.
3. **Given** any on-device generation, **When** it runs, **Then** it has an
   explicit output limit and time budget (no unbounded generation).

---

### Edge Cases

- Companion not connected at queue start: the v1.5.0 behavior stands —
  proceed in the assistant window with the loud path notice; the shared
  decision core gives that path the same choice-aware answers.
- Extension service worker restarts mid-fill: the watched-tab set survives
  (persisted session state); filling resumes on the next scan.
- Apply control not recognized: no click happens; the user opens the form
  themselves and detection/filling proceeds as normal.
- The same question appears twice on one form: both fields receive the one
  cached draft; the drafter still runs once.
- Draft fails or times out: the field stays empty and flagged; retries back
  off exponentially; it never spins every scan.
- User edits a field, then a rescan or Fill-again runs: user-typed values
  are never overwritten.
- Multi-select checkbox groups: not auto-answered (pick-one does not apply);
  members stay individual with the group question as context; unknown
  multi-selects stay blank + flagged. Single consent-style checkboxes keep
  today's behavior.
- Discovery badge on the same page: its score traffic is cached per page and
  can never delay fill processing.
- Repeated AI-runtime deaths: each restart is counted and visible in
  diagnostics; requests fail cleanly each time.
- Scanner error on a page: reported and visible (doctor/panel), not a
  permanently silent tab.

## Requirements *(mandatory)*

### Functional Requirements

**Fill pipeline (US1)**

- **FR-001**: Companion message processing MUST never be blocked by answer
  drafting or any long-running work; companion status freshness MUST stay
  under 5 seconds throughout a fill session.
- **FR-002**: Fields whose answers are already known MUST be dispatched to
  the page incrementally as they are decided — never withheld until the
  whole form is decided.
- **FR-003**: Unknown questions MUST be drafted in the background with
  bounded concurrency; at most one draft attempt per unique question per
  session, with exponential backoff after failures.
- **FR-004**: A completed draft MUST reach the page without user action,
  and MUST be auto-saved to the answer bank marked as AI-drafted.
- **FR-005**: A tab opened from the fill target MUST become the new fill
  target; the watched-tab set MUST survive extension service-worker
  restarts.
- **FR-006**: A job open that fails or never acknowledges MUST advance the
  queue with a visible failure outcome within a bounded time; field-level
  failure states MUST become retryable when a new answer arrives for that
  field.
- **FR-007**: Discovery/badge traffic MUST be requested at most once per
  page state and MUST never delay fill processing.
- **FR-008**: Companion-path errors (busy, scan failure, wrong-tab drops)
  MUST be visible to the user (popup, panel, or doctor) — never silently
  discarded; the app's Re-scan action MUST work in companion mode.
- **FR-009**: Starting a queue with a live companion MUST NOT launch the
  assistant browser for preflight.

**Choice-aware answering (US2)**

- **FR-010**: Field capture MUST include control type and available
  options: native select options, radio groups unified as one logical field
  (group question from its group label; stable identity across rescans),
  and custom dropdowns marked for fill-time option harvesting; both capture
  paths (companion and assistant window) MUST produce the same logical
  fields for the same page.
- **FR-011**: Answer drafting MUST receive the field's type, options, and
  length limit. Option-bearing fields MUST be answered only with one of the
  real options (validated); custom-dropdown answers MUST be short option
  labels matched against harvested options at fill time; on no match the
  field MUST stay unfilled and flagged.
- **FR-012**: Yes/no and profile-fact questions (work authorization,
  sponsorship, relocation) MUST be answered from the profile without AI.
- **FR-013**: Sensitive questions — EEO/demographic, disability, veteran
  status, criminal history, references — MUST never be AI-answered; they
  MUST be left unfilled and visibly flagged.
- **FR-014**: Fillers MUST correctly set radios, selects, custom dropdowns,
  and checkboxes, and MUST report honest outcomes (never "filled" when the
  page did not change).
- **FR-015**: Fill instructions of new kinds MUST NOT be sent to an older
  companion; affected fields go unfilled + flagged (no silent mis-fill).

**On-page experience (US3)**

- **FR-016**: On a queue-driven watched page of a recognized job board with
  no fillable form, the assistant MUST click a recognized form-OPENING
  Apply control exactly once per page state; it MUST NEVER click any
  control that submits, advances, saves, logs in, registers, or pays
  (constitution v1.1.4 clarification).
- **FR-017**: An on-page panel MUST show connection status, fill progress
  (filled / needs-attention counts), per-field results, and a Fill-again
  action that re-fills retryable fields and never overwrites user-typed
  values.
- **FR-018**: AI-drafted and needs-attention fields MUST carry a visible
  on-page highlight until the user edits them.
- **FR-019**: Filling MUST NOT be gated on any in-app approval; the answer
  confirm/edit endpoints remain for curating the answer bank (with the
  existing practice/ad-hoc sentinel guard); the app shows a passive
  activity log including drafting-in-progress items.

**AI runtime (US4)**

- **FR-020**: On-device AI MUST run fault-isolated by default so a native
  fault cannot close the app; each runtime restart MUST be counted and
  visible in diagnostics; an environment override MAY disable isolation.
- **FR-021**: Every on-device generation MUST have an explicit output limit
  and time budget; the tailoring prompt MUST fit the documented safe local
  band; a failing embedding-model load MUST NOT be retried unboundedly.
- **FR-022**: Tailoring MUST show an honest in-progress state and a clean
  rendered failure on error; a successful tailor MUST persist.

### Key Entities

- **Logical field**: one fillable question as the user sees it — control
  type, question text, options (or "harvest at fill time"), length limit,
  required flag, member elements (for grouped radios), stable identity
  across rescans.
- **Draft record**: per unique question this session — state (drafting /
  done / failed), the answer, attempt count, next-retry time; feeds both
  the page and the answer bank.
- **Fill target**: the browser tab currently being filled for the active
  job; transfers to child tabs; survives extension restarts.
- **Field outcome**: per field per page state — filled / skipped (existing
  value) / no-match / needs-human, with retryability tied to the arrival of
  a new answer.
- **On-page annotation**: highlight + badge state for a field (AI-drafted /
  needs-you), cleared by user edit.
- **AI runtime status**: isolation mode, restart count, last restart cause —
  surfaced in diagnostics.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the representative fixture application (text, select,
  radio yes/no, custom combobox), at least 90% of fields with known or
  derivable answers are filled without user action, in both supported
  browser families.
- **SC-002**: Known fields appear on the page within 2 seconds of form
  detection, and app status staleness never exceeds 5 seconds — including
  while a slow draft is running.
- **SC-003**: Each unique question triggers at most one draft attempt per
  session (verified under a repeated-scan hammer).
- **SC-004**: Zero automated clicks on submit/login/advance/pay controls
  across the entire end-to-end suite (explicitly asserted).
- **SC-005**: An induced AI fault during tailoring never closes the app;
  tailoring completes and persists in the packaged-build check; the user
  always sees either a result or a clean error.
- **SC-006**: Every AI-drafted or needs-attention field is visibly flagged
  on the page; sensitive questions are auto-answered zero times.
- **SC-007**: A user can complete the practice application start-to-finish
  on the page alone — corrections included — without opening the app
  window, and submits it themselves.

## Assumptions

- Recognized job boards for auto-opening the form are the Greenhouse /
  Lever / Ashby families first; on unrecognized boards the user opens the
  form and everything else still works.
- The v1.5.0 pairing layer (hello/secret, doctor, wizard, PREFERRED_BROWSER)
  is kept as-is; companion and app ship as one version and mismatches are
  already surfaced by the doctor.
- The assistant-window fallback (015 D2: proceed with loud notice when no
  companion) remains, and inherits the choice-aware improvements through
  the shared decision core.
- One application form is filled at a time (a single fill target).
- The constitution v1.1.4 clarification (form-opening Apply clicks) is
  amended as part of this feature, before implementation.
- Wire-protocol changes are additive only (existing protocol version
  retained); older companions degrade safely per FR-015.
- The user corrects highlighted fields themselves (locked D2); no in-app
  approval flow is reintroduced.
