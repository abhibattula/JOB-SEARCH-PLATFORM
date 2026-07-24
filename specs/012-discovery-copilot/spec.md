# Feature Specification: The Discovery Copilot

**Feature Branch**: `012-discovery-copilot`  
**Created**: 2026-07-24  
**Status**: Draft  
**Input**: User description: "Surface the job engine's scoring and sponsorship intelligence at DISCOVERY time, in the browser — an auto-appearing floating badge on any job posting the user browses (LinkedIn, Indeed, Greenhouse/Lever/Ashby, company career pages) showing their match score, an H-1B sponsorship flag, and a one-click Save to Job Engine. Detection via schema.org JobPosting JSON-LD plus LinkedIn/Indeed DOM extractors; scoring done on demand by the local app over the existing companion bridge, reusing the offline match scorer and sponsorship intelligence. Read-only, separate from and non-interfering with Apply Assist's fill flow."

## Clarifications

### Session 2026-07-24

- Q: When the app is closed / companion disconnected, what should the badge do on a job page? → A: Show nothing — the badge only ever appears after a score returns; zero footprint when the app isn't running (reinforces FR-006).
- Q: When the user clicks "Save to Job Engine", how is the job recorded? → A: Mark it as "saved" (not just added to the feed) so it appears in the Saved/bookmarked view, matching the explicit save intent (refines FR-008).
- Q: How deep should the sponsorship lookup go for a browsed company not already in the feed? → A: Two-tier on-demand — instant lookup of the already-graded company; on a miss, an on-demand fuzzy match against the bundled USCIS H-1B records so even brand-new companies get a grade; "unknown" only when there is genuinely no evidence (refines FR-004).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See my match + sponsorship on any job I browse (Priority: P1)

While browsing a job posting on LinkedIn, Indeed, a Greenhouse/Lever/Ashby
board, or a company career page, the user sees a small badge appear that tells
them, at a glance, how well the role matches their resume and whether the
company has a track record of sponsoring H-1B visas — without leaving the page
or copying anything into the app.

**Why this priority**: This is the core value — turning the app's existing
scoring and sponsorship intelligence into an at-a-glance signal exactly when
the user is deciding whether a posting is worth their limited time. It is the
minimum that makes the feature worth shipping; everything else builds on it.

**Independent Test**: With the app running and the companion connected, open a
job posting that exposes schema.org JobPosting data (or a LinkedIn/Indeed
posting). Confirm the badge appears showing a numeric match score and a
sponsorship indicator for the correct company, and that it disappears/does not
appear on pages that are not job postings.

**Acceptance Scenarios**:

1. **Given** the app is running, the companion is connected, and the user has a
   resume/profile saved, **When** the user opens a job posting page that
   publishes JobPosting metadata, **Then** a floating badge appears showing the
   role's match score against the user's resume and a sponsorship flag for the
   posting's company.
2. **Given** the same setup, **When** the user opens a LinkedIn job-view page or
   an Indeed job page (which may not publish clean JobPosting metadata), **Then**
   the badge still appears with the correct role title, company, match score, and
   sponsorship flag.
3. **Given** the company has no reliable sponsorship record, **When** the badge
   renders, **Then** the sponsorship flag reads as "unknown" rather than showing
   a fabricated grade.
4. **Given** the user has not saved a resume/profile yet, **When** the badge
   renders, **Then** it shows an honest "add your resume to see your match"
   state instead of a misleading score.
5. **Given** the user is on a page that is not a job posting, **When** the page
   loads, **Then** no badge appears.

---

### User Story 2 - Save a job to the engine in one click (Priority: P2)

From the badge, the user can add the posting they are viewing to their Job
Engine feed/tracker with a single click, so promising roles they find while
browsing are captured in the same place they manage every other application —
no manual copy-paste of title, company, or link.

**Why this priority**: Seeing the score is valuable, but the payoff is capturing
the good ones into the pipeline the user already works from. It depends on US1
(the badge must exist first) but delivers the "one-stop destination" promise.

**Independent Test**: With the badge showing on a job posting, click Save;
confirm the posting appears in the app's feed/tracker as a saved job with the
correct title, company, and link, and that clicking Save again (or reopening the
same posting) reflects an "already saved" state rather than creating a
duplicate.

**Acceptance Scenarios**:

