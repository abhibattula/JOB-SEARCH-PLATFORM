# Feature Specification: The Moat Release

**Feature Branch**: `007-moat-release`
**Created**: 2026-07-21
**Status**: Draft
**Input**: User description: "Make the platform decisively better than every paid competitor on its four unique pillars, shipping as one release (v0.7.0): Apply Assist depth, sponsorship intelligence, resume builder + tailored resume PDF export, and a full 'Instrument, evolved' visual redesign. Constitution rules bind: never auto-submit, never auto-login, $0 recurring cost, local-first. Design doc: docs/superpowers/specs/2026-07-21-feature-007-design.md"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apply Assist completes real applications, not just first pages (Priority: P1)

As a job seeker running Apply Assist over my shortlisted jobs, I want the
assistant to attach my resume file, keep filling as I advance through
multi-page application forms, and show me exactly what it filled — so that
a real application (not just a demo form) is substantially completed with
me only reviewing, correcting, and clicking the site's own buttons.

**Why this priority**: This is the pillar the user explicitly reported as
"not as expected." Resume attachment is the single most-missed capability
compared with paid competitors, and most real ATS applications are
multi-page — without these, Apply Assist only helps on page one.

**Independent Test**: Queue one saved job whose application form has a
resume-upload field and at least two pages. Verify the resume file is
attached automatically, each new page the user advances to gets scanned and
filled, the status panel lists every filled field, and at no point does the
app click next/submit/login itself.

**Acceptance Scenarios**:

1. **Given** a profile with an uploaded resume and a queued job whose form
   has a resume file input, **When** Apply Assist fills the page, **Then**
   the stored resume file is attached to that input and the fill report
   lists it.
2. **Given** a job with a generated tailored resume PDF and the "use
   tailored resume" preference on, **When** the resume field is filled,
   **Then** the tailored PDF for that job is attached instead of the
   generic resume.
3. **Given** the user clicks the site's own Next button onto page 2 of an
   application, **When** the new page loads, **Then** recognized fields on
   page 2 are filled automatically without any further user action, and the
   app itself never clicks any navigation/submit/login control.
4. **Given** a page was filled, **When** the user opens the Apply Assist
   status panel, **Then** they see a per-field report (field label + what
   was entered) for the current job.
5. **Given** a dropdown asking "Are you authorized to work in the US?"
   with options Yes/No, **When** the profile/answer bank has a confirmed
   answer, **Then** the matching option is selected (not typed as free
   text); unconfirmed sensitive questions still pause for review.
6. **Given** the automation browser window is closed mid-queue, **When**
   the user returns to the Apply Assist page, **Then** they can resume the
   queue from the job they were on rather than starting over.
7. **Given** a queue finishes, **When** the user views the page, **Then**
   a summary shows per-job outcomes (filled / manual / skipped).

---

### User Story 2 - Build my resume once, export a tailored PDF per job (Priority: P1)

As a job seeker, I want the app to turn my uploaded resume into structured,
editable sections and generate a clean, ATS-safe resume PDF tailored to any
specific job (plus a cover-letter PDF) — so every application I submit uses
a resume aimed at that posting without me maintaining resume variants by
hand.

**Why this priority**: Per-job tailored resumes are the flagship paid
feature of every competitor; doing it locally/free/offline is the release's
headline capability, and it feeds Story 1's resume attachment.

**Independent Test**: Upload a resume, review the auto-extracted sections
in Profile, correct one entry, open a scored job, generate the tailored
PDF, and confirm the downloaded file contains the corrected entry and the
job-tailored summary/bullets.

**Acceptance Scenarios**:

1. **Given** a resume PDF is uploaded and an AI tier (cloud or local) is
   available, **When** extraction completes, **Then** Profile shows
   structured sections (experience, education, projects, skills) populated
   from the resume for the user to review and edit.
2. **Given** no AI tier is available, **When** the user opens the Resume
   builder, **Then** the same sections are present as empty editable forms
   for manual entry.
3. **Given** structured sections exist, **When** the user edits and saves
   an entry, **Then** the change persists and later PDFs reflect it —
   extraction never overwrites user edits without consent.
4. **Given** a job with tailoring output, **When** the user clicks
   "Download tailored resume (PDF)", **Then** a single-column, text-based
   PDF downloads containing their identity header, the job-tailored
   summary/bullets, and their structured sections.
