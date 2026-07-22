# Feature Specification: Launch Release

**Feature Branch**: `008-launch-release`
**Created**: 2026-07-22
**Status**: Draft
**Input**: User description: "Launch Release (v0.8.0): make the app launch-ready by fixing the desktop shell (text selection, clipboard, external links, downloads), rebuilding Apply Assist's browser layer to drive the user's installed Edge/Chrome with visible per-failure reasons and a preflight, sourcing genuine fresh jobs (14-day default window end-to-end, dead-posting delisting, 300+ curated company ATS boards, editable watchlist, Google Jobs, LinkedIn opt-in + link-out, profile-driven search terms), auto-filling the profile identity fields from the uploaded resume with consent gates, upgrading AI tiers (strict-JSON cloud model for extraction, grammar-constrained local decoding, embeddings pre-ranking stage) and adding true in-app self-update (download + silent install + relaunch) with installer hardening, a Diagnostics page, What's New screen, feed sort/pagination fixes, and a frozen-shell release gate."

Approved design doc: `docs/superpowers/specs/2026-07-22-feature-008-design.md`
(root causes confirmed by the 2026-07-22 audit with file:line evidence).

## Clarifications

### Session 2026-07-22

- Q: Which version was the user running when reporting the defects? → A:
  v0.7.0 (footer-confirmed) — all complaints are real defects in the
  shipped desktop shell and defaults, not a stale install.
- Q: Apply Assist browser engine? → A: Drive the user's installed
  Edge/Chrome (isolated app profile); remove the downloaded-browser flow
  entirely.
- Q: LinkedIn posture given $0 rate-limit reality? → A: Opt-in scraping
  with explicit warning + always-available "Search on LinkedIn" link-outs.
- Q: Release shape? → A: One v0.8.0 launch release containing everything.
- Defaults adopted without further questions (project precedent: core
  scoring assets are bundled, opt-in assets are downloaded): the semantic
  ranking model ships in the installer; the obsolete downloaded-Chromium
  directory is left on disk with a "reclaim space" cleanup offered in
  Diagnostics; delisted jobs stay visible only in the "all" window with a
  delisted badge.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apply Assist that visibly works or visibly explains (Priority: P1)

