# Feature Specification: Door to Door

**Feature Branch**: `019-door-to-door`
**Created**: 2026-07-31
**Status**: Draft
**Input**: User description: "same thing it is not filing jobs i want this to
also fill USERID/ Email and also Password also click continue and this not
clicking apply button i also want to automate this what can we do what all
improvements can be made" — plus four decisions locked in session: automation
runs all the way to the final Review/Submit page and stops (the human presses
Submit); sign-in is automated with saved logins and account creation is
assisted (generated password saved to the OS credential vault, the human
presses Create account); target sites in order Workday, Greenhouse,
Lever/Ashby (iCIMS generic only); LinkedIn stays fill-only. Governed by
constitution v1.2.0 (progression clicks).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The companion never lies about its state (Priority: P1)

As an applicant, when anything between the app and the companion is broken or
stale, I can see it and fix it in one step — and the actions I trigger act on
the page I am looking at, not somewhere I can't see.

**Why this priority**: Every later capability is invisible or misleading if
the surface itself can silently run stale code, hijack the session into a
different tab, refuse work because of a phantom session, or drop fills with
no trace. These are the confirmed reasons v1.8.0 "still didn't fill".

**Independent Test**: Load an outdated companion against a newer app and
confirm the mismatch is flagged everywhere with reload instructions; start
Apply Assist from an open posting and confirm the same tab fills; retry a
resume attach and confirm it succeeds.

**Acceptance Scenarios**:

1. **Given** the app was upgraded but the browser still runs the previous
   companion, **When** the companion connects, **Then** the app's connect
   page, the extension popup, and the on-page widget all show an unmissable
   "reload the companion" state instead of a green tick — and no fill is
   ever silently dropped because of the mismatch (any affected field appears
   as needs-attention with the mismatch named as the reason).
2. **Given** I am reading a recognised posting in a tab, **When** I press
   "Apply with Apply Assist" on the widget, **Then** the application fills in
   that same tab; no duplicate tab opens; the widget I pressed shows the live
   progress.
3. **Given** an earlier fill session ended or was abandoned, **When** I press
   "Fill this page" anywhere, **Then** it works immediately — the stale
   session is superseded, never reported as "busy".
4. **Given** a resume attach failed mid-transfer, **When** the fill retries
   moments later, **Then** the attach succeeds (a retry is not punished).
5. **Given** the browser suspends and restarts the extension's background
   worker mid-session, **When** the session continues, **Then** automated
   progression remains armed (it does not silently degrade to fill-only).

---

### User Story 2 - Real application forms actually fill (Priority: P2)

As an applicant on a real Workday, Greenhouse, Lever, or Ashby form, the
fields the page shows are the fields that fill — including custom dropdowns,
and I can see a reason for anything that didn't.

**Why this priority**: The user reported fields, dropdowns, and the resume
not filling on real sites. Five verified scan/fill blind spots cause this;
until they are fixed, escorting (P4) would advance past half-empty pages.

**Independent Test**: A fixture set reproducing each blind spot fills
end-to-end: a field labelled only by referenced text, a form inside a shadow
root, a Workday-style custom menu, a dropdown showing a placeholder choice,
and a form in a fixed-position dialog.

**Acceptance Scenarios**:

1. **Given** a field whose visible question is provided by referenced label
   text (not a wrapping label), **When** the page is scanned, **Then** the
   field's question is captured and it fills like any other field.
2. **Given** an application form rendered inside an open shadow root,
   **When** the page is probed and scanned, **Then** the widget appears and
   the form's fields fill.
3. **Given** a Workday-style custom dropdown whose options are plain
   highlighted rows, **When** the fill runs, **Then** the right option is
   chosen and confirmed.
4. **Given** a dropdown resting on a placeholder choice ("Select…"),
   **When** the page is scanned, **Then** that field counts as unanswered
   and gets filled — not skipped as already-answered.
5. **Given** a form inside a fixed-position dialog, **When** the page is
   scanned, **Then** its fields count as visible and fill.
