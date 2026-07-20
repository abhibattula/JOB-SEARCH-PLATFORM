# Feature Specification: Apply Assist

**Feature Branch**: `005-apply-assist`
**Created**: 2026-07-20
**Status**: Draft
**Input**: User description: "Apply Assist: bundle a local AI model in the installer for
offline scoring/tailoring/Q&A drafting with no API key required, as a new tier
alongside the existing cloud and basic deterministic match. Add app-driven browser
automation that opens each shortlisted job's application page in turn and autofills
recognized fields using the user's profile and a reusable 'answer bank' of common
application Q&A — first-time/unrecognized questions get an AI-drafted suggested
answer that the user must explicitly confirm/edit before it is saved or typed
anywhere. The app must never click a final submit/apply button or a login button —
the human always performs both. Saved logins are stored in the OS keychain,
autofilled into recognized login fields only, never auto-submitted, never
re-displayed once saved. After the user finishes or abandons one application, the
queue automatically advances to the next shortlisted job. Any site the field-reader
can't confidently handle falls back gracefully to manual completion. This phase also
folds in a bug-sweep/regression pass across the existing shipped application before
new work begins."

## Clarifications

### Session 2026-07-20

- Q: How should Apply Assist know a job application is "finished" so it can
  auto-advance to the next one? → A: An explicit "Done, next application"
  control the user clicks — not automatic detection of a success/confirmation
  page, which varies too much across sites to be reliable.
- Q: Should Apply Assist automate inside a separate, dedicated browser
  profile, or the user's regular everyday browser? → A: A separate, dedicated
  profile — isolated from the user's normal browsing, with its own cookies
  and logins (first-time site logins go through the saved-credential flow).
- Q: Beyond the general answer bank, should there be a record of exactly
  which answer was used on which specific application? → A: Yes — a
  lightweight per-application record of the confirmed answers actually used,
  in addition to the general reusable answer bank.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Works offline, no signup, out of the box (Priority: P1)

A newly-installed user opens the app for the first time, uploads a resume, and
immediately sees match scores and drafted tailoring content for jobs — without
creating any account, entering any API key, or having an internet connection for
the AI features specifically. Today the app only produces a rough deterministic
score until the user finds and configures a cloud AI key.

**Why this priority**: This removes the single biggest remaining friction point in
the existing product (the user must go find/paste an API key to get real AI
quality) and benefits every single user of the app, not just those who use the
newer application-assist features below. It also underpins Story 3's answer
drafting.

**Independent Test**: Fresh install, no API key ever entered, no internet
connection required for scoring — resume upload produces AI-quality match
scores and tailored content immediately, distinguishable in the UI from both the
existing cloud-AI results and the existing basic/no-AI results.

**Acceptance Scenarios**:

1. **Given** a fresh install with no API key configured, **When** the user
   uploads a resume and refreshes jobs, **Then** jobs are scored using the
   bundled local AI, visibly labeled as such (distinct from cloud-AI and
   basic-match labels already in the product).
2. **Given** the user later adds a cloud API key, **When** jobs are next
   scored, **Then** the cloud AI is used in preference to the local AI, and
   previously local-AI-scored jobs are automatically upgraded.
3. **Given** a future app update ships an improved local AI model, **When** the
   user checks for updates (existing feature), **Then** the update is offered
   through that same flow — no separate "model update" step exists.

---

### User Story 2 - Apply Assist opens and pre-fills applications, human submits (Priority: P2)

The user shortlists several jobs, then starts "Apply Assist." The app opens each
job's real application page, one at a time, in a visible browser window running
in its own dedicated, isolated profile (separate from the user's everyday
browser — see Clarifications), and fills in the fields it recognizes (name,
contact info, resume, links, common yes/no and short-answer questions) using the
user's saved profile. The user reviews what was filled, makes any corrections,
and clicks the actual apply/submit button themselves — the app never does this
on their behalf. When done (or choosing to skip), the user clicks an explicit
"Done, next application" control to move on (see Clarifications) — the app does
not try to guess completion from the page itself.