The user selects saved jobs and clicks Start. A real, visible browser window
opens using the browser already installed on their computer — no separate
multi-hundred-megabyte download step exists anymore. Each job's application
page opens and recognized fields are filled. When anything goes wrong (the
browser can't launch, a page won't load, a form can't be read), the user sees
a specific, honest reason and a suggested next action — never a silent
nothing, never a message claiming a window is open when none is.

**Why this priority**: This is the user's most severe complaint ("total
waste"; three versions of clicking Start with no browser and no explanation).
The confirmed defects are (a) a first-use browser download whose failure is
never surfaced, and (b) launch errors silently reclassified as "manual
completion needed."

**Independent Test**: In the installed desktop app with no prior Apply
Assist setup, save two jobs, click Start, and observe a visible browser
window open and fields fill on the first page. Then simulate a failure
(e.g., no supported browser found) and observe a specific error with a
recovery hint instead of a silent no-op.

**Acceptance Scenarios**:

1. **Given** a fresh install where the user has never used Apply Assist,
   **When** they start a queue of saved jobs, **Then** a visible browser
   window opens within seconds using the machine's installed browser, with
   no separate download step required first.
2. **Given** the browser layer cannot start (no supported browser found or
   launch error), **When** the user clicks Start, **Then** the queue does
   not pretend to run: the user sees the actual failure reason and a
   suggested fix, and a preflight check is available from the app.
3. **Given** a job whose page loads but whose fields cannot be read,
   **When** the fill pass runs, **Then** the job is marked "needs manual
   completion" with the *reason class* shown (page unreadable), distinct
   from "browser failed to launch" or "page failed to load".
4. **Given** an active queue, **When** the user closes the browser window
   mid-run, **Then** the app reports the interruption and offers Resume, as
   today — unchanged behavior, now on the new browser layer.
5. **Given** any Apply Assist session, **When** the final submit or any
   login button is reached, **Then** the app never clicks it — the user
   always performs the final action (unchanged constitutional rule, stated
   plainly in the UI).

---

### User Story 2 - A desktop window the user can trust (Priority: P2)

Inside the installed desktop app, the user can select and copy any text
(job titles, error messages, cover letters), copy a job's apply link with
one click, open any posting in their normal system browser, and download
the PDFs the app generates. Every copy/open action confirms visibly that it
happened.

**Why this priority**: Confirmed audit findings show text selection is
disabled app-wide, all three copy buttons fail silently, external links are
version-dependent no-ops, and PDF downloads are blocked — in the shipped
desktop shell only. These bugs make v0.7.0's features invisible, which is
why the user reported "no updates or progress."

**Independent Test**: In the installed desktop app (not a dev browser):
select and copy a job title with the mouse; click Copy link on a feed row
and paste the URL elsewhere; click Open posting and see the system browser
open; download a tailored resume PDF. Each action shows a confirmation.

**Acceptance Scenarios**:

1. **Given** any page in the desktop app, **When** the user drags to select
   text, **Then** the text highlights and Ctrl+C copies it.
2. **Given** a job row or job detail page, **When** the user clicks "Copy
   link", **Then** the job's apply URL is on the clipboard and a toast
   confirms it; if copying fails, a toast says so.
3. **Given** a job detail page in the desktop shell, **When** the user
   clicks "Open posting", **Then** the posting opens in the system default
   browser.
4. **Given** a tailored resume exists, **When** the user clicks the PDF
   download link in the desktop shell, **Then** the file is saved to disk.
5. **Given** the update banner or any external link (e.g., the AI key
   signup page), **When** clicked inside the shell, **Then** it opens in
   the system browser — no dead clicks anywhere.

---

### User Story 3 - Genuine, fresh, sortable job feed (Priority: P3)

The feed shows real, recent postings — sourced primarily from companies'
own career boards — defaulting to the last 14 days. Postings that have been
closed or removed disappear or are flagged. The user can sort by match
score or posted date with one click, page through results beyond the first
hundred, and see clearly which source each job came from. LinkedIn is
reachable via honest one-click search links (and optional scraping with a
clear rate-limit warning).

**Why this priority**: "Genuine and real latest" postings and sorting were
explicit demands. Audit confirmed: no 14-day window exists, dead postings
linger up to 45 days, search volume knobs are hardcoded, and sort exists
but is hidden behind a manual Apply click that also loses filters.

**Independent Test**: Refresh, then confirm the default view shows only
jobs posted within 14 days; change sort to "newest" and see the order flip
immediately without losing active filters; verify a posting removed from
its company board no longer appears as active; click "Search on LinkedIn"
and see a relevant LinkedIn search open in the system browser.

**Acceptance Scenarios**:

1. **Given** default settings after this release, **When** the feed loads,
   **Then** it shows jobs from a 14-day window, and postings fetched from
   job boards older than 14 days are not ingested as new.
2. **Given** a job that disappeared from its company career board,
   **When** the next refresh completes, **Then** the job is marked
   delisted and excluded from the default view (saved/applied jobs keep
   their history but show the delisted flag).
3. **Given** any combination of active filters, **When** the user changes
   the sort selector, **Then** the new order applies immediately and no
   filter is lost; window/view switches likewise preserve all filters.
4. **Given** more results than one page, **When** the user reaches the end
   of the list, **Then** next/previous controls let them see every result.
5. **Given** the shipped company watchlist, **Then** it contains at least
   300 companies whose career boards are fetched directly, and the user can
   add or remove companies from Settings without editing files.
6. **Given** a job title or the user's own search terms, **When** the user
   clicks "Search on LinkedIn", **Then** a LinkedIn job search for those
   terms opens in the system browser; LinkedIn scraping remains available
   as an opt-in with an explicit warning about rate limits.
7. **Given** a job whose true posted date is unknown, **Then** the feed
   marks its date as approximate instead of silently presenting the date
   it was first seen as the posted date.

---

### User Story 4 - Profile fills itself; search follows the profile (Priority: P4)

Uploading a resume fills the profile: not just skills and resume sections,
but name, email, phone, LinkedIn/portfolio links, and location — with the
user's consent before anything they typed is overwritten. The search terms
used to find jobs are derived from the resume and profile, are visible and
editable on the Profile page, and the user's target locations actually
steer where jobs are searched.

**Why this priority**: The user asked for the profile to be "capable of
filling all fields according to my resume" and for search to follow it.
Audit confirmed identity fields are 100% manual and search terms are
hardcoded constants unaffected by the profile.

**Independent Test**: Upload a resume into an empty profile and see
identity fields populate; type a custom phone number, re-upload, and
confirm the app asks before replacing it; edit the derived search terms on
the Profile page, refresh, and confirm the new terms drive the search.

**Acceptance Scenarios**:

1. **Given** an empty profile, **When** the user uploads a resume, **Then**
   name, email, phone, link URLs, and location found in the resume populate
   the corresponding blank fields, and skills/sections populate as today.
2. **Given** a profile field the user previously typed, **When** a new
   resume upload extracts a different value, **Then** the app asks
   keep-or-replace instead of overwriting silently.
3. **Given** no AI key and no local AI model, **When** a resume is
   uploaded, **Then** contact details are still extracted using built-in
   pattern matching (email/phone/links), so auto-fill works on every tier.
4. **Given** a saved profile with resume sections, **Then** the Profile
   page shows the derived search terms (from titles/skills), editable and
   capped in count, with a note that these drive the job search.
5. **Given** edited search terms and target locations, **When** the next
   refresh runs, **Then** searches use those terms and locations; with an
   empty profile the current built-in defaults are used unchanged.
6. **Given** any resume upload, **Then** work-authorization/visa fields are
   never auto-filled without explicit per-field confirmation.

---

### User Story 5 - Updates from inside the app, and visible progress (Priority: P5)

The app checks for updates on its own (quietly, at most once a day), shows
a banner when a new version exists, and — on the user's click — downloads
the installer with a progress bar, verifies it, installs silently, and
relaunches the updated app. After any update, a "What's New" screen shows
exactly what changed. A Diagnostics page lets the user (and support) see at
a glance whether the AI model, PDF engine, browser layer, and job sources
are healthy, and export logs.

**Why this priority**: "When I check for updates I should be able to
download and update from the app itself" — today the updater is a
hyperlink that doesn't even open in the shell. "I don't see any updates or
progress" — there is no What's New surface. Both are launch-blockers for a
final version.

**Independent Test**: On a machine running the previous version, trigger
the update check, click Update, watch download progress, and confirm the
app relaunches at the new version showing a What's New screen. Open
Diagnostics and run all self-tests.

**Acceptance Scenarios**:

1. **Given** a newer release exists, **When** the app starts (throttled to
   once daily) or the user clicks Check for updates, **Then** a banner
   shows the new version with an Update button; offline, the check stays
   silent.
2. **Given** the user clicks Update, **Then** the installer downloads with
   visible progress, its integrity is verified before running, the install
   proceeds without wizard interaction, and the app closes and relaunches
   updated. If any step fails, the user sees why and can retry or download
   manually.
3. **Given** the first launch after an update, **Then** a What's New
   screen summarizes the changes in plain language, dismissible, never
   shown twice for the same version.
4. **Given** the Diagnostics page, **When** the user runs it, **Then**
   each self-check (AI scoring, PDF rendering, browser launch, source
   reachability) reports pass/fail with the actual error text on failure,
   and an Export logs button produces a shareable log file.
5. **Given** an update is applied over an existing database, **Then** the
   database is backed up first and the app migrates user data without loss
   (verified against a real populated previous-version database).

---

### User Story 6 - Smarter matching within free limits (Priority: P6)

Match scores get more trustworthy: jobs are pre-ranked by semantic
similarity to the resume before the AI scores the best candidates, so the
limited free AI quota is spent on the jobs that matter. Structured
extraction (resume sections, scores) uses the most schema-reliable free
cloud model, more than one free AI provider is offered, and the offline
model produces reliably valid output.

**Why this priority**: The user asked whether the AI model is good enough.
Research verdict: the current model is fine; ranking architecture and
extraction reliability are the actual levers. Valuable, but the app works
without it — hence lowest priority.

**Independent Test**: With a resume on file and no cloud key, confirm jobs
still receive a semantic relevance ranking offline; with a free cloud key,
confirm extraction tasks succeed with schema-valid output and that only
top-ranked jobs consume AI scoring quota.

**Acceptance Scenarios**:

1. **Given** a resume on file, **When** a refresh ingests new jobs,
   **Then** every job receives a local relevance rank (no network, no
   cost), and AI scoring is applied to the top-ranked jobs first, within a
   per-run cap.
2. **Given** a configured free cloud provider, **When** structured
   extraction runs (resume sections, match scoring), **Then** the model
   used guarantees schema-valid output, with the prose model still used
   for bullets and cover letters.
3. **Given** the Settings page, **Then** at least two free AI providers
   are offered as one-click presets with their limits stated, and any
   provider privacy caveats are disclosed.
4. **Given** only the bundled offline model, **When** structured
   extraction runs, **Then** output is schema-valid via constrained
   generation (no invalid-JSON retries needed).

---

### Edge Cases

- Machine with neither Edge nor Chrome installed (rare; e.g., stripped
  enterprise image): Apply Assist preflight reports "no supported browser
  found" with guidance; the rest of the app is unaffected.
- Update downloaded but installer blocked (e.g., SmartScreen on an
  unsigned build): the app surfaces the block, offers the manual download
  path, and documents the "More info → Run anyway" flow.
- Update check while offline or rate-limited: silent no-op; manual check
  shows "couldn't reach the update server."
- Resume with unusual layout where contact extraction finds nothing: all
  fields stay blank and editable; no error, no fabricated values.
- Two different jobs at the same company with identical titles in
  different locations must not be merged by dedup; the same job reposted
  under a new URL by the same source must not appear twice.
- A company board that starts redirecting to its careers homepage (instead
  of returning postings): jobs from that board are not mass-delisted on a
  single failed fetch; delisting requires a successful fetch that omits
  the job.
- Watchlist entry with an invalid/renamed board identifier: the source
  reports "board not found" in the refresh strip instead of failing
  silently forever.
- Clipboard unavailable at the OS level: copy actions report failure
  honestly via toast rather than claiming success.
- App closed (or crashes) mid-update-download: no partial installer is
  ever executed; the download restarts cleanly next time.
- Database migration failure on first launch after update: the app
  restores the pre-update backup and reports the error rather than
  starting with a half-migrated database.

## Requirements *(mandatory)*

### Functional Requirements

**Desktop shell correctness**

- **FR-001**: Users MUST be able to select and copy any visible text
  anywhere in the desktop app window.
- **FR-002**: Every copy action in the app MUST use one shared mechanism
  that works inside the desktop shell and MUST confirm success or failure
  visibly (toast).
- **FR-003**: Users MUST be able to copy any job's apply link from both
  the feed row and the job detail page.
- **FR-004**: Any external link clicked inside the desktop shell MUST open
  in the system default browser; no link may silently do nothing. This
  includes links generated by server responses (e.g., the update link).
- **FR-005**: File downloads generated by the app (resume/cover-letter
  PDFs, log exports) MUST save to disk when triggered inside the desktop
  shell.
- **FR-006**: Closing the desktop window during an active operation
  (refresh, Apply Assist queue, update download) MUST ask for confirmation.

**Apply Assist rebuild**

- **FR-007**: Apply Assist MUST drive a visible browser session using the
  browser(s) already installed on the user's machine (preferring the
  system's built-in browser, falling back to other supported installed
  browsers), in an isolated profile dedicated to the app, with no separate
  browser download step.