5. **Given** a job with a generated cover letter, **When** the user clicks
   the cover-letter PDF download, **Then** a formatted cover-letter PDF
   downloads.
6. **Given** no LLM is available at all, **When** the user requests a
   resume PDF, **Then** an untailored PDF renders from the structured
   sections alone (no invented content, no error).

---

### User Story 3 - Sponsorship intelligence tells me where my visa odds are best (Priority: P2)

As an international candidate on OPT, I want each company in my feed graded
on real sponsorship evidence — approval/denial history, wage levels,
cap-exempt status — so I can prioritize applications where my H-1B odds are
genuinely best instead of guessing from a binary badge.

**Why this priority**: It's the moat no competitor has, directly serving
the user's stated situation, but it enriches decisions rather than
unblocking a broken flow — so it follows the two P1 capabilities.

**Independent Test**: Load USCIS + DOL files, refresh, and verify feed rows
show sponsor grades, a university employer shows a cap-exempt badge, a
company detail shows wage-level evidence, and the "Strong sponsors only"
filter narrows the feed accordingly.

**Acceptance Scenarios**:

1. **Given** sponsorship data is loaded, **When** the feed renders,
   **Then** companies with sufficient history display a letter grade (A-F)
   derived from approvals, denials, engineering-role filings, and wage
   levels.
2. **Given** a job at a university/nonprofit research employer, **When**
   its row/detail renders, **Then** a cap-exempt indicator explains that
   this employer can sponsor year-round outside the lottery.
3. **Given** a company with wage data, **When** its detail page renders,
   **Then** a lottery-odds hint reflects its median wage level under the
   wage-weighted selection rule.
4. **Given** the "Strong sponsors only" filter is on, **When** the feed
   renders, **Then** only jobs at companies graded B or better, or
   cap-exempt employers, appear.
5. **Given** a company with no loaded records, **When** it renders,
   **Then** it shows the existing UNKNOWN treatment — never a fabricated
   grade.

---

### User Story 4 - A redesigned instrument that gives feedback and never fights me (Priority: P2)

As a daily user, I want the app to look and behave like a precision
instrument — a coherent design system with light "datasheet" and dark
"scope" themes, grouped navigation that shows where I am, immediate
feedback for every action, a kanban pipeline, an Apply Assist mission
panel, and a first-run checklist — so the app feels trustworthy and
efficient instead of homemade, and never loses my in-progress edits.

**Why this priority**: The redesign transforms perceived quality and fixes
real correctness bugs (silent actions, the feed poll clobbering open
editors), but the app is usable without it — so it follows the P1
capabilities. Its foundation ships first in implementation order.

**Independent Test**: Walk every page in both themes; verify tokens (no
per-page odd styling), active nav state, a toast on each action, an open
notes editor surviving a poll cycle, kanban stage moves, the Apply Assist
queue panel, and the onboarding checklist reflecting real completion state.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the app opens, **Then** the light
   "datasheet" theme renders; **When** the user switches to dark "scope"
   mode in Settings, **Then** every page renders correctly in it and the
   choice persists across restarts.
2. **Given** any page, **When** it renders, **Then** the nav shows grouped
   sections with the current page visibly active.
3. **Given** the user marks a job saved/applied/hidden or changes a stage,
   **When** the action completes, **Then** visible confirmation appears
   within a second — no silent actions anywhere.
4. **Given** a notes editor is open on the Applied view, **When** the
   periodic feed refresh fires, **Then** the editor and its unsaved text
   survive untouched.
5. **Given** the Applied view, **When** the user switches to board view,
   **Then** applications appear as cards in stage columns with counts, and
   moving a card updates its stage; the table view remains available.
6. **Given** an Apply Assist queue is running, **When** the user views its
   panel, **Then** they see every queued job with its state (done /
   current / pending / failed), progress like "3 of 8", and the current
   job's title and company.
7. **Given** a first run, **When** the feed renders, **Then** an
   onboarding checklist shows setup steps with live completion state, and
   disappears once all steps are done.
8. **Given** any icon-only control, **When** inspected by assistive
   technology, **Then** it exposes a descriptive accessible name.

---

