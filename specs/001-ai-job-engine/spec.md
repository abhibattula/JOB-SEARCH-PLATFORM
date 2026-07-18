# Feature Specification: Personalized AI Job Engine

**Feature Branch**: `001-ai-job-engine`
**Created**: 2026-07-18
**Status**: Draft
**Input**: User description: "Personalized AI job engine webapp: aggregates recent entry-level SWE and hardware jobs with visa sponsorship detection and AI resume matching. Zero recurring cost, single user now but shareable later. On open, the app instantly shows cached jobs from the past week (with a last-24-hours filter) and automatically refreshes in the background."

## Clarifications

### Session 2026-07-18

- Q: Should v1 let you track your interaction with each job (saved / applied / hidden)? → A: Yes, minimal statuses — Saved, Applied, Hidden; default feed shows only unhandled jobs; dedicated filters reveal saved/applied lists.
- Q: How should location preferences affect the job feed? → A: Show all US + remote jobs by default; an on-demand location filter narrows the view; preferences pre-populate the filter but never silently hide jobs.

### Session 2026-07-18 (feature 002)

- Superseded by [002-desktop-eligibility-coverage](../002-desktop-eligibility-coverage/spec.md): EXCLUDED (sponsorship-ineligible) jobs are now *hidden* from all normal views rather than shown with a badge (FR-003/FR-009 deltas), and the ineligibility detector covers ITAR/clearance/citizenship wording.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open the App and See Fresh, Relevant Jobs (Priority: P1)

As a recent computer engineering graduate hunting for entry-level software and
hardware roles, I open the app and immediately see a feed of relevant job postings
from the past week. The app automatically checks all its job sources in the
background and new postings appear in the feed as they are found, without me doing
anything. I can narrow the view to only jobs posted in the last 24 hours.

**Why this priority**: This is the product's reason to exist — a single place that
surfaces recent, relevant openings faster than manually checking many job boards.
Without it, no other feature matters.

**Independent Test**: Start the app with an empty library, open it in a browser,
and confirm the feed populates with real recent postings without any manual action;
toggle the 24-hour filter and confirm the list narrows correctly.

**Acceptance Scenarios**:

1. **Given** the app has previously collected jobs, **When** I open it, **Then** I
   see the stored jobs from the past 7 days immediately (no waiting on a fetch).
2. **Given** the app is open, **When** the automatic background check finds new
   postings, **Then** they appear in the feed without a manual page reload and are
   visibly marked as new.
3. **Given** the feed shows the past week, **When** I switch to "last 24 hours",
   **Then** only jobs posted (or first seen) within 24 hours remain.
4. **Given** a background check completed less than 30 minutes ago, **When** I
   reopen the app, **Then** it does not start another check and the feed loads
   instantly from stored data.
5. **Given** one job source is unavailable, **When** a background check runs,
   **Then** jobs from the remaining sources still arrive and the failed source is
   indicated without blocking the feed.
6. **Given** the same job appears on two sources, **When** it is collected twice,
   **Then** the feed shows it only once.
7. **Given** I have marked a job as Applied or Hidden, **When** I open the app or
   a refresh runs, **Then** that job does not reappear in the default feed, and I
   can still find it under its status filter.

---

### User Story 2 - Filter for Entry-Level and Visa-Friendly Jobs (Priority: P2)

As an international candidate (OPT, future H-1B), I only want to see roles I can
realistically get: entry-level positions at companies likely to sponsor a work
visa. Each job shows a sponsorship indicator backed by evidence (the company's
historical sponsorship record and/or wording found in the job description), and
jobs that explicitly refuse sponsorship are flagged so I don't waste time on them.

**Why this priority**: Sponsorship-aware filtering is the differentiator existing
free tools lack — it directly prevents wasted applications, but it needs the P1
feed to exist first.

**Independent Test**: Load the sponsorship reference data, run a collection pass,
and spot-check known sponsor companies show a positive indicator while a posting
containing "US citizens only" is flagged as excluded.

**Acceptance Scenarios**:

