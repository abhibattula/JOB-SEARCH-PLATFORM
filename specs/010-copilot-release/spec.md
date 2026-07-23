# Feature Specification: The Copilot Release — In-Browser Filling, AI Answers, and a Professional Face

**Feature Branch**: `010-copilot-release`
**Created**: 2026-07-23
**Status**: Draft
**Input**: User description: "Chrome extension becomes the primary Apply Assist fill path (fills applications in the user's own Chrome where they are logged in, connected to the local app), AI answering for open-ended application questions grounded in the user's resume/profile (draft → fill → flag for review), and a full UI overhaul (Apply Assist flow, dashboard, tracker board, visual identity) — one free v1.0.0 release."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apply Assist fills in MY browser (Priority: P1)

The user installs the app's browser companion into their everyday Chrome
(one-time, guided setup). The companion shows "Connected" when the desktop
app is running. When the user starts Apply Assist on a job, the posting
opens as a normal tab in their own Chrome — where they are already signed
in to job sites — and the application form fills there, live, exactly as
the current assistant browser does: fields fill as they appear, nothing is
ever clicked or submitted, their typing is never overwritten, and a
progress panel on the page shows what was filled. If the companion is not
connected, Apply Assist works exactly as today in the separate assistant
browser window.

**Why this priority**: This is the release's reason to exist — filling in
the user's real, logged-in browser removes the biggest friction of v0.9.0
(a separate logged-out window) and is the capability the user explicitly
asked for. Everything else builds on the connection.

**Independent Test**: Install the companion, confirm "Connected" appears
in both the app and the companion, queue one job, and watch the form fill
in the user's own Chrome tab with the progress panel visible. Disconnect
(quit the app) and confirm the companion shows disconnected; restart and
confirm it reconnects without any user action.

**Acceptance Scenarios**:

1. **Given** the desktop app is running and the companion is installed,
   **When** the user opens the companion's status view, **Then** it shows
   "Connected" within a few seconds, and the app's Apply Assist page shows
   the same connection state.
2. **Given** a connected companion, **When** the user starts Apply Assist
   on a queued job, **Then** the job's application page opens as a tab in
   the user's own Chrome and recognized fields fill within ~2 scan passes
   of appearing, using the same profile/answer values as today.
3. **Given** a form field the user is actively typing in, **When** the
   companion is filling other fields, **Then** the user's field is never
   touched (same protection as today).
4. **Given** an application form inside an embedded frame (e.g. a job page
   embedding the application), **When** filling runs, **Then** fields
   inside the frame fill the same as top-level fields.
5. **Given** the companion is NOT connected, **When** the user starts
   Apply Assist, **Then** the queue runs in the assistant browser window
   exactly as v0.9.0, and the UI clearly states which mode is being used.
6. **Given** an active fill session in the user's Chrome, **When** the
   desktop app is closed mid-job, **Then** the companion stops touching
   the page, shows disconnected, and the app on restart offers to resume
   the queue.
7. **Given** any page state, **Then** the companion never clicks apply,
   submit, next, or login buttons, and never submits anything — the user
   always performs those actions themselves.
8. **Given** a login or account-creation form on a matching job-site
   domain with saved credentials, **When** filling runs, **Then** email
   and password fields fill (password never shown in any report or panel),
   and the login/submit button is never clicked.

---

### User Story 2 - Open-ended questions get grounded AI drafts (Priority: P2)