1. **Given** the badge is showing on a job posting, **When** the user clicks
   "Save to Job Engine", **Then** the posting is added to the user's feed/tracker
   with its title, company, and URL, and the badge confirms it was saved.
2. **Given** a posting the user already saved (via the badge or already present
   in the feed), **When** the badge renders for that posting, **Then** it shows
   an "already saved" state and saving again does not create a duplicate entry.
3. **Given** a saved posting, **When** the user opens the app's feed/tracker,
   **Then** the saved job is visible and behaves like any other saved job
   (can be opened, marked applied, etc.).

---

### User Story 3 - Stay out of the way, always (Priority: P3)

The badge respects the user's browsing: it can be collapsed or dismissed, never
covers the page's own buttons or the actual job content, and never touches the
page (no clicking, typing, or submitting on the user's behalf). It coexists with
Apply Assist without interfering when the user later goes to fill an application.

**Why this priority**: Trust and non-intrusiveness are what separate a helpful
copilot from adware. This story hardens the experience but is not required to
demonstrate the core value, so it is P3.

**Independent Test**: Confirm the badge can be dismissed and collapsed, does not
overlap page controls, takes no action on the page itself, and that starting an
Apply Assist fill on the same or another tab still works exactly as before.

**Acceptance Scenarios**:

1. **Given** the badge is visible, **When** the user dismisses it, **Then** it
   disappears for that posting and does not obstruct any page content or controls.
2. **Given** the badge is visible, **When** the user collapses it, **Then** it
   shrinks to a minimal indicator that can be re-expanded.
3. **Given** the discovery badge is active on a page, **When** the page is
   inspected for actions taken by the companion, **Then** no clicks, form input,
   or submissions were performed by the companion on that page.
4. **Given** an Apply Assist fill session is running, **When** the discovery
   badge is also present, **Then** neither disrupts the other (fills complete
   normally; the badge still scores/saves normally).

---

### Edge Cases

- **App not running / companion not connected**: no score can be produced, so no
  badge appears (the badge only renders once a score comes back) — the page is
  left untouched.
- **Company name is ambiguous or absent** (e.g., "Confidential" postings): the
  match score still renders from title + description; the sponsorship flag reads
  "unknown".
- **Page updates in place** (single-page navigation between postings, e.g.,
  scrolling LinkedIn's job list): the badge re-detects the new posting and
  refreshes its score/company rather than showing stale data.
- **Very large job descriptions**: the extracted text is bounded before it is
  sent to the app so a page cannot overwhelm the bridge.
- **Duplicate/repeat visits**: re-opening a posting already in the feed shows
  "already saved"; saving never creates duplicates.
- **Non-posting pages that happen to embed JobPosting-like data**: only genuine
  single-posting pages show a badge; search-result lists and unrelated pages do
  not.
- **Multiple job-related structured-data blocks on one page**: the first genuine
  posting is used; the badge never shows more than one score at a time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect when the page the user is viewing is a
  single job posting, using published structured job metadata as the primary
  signal and dedicated recognition for LinkedIn and Indeed postings as a
  fallback.
- **FR-002**: The system MUST extract the posting's role title, company name,
  job description text, and the posting URL from the current page for scoring and
  saving.
- **FR-003**: The system MUST compute the user's match score for the detected
  role against their saved resume/profile, using the app's existing offline
  scoring so no paid service or API key is required.
- **FR-004**: The system MUST determine an H-1B sponsorship indicator for the
  posting's company from the app's existing sponsorship intelligence, using a
  two-tier on-demand lookup: first an instant lookup of the company if it is
  already graded, then — on a miss — an on-demand fuzzy match against the
  bundled H-1B records so a brand-new company can still be graded. The indicator
  is a letter grade when there is sufficient evidence, a cap-exempt likelihood
  signal where applicable, and "unknown" when evidence is genuinely insufficient
  — never a fabricated grade.
- **FR-005**: The system MUST display the match score and sponsorship indicator
  in a floating on-page badge, together with the detected role title and company.
- **FR-006**: The badge MUST appear only when the app is running and connected
  and only after a score has been returned; on any page where no posting is
  detected, or when no score is available, no badge is shown.
- **FR-007**: Users MUST be able to save the currently detected posting to their
  Job Engine feed/tracker with a single action from the badge.
- **FR-008**: The system MUST record a saved posting as a tracked job (title,
  company, URL, description) that appears in the feed/tracker alongside jobs from
  every other source, and MUST mark it as "saved" so it also appears in the
  user's Saved/bookmarked view (matching the explicit save intent).
- **FR-009**: The system MUST NOT create a duplicate when a posting that already
  exists in the feed is saved again, and MUST reflect an "already saved" state
  for such postings.
- **FR-010**: The badge MUST be dismissable and collapsible, and MUST NOT cover
  the page's own controls or the job content.
- **FR-011**: The discovery capability MUST be strictly read-only with respect to
  the browsed page: it MUST NOT click, type into, submit, or otherwise modify the
  page — it only reads visible posting metadata and renders its own badge.
- **FR-012**: The system MUST send the extracted posting metadata only to the
  user's local app over the existing authenticated companion channel, and never
  to any external/off-machine service.
- **FR-013**: The discovery capability MUST operate independently of Apply
  Assist's fill flow — it MUST NOT alter, pause, or depend on an active fill
  session, and an active fill session MUST NOT be affected by discovery.
- **FR-014**: The system MUST refresh the badge when the viewed posting changes
  within the same page (in-place navigation), so the score and company always
  reflect the posting currently on screen.
- **FR-015**: The system MUST re-use the existing companion pairing/authentication
  — discovery introduces no new trust boundary and no new stored secrets.
- **FR-016**: The system MUST handle the "no resume/profile yet" case by showing
  an honest prompt to add a resume rather than a misleading or zero score.
- **FR-017**: Sensitive-question handling is out of scope for discovery — the
  discovery capability MUST NOT read, infer, or fill visa/EEO answers; it only
  scores and saves.

### Key Entities *(include if feature involves data)*

- **Detected Posting**: the job the user is currently viewing, as read from the
  page — role title, company name, description text, and source URL. Transient;
  it exists only to be scored and (optionally) saved.
- **Discovery Result**: the app's response for a detected posting — the match
  score and a short band label, the company sponsorship indicator (grade /
  cap-exempt likelihood / unknown), and whether the posting is already saved.
- **Saved Job (manual source)**: a Detected Posting the user chose to keep,
  persisted as a tracked job in the feed with a source that marks it as
  user-captured while browsing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a job posting that publishes standard job metadata, the badge
  appears with a match score and sponsorship indicator within 2 seconds of the
  page settling, with the app running and connected.
- **SC-002**: Across a representative set of postings on LinkedIn, Indeed, and at
  least one structured-data board (Greenhouse/Lever/Ashby or a company career
  page), the correct role title and company are shown in at least 9 of 10 cases.
- **SC-003**: The sponsorship indicator never displays a letter grade for a
  company without sufficient evidence — such companies show "unknown" 100% of the
  time.
- **SC-004**: Saving a posting from the badge results in that job appearing in
  the feed/tracker with correct title, company, and link in 100% of successful
  saves, and repeat saves of the same posting produce zero duplicates.
- **SC-005**: The discovery capability performs zero page actions (no clicks,
  input, or submissions) on the browsed page, verified by inspection, in 100% of
  sessions.
- **SC-006**: Running Apply Assist on a page while the discovery badge is present
  produces the same fill outcomes as without it (no regression in existing fill
  behavior).
- **SC-007**: No posting metadata leaves the user's machine — all scoring happens
  locally with no external network calls attributable to discovery.

## Assumptions

- The user runs the local app and has installed/connected the browser companion
  (same prerequisite as Apply Assist); discovery does nothing when disconnected.
- The user has, ideally, saved a resume/profile so a meaningful match can be
  computed; if not, the badge prompts them to add one.
- The primary detection signal is standard published job metadata; LinkedIn and
  Indeed get dedicated recognition because they are the highest-traffic boards
  that do not always publish it cleanly. Other boards are covered opportunistically
  via the standard metadata signal.
- Match scoring reuses the app's existing offline scorer and sponsorship
  intelligence unchanged; this feature adds no new scoring model and requires no
  cloud key.
- Saved jobs reuse the existing feed/tracker storage and dedup behavior; a job
  captured while browsing is a normal tracked job distinguished only by its
  source label.
- Detection targets single-posting pages; search-result lists and non-job pages
  are intentionally excluded.
- "One-stop destination, free of cost" remains a hard product constraint: no new
  paid dependencies, no off-machine data flow.