1. **Given** a job at a company with a strong historical sponsorship record and no
   negative wording, **When** I view the feed, **Then** the job shows a "high"
   sponsorship indicator with the supporting evidence viewable.
2. **Given** a job description containing wording like "unable to sponsor" or
   "US citizens only", **When** it is processed, **Then** the job is marked
   excluded regardless of the company's history.
3. **Given** a senior or staff-level posting, **When** collection runs, **Then**
   it does not appear in the entry-level feed.
4. **Given** a posting titled for new grads or early-career hardware roles (e.g.,
   firmware, FPGA, ASIC verification), **When** collection runs, **Then** it is
   classified as entry-level and appears in the feed.

---

### User Story 3 - Match My Resume and See What's Missing (Priority: P3)

As the job seeker, I upload my resume once, and every relevant job gets a 0–100
match score. Opening a job shows the description side-by-side with the analysis:
which of my skills match, which required skills I'm missing, and specific
actionable suggestions ("add X to your resume") to improve my fit.

**Why this priority**: Scoring and gap analysis turn a job list into a
prioritized action plan, but they depend on the P1 feed and are valuable only
after filtering (P2) keeps the list relevant.

**Independent Test**: Upload a resume, let the analysis run over a handful of
jobs, and confirm scores appear in the feed, rank plausibly, and each job detail
view shows matching skills, missing skills, and concrete suggestions.

**Acceptance Scenarios**:

1. **Given** I have uploaded my resume, **When** new entry-level jobs are
   collected, **Then** each receives a match score visible in the feed, and the
   feed can be sorted by score.
2. **Given** a scored job, **When** I open its detail view, **Then** I see the
   job description alongside matching skills, missing skills, and at least one
   actionable improvement suggestion.
3. **Given** the analysis service fails for a job, **When** I view the feed,
   **Then** the job still appears (unscored) rather than disappearing.
4. **Given** I have not uploaded a resume, **When** I browse the feed, **Then**
   everything else works and the app prompts me to add a resume to unlock scores.

---

### Edge Cases

- First run with an empty library: feed shows an empty state plus live progress
  while the first collection fills it.
- A source provides no posting date: the job is treated as posted when first seen
  so recency filters still work.
- A background check is already running when another is requested: the second
  request is ignored rather than doubling traffic.
- Sponsorship reference data not yet loaded: jobs show "unknown" sponsorship
  rather than a misleading indicator.
- The AI analysis returns malformed output: retried once, then the job is left
  unscored and visible.
- A company's name differs slightly between a job source and the sponsorship
  records (e.g., "NVIDIA Corp" vs "NVIDIA Corporation"): the records still match.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST collect job postings from multiple public sources
  (major applicant-tracking-system boards, large-employer career sites, community
  hiring threads, and general job boards) on each refresh.
- **FR-002**: The system MUST record, for every job, the source's posting date
  when available and the time the system first saw it; recency filtering uses the
  posting date and falls back to first-seen.
- **FR-003**: Opening the app MUST immediately display stored jobs from the past
  7 days, sorted by match score (when available) and recency, excluding jobs the
  user has marked Applied or Hidden.
- **FR-004**: The user MUST be able to narrow the feed to jobs from the last 24
  hours with a single action.
- **FR-005**: Opening the app MUST automatically start a background refresh
  unless one is already running or one completed within the last 30 minutes.
- **FR-006**: While a refresh runs, the app MUST show per-source progress, and
  newly found jobs MUST appear in the feed without a manual reload.
- **FR-007**: The system MUST show each unique job once, even when it is found on
  multiple sources.
- **FR-008**: The system MUST classify jobs as entry-level (including new-grad,
  early-career, and entry hardware roles such as firmware, FPGA, ASIC, and
  verification) and exclude senior/staff/lead-level postings from the default feed.
- **FR-009**: The system MUST assign each job a sponsorship indicator — high,
  medium, excluded, or unknown — combining the company's historical sponsorship
  record with wording found in the job description; explicit negative wording MUST
  override a positive history.
