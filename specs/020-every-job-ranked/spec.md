# Feature Specification: Every Job Ranked

**Feature Branch**: `020-every-job-ranked`
**Created**: 2026-08-01
**Status**: Draft
**Input**: User description: "what can be done in next phase check for errors
re check all the functonality and working what can be improved how can we make
it faster" — answered by an audit of the running system rather than a guess.
Both gates were green (1622 unit, 90 browser), so the phase is aimed at what
the measurements found: the scoring pipeline leaves two-thirds of the feed
unranked, holds the refresh open for hours, and stacks duplicate runs on top of
itself. Three decisions locked in session: every job gets a score immediately
with the AI tier spent top-down on the best candidates; the full AI analysis
stays pre-computed for whatever the AI scores (no on-demand generation); and
four ride-along gaps are in scope (rich-text cover letters, extension idle
cost, feed query index, iCIMS advance selectors). Governed by constitution
v1.2.0 — unchanged, since nothing here adds an automated click.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every job in my feed has a score (Priority: P1)

As an applicant, when I open my feed, every job that survived eligibility
filtering carries a match score I can sort and filter by — not just the
handful the AI happened to reach before something interrupted it.

**Why this priority**: This is the reported problem in its most literal form.
The applicant's own database holds 937 eligible jobs of which 627 have no
score at all; the score filter silently drops all of them, so two-thirds of
the feed is invisible to the applicant's primary triage tool. Nothing else in
this feature matters if the feed stays two-thirds empty.

**Independent Test**: Load a database with a backlog of unscored eligible
jobs, run one refresh, and confirm zero eligible jobs remain unscored — with
the AI model unavailable, proving ranking never depends on inference.

**Acceptance Scenarios**:

1. **Given** eligible jobs with no score, **When** a refresh completes,
   **Then** every one of them has a match score and none is left unranked.
2. **Given** the on-device AI is unavailable or fails, **When** a refresh
   completes, **Then** every eligible job still has a score, and the failure
   does not leave any job unranked.
3. **Given** a scored feed, **When** the applicant looks at any job's score,
   **Then** the feed itself shows whether that score is a quick keyword match
   or a full AI assessment — the distinction is not hidden on another page.
4. **Given** a job holding a quick keyword score, **When** the AI tier later
   assesses it, **Then** its score and its displayed kind both upgrade in
   place, without the applicant doing anything.

---

### User Story 2 - The refresh finishes, and says what it is doing (Priority: P2)

As an applicant, a refresh completes in the time the app implies, tells me
what is still happening in the background, and never blocks me from starting
another one for hours.

**Why this priority**: Today the refresh holds itself open for the entire
scoring pass — measured at 2 h 47 m for one capped run — while every source
shows "done" and any new refresh is refused as "running". This is the
mechanism that produced the unranked backlog in User Story 1, so it must be
fixed for that fix to hold. It also delays fresh-match alerts by hours.

**Independent Test**: Run a refresh against a large unscored backlog and
confirm the run reaches its finished state in seconds, alerts fire on the new
jobs immediately, and a second refresh is accepted normally afterwards.

**Acceptance Scenarios**:

1. **Given** a large backlog of unscored jobs, **When** a refresh runs,
   **Then** it reaches its finished state promptly and the applicant may start
   another refresh under the ordinary cooldown rules.
2. **Given** a refresh has finished, **When** background AI assessment is
   still working through the backlog, **Then** the applicant can see that it
   is running and how far along it is.
3. **Given** new jobs matching the applicant's criteria arrived,
   **When** the refresh completes, **Then** alerts fire without waiting for
   any AI assessment to finish.
4. **Given** background AI assessment is already running, **When** anything
   tries to start it again, **Then** exactly one assessment pass exists — a
   second never runs alongside the first.
5. **Given** the app is closed part-way through background assessment,
   **When** it is reopened, **Then** assessment resumes and no more than one
   job's work is lost.

---

### User Story 3 - Applying always beats ranking (Priority: P3)

As an applicant filling in a real application, the app's background work never
makes the form in front of me slower.

**Why this priority**: Moving AI assessment out of the refresh means it can
now run at any moment, including while Apply Assist is filling a form. Both
share one serialized on-device AI worker with no priority ordering, so an
unguarded change here would trade a slow feed for a slow application — a
strictly worse outcome. This story is the guard rail on User Story 2.

**Independent Test**: Start background assessment, then start a fill session
that needs a generated answer, and confirm the answer arrives within its
normal budget.

**Acceptance Scenarios**:

1. **Given** background AI assessment is running, **When** an application fill
   session starts, **Then** assessment stands down until the session ends.
2. **Given** an application needs a generated answer, **When** assessment work
   also exists, **Then** the answer is produced within its normal time budget.
3. **Given** both kinds of work exist, **When** they run, **Then** only one
   on-device AI call executes at a time — the existing single-flight guarantee
   is never weakened.

---

### User Story 4 - Rich-text cover letters fill (Priority: P4)