- **FR-008**: The former first-use browser download flow MUST be removed;
  any stored state from it MUST be migrated or ignored safely.
- **FR-009**: Every per-job fill outcome MUST carry a distinct reason
  class — at minimum: browser launch failed, page failed to load, page
  unreadable, fields not recognized — and the status panel MUST present a
  distinct, honest message for each, including the underlying error text
  where available.
- **FR-010**: A preflight check MUST verify the browser layer can actually
  start before a queue begins; on failure the queue MUST NOT start and the
  user MUST see the reason and a suggested fix.
- **FR-011**: All existing Apply Assist behaviors (idempotent fills,
  option matching, resume attachment incl. tailored PDF preference,
  multi-page rescan, interruption/resume, fill report with credential
  masking, batch summary, never auto-submit / never auto-login / never
  click) MUST be preserved on the new browser layer.

**Genuine, fresh sourcing**

- **FR-012**: The default feed window MUST be the last 14 days, offered
  alongside the existing narrower/wider windows, and ingestion MUST NOT
  admit postings older than 14 days from date-bearing sources.
- **FR-013**: Each job MUST record when it was last seen at its source;
  jobs absent from a successfully fetched company board MUST be marked
  delisted, excluded from default views, and flagged (not deleted) on
  saved/applied records. A delisted job that reappears at its source MUST
  be restored automatically. Liveness checks on scraped-board URLs MUST
  stay within the existing ingestion politeness budget (rate limits,
  honest headers).