- **FR-010**: The sponsorship indicator MUST expose its evidence (e.g., approval
  counts, the matched phrase) in the job detail view.
- **FR-011**: The user MUST be able to upload a resume (PDF) once and have its
  content used for all subsequent match analysis; replacing the resume MUST be
  possible.
- **FR-012**: The system MUST produce, for each entry-level job, a 0–100 match
  score, matching skills, missing skills, and at least one actionable improvement
  suggestion; jobs whose analysis fails MUST remain visible unscored.
- **FR-013**: A failure in any single source MUST NOT prevent other sources from
  completing, and the failure MUST be visible to the user.
- **FR-014**: The full collection-and-analysis cycle MUST be runnable without the
  web interface (headless), producing the same stored results.
- **FR-015**: The system MUST operate at zero recurring cost, and all personal
  data (resume, preferences) MUST remain on the user's machine.
- **FR-016**: Collection MUST be polite to sources: no authentication bypass, no
  more than one request per second to any single site.
- **FR-017**: The user MUST be able to mark any job as Saved, Applied, or Hidden
  with a single action. Applied and Hidden jobs are excluded from the default
  feed; Saved jobs remain visible in it. Each status has a dedicated filtered
  view, and statuses survive refreshes.
- **FR-018**: The default feed MUST show all US and remote jobs; a location
  filter (specific states/cities or remote-only) MUST be available to narrow the
  view on demand. Stored location preferences pre-populate this filter but MUST
  NOT silently exclude jobs from the default view.

### Key Entities

- **Job Posting**: A single opening — title, company, location, remote flag,
  description, source, link, posting date, first-seen time, entry-level flag,
  sponsorship indicator, match score and analysis, and user status (none, saved,
  applied, or hidden).
- **Company**: An employer — name, historical sponsorship record (approval
  counts, sponsored titles), derived sponsorship rating; linked to its postings.
- **User Profile**: The single user's resume text, extracted skills, and
  preferences (locations, targets).
- **Refresh Run**: One background collection cycle — start/end time, per-source
  status and counts; at most one active at a time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Opening the app displays the stored feed in under 2 seconds, with
  no waiting on external sources.
- **SC-002**: A full background refresh across all sources completes within 5
  minutes, with new jobs appearing progressively throughout.
- **SC-003**: The feed draws from at least 5 distinct source families, and a
  weekly view regularly contains 100+ relevant postings.
- **SC-004**: Entry-level classification achieves at least 90% accuracy on a
  curated set of ~40 real job titles spanning software, hardware, and senior
  roles.
- **SC-005**: In a spot-check of 10 well-known sponsoring employers, all 10 show
  a positive sponsorship indicator, and a posting with explicit "citizens only"
  wording is excluded.
- **SC-006**: With a resume uploaded, the user can go from opening the app to
  clicking "apply" on a scored, sponsorship-positive job in under 1 minute.
- **SC-007**: Running the system for a month costs $0 in subscriptions or usage
  fees.
- **SC-008**: No duplicate postings are visible in a feed of 100+ jobs collected
  from overlapping sources.

## Assumptions

- Single user (the project owner) for v1; the design must not preclude adding
  more users later, but no login or account features are included now.
- Target roles are US-based entry-level software and hardware engineering
  positions; postings are in English.
- The set of monitored companies/sources starts from a curated seed list that the
  user can extend by editing a simple list; automatic company discovery is out of
  scope for v1.
- Sponsorship reference data comes from public government records (historical
  petition/approval data) refreshed manually a few times a year; it is a strong
  signal, not a guarantee.
- The resume is provided as a PDF; scanned-image resumes (no extractable text)
  are out of scope.
- Free AI service tiers (or local models) remain available at sufficient daily
  volume for scoring newly collected entry-level jobs.
- Deferred to v2 (explicitly out of scope): accounts/multi-user, hosted
  deployment, application auto-fill, resume tailoring per job, CLI/agent
  integrations, and sources that require fighting bot protection.