**Why this priority**: This is the core "apply co-pilot" value the user asked
for — the repetitive typing goes away, but the user stays in control of every
submission and every login, which is both the explicit requirement and the
guardrail that keeps this safe to use.

**Independent Test**: With at least one shortlisted job and a saved profile,
starting Apply Assist opens that job's real application page in a visible
browser window with recognized fields pre-filled, and no automated click ever
lands on a submit or apply button anywhere in the flow.

**Acceptance Scenarios**:

1. **Given** a shortlisted job with a reachable application page, **When**
   Apply Assist opens it, **Then** recognized fields (name, email, phone,
   resume upload, links, work-authorization/sponsorship, years of experience,
   salary expectation, how-heard, cover letter) are filled from the user's
   profile and the answer bank (Story 3).
2. **Given** the application page has been fully processed, **When** the user
   has reviewed and submitted it themselves and clicks "Done, next
   application," **Then** the app opens the next shortlisted job's
   application page without further setup (Story 4).
3. **Given** an application page where the system cannot recognize at
   least the core identity fields — name, email, and a resume upload if
   present (e.g., a heavily dynamic multi-step application system, or one
   already known to block automated access), **When** Apply Assist reaches
   it, **Then** the page still opens for the user to complete manually, the
   user sees a clear indication this job fell back to manual mode (rather
   than it looking like a normal, silent autofill), and the queue still
   advances afterward — it does not get stuck or fail loudly.
4. **Given** any application page in any state, **When** Apply Assist is
   running, **Then** at no point does the app itself click a final submit,
   apply, or login button — only the human does.

---

### User Story 3 - Reusable answer bank with review-before-use for sensitive questions (Priority: P3)