As an applicant on a form whose cover-letter box is a rich-text editor rather
than a plain text area, that box is seen, filled or flagged — never silently
absent.

**Why this priority**: The cover letter is the highest-value field on most
applications. Today rich-text boxes are not merely unfilled — they are outside
the scanner's reach entirely, so they are not counted, not flagged, and carry
no explanation. That is the one failure mode this project treats as
unacceptable: a silent gap the applicant cannot see.

**Independent Test**: On fixture pages with rich-text cover-letter editors,
confirm the box is discovered, counted, and either filled with the applicant's
answer or listed as needing them.

**Acceptance Scenarios**:

1. **Given** a form whose cover letter is a rich-text editor, **When** the
   page is scanned, **Then** the box is discovered and counted as a field.
2. **Given** an answer is available for it, **When** the fill runs, **Then**
   the text lands in the editor and the page registers it as user input.
3. **Given** no answer is available or the editor cannot be written,
   **When** the fill runs, **Then** the box is listed as needing the
   applicant, never left silently blank.
4. **Given** a rich-text box holds an answer, **When** the step is assessed,
   **Then** it counts as answered for the purpose of advancing the wizard.

---

### User Story 5 - The companion is cheap on pages that are not applications (Priority: P5)

As someone who browses the web all day with the companion installed, it costs
me nothing noticeable on pages that have nothing to do with job applications.

**Why this priority**: The companion inspects every frame of every page on a
fixed interval, forever. It is a background tax on ordinary browsing rather
than a defect in any single feature, so it ranks below correctness — but it is
real, and it is paid on a low-power laptop.

**Independent Test**: Measure the companion's periodic inspection cost on a
large page with no application form, before and after, and confirm a
substantial reduction with no loss of detection.

**Acceptance Scenarios**:

1. **Given** a large page with no application form, **When** the companion has
   observed that for a while, **Then** it inspects the page less often.
2. **Given** the companion has backed off on a page, **When** an application
   form appears (including after in-page navigation), **Then** it is detected
   without a noticeable delay.

---

### User Story 6 - Reach and responsiveness (Priority: P6)

As an applicant, the feed opens quickly however many jobs I have collected,
and iCIMS applications advance as reliably as Workday and Greenhouse ones.

**Why this priority**: Two contained improvements with known causes. Neither
blocks anything else, and both are small enough to ride along safely.

**Independent Test**: Confirm the feed listing no longer sorts without index
support, and that an iCIMS fixture advances by its own recognised control
rather than the generic fallback.

**Acceptance Scenarios**:

1. **Given** a large collection of jobs, **When** the feed page is listed,
   **Then** the listing is served without an unindexed sort.
2. **Given** an iCIMS application step, **When** the step is complete,
   **Then** it advances using an iCIMS-recognised control under the same
   safety rules as every other site.

---

### Edge Cases

- A job with no description, or an empty resume, must still receive a score
  rather than being skipped back into the unranked pool.
- The applicant changes their resume: previously assessed jobs keep their
  scores; nothing is invalidated or re-run en masse.
- A single job's AI assessment fails repeatedly — it must keep its quick score
  and must not block the rest of the backlog behind it.
- The applicant opens the feed repeatedly within the cooldown window: no
  background assessment pass may be started more than once.
- A rich-text editor that rejects programmatic input entirely must degrade to
  a needs-attention item, never to a wrong or partial value.
- Backing off the companion's inspection must not delay a form that appears
  long after page load.
- An unscored job that becomes ineligible (delisted, reclassified) between
  ranking and assessment must simply be skipped.

## Requirements *(mandatory)*

### Functional Requirements

**Ranking coverage**

- **FR-001**: Every eligible job without a score MUST receive one during the
  refresh that ingests it, with no per-run cap.
- **FR-002**: Assigning scores to the full eligible set MUST NOT depend on the
  on-device or cloud AI being available, working, or fast.
- **FR-003**: The system MUST distinguish, per job, whether a score came from
  quick keyword matching or from full AI assessment, and MUST show that
  distinction in the feed listing as well as on the job page.
- **FR-004**: The system MUST upgrade quick-scored jobs to full AI assessment
  over time, choosing which jobs to upgrade by semantic similarity to the
  applicant's resume, best first.
- **FR-005**: An upgraded job MUST carry the same full assessment content
  (matching skills, missing skills, gap actions, reasoning) that AI-scored
  jobs carry today; assessment content is never generated on demand when the
  applicant opens a job.
- **FR-006**: The number of AI upgrades attempted per pass MUST be a
  user-visible setting with a default chosen to complete in a reasonable
  background window.

**Refresh lifecycle**

- **FR-007**: A refresh run MUST reach its finished state without waiting for
  any AI assessment.
- **FR-008**: Fresh-match alerts, liveness checks, and pruning MUST NOT be
  delayed by AI assessment.
- **FR-009**: At most one background AI assessment pass MUST exist at any
  time; any attempt to start another while one is running MUST be a no-op.