### Edge Cases

- Resume extraction returns malformed/partial structure → user sees
  whatever was extracted plus empty forms for the rest; saving works;
  no crash. Extraction failure falls back to manual entry with a notice.
- A tailored PDF is requested for a job whose tailoring is stale (resume
  changed since) → regenerate tailoring first or clearly label the PDF's
  basis; never silently mix old bullets with a new resume.
- Multi-page detection fires on a page that is actually a new site (job
  board redirect) → fields are still classified conservatively;
  legally-sensitive tags still require confirmed answers; login fields
  still require a domain-matched credential.
- The same page mutates repeatedly (SPA re-renders) → re-fill must be
  idempotent: never duplicate text into a field the user already edited,
  never overwrite a user-typed value.
- File input rejects programmatic attachment (rare custom widgets) → field
  is reported as "needs manual upload" in the fill report; queue continues.
- USCIS/DOL files with unexpected column layouts → rows are skipped with a
  logged warning; grades render only from successfully parsed data.
- A company matches USCIS records but has no DOL wage rows → grade computes
  from available signals; wage/lottery hint is simply absent.
- Dark theme with OS light preference (and vice versa) → explicit user
  choice in Settings always wins over the OS signal.
- Queue resume attempted after the app itself restarted (not just the
  browser) → queue state is not preserved across app restarts; the page
  says so and offers a fresh start (documented limitation).

## Requirements *(mandatory)*

### Functional Requirements

**Apply Assist depth**

- **FR-001**: The system MUST retain the user's uploaded resume file
  (not only its extracted text) and use it to fill resume file-upload
  fields in applications.
- **FR-002**: When a job has a generated tailored resume PDF and the user
  preference (default on) allows it, the system MUST attach that job's
  tailored PDF instead of the generic resume.
- **FR-003**: When the user navigates to a subsequent page of the same
  application, the system MUST detect the new page and automatically
  classify and fill its fields, subject to all existing confirmation
  rules.
- **FR-004**: The system MUST NOT click any navigation, submit, apply, or
  login control under any circumstance (existing constitutional rule,
  restated because multi-page support makes it newly tempting).
- **FR-005**: The system MUST record every filled field (label, category,
  value entered) per job and present this report in the status panel.
- **FR-006**: For select/radio/checkbox inputs, the system MUST choose the
  option whose text best matches the confirmed answer, and MUST leave the
  input untouched (reported as unfilled) when no option matches
  confidently.
- **FR-007**: Re-filling a page MUST be idempotent: a field the user has
  manually edited is never overwritten, and values are never duplicated.
- **FR-008**: If the automation browser window is closed mid-queue, the
  system MUST allow resuming the queue from the current position within
  the same app session.
- **FR-009**: When a queue ends, the system MUST present a per-job outcome
  summary (filled / manual / skipped).

**Sponsorship intelligence**

- **FR-010**: Sponsorship data loading MUST additionally capture denial
  counts and prevailing-wage levels / offered wages for engineering
  roles, retaining current behavior for files lacking those columns.
- **FR-011**: The system MUST compute a per-company sponsor grade (A-F)
  locally from approval volume, denial ratio, engineering-filing
  presence, and wage levels; companies without sufficient data remain
  UNKNOWN.
- **FR-012**: The system MUST flag likely cap-exempt employers
  (universities, colleges, hospitals, research institutes, foundations)
  and present the flag with a plain-language explanation.
- **FR-013**: The system MUST present a wage-weighted lottery-odds hint
  derived from a company's median wage level, labeled as an estimate.
- **FR-014**: The feed MUST offer a "Strong sponsors only" filter (grade
  B or better, or cap-exempt) that composes with existing filters.
- **FR-015**: Grade evidence (approvals, denials, wage level, filings)
  MUST be visible on the job detail page.

**Resume builder + PDFs**

- **FR-016**: On resume upload with an AI tier available, the system MUST
  extract structured sections (experience, education, projects, skills)
  for user review; extraction MUST NOT silently overwrite prior user
  edits.
- **FR-017**: The user MUST be able to create, edit, and delete structured
  resume entries manually, with identical capability whether or not any
  AI tier exists.