6. **Given** a custom widget whose surrounding text happens to contain words
   like "next" or "save", **When** the fill needs to operate that widget,
   **Then** the widget itself is judged by its own accessible name and still
   fills (real progression buttons remain protected).

---

### User Story 3 - Sign-in is handled (Priority: P3)

As an applicant hitting a sign-in or create-account wall, the companion shows
up, uses my saved login for that site, signs me in, and on first-time sites
prepares the registration for me — instead of showing nothing.

**Why this priority**: Most Workday applications sit behind an account wall;
today the companion deliberately hides there, which reads as "it does
nothing". Requires P2's labelling work to recognise the wall's fields.

**Independent Test**: On a sign-in fixture with a saved login, the wall is
crossed without any manual click; without a saved login, the widget asks for
one and saves it to the OS credential vault; on a registration fixture the
password pair is generated and filled and the final click is left to me.

**Acceptance Scenarios**:

1. **Given** a page asking me to sign in, **When** the companion probes it,
   **Then** the widget appears in a dedicated sign-in state (today it hides).
2. **Given** a saved login exists for this site, **When** the sign-in state
   engages, **Then** the username/email and password fill from the vault and
   the Sign in control is clicked exactly once, immediately after those
   fills, in that same frame — and I am through the wall.
3. **Given** no saved login exists for this site, **When** the wall is
   detected, **Then** the widget tells me plainly and lets me save one from
   the page; the secret goes only to the OS credential vault, is write-only
   thereafter, and never appears in the app's database, extension storage,
   logs, reports, or the on-page answer list.
4. **Given** the browser's own password manager already filled the login,
   **When** the sign-in state engages, **Then** the prefilled values count as
   satisfied and sign-in proceeds (no stuck "already filled" dead end).
5. **Given** a create-account form (password plus confirmation), **When**
   the fill runs, **Then** both password fields fill with a generated strong
   password which is saved to the vault at that moment, and the widget hands
   me the Create account click with a clear "your turn" prompt — the system
   never clicks it.
6. **Given** a sign-in attempt fails (site shows an error), **When** the
   page re-renders, **Then** the system does not loop retrying the click —
   it pauses to me with the site's error visible.

---

### User Story 4 - Escorted to the door (Priority: P4)

As an applicant, from the posting I press one button and the next time I am
needed is either a question only I can answer, a bot-check, or the final
Review/Submit page — where it parks and hands me the keys.