- **FR-010**: Background AI assessment MUST be resumable — interrupting it
  (including closing the app) MUST lose at most the single job in progress.
- **FR-011**: While background AI assessment is running, the applicant MUST be
  able to see that it is running and how far through the pass it is.
- **FR-012**: A job whose AI assessment fails MUST retain its quick score, MUST
  NOT be retried indefinitely within a pass, and MUST NOT prevent other jobs
  in the pass from being assessed.

**On-device AI fairness**

- **FR-013**: Background AI assessment MUST stand down for the duration of an
  active application fill session.
- **FR-014**: Background AI assessment MUST submit at most one on-device AI
  request at a time and MUST NOT enqueue a batch, so that other work waits
  behind at most one assessment.
- **FR-015**: The existing guarantee that only one on-device AI call executes
  at any instant MUST remain intact.

**Rich-text answers**

- **FR-016**: Rich-text editing regions used as form inputs MUST be discovered
  and counted by the page scan exactly as native text areas are.
- **FR-017**: An answer written into a rich-text region MUST be registered by
  the host page as user input.
- **FR-018**: A rich-text region that cannot be written MUST be surfaced as a
  needs-attention item naming the field, never left silently blank.
- **FR-019**: A rich-text region holding an answer MUST count as answered when
  judging whether an application step is complete.

**Companion cost**

- **FR-020**: The companion's periodic page inspection MUST reduce its
  frequency on pages that have repeatedly shown no application form.
- **FR-021**: Reduced inspection frequency MUST NOT delay detection of a form
  that appears later, including after in-page navigation.

**Reach and responsiveness**

- **FR-022**: The feed listing MUST be served without an unindexed sort.
- **FR-023**: iCIMS application steps MUST advance using iCIMS-recognised
  progression controls, under the same allowlist-first, one-shot, capped,
  pause-on-ambiguity rules as every other supported site.

**Unchanged guarantees**

- **FR-024**: No automated click is added, removed, or relaxed by this
  feature; the human still performs the final Submit, Create account, and pay,
  CAPTCHAs are never interacted with, and nothing is ever clicked on LinkedIn.
- **FR-025**: Credential secrets remain fill-and-forget: never in the
  application database, extension storage, logs, reports, or diagnostics.

### Key Entities

- **Job score**: a number plus the assessment that produced it, carrying which
  tier assigned it (quick keyword match vs full AI assessment) so the applicant
  is never shown a keyword score as though it were a judgement.
- **Assessment pass**: one bounded, resumable, single-flight sweep that
  upgrades quick-scored jobs to full AI assessment, ordered by semantic
  similarity, with visible progress and a per-pass limit.
- **Rich-text field**: a form input that is an editable region rather than a
  native control — it has no intrinsic value, name, or label association, so
  its question and its answer are read and written differently.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After one refresh, 100% of eligible jobs carry a score (measured
  against a real backlog; the applicant's own database goes from 33% to 100%).
- **SC-002**: Assigning scores to the entire eligible backlog completes in
  under 30 seconds with no AI involvement.
- **SC-003**: A refresh reaches its finished state in under 60 seconds on a
  backlog that previously held it open for over two hours.
- **SC-004**: Fresh-match alerts fire within the same refresh that ingests the
  matching jobs, rather than hours later.
- **SC-005**: Concurrent assessment passes are impossible: zero duplicate
  passes under repeated start attempts.
- **SC-006**: A generated application answer requested during a background
  assessment pass arrives within its normal budget, 100% of attempts.
- **SC-007**: Rich-text cover-letter boxes on the covered fixture sites are
  discovered 100% of the time and are either filled or flagged — never
  silently absent.
- **SC-008**: The companion's periodic inspection cost on a large
  form-free page falls by at least half, with no detection regressions in the
  browser suite.
- **SC-009**: The feed listing query plan contains no unindexed sort.
- **SC-010**: Both existing gates stay green: the full unit battery and the
  real-browser suite pass, and secret hygiene remains clean.

## Assumptions

- Single user on their own machine, human-scale volumes; the eligible pool is
  hundreds of jobs, not millions.
- Quick keyword scores are genuinely useful for triage and ordering; their
  value comes from covering everything, and the applicant is told which kind
  of score they are looking at rather than being asked to trust them equally.
- The applicant would rather have every job ranked approximately now than a
  third of them ranked precisely later — the decision locked this session.
- Full AI assessment stays pre-computed; a job page never blocks on
  generation.
- Applying is always more urgent than ranking, so assessment yields to it
  unconditionally rather than negotiating priority.
- Rich-text support targets the editors used by the covered ATSs; unknown
  editors degrade to needs-attention rather than being guessed at.
- The on-device AI cost per assessed job (measured at roughly a minute on the
  applicant's laptop) is treated as fixed; this feature spends less of it
  rather than making it faster.
- The truthful-fill answer semantics from v1.7.0 and the progression rules
  from v1.9.0 are unchanged; this feature changes coverage and cost, not
  honesty or automation reach.