- **FR-018**: The system MUST generate a single-column, machine-readable
  (selectable-text) resume PDF from the structured sections and identity
  fields, with a per-job tailored variant using that job's tailoring
  output, and a cover-letter PDF.
- **FR-019**: PDF generation MUST work fully offline and MUST NOT include
  any content the user has not either provided or explicitly confirmed
  (tailored bullets come from the existing no-invention tailoring
  pipeline).
- **FR-020**: Tailored PDFs MUST be regenerated or clearly invalidated
  when the underlying resume or tailoring changes.

**Visual redesign**

- **FR-021**: All pages MUST render from a single design-token system with
  a light default theme and a dark alternate; the user's explicit theme
  choice persists and overrides the OS preference.
- **FR-022**: Navigation MUST be grouped with a visible active state for
  the current page.
- **FR-023**: Every user action MUST produce visible feedback within one
  second (confirmation, progress, or error) — no silent actions.
- **FR-024**: Periodic background refreshes MUST NOT discard or replace
  in-progress user edits (open editors, focused inputs).
- **FR-025**: The Applied view MUST offer a stage-column board view with
  per-stage counts alongside the existing table view.
- **FR-026**: The Apply Assist page MUST show queue composition and
  per-job state, overall progress, the current job's title and company,
  and the FR-005 fill report.
- **FR-027**: A first-run onboarding checklist MUST reflect actual
  completion state of setup steps and stop appearing once complete.
- **FR-028**: Interactive controls MUST have accessible names; live
  regions MUST not disrupt assistive technology; theme colors MUST meet
  reasonable contrast for their text sizes.

### Key Entities

- **Stored resume file**: the original uploaded document, retained for
  attachment into applications; linked to the profile.
- **Structured resume**: ordered sections (experience entries, education
  entries, projects, skills) with per-entry fields (title, organization,
  dates, bullet points); user-editable; sourced from AI extraction or
  manual entry.
- **Tailored resume document**: a per-job rendered PDF combining the
  structured resume with that job's tailoring output; invalidated when
  its inputs change.
- **Fill report entry**: per job, per field — label, category, value
  entered, outcome (filled / needs manual / skipped).
- **Queue session**: the ordered set of jobs in an Apply Assist run with
  per-job state (pending / current / done / failed) and outcomes;
  resumable within an app session.
- **Sponsor profile (extended)**: per company — approvals, denials, wage
  level median, cap-exempt flag, computed grade, evidence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a real multi-page ATS application with a resume-upload
  field, at least 80% of standard fields (identity, links, authorization,
  screening questions with confirmed answers, resume attachment) are
  filled across all pages with the user only reviewing and clicking the
  site's own buttons.
- **SC-002**: A user can go from uploaded resume to a downloaded tailored
  resume PDF for a specific job in under 3 minutes (excluding LLM
  latency), including reviewing extracted sections.
- **SC-003**: With sponsorship data loaded, at least 90% of feed companies
  that have USCIS records display a grade or explicit UNKNOWN — none show
  fabricated values; cap-exempt universities in the feed are flagged.
- **SC-004**: Every user action in the redesigned UI produces visible
  feedback within 1 second, and zero in-progress edits are lost to
  background refreshes during a 10-minute working session.
- **SC-005**: The app passes its full automated suite and frozen-build
  smoke test (including a PDF-generation self-check) on both platforms,
  and both installers publish for the release tag.
- **SC-006**: The app never clicks a submit/next/login control in any
  automated scenario — verified by test assertions and a live multi-page
  walkthrough.

## Assumptions

- The four pillars ship together as v0.7.0 (user-confirmed); the v0.6.1
  mac CI fix precedes this feature and is tracked outside this spec.
- Resume files are PDFs (existing upload constraint); one active resume
  at a time (existing single-profile model).
- Structured-resume extraction quality depends on the available AI tier;
  the user-review step is the quality gate, so imperfect extraction is
  acceptable by design.
- Queue resume-after-browser-close is scoped to the same app session;
  surviving an app restart is out of scope and documented.
- Sponsor grades are estimates from public data and presented as such;
  they are decision support, not legal advice.
- "Instrument, evolved" direction and light-first default are locked
  design decisions from the brainstorming session (see design doc).
- Existing constitution v1.1.0 continues to bind; no amendment is needed
  for this feature (no new deferred-item conflicts).