**Why this priority**: This is the automation the user asked for ("click
continue… clicking apply… automate this"). It is only safe once P1-P3 make
what's on each page true, filled, and signed-in.

**Independent Test**: On a multi-page wizard fixture behind a login wall,
one press escorts through apply → sign-in → two filled steps → parked at the
review page, with the Submit control provably un-clicked; cap, bot-check,
and needs-you fixtures each pause instead of advancing.

**Acceptance Scenarios**:

1. **Given** a recognised posting whose Apply control navigates to the
   application, **When** the session starts, **Then** Apply is clicked for
   me (allowlisted, once) and the application page begins filling.
2. **Given** a wizard step where every visible required field is decided,
   nothing is mid-fill, and nothing needs me, **When** the step has been
   quiet for a moment, **Then** the step's Continue/Next control is clicked
   for me exactly once and the next step fills.
3. **Given** a step with an unanswered question that needs me, **When** the
   escort reaches it, **Then** it pauses, the widget expands showing what's
   needed, and after I answer it continues by itself.
4. **Given** a bot-check (CAPTCHA-class) appears anywhere, **When** it is
   detected, **Then** the session enters a "your turn" state, nothing is
   ever clicked on or near the check, and after I solve it the escort
   resumes.
5. **Given** the page's only remaining progression control is final-class
   (Submit application / Review and submit / bare Submit at the end),
   **When** the escort evaluates it, **Then** it parks in a prominent
   "Review & submit — your turn" state and never clicks it.
6. **Given** a wizard that keeps presenting steps, **When** the automated
   advance count for this job reaches its hard cap, **Then** the escort
   pauses to me rather than advancing further.
7. **Given** the application is on LinkedIn, **When** any session runs
   there, **Then** nothing is ever clicked — filling only.
8. **Given** any automated progression click occurs, **Then** it is recorded
   in the session's activity trail, and app-initiated advances are never
   counted as my own submissions in follow-up tracking.
9. **Given** I turn the escort off (a standing setting, default on) or press
   pause on the widget, **When** a step completes, **Then** nothing is
   clicked and the session behaves like today's fill-only mode.

---

### User Story 5 - The promises match the product (Priority: P5)

As a user reading any surface of the product — the widget footer, the store
description, the manual, the settings page — what it says about clicking
matches what it now does, including that my saved logins will be used to
sign in automatically and that the final Submit is always mine.

**Why this priority**: The old promise ("never clicks — you always do that")
is load-bearing copy in several places; shipping new behavior under old
promises would be worse than either alone.

**Independent Test**: Every surface that stated the old promise states the
new one; the settings page explains auto sign-in where logins are saved; a
release-notes entry describes the change.

**Acceptance Scenarios**:

1. **Given** the new release, **When** I read the widget footer, extension
   description, manual, README, and in-app activity messages, **Then** they
   all state the new contract: it fills, signs in, and advances; I always
   press the final Submit.
2. **Given** the settings page where logins are saved, **When** I read it,
   **Then** it says those logins will be used to sign in automatically
   during Apply Assist, and how to turn the escort off.

---

### Edge Cases

- A wizard that keeps the same address while swapping steps in place: each
  rendered step must still get exactly one advance, keyed by the rendered
  document and its field set — never by the address.
- A mislabelled final control (a terminal Submit dressed as "Continue"): the
  final-class judgment reads the control's full accessible name and type;
  any final-class match refuses the click regardless of allowlist.
- Sign-in fails (wrong saved password): one click per rendered document —
  the re-rendered error page never triggers a second automatic attempt.
- The account already exists when registering: the human is on the click and
  sees the site's message; the generated password saved to the vault is
  overwritten the next time a registration fill runs for that site.
- The browser's service worker dies mid-escort: on revival, arming state and
  the advance count restore; the cap cannot reset by worker death.
- The user starts typing while a step is otherwise complete: a focused field
  blocks the completeness gate (typing always wins; no advance under the
  user's hands).
- Multiple frames on one page: sign-in clicks and advances act only in the
  frame whose fields the system itself just filled.
- A page that is both a posting and a login wall: sign-in state wins until
  the wall is crossed, then normal escort behavior resumes.
- The resume file token expires mid-retry: a fresh scan re-decides the field
  and mints a new transfer, rather than dead-ending.
- CAPTCHA appears after a step was judged complete but before the click
  lands: the click is withheld; bot-check detection outranks completeness.

## Requirements *(mandatory)*

### Functional Requirements

**Trust and state honesty**

- **FR-001**: The system MUST detect an app/companion version mismatch at
  connection time and present it on the app's connect page, the extension
  popup, and the on-page widget, with one-step reload instructions.
- **FR-002**: A version mismatch MUST NOT silently drop any fill; any
  capability withheld due to mismatch MUST surface the affected field as
  needs-attention with the mismatch named, and MUST count on the diagnostics
  page.
- **FR-003**: Starting Apply Assist from a page the user is viewing MUST run
  the session in that same tab; the system MUST NOT open a duplicate tab of
  the same posting.
- **FR-004**: "Fill this page" MUST always be honoured on a fillable page: a
  finished or abandoned prior session is superseded automatically; "busy" is
  only reported while another tab is actively mid-fill, and then it MUST say
  which tab.
- **FR-005**: A failed or interrupted file attach (e.g., the resume) MUST be
  retryable within the same session without manual intervention.
- **FR-006**: Automated-progression arming MUST survive an extension
  background restart within the same session.

**Fill coverage**

- **FR-007**: Field questions MUST be read from all standard labelling
  forms: wrapping/associated labels, direct accessible labels, referenced
  label text, and — when none exist — the nearest enclosing or preceding
  visible label text.
- **FR-008**: Fields, options, and progression controls inside open shadow
  roots MUST be discovered, scanned, filled, and clicked the same as
  light-DOM equivalents.
- **FR-009**: Workday-style custom menus (plain option rows without native
  option semantics) MUST be operable: the right option found, chosen, and
  the result verified.
- **FR-010**: A choice control resting on a placeholder ("Select…" or
  equivalent empty-meaning value) MUST count as unanswered, not as a value
  the user chose.
- **FR-011**: Fields inside fixed- or sticky-positioned containers MUST
  count as visible when actually shown.
- **FR-012**: A fillable widget MUST be judged by its own accessible name
  when deciding whether operating it is safe; surrounding or descendant text
  containing progression words MUST NOT block filling the widget. Real
  progression/submission controls remain protected.
- **FR-013**: Recognition coverage for Workday field identifiers MUST be
  materially expanded so that common Workday profile/contact/source fields
  classify without AI assistance.

**Sign-in and accounts**

- **FR-014**: A page whose form is a credential wall MUST present the
  companion in a dedicated sign-in state (walls are no longer hidden).
- **FR-015**: With a saved login matching the site, the system MUST fill the
  username/email and password from the OS credential vault.
- **FR-016**: The Sign in control MUST be clicked only immediately after the
  system itself filled credentials into that exact frame, exactly once per
  rendered document — never inferred from button text alone, never retried
  on the same rendering.
- **FR-017**: With no saved login for the site, the system MUST say so as a
  needs-attention item and MUST offer saving one from the page; the saved
  secret goes only to the OS credential vault. After a login is saved from
  the page, sign-in MUST proceed in the same session without re-asking.
- **FR-018**: Credential secrets MUST never be stored in the application
  database, extension storage, logs, fill reports, diagnostics, or the
  on-page answer list; saved secrets are write-only after saving.
- **FR-019**: Credentials already filled by the browser's own password
  manager MUST count as satisfied for sign-in purposes.
- **FR-020**: Login identifier fields labelled as username (not only email)
  MUST be recognised on credential walls.
- **FR-021**: On a create-account form, the system MUST generate a strong
  password, fill the password and confirmation fields, save the credential
  to the vault at fill time, and hand the Create account click to the human
  with an explicit prompt; the system MUST NOT click it.

**Escort (automated progression)**

- **FR-022**: On a recognised posting, the system MUST click the allowlisted
  Apply control for the user — including Apply controls that navigate to a
  separate application page — once per rendered document.
- **FR-023**: The system MUST advance a wizard step only when the step is
  complete: every visible required field decided, no fill in flight, zero
  needs-attention items, no focused user input, and a short quiet period
  elapsed.
- **FR-024**: Progression controls MUST be matched allowlist-first per
  supported site, with a conservative generic fallback (exact accessible
  names meaning next/continue/save-and-continue) used only when no allowlist
  matches; any final-class match MUST refuse the click. If a complete step
  yields no clickable progression control at all, the session MUST pause to
  the human with a "your turn" state rather than wait silently.
- **FR-025**: Final-class controls MUST never be clicked: any submission of
  the application in any phrasing, account creation/registration, payment,
  and bot-check widgets.
- **FR-026**: Each rendered step MUST receive at most one automated advance,
  keyed to the rendered document and its field set, not the page address.
- **FR-027**: Automated advances per job MUST stop at a hard cap (12); at
  the cap the session pauses to the human.
- **FR-028**: A detected bot-check MUST pause the session into a "your turn"
  state; the system MUST NOT interact with the check in any way, and MUST
  resume automatically once the human clears it and the page moves on.
- **FR-029**: Needs-attention items MUST pause progression; after the human
  answers, the escort resumes without further action.
- **FR-030**: When the only remaining progression control is final-class,
  the session MUST park in a prominent "Review & submit — your turn" state
  on both the widget and the app.
- **FR-031**: Every automated progression click MUST be recorded in the
  session's activity trail (kind, target description, step, outcome).
- **FR-032**: App-initiated advances MUST NOT be attributed to the user in
  submission follow-up tracking.
- **FR-033**: On LinkedIn, the system MUST NOT click anything; filling
  remains available.
- **FR-034**: The escort MUST be a standing setting (default on) and MUST be
  pausable from the widget during a session; with it off, behavior matches
  fill-only.

**Compatibility and messaging**

- **FR-035**: All protocol changes MUST be additive; a previous-version
  companion MUST still connect and operate at its own level while showing
  the mismatch state (FR-001). The escort MUST NOT arm against a mismatched
  companion — the session behaves as fill-only until the companion is
  reloaded, and the mismatch state says so.
- **FR-036**: Every user-facing promise about clicking MUST be updated to
  the new contract (widget footer, extension description, manual, README,
  in-app activity messages, release notes).
- **FR-037**: The settings surface where logins are saved MUST disclose that
  they are used to sign in automatically during Apply Assist and how to turn
  the escort off.

### Key Entities

- **Saved Login**: A site domain, an identifier (email or username), and a
  secret held only by the OS credential vault; write-only after saving; a
  default login plus per-site overrides.
- **Progression Click Record**: One automated click — its kind (open apply /
  sign in / advance), the control's description, the step it acted on, the
  outcome, and when it happened; part of the session activity trail.
- **Step**: A rendered document plus its set of scanned fields; the unit of
  one-shot advancing and of completeness evaluation.
- **Session State**: The escort's externally visible mode — escorting,
  needs sign-in, your-turn (bot-check), ready-for-review, paused (cap or
  user) — shown consistently on the widget and the app.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the reference wizard behind a login wall with a saved
  login, one button press escorts to the review page with zero manual
  navigation clicks by the user (only flagged questions, if any).
- **SC-002**: A stale companion is flagged on every surface within 5 seconds
  of connecting, and zero fills are silently dropped due to mismatch.
- **SC-003**: "Apply with Apply Assist" fills the tab it was pressed in, in
  100% of runs; duplicate tabs occur zero times across the suites.
- **SC-004**: Every field on the blind-spot fixture set (referenced labels,
  shadow root, custom menus, placeholder choices, fixed dialogs) is either
  filled or listed with a stated reason — zero silent misses.
- **SC-005**: Credential walls show an actionable companion state in 100% of
  fixture runs; with a saved login, the wall is crossed with zero user
  clicks.
- **SC-006**: The final Submit is clicked zero times across all automated
  suites and manual verification.
- **SC-007**: Bot-check fixtures show the pause state in 100% of runs with
  zero interactions with the check.
- **SC-008**: From pressing Apply on the reference posting to the
  ready-for-review park takes under 2 minutes, excluding time waiting on
  the human.
- **SC-009**: Zero occurrences of any credential secret outside the OS
  vault across a full instrumented run (database, storage, logs, reports,
  page, diagnostics all grepped clean).

## Assumptions

- Single user automating their own job applications with their own accounts
  on their own machine; volume is human-scale (a queue the user curated).
- The OS credential vault (Windows Credential Manager / macOS Keychain) is
  available; it is the only place secrets rest.
- Bot checks are never bypassed or automated — pausing to the human is the
  designed behavior, not a limitation to engineer around.
- Email verification during account creation belongs to the human and may
  interrupt an escort; the session parks accordingly.
- iCIMS and other unlisted ATSs receive only the conservative generic
  fallback this release; LinkedIn receives no clicks at all.
- The truthful-fill answer semantics (refusal contract, answer-shape rules)
  from v1.7.0 are unchanged; this feature changes reach, not honesty.
- The existing fill-only Playwright fallback path keeps today's behavior
  (user advances manually); the escort applies to the companion path.
