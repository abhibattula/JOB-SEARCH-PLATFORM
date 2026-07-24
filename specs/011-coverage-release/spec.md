# Feature Specification: The Coverage Release — fill the fields the assistant can't yet

**Feature Branch**: `011-coverage-release`
**Created**: 2026-07-24
**Status**: Draft
**Input**: User description: "Raise Apply Assist's fill coverage on harder application pages — custom dropdowns, typeaheads, and the Workday/iCIMS/Taleo ATS families — by allowing the companion to click a field's own widget to set a value, while a hard denylist keeps it from ever clicking submit/apply/next/login. One free v1.1.0 release."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Custom dropdowns fill themselves (Priority: P1)

Many applications use "fancy" dropdowns that look like a box you click open,
not a plain menu — for work authorization, sponsorship, EEO questions, "how
did you hear about us", years of experience, and similar. Today Apply Assist
leaves every one of these for the user to do by hand. In this release, the
assistant sets them the same way it fills a text box: it opens the dropdown,
picks the option that matches the user's saved answer, and confirms the
value took — then moves on. If it can't find a matching option, it leaves
the field alone and reports it for manual attention, exactly as before.

**Why this priority**: Custom dropdowns are the single largest "left for you
to do" bucket across every ATS, including the ones already supported. Making
them fill lifts real coverage on applications the user already runs today.

**Independent Test**: On a page with a custom (non-native) dropdown, start
Apply Assist and confirm the dropdown ends up showing the user's saved value
(e.g. work authorization), with the field reported as filled — and that a
dropdown with no matching option is reported "fill manually", untouched.

**Acceptance Scenarios**:

1. **Given** a custom dropdown whose options include the user's saved answer,
   **When** Apply Assist runs, **Then** the dropdown displays that answer and
   the field is reported filled.
2. **Given** a custom dropdown whose options do NOT include any form of the
   user's answer, **When** Apply Assist runs, **Then** the dropdown is left
   untouched and reported "fill manually" (never a wrong or guessed option).
3. **Given** a custom dropdown the user has already set, **When** Apply
   Assist runs, **Then** it is left as the user set it (non-empty is sacred).
4. **Given** any page, **When** the assistant operates a dropdown, **Then**
   it only clicks that dropdown and its options — never a submit, apply,
   next, continue, save, finish, login, register, or pay control.

---

### User Story 2 - Workday applications fill (Priority: P1)

The user's target hardware employers (NVIDIA, AMD, Qualcomm, Intel) post on
Workday, where today the assistant fills almost nothing. In this release,
Workday's standard fields — legal name, email, phone, address, source/"how
did you hear", work authorization, and the location/school suggestion boxes —
fill from the user's profile and answer bank. Workday applications span
several pages; the user clicks Workday's own "Next"/"Continue" between pages
(the app never does), and each new page fills as it appears.

**Why this priority**: Workday is where the user's most-wanted employers
live, and it is currently the emptiest experience. This is the release's
headline coverage win.

**Independent Test**: On a Workday-style application, start Apply Assist and
confirm the standard identity/contact fields and at least one custom
dropdown and one suggestion box (typeahead) fill; advance to the next page
yourself and confirm the new page's fields fill too; confirm the app never
clicks Workday's Next/Continue.

**Acceptance Scenarios**:

1. **Given** a Workday application page, **When** Apply Assist runs, **Then**
   the recognized identity and contact fields fill from the profile.
2. **Given** a Workday location or school box that shows suggestions as you
   type, **When** Apply Assist runs, **Then** it enters the value and selects
   the matching suggestion.
3. **Given** a multi-page Workday application, **When** the user clicks
   Workday's own Next, **Then** the following page's fields fill on their own;
   the app never advances the wizard itself.
4. **Given** a Workday page with a "Next"/"Continue"/"Submit" control,
   **Then** the app never clicks it.

---

### User Story 3 - iCIMS and Taleo applications fill (Priority: P2)

Many established companies use older ATS platforms (iCIMS, Taleo). Their
standard fields should fill like the already-supported boards do, so the
assistant is useful across the breadth of postings the user actually finds —
not only on the three modern ATS.

**Why this priority**: Broadens usefulness across mid-size and established
employers; lower effort than Workday since these are mostly standard forms.