When an application asks an open-ended question ("Why do you want to work
here?", "Describe a relevant project"), the app writes a draft answer
grounded in the user's actual resume, profile, and past answers, fills it
into the field, and clearly flags it as an AI draft needing review — in
the on-page progress panel and in the app's fill report. The user reviews,
edits if needed (in the app or directly on the page), and submits
themselves. Once the user confirms a draft (or edits and saves it), it
becomes a saved answer and future applications reuse it directly without
AI. Questions about work authorization, visa status, or demographics are
never AI-answered — they keep the existing explicit-confirmation flow.

**Why this priority**: Free-text questions are today's biggest "needs
manual" bucket; competitors charge $20–40/month for exactly this. It turns
Apply Assist from an autofill into a copilot, but it depends on US1's
fill-and-flag surfaces to be visible.

**Independent Test**: On the practice application's essay question,
confirm a draft grounded in the user's resume appears in the field flagged
as an AI draft, edit and confirm it in the app, re-run the practice
application, and confirm the saved answer now fills without any AI flag.

**Acceptance Scenarios**:

1. **Given** an open-ended question with no saved answer, **When** filling
   reaches it, **Then** a draft answer generated from the user's resume/
   profile/saved answers fills the field and is visibly flagged "AI draft —
   review before submitting" both on-page and in the app's report.
2. **Given** an AI draft the user confirms or edits in the app, **When**
   the same (or equivalent) question appears in a later application,
   **Then** the saved answer fills directly with no AI flag.
3. **Given** a question about work authorization, visa, sponsorship, or
   demographics, **When** filling reaches it, **Then** no AI draft is
   generated; the existing confirm-before-use gate applies unchanged.
4. **Given** the offline model is preferred (default), **When** a draft is
   generated, **Then** it is produced locally at $0; if local generation
   fails and a cloud key exists, the cloud answers instead (same as other
   AI features).
5. **Given** AI drafting fails entirely, **When** filling reaches the
   question, **Then** the field is left untouched and reported as needing
   manual attention (never a fabricated or placeholder fill).

---

### User Story 3 - A professional, coherent app (Priority: P3)

The app looks and flows like a polished product, not a collection of
pages. The home screen leads with today's best matches, application stats,
and next actions (drafts to review, follow-ups due). The Apply Assist
screen is built around the connection: companion status, active queue with
live per-job activity, and an AI-drafts review list. The tracker board
supports the full pipeline with notes and follow-up nudges, and
applications submitted through the companion are detected and offered a
one-click status advance (user-confirmable, never silent). A consistent
visual identity (typography, color, spacing, light/dark) runs through
every page.

**Why this priority**: The user explicitly asked for a professional UI
competitive with commercial tools; it's high-value but meaningless without
US1/US2 working underneath.

**Independent Test**: Walk every page in both themes; confirm the home
screen surfaces matches/stats/next-actions, the Apply Assist screen shows
connection + queue + drafts, the tracker supports notes/follow-ups and
detected-submission confirmation, and no page looks unstyled or
inconsistent with the rest.

**Acceptance Scenarios**:

1. **Given** a fresh session with scored jobs, **When** the user opens the
   app, **Then** the home screen shows top matches with scores, current
   application counts by stage, and a next-actions list.
2. **Given** the user submits an application in their Chrome during a
   companion session, **When** the submission is detected, **Then** the
   tracker offers "Mark as applied?" for that job — one click to confirm,
   never auto-changed silently.
3. **Given** any page in light or dark theme, **Then** typography, colors,
   and spacing follow one coherent system and all existing accessibility
   behaviors (focus, aria-live regions) are preserved.
4. **Given** the tracker board, **When** the user adds a note or a
   follow-up date to an application, **Then** it persists and due
   follow-ups appear in the home screen's next actions.

---

### Edge Cases

- Companion installed in multiple Chrome profiles: only one connects at a
  time; the newer connection wins and the other shows disconnected.
- Companion version doesn't match the app (app updated, extension folder
  stale): the app refuses the session and tells the user to reload the
  extension once; the app keeps the bundled extension folder up to date.
- Browser restarts or the companion's background process is suspended
  mid-session: reconnection is automatic; re-scans are harmless (already
  filled fields are never re-filled or duplicated).
- The user closes the job tab mid-fill: the app marks the job interrupted
  (same as closing the assistant window today) and Resume works.
- A site's custom dropdown can't be set without clicking: reported
  honestly as needs-manual (never clicked) — same policy as today.
- File-upload fields: the companion attaches the resume file where the
  browser allows it; where a widget refuses, it reports needs-manual.
- Two fill sessions attempted at once (extension + assistant window):
  impossible by design — one queue, one backend at a time, chosen at
  queue start.