- **FR-014**: Jobs whose posted date is unknown MUST be displayed as
  approximate rather than silently substituting the first-seen date.
- **FR-015**: The shipped company watchlist MUST contain at least 300
  directly-fetched company career boards, curated toward the user's field,
  and MUST be user-editable (add/remove/disable) from Settings without
  file editing; user changes MUST survive app updates.
- **FR-016**: Google's job search index MUST be added as a source; LinkedIn
  scraping MUST remain opt-in with an explicit rate-limit warning; every
  job and the feed toolbar MUST offer a one-click "Search on LinkedIn"
  link-out built from the relevant terms.
- **FR-017**: Same-source reposts of an already-known job MUST NOT create
  duplicate feed entries.
- **FR-018**: Search volume knobs (results per search, search sites,
  per-source page caps) MUST be exposed as settings with safe defaults,
  and the per-run AI scoring cap MUST scale so that widened searches do
  not produce permanently unscored jobs.

**Feed usability**

- **FR-019**: Sort (match score / posted date) MUST apply immediately on
  selection, and all view/window/sort navigation MUST preserve every other
  active filter.
- **FR-020**: The feed MUST provide paging controls whenever more results
  exist than are displayed, and MUST allow filtering by source.
- **FR-021**: The non-functional entry-level filter state ("non-entry
  only") MUST either work or be removed from the interface.

**Profile auto-fill & profile-driven search**

- **FR-022**: Resume upload MUST extract contact/identity details (first
  and last name, email, phone, profile links, location) and target titles,
  filling only blank profile fields automatically; conflicts with
  user-entered values MUST be resolved by explicit keep-or-replace consent.
- **FR-023**: Contact extraction MUST work on every tier, including with
  no AI available (pattern-based fallback).
- **FR-024**: Work-authorization/visa fields MUST never be auto-filled
  without explicit per-field user confirmation.
- **FR-025**: Search terms MUST be derived from the profile (titles,
  skills), stored, shown, and editable on the Profile page, capped in
  count, and used by the job search together with the user's target
  locations; built-in defaults MUST apply when the profile is empty.

**AI tiers & ranking**

- **FR-026**: Structured extraction and scoring via cloud AI MUST use a
  model with guaranteed schema-valid output where the provider offers one;
  prose generation MAY use a different model.
- **FR-027**: Settings MUST offer at least two free cloud AI providers as
  presets, each with stated limits and privacy caveats.
- **FR-028**: The offline model MUST use constrained generation so
  structured outputs are always schema-valid.
- **FR-029**: An offline semantic relevance ranking MUST order new jobs
  before AI scoring, so AI quota is spent top-down; it MUST work with no
  network and no key.

**Self-update, visibility & diagnostics**

- **FR-030**: The app MUST check for updates at most once daily on
  startup (silent when offline) and on demand; when an update exists it
  MUST offer in-app download with progress, integrity verification before
  execution, unattended install, and automatic relaunch; every failure
  mode MUST be reported with a manual-download fallback.
- **FR-031**: The installer/uninstaller MUST be hardened for unattended
  upgrades: the running app is detected and closed safely, file versions
  are stamped, stale files from prior versions are cleaned up, and the
  single version string is asserted consistent across app, installer, and
  release tag at build time.
- **FR-032**: On first launch after an update the app MUST show a
  version-specific What's New summary exactly once.
- **FR-033**: A Diagnostics page MUST run self-checks for AI scoring, PDF
  rendering, browser launch, and source reachability, showing real error
  text on failure, and MUST offer log export; unhandled errors in
  background work MUST be captured to the log with a crash marker shown on
  next launch.
- **FR-034**: Updates MUST back up the user database before migration and
  restore it if migration fails; the upgrade path MUST be verified against
  a real populated previous-version database before release.

### Key Entities

- **Fill outcome**: per-job Apply Assist result; reason class (launch
  failed / load failed / unreadable / unrecognized / filled / manual /
  skipped), underlying error text, timestamps.
- **Watchlist entry**: a company whose career board is fetched directly;
  identifier per board type, display name, enabled flag, user-added vs
  shipped origin.
- **Job freshness state**: posted date (exact or approximate), last seen
  at source, delisted flag.
- **Derived search term set**: capped list of search phrases derived from
  the profile, user-editable, with locations; provenance (derived vs
  user-edited).
- **Extracted contact details**: identity fields found in the resume with
  per-field conflict state (auto-filled / kept / replaced).
- **Update package**: release version, platform artifact, size, integrity
  digest, download state.
- **Diagnostic result**: check name, pass/fail, error text, run timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a clean Windows 11 machine with the installed app, a user
  can go from clicking Start to a visible browser window with fields
  filling in under 15 seconds, with zero prior setup steps.
- **SC-002**: 100% of Apply Assist failure modes exercised in testing
  (no browser, dead URL, unreadable page, closed window) produce a
  specific on-screen explanation; zero silent failures.
- **SC-003**: In the installed desktop shell, 100% of copy actions,
  external links, and PDF downloads succeed with visible confirmation
  (verified as part of the release gate, in the shell, not a dev browser).
- **SC-004**: With default settings, at least 95% of feed jobs display a
  posted date within the last 14 days, and a posting removed from a
  watched company board stops appearing as active within one refresh.
- **SC-005**: A user can re-sort the visible feed in one click without
  losing any active filter, and can reach every result via paging.
- **SC-006**: Uploading a typical single-column resume into an empty
  profile fills at least name, email, and phone without any AI key
  configured.
- **SC-007**: A user on the previous version can reach the new version
  entirely from inside the app in under 5 minutes on a typical connection,
  ending on a What's New screen, with all their data intact.
- **SC-008**: With a free-tier AI key, a refresh that ingests 500 jobs
  stays within the provider's daily free quota while scoring the
  top-ranked jobs, because semantic pre-ranking limits AI calls.

## Assumptions

- The primary platform is Windows 11 (the user's machine); the system
  browser (Edge) is present on all US-market Windows 11 installs, with
  Chrome as fallback. macOS keeps manual updates and is explicitly
  secondary this release.
- The app remains unsigned this release; SmartScreen friction is
  documented rather than eliminated (code signing stays deferred).
- "Genuine" is operationalized as: sourced directly from a company's own
  career board wherever possible, with scraped-board results
  URL-validated; no source can guarantee a posting isn't a ghost job, but
  employer-direct sourcing minimizes it.
- LinkedIn cannot be scraped sustainably at $0 (verified); the link-out
  satisfies "search LinkedIn" honestly, and opt-in scraping remains for
  users who accept rate limits.
- The 14-day freshness rule applies to date-bearing sources; sources
  without dates (some boards) rely on first-seen + delisting to stay
  honest.
- Free AI provider limits and model availability were verified 2026-07-22
  and may drift; presets state limits and the app degrades gracefully.
- All decisions recorded in the design doc (installed-browser engine, one
  v0.8.0 release, LinkedIn posture) were explicitly approved by the user
  on 2026-07-22.