**Independent Test**: On an iCIMS-style and a Taleo-style application, start
Apply Assist and confirm the standard identity/contact fields fill.

**Acceptance Scenarios**:

1. **Given** an iCIMS application, **When** Apply Assist runs, **Then** the
   recognized standard fields fill.
2. **Given** a Taleo application, **When** Apply Assist runs, **Then** the
   recognized standard fields fill.

---

### User Story 4 - Same coverage whether or not the companion is connected (Priority: P2)

The new fill abilities work in the user's own browser (via the companion)
AND in the fallback assistant window, so a user without the companion is not
left behind on the harder fields.

**Why this priority**: Preserves the "fallback loses nothing" promise from
the previous release; a user who declined the companion still benefits.

**Independent Test**: With the companion disconnected, run Apply Assist on a
custom-dropdown page in the assistant window and confirm the dropdown fills
the same way it would with the companion.

**Acceptance Scenarios**:

1. **Given** the companion is not connected, **When** Apply Assist fills a
   custom dropdown in the assistant window, **Then** it fills the same value,
   with the same never-click-submit guarantee.

---

### Edge Cases

- A control that is styled as a dropdown option but is actually a submit/next
  button (or contains one): the app must never click it — the denylist wins
  over "looks fillable".
- A dropdown that opens but never renders options (broken/slow widget): the
  app waits briefly, then leaves the field and reports "fill manually",
  closing any popup it opened so the page is not left in a stuck state.
- A typeahead that returns no suggestion matching the user's value: left
  untouched, reported "fill manually" — never a partial/wrong pick.
- The user is actively interacting with a dropdown when the assistant scans:
  the assistant does not touch a field the user is engaging with.
- A disabled Next/Submit control: still never clicked (disabled or not).
- A custom dropdown whose options are only revealed after typing (combobox +
  typeahead hybrid): treated as a typeahead.
- Multi-select custom widgets: out of scope for this release; reported "fill
  manually" rather than half-filled.
- A page the assistant genuinely cannot read (e.g. a site that blocks
  automated interaction): it fills what it can and leaves the rest, never
  attempting to defeat the protection.

## Requirements *(mandatory)*

### Functional Requirements

**Safe interaction (the enabling change)**

- **FR-001**: The assistant MUST be able to click a form field's OWN
  interactive parts — a dropdown's control and its option list, or a
  typeahead's suggestion — for the sole purpose of setting that field's
  value.