The same handful of questions come up across many applications (work
authorization, sponsorship needs, years of experience, "how did you hear about
us"). The user answers each one once; after that, Apply Assist reuses the saved
answer automatically. The first time a new or unrecognized question appears, the
app drafts a suggested answer from the user's profile, but always pauses and
shows it to the user for confirmation or editing before it is saved or used —
it is never typed into a form unreviewed.

**Why this priority**: This is what makes Story 2 fast on the 3rd, 10th, 50th
application instead of just the 1st, and the review gate specifically protects
against a wrong automated answer on a question that has real legal weight for
this user's visa/work-authorization situation.

**Independent Test**: Answer a work-authorization-style question once through
the review flow; on a later, different job with the same or a very similarly
worded question, the saved answer is applied automatically without being asked
again, and no eligibility-related answer is ever visible as "filled" without
having gone through a review step at least once.

**Acceptance Scenarios**:

1. **Given** no saved answer exists for a question Apply Assist encounters,
   **When** the field is reached, **Then** the queue pauses, shows an
   AI-drafted suggested answer clearly marked as unreviewed, and requires the
   user to confirm or edit it before it is saved or typed anywhere.
2. **Given** a previously confirmed answer for a matching or near-matching
   question, **When** Apply Assist encounters it again on a different job,
   **Then** it is filled automatically without pausing.
3. **Given** a work-authorization or sponsorship-requirement question
   specifically, **When** it is filled, **Then** it can only ever be filled
   from a previously user-confirmed answer — never from an unreviewed draft.

---

### User Story 4 - Saved logins autofill without auto-login (Priority: P4)

For job sites the user has an account on, the user can save an email/password
once; afterward, when Apply Assist lands on that site's login page, the
credential is filled into the recognized login fields, but the user clicks the
actual login button themselves.

**Why this priority**: Removes another repetitive step (typing the same
credentials for the same job-board accounts) while keeping the same "human
performs the sensitive action" guardrail as Story 2, and keeps stored
credentials out of reach of casual exposure (never re-displayed once saved).

**Independent Test**: Save a credential for a domain once; on a later visit to
that domain's login page, the email/password fields are pre-filled and the
login button is never clicked automatically; the saved password cannot be
viewed again through any part of the app after saving.

**Acceptance Scenarios**:

1. **Given** a saved credential for a domain, **When** Apply Assist reaches
   that domain's recognized login page, **Then** the email and password
   fields are filled automatically and the login button is left for the user.
2. **Given** a previously saved credential, **When** the user views its entry
   in the app, **Then** the password itself is never shown again (write-only,
   like a typical password manager).

---

### Edge Cases

- What happens when the bundled local AI model file is missing, corrupted, or
  fails to load at runtime? The app MUST fall back to the existing
  deterministic basic-match tier rather than crashing or hanging, and MUST
  surface this state somewhere the user can see it (not a silent failure).
- What happens when the user has no shortlisted jobs when starting Apply
  Assist? The feature MUST explain what's needed instead of opening nothing.
- What happens when the user closes the automated browser window mid-queue,
  or manually navigates away? Apply Assist MUST treat this as "stopped," not
  crash, and MUST NOT continue trying to act on a window the user closed.
- What happens on an application page requiring a one-time code, CAPTCHA, or
  other step only a human can complete? Apply Assist MUST leave those to the
  user like any other unrecognized field, never attempt to bypass them.
- What happens when the OS-level secure storage itself is unavailable, locked,
  or denies access when saving or retrieving a credential (distinct from the
  credential simply not existing yet)? The system MUST surface this clearly
  to the user rather than silently failing to save, or worse, falling back
  to a less secure storage location.
- What happens if the same question is asked with slightly different wording
  across two different job sites (e.g., "Are you legally authorized to work in
  the US?" vs. "Do you require visa sponsorship now or in the future?")? These
  MUST be treated as related-but-distinct — near-identical phrasing may reuse
  a saved answer, but meaningfully different questions MUST still trigger a
  fresh review rather than silently reusing an answer to a different question.
- What happens if disk space is insufficient, or the download is interrupted
  partway, for the one-time browser-engine or the bundled model asset? The
  user MUST see a clear message rather than a silent failure or a partial,
  broken install — a partial download MUST NOT be treated as a successful
  install.
- What happens if the user neither confirms nor edits a paused drafted
  answer (Story 3) — e.g., navigates away or leaves it indefinitely? Apply
  Assist MUST keep that field/question paused rather than guessing or
  silently skipping it — an unreviewed legally-significant question MUST
  never be left filled with an unconfirmed draft merely because the user
  didn't respond right away.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide AI-quality job scoring and content
  drafting (tailored bullets, cover letters, application-question answers)
  without requiring any API key, account, or internet connection, using an
  AI capability bundled with the installed application.
- **FR-002**: The system MUST prefer a user-configured cloud AI key over the
  bundled local AI when both are available, and MUST prefer the bundled local
  AI over the existing non-AI deterministic scoring when no cloud key is set.
- **FR-003**: The system MUST automatically upgrade previously
  deterministically-scored or locally-scored jobs when a higher-quality tier
  (local, then cloud) becomes available, without requiring the user to
  manually re-trigger scoring for each job.
- **FR-004**: Updates to the bundled local AI capability MUST be delivered
  through the existing application update-check mechanism; the system MUST
  NOT introduce a separate, independent update path just for the AI model.
- **FR-005**: The system MUST let the user select one or more shortlisted
  jobs and start an assisted-application session ("Apply Assist") covering
  them in sequence.
- **FR-006**: For each job in the session, the system MUST open that job's
  real, live application page in a visible, user-controllable browser window
  (not hidden/headless), so the user can see, take over, or correct anything
  at any time. This window MUST run in a separate, dedicated browser profile
  isolated from the user's regular everyday browser (its own cookies/session
  state), not the user's default browser.
- **FR-007**: The system MUST attempt to recognize and fill common
  application-form fields (full/first/last name, email, phone, resume
  upload, LinkedIn/portfolio links, work authorization, sponsorship
  requirement, years of experience, salary expectation, "how did you hear
  about us," cover letter/free-text) from the user's saved profile and the
  answer bank (FR-010–FR-013).
- **FR-008**: The system MUST NEVER, under any circumstance, automatically
  click a final submit/apply button, a login button (including single-
  sign-on/social-login buttons such as "Sign in with Google"), or any
  control that itself submits the application or completes a login. The
  human MUST always perform the actual submission and the actual login.
  This does NOT prohibit the system from advancing between pages of a
  multi-step application form using non-submitting "Next"/"Continue"
  controls that only reveal the next section — the prohibition is
  specifically on the action that submits the application or completes
  authentication, not on intra-form page navigation.
- **FR-009**: When the system cannot recognize at least the page's core
  identity fields (name, email, and a resume-upload control, if present) —
  including but not limited to pages known to actively block automated
  access — it MUST treat the page as unreadable, still open it for the
  user to complete manually, and MUST still allow the session to continue
  to the next job — it MUST NOT fail the whole session or leave it stuck.
  The system MUST also make it visible to the user, distinct from a normal
  successful autofill, that a given job fell back to manual completion.
- **FR-010**: The system MUST maintain a reusable store of previously
  answered application questions ("answer bank") and MUST reuse a matching
  or clearly-equivalent previously-confirmed answer automatically on later
  jobs.
- **FR-011**: When the system encounters a question with no matching saved
  answer, it MUST draft a suggested answer (using the local or cloud AI) and
  MUST pause for the user to explicitly confirm or edit it — the draft MUST
  NOT be saved to the answer bank or typed into any form field until the
  user has done so.
- **FR-012**: Work-authorization and sponsorship-requirement questions, and
  any other legally-significant personal-disclosure question the system
  encounters (including but not limited to disability status, veteran
  status, or race/ethnicity/gender self-identification questions of the
  kind commonly present on job applications for compliance/EEO purposes),
  MUST only ever be filled from an answer the user has previously and
  explicitly confirmed — an AI-drafted-but-unreviewed answer MUST NEVER be
  used for these fields under any circumstance. The field classifier's
  taxonomy (see plan.md) MUST treat this as an open category it can extend,
  not a fixed two-item list.
- **FR-013**: The system MUST distinguish, near-identical wording aside,
  between genuinely different questions, and MUST NOT silently apply an
  answer to a question it was not actually confirmed for.
- **FR-014**: After the user finishes (submits) or abandons the current
  job's application and explicitly signals completion via a "Done, next
  application" control, the system MUST open the next shortlisted job's
  application page without requiring the user to manually restart the
  session. The system MUST NOT attempt to automatically detect completion
  from the page itself (e.g., guessing at a confirmation/success page).
- **FR-015**: The system MUST let the user save a login credential
  (identifier + secret) per site/domain, store it securely on the user's own
  machine (not in the application's regular data store in plain form), and
  MUST fill recognized login fields with it automatically when Apply Assist
  reaches a matching site's login page.
- **FR-016**: The system MUST NEVER automatically submit a login form; the
  user MUST always click the login action themselves.
- **FR-017**: Once a login credential's secret has been saved, the system
  MUST NOT display, log, or otherwise surface that secret again anywhere —
  including diagnostic output and log files, not only the normal
  settings-page UI (write-only, view/edit of the identifier only).
- **FR-018**: The system MUST allow the user to view which sites have a
  saved credential, and to update or delete a saved credential.
- **FR-019**: The system MUST NOT attempt to defeat, evade, or work around
  any site's active bot-detection or access-blocking measures — the
  graceful-fallback behavior in FR-009 applies instead.
- **FR-020**: Before any new work in this phase begins, the existing shipped
  application's current features MUST be re-verified against a full
  automated test pass and a manual pass through every existing page/action,
  and any issues found MUST be resolved first, so later problems can be
  attributed to new work rather than a pre-existing regression.
- **FR-021**: In addition to the reusable answer bank (FR-010), the system
  MUST keep a lightweight per-application record of which confirmed answer
  was actually used for which question on each specific job application,
  distinct from the answer bank's "current answer per question" record —
  so the user has a reference of exactly what was submitted where, even if
  the general answer bank entry is later edited.

### Key Entities

- **Local AI Capability**: The bundled, offline scoring/drafting tier
  installed with the application; has an availability state (ready /
  unavailable) that the rest of the system reacts to.
- **Answer Bank Entry**: A question (as originally asked, plus a
  normalized/comparable form), its confirmed answer, an optional category
  (e.g., work-authorization, sponsorship, general), and whether it came
  directly from the user or was an AI draft the user then confirmed.
- **Saved Credential**: A per-site/domain identifier and securely-stored
  secret, with save/update/delete lifecycle; secret is never re-displayed
  after saving.
- **Apply Session / Queue**: An ordered set of shortlisted jobs being
  processed by Apply Assist, with a notion of "current job," an explicit
  user-driven advance to the next one (not automatic detection), start, and
  stop. Runs in its own dedicated, isolated browser profile separate from
  the user's everyday browser.
- **Application Answer Record**: A per-application record of exactly which
  confirmed answer (from the answer bank) was used for which question on a
  specific job's application — distinct from the answer bank's single
  current-answer-per-question record, and not affected by later edits to it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with no cloud API key and no internet connection still
  receives AI-quality match scores and drafted tailoring content for 100% of
  jobs, immediately after installing the application and uploading a resume.
- **SC-002**: Across a batch of shortlisted jobs processed through Apply
  Assist, common recognized fields (name, contact info, links, standard
  yes/no questions) are pre-filled correctly without the user retyping them
  on at least 80% of applications on sites the field-reader supports well.
- **SC-003**: 0% of applications are submitted, and 0% of logins are
  completed, without the user's own final action — across every session,
  every job, every site, with no exceptions.
- **SC-004**: After a question has been answered and confirmed once, it is
  never presented again for manual re-typing on a subsequent job where the
  same or a clearly equivalent question appears.
- **SC-005**: 100% of work-authorization/sponsorship-requirement answers
  used in any filled application trace back to a user-confirmed answer, with
  zero instances of an unreviewed AI draft being used for these fields.
- **SC-006**: A user can go from "select shortlisted jobs" to "move to the
  next application" with no manual setup step in between beyond reviewing
  and submitting the current one.
- **SC-007**: On an application page the system cannot confidently handle,
  the user experience degrades to "open the page, fill it in yourself" —
  never a stuck queue, crash, or silent skip.
- **SC-008**: The full existing test suite and a manual pass over every
  existing feature both pass cleanly before any new feature work in this
  phase is considered started.

## Assumptions

- The user has already completed the existing profile/resume setup from
  prior phases; Apply Assist reuses that data rather than collecting it
  again.
- "Shortlisted" reuses the existing saved/status concept already in the
  product rather than introducing a separate selection mechanism.
- Sites that actively block automated access (e.g., ones already known to
  block this application's job-listing retrieval) are expected to fall into
  the graceful-fallback path (FR-009) rather than being specially supported
  in this phase; broad reliable support across every possible application
  system is not a requirement of this phase.
- A one-time local setup step (e.g., downloading a browser engine component)
  the first time Apply Assist is used is acceptable, provided it is visible
  to the user and does not silently fail.
- Model/update delivery for the bundled local AI rides the existing
  application release/update mechanism; no independent in-place model
  update path is in scope for this phase.
- Single-user, single-machine use continues to be assumed, consistent with
  the rest of the product.