- An AI draft for a question the user already answered slightly
  differently phrased: the saved answer matches first (existing behavior);
  AI runs only when no saved answer matches.
- Question text too long or page in a non-English language: drafting is
  attempted; on low-confidence output the field is left untouched and
  reported needs-manual rather than filled with junk.

## Requirements *(mandatory)*

### Functional Requirements

**Companion connection (US1)**

- **FR-001**: The app MUST include a browser companion for the user's own
  Chrome, installable once via a guided in-app walkthrough at $0 cost.
- **FR-002**: The companion and app MUST connect automatically whenever
  both are running on the same machine, with no per-session user action,
  and MUST authenticate each other so no other local software can issue
  fill instructions or receive profile data.
- **FR-003**: Both the app and the companion MUST always display the
  current connection state; state changes MUST reflect within 10 seconds.
- **FR-004**: When the companion is connected, starting Apply Assist MUST
  open the job in the user's own Chrome and fill there; when not
  connected, Apply Assist MUST run exactly as v0.9.0 in the assistant
  window, and the active mode MUST be stated in the UI.
- **FR-005**: The mode MUST be fixed for the duration of a queue run;
  a mid-queue disconnect MUST preserve queue position and offer the user
  an explicit choice (wait/reconnect or restart the job in the assistant
  window) — never a silent mid-job switch.

**Filling behavior parity (US1)**

- **FR-006**: Companion filling MUST preserve every existing fill
  guarantee: fields fill as they appear (including late-rendered and
  embedded-frame fields); non-empty values are never overwritten; the
  field the user is typing in is never touched; nothing is ever clicked;
  nothing is ever submitted; every fill is recorded in the per-job report
  with the same outcomes as today.
- **FR-007**: All field understanding and value selection MUST remain in
  the app (single source of truth); the companion only reads form
  structure, fills instructed values, and reports outcomes.
- **FR-008**: Saved login credentials MUST fill only on pages whose
  domain matches the saved entry; passwords MUST never be stored,
  displayed, or logged by the companion and MUST appear masked in all
  reports (existing policy extended to the companion).
- **FR-009**: The companion MUST show an on-page progress panel (fields
  seen/filled, per-field outcomes, AI-draft flags, "you click submit"
  reminder) that never obstructs or interacts with the page's own
  controls, plus a compact status in its toolbar icon.
- **FR-010**: The resume file MUST attach to file-upload fields where the
  browser permits; refusals are reported needs-manual.

**AI question answering (US2)**

- **FR-011**: For open-ended questions with no saved-answer match, the
  system MUST generate a draft grounded ONLY in the user's resume,
  profile, saved answers, and the job's title/company/description — never
  fabricated facts (no invented employers, dates, or credentials).
- **FR-012**: Every AI-drafted fill MUST be visibly flagged as an AI draft
  needing review, on the page and in the app's fill report; drafts MUST be
  editable and confirmable in the app.
- **FR-013**: A confirmed (or edited-then-saved) draft MUST become a saved
  answer reused directly in future applications, without AI and without
  the draft flag.
- **FR-014**: Questions concerning work authorization, visa/sponsorship,
  or demographic/EEO information MUST never receive AI drafts; the
  existing explicit confirm-before-use flow applies unchanged.
- **FR-015**: Draft generation MUST follow the existing AI-tier rules:
  offline model preferred by default (private, $0), automatic cloud
  fall-through only if a key is configured; total failure leaves the field
  untouched and reported needs-manual.
- **FR-016**: The practice application MUST include an open-ended question
  so the entire draft → flag → confirm → reuse loop can be exercised
  end-to-end at home.

**UI overhaul (US3)**

- **FR-017**: The home screen MUST lead with top current matches (with
  scores), application-stage counts, and a next-actions list (AI drafts to
  review, follow-ups due, import review pending).
- **FR-018**: The Apply Assist screen MUST be organized around the
  companion: connection card (state + install walkthrough entry), queue
  with live per-job activity, mode indicator, and an AI-drafts review
  list.