- **FR-002**: The assistant MUST NEVER click a control that submits, applies,
  advances (next/continue), saves, finishes, logs in, registers, creates an
  account, or pays — identified by the control's visible text, type, and
  role — regardless of how the page is styled. This MUST hold in every fill
  path (the user's own browser and the fallback assistant window) and be
  guaranteed by automated test.
- **FR-003**: Every field-value fill MUST still honor the existing
  guarantees: a non-empty field is never overwritten, a field the user is
  interacting with is never touched, nothing is ever auto-submitted, and the
  application is never advanced to the next page by the app.

**Custom dropdowns & typeaheads (US1, US2)**

- **FR-004**: For a custom (non-native) dropdown, the assistant MUST select
  the option matching the user's saved value and confirm the field's
  displayed value changed; on no match or if the value does not take, it MUST
  leave the field untouched and report it "fill manually", never selecting a
  non-matching option.
- **FR-005**: For a typeahead/suggestion box, the assistant MUST enter the
  value and select the matching suggestion; on no matching suggestion it MUST
  leave the field and report "fill manually".
- **FR-006**: When a dropdown is opened but yields no usable options within a
  short wait, the assistant MUST abandon the field, close the popup, and
  report "fill manually" — never leaving the page in an opened/stuck state.

**ATS coverage (US2, US3)**

- **FR-007**: The assistant MUST recognize and fill the standard identity and
  contact fields on Workday applications (name, email, phone, address, and
  the source/"how did you hear" and work-authorization selectors), including
  Workday's location/school suggestion boxes.
- **FR-008**: The assistant MUST keep filling across the pages of a
  multi-page Workday application as each page appears after the user advances
  it; the app MUST NOT advance the wizard.
- **FR-009**: The assistant MUST recognize and fill the standard identity and
  contact fields on iCIMS and Taleo applications.
- **FR-010**: Custom dropdowns MUST fill on the already-supported boards
  (Greenhouse, Lever, Ashby) too, not only on the new ATS.

**Parity & continuity (US4, cross-cutting)**

- **FR-011**: All new fill abilities (custom dropdowns, typeaheads, the new
  ATS) MUST work identically whether filling happens in the user's own
  browser or the fallback assistant window.
- **FR-012**: All prior capabilities MUST continue to work unchanged: native
  fields and native dropdowns, file/resume upload, AI drafts for open-ended
  questions, the pause-for-review flow for unrecognized/sensitive questions,
  saved-login fill, the live activity feed, and per-job fill reports.
- **FR-013**: Visa/sponsorship/EEO questions MUST remain confirm-gated and
  never AI-drafted, even when presented as a custom dropdown.
- **FR-014**: The per-job report and batch summary MUST reflect the new
  fills, and the user MUST be able to see how many recognized fields were
  filled versus left for manual attention.

**Governance**

- **FR-015**: The project's governing principles MUST be clarified in writing
  to record that the assistant may click a field's own widget to set a value,
  while submit/apply/next/login controls remain never-clicked — so the new
  behavior is a documented, bounded rule, not a silent change.

### Key Entities

- **Field widget kind**: how a field is operated — native input, native
  dropdown, custom dropdown, or typeahead — which determines how the
  assistant sets its value.
- **Click safety verdict**: for any element the assistant might click, a
  yes/no on whether it is a field-value control (allowed) or a submit-class
  control (forbidden), derived from the element's text, type, and role.
- **Fill outcome**: unchanged vocabulary (filled, kept your value, no match,
  fill manually) now also produced for custom dropdowns and typeaheads.
- **ATS profile**: the per-platform recognition rules (Workday, iCIMS, Taleo,
  plus the existing Greenhouse/Lever/Ashby) that map a page's fields to the
  user's data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a representative Workday-style application, the number of
  fields the assistant fills increases from near-zero (today) to the majority
  of the standard identity/contact/selector fields on the page.
- **SC-002**: A custom dropdown whose options include the user's saved answer
  is filled correctly in at least 9 of 10 attempts on the test pages; one
  whose options do not match is never filled with a wrong option (0
  incorrect fills).
- **SC-003**: Across the full test suite and a live check, the assistant
  clicks a submit/apply/next/continue/save/login control **zero** times — no
  exceptions — including on pages where such a control is styled to look like
  a dropdown option.
- **SC-004**: A typeahead box with a matching suggestion is filled correctly;
  one with no matching suggestion is left untouched (no partial value).
- **SC-005**: Every new fill ability produces the same result in the user's
  own browser and in the fallback assistant window (parity verified on the
  same test pages).
- **SC-006**: All previously working fills (native fields, native dropdowns,
  file upload, AI drafts, saved-login, pause-for-review) continue to pass
  their existing checks with no regressions.
- **SC-007**: The release remains $0 (no new paid service, no store or
  signing fee) and fully offline-capable.

## Assumptions

- "Fill more, on harder sites" was the user's chosen direction for this
  release; custom dropdowns, Workday, iCIMS/Taleo, and depth on the existing
  ATS are all in scope (user selection, 2026-07-24).
- The user accepted allowing field-value-only clicks with a submit denylist
  (user selection, 2026-07-24); the never-auto-submit / never-auto-login /
  never-bypass-bot-protection rules are unchanged.
- Workday exposes stable per-field identifiers that make its fields
  reliably addressable across employers; where a specific employer deviates,
  those fields degrade gracefully to "fill manually".
- Sites that actively block automated interaction (e.g. bot-protected pages)
  are out of scope to "make work" — the assistant fills what it can and
  leaves the rest, never attempting to defeat protection.
- Multi-select custom widgets, discovery overlays, Chrome Web Store
  publishing, code signing, and scanned-image resume OCR are explicitly out
  of scope for this release.
- The existing test harnesses (unit, real-browser extension suite against
  local fixture pages, offline model gate, frozen smoke) remain the
  regression baseline; this release adds fixture pages and tests for the new
  widget/ATS cases.