- **FR-019**: The tracker board MUST support per-application notes and
  follow-up dates; due follow-ups surface in next actions.
- **FR-020**: When a submission is detected during a companion session,
  the system MUST offer a one-click, user-confirmable status advance for
  that job — never changing status silently.
- **FR-021**: A single visual identity (typography, color, spacing,
  light/dark) MUST apply across every page; existing accessibility
  behaviors (keyboard focus, aria-live updates, reduced motion) MUST be
  preserved or improved.

**Packaging & guardrails (cross-cutting)**

- **FR-022**: The companion MUST ship inside the existing installers; the
  guided setup MUST work fully offline and require no store, account, or
  payment; app updates MUST keep the installed companion current without
  re-doing the walkthrough.
- **FR-023**: All existing constitutional guarantees remain binding:
  never click apply/submit/login, never auto-submit, $0 recurring cost,
  visa/EEO answers only with explicit confirmation, passwords never in the
  app's database and masked everywhere.
- **FR-024**: All v0.9.0 capabilities (practice application, import
  review, offline-first extraction, assistant-window filling, live
  activity feed) MUST continue to work unchanged.

### Key Entities

- **Companion session**: the authenticated link between app and browser
  companion — connection state, companion version, last-seen time; at most
  one active at a time.
- **Fill instruction / fill outcome**: one field-level command from app to
  companion and its reported result; outcomes match today's report
  vocabulary (filled, skipped existing, no match, needs manual) plus
  "AI draft".
- **AI draft**: a generated answer tied to a question and job — question
  text, draft text, grounding provenance, status (drafted → confirmed/
  edited/discarded); confirmed drafts become saved answers (existing
  entity).
- **Next action**: a home-screen work item derived from existing data
  (draft awaiting review, follow-up due, import ready) — no new user
  bookkeeping.
- **Follow-up**: a per-application date + optional note powering tracker
  nudges.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the machine where it's tested, the companion connects
  automatically within 10 seconds of both sides running, and survives an
  app restart plus a browser restart without any user action beyond the
  one-time install.
- **SC-002**: On live postings across the three directly-fillable major
  ATS families (the same set proven in v0.9.0), companion filling achieves
  at least the same fields-filled counts as the v0.9.0 assistant window on
  the same postings, in the user's own logged-in Chrome.
- **SC-003**: The user's typing is never overwritten and no page control
  is ever clicked in any test (fixture suite + live gate) — zero
  exceptions.
- **SC-004**: On the practice application, an open-ended question receives
  a grounded AI draft, flagged, in under 60 seconds on the offline model;
  after confirmation, the same question refills from the saved answer in
  under 5 seconds with no flag.
- **SC-005**: 100% of AI-drafted fills are visibly flagged; 0 visa/
  sponsorship/EEO questions ever receive an AI draft (enforced by test).
- **SC-006**: A first-time user can complete the companion install
  walkthrough in under 3 minutes without external help.
- **SC-007**: Every page renders correctly in light and dark themes with
  the new identity; all pre-existing tests for accessibility behaviors
  still pass.
- **SC-008**: The entire release remains $0: no store fees, no signing
  fees, no cloud requirement (offline mode fully functional).

## Assumptions

- The user's primary browser is Chrome (or a Chromium browser that loads
  unpacked extensions); the assistant-window fallback covers everything
  else, so non-Chrome users lose nothing relative to v0.9.0.
- One machine, one user profile: the companion pairs with the single app
  instance on the same computer; remote/multi-machine setups are out of
  scope.
- "Detected submission" is a best-effort signal (page navigation/confirm
  heuristics); that is acceptable because the advance is user-confirmed,
  and missed detections cost nothing (manual status change remains).
- The unpacked-extension developer-mode notice Chrome shows at startup is
  acceptable to the user (store publishing was explicitly declined).
- Windows "Unknown publisher" remains (signing explicitly deferred);
  the install guide documents the SmartScreen click-through.
- Existing Playwright engine, practice pages, fixture suite, and live-gate
  scripts remain the regression baseline; the companion adds a parallel
  test layer using the same fixture pages.
