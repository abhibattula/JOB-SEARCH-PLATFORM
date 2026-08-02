# Research: Every Job Ranked (feature 020)

Every decision here is backed by a measurement taken on the applicant's own
machine (Intel i5-10210U, 4 physical / 8 logical cores, Windows 11) against
the applicant's own database (`data/jobs.db`, 22,145 jobs). Nothing in this
document is an estimate.

---

## R1 — Where the time actually goes

**Decision**: Cut *generated tokens* and *jobs sent to the model*, not
threads, not model parameters.

**Measurement** — one `analyze_match`-shaped call, resume prefix warm:

| variant | per job | 627-job backlog |
|---|---|---|
| full analysis schema, 6000-char JD (today) | **66.8 s** | 11.6 h |
| score-only output, 6000-char JD | 24.1 s | 4.2 h |
| score-only output, 2000-char JD | 13.9 s | 2.4 h |
| `semantic.embed()` | 0.60 s | 6.3 min |
| `basic_match.score()` | **0.0044 s** | **2.8 s** |

A controlled A/B isolated the two components. Re-issuing an identical prompt
returned in **1.7 s** (pure generation, KV prefix fully cached), while changing
only the system message forced a full re-evaluation costing **35.3 s** for
~1500 tokens (≈42 tok/s prompt eval). Generation measured ≈5–6 tok/s. So the
~250 tokens of `matching_skills` / `missing_skills` / `gap_actions` /
`reasoning` prose are the dominant term, and the JD half of the prompt is the
second.

**Rationale**: `basic_match.score()` is 15,000× cheaper than an AI assessment
and is already written, already tested, and already understood by the UI. It
is the only thing that can cover 100% of the backlog on this hardware.

**Alternatives considered and rejected**:

- **CPU thread tuning** — measured 8 / 4 / 3 threads at 22.9 / 23.2 / 24.0 s.
  Flat. The workload is memory-bandwidth-bound, so `os.cpu_count()` is not the
  misconfiguration it looks like. **Rejected: no effect.** Recorded here so it
  is never re-attempted.
- **Reordering the prompt for prefix caching** — already optimal. The resume
  is emitted before the JD (`matcher.analyze_match`), so llama-cpp's automatic
  longest-common-prefix reuse already skips re-evaluating it across jobs. No
  change available.
- **Shrinking `MAX_CHARS` from 6000** — worth 24.1 s → 13.9 s, but it silently
  degrades assessment quality on long postings. **Rejected as a default**; the
  session decision keeps the full analysis intact.
- **Generating the analysis on demand when a job is opened** — offered and
  **explicitly rejected by the applicant this session**. Full analysis stays
  pre-computed for every AI-scored job.
- **A GPU wheel** — violates the bundle/$0/offline constraints and is
  unavailable on the target laptop.

---

## R2 — Why the backlog never cleared

**Decision**: Move AI assessment out of the refresh run entirely and give it
its own single-flight lifecycle.

**Evidence** (read from code, confirmed against the database):

- `_score_new_jobs()` runs inline in `_post_ingest` (`engine/pipeline.py:156`),
  so `db.finish_run()` is unreachable for the whole pass — **2 h 47 m** at the
  150-job cap.
- `STALE_RUN_MINUTES = 30` (`engine/db.py:21`) is *shorter than that pass*.
  At 30 minutes `start_run()` declares the live run crashed, marks it finished,
  and starts a second — while the first scoring thread is still running.
- The trigger is not a button. `web/templates/feed.html:5` fires
  `hx-post="/api/refresh"` on **every feed page load**.
- Both loops then read the same `jobs_needing_score` set (a job is not marked
  until `set_match` completes), so they re-score the same jobs through one
  serialized inference worker, each slowing the other.

**Observed end state**: 937 eligible jobs, **310 scored, 627 unscored**, 600
embedded — a database last written 2026-07-28 that never converged.

**Rationale**: The pass cannot be made short enough to fit inside a 30-minute
staleness window at 67 s/job. The lifecycle has to change, not the timeout.

**Alternatives considered and rejected**:

- **Raise `STALE_RUN_MINUTES` to ~4 hours** — leaves the refresh blocked for
  hours, alerts delayed, and a genuinely crashed run undetected for a whole
  afternoon. **Rejected**: treats the symptom and makes crash recovery worse.
- **Lower `MAX_SCORE_PER_RUN` until the pass fits in 30 minutes** (~26 jobs) —
  the backlog then never clears at all. **Rejected.**
- **A lock around `_score_new_jobs`** — prevents the duplicate loop but still
  holds the run open for hours. **Rejected as insufficient**; the single-flight
  guard is kept, but on the new background pass.

---

## R3 — Not starving Apply Assist

**Decision**: The assessment pass submits exactly one inference request at a
time and stands down completely while a fill session is live.

**Evidence**: `engine/inference.py` is a strict-FIFO `queue.Queue`
(`maxsize=32`) drained by one owner thread, with **no priority ordering** and a
180 s chat budget. Today's scoring loop blocks on each future, so any
concurrent drafter request waits behind at most one call (~67 s, inside
budget). That is an accident of the current structure that becomes
load-bearing once assessment can run at any time rather than only during a
refresh.

**Rationale**: Batch-enqueuing 40 assessments would put a drafter request
behind up to 40 × 67 s ≈ 45 min — far past its timeout — turning a slow feed
into a broken application. Yielding entirely to an active fill session is
simpler and stronger than any priority scheme, and matches Principle I:
completing an application always outranks ranking one.

**Alternatives considered and rejected**:

- **A priority queue in `inference.py`** — changes the module every AI path in
  the app depends on, to solve a problem a stand-down solves for free.
  **Rejected**: risk out of proportion to benefit.
- **A second inference worker** — llama-cpp model objects are not thread-safe;
  unserialized concurrency is the recorded cause of the feature-015
  `ggml-cpu.dll` access violation. **Rejected: unsafe.**
- **Shortening the chat timeout so assessments give up sooner** — makes
  assessment fail rather than making drafting win. **Rejected.**

---

## R4 — Honesty about score provenance

**Decision**: Render the existing `match_method` in the feed listing.

**Evidence**: The mechanism is already built and simply unused at the feed
level. `job_detail.html:85` renders `~` for a quick score and `•` for an AI
score with distinct explanatory copy, and `_JOB_COLUMNS` (`engine/db.py:574`)
already selects `json_extract(j.match_json, '$.method') AS match_method`. The
feed template just never reads it.

**Rationale**: This release makes most scores quick-tier. Showing a keyword
score in the same visual form as an AI judgement would be the kind of quiet
overclaim this project treats as a defect. Because the plumbing exists, the
honest presentation costs one template change plus a pinned test.

**Alternatives considered and rejected**:

- **Show only AI scores in the feed and hide quick ones** — reproduces the
  original problem (a two-thirds-empty feed). **Rejected.**
- **Two separate score columns** — more UI than the distinction warrants.
  **Rejected.**

---

## R5 — Rich-text fields

**Decision**: Add editable regions to the scan selector and give the filler an
editor-aware write path; anything unwritable degrades to needs-attention.

**Evidence**: `FIELD_SELECTOR` (`extension/content/scanner.js:13`) covers
`input`, `select`, `textarea` and ARIA combobox/listbox shapes only. There is
no `contenteditable` or `role=textbox` entry anywhere in `engine/` or
`extension/` — a repository-wide search returns nothing. A rich-text cover
letter is therefore not counted, not flagged, and carries no reason: the
silent-gap failure mode 018 and 019 were both spent eliminating.

**Rationale**: The cover letter is the highest-value field on most
applications, and this is the last known place where the applicant sees
nothing at all.

**Known traps, each getting its own test**: an editable `div` has no `.value`
(read `innerText`), no `.labels` (the 019 `aria-labelledby` → wrapping-label →
preceding-sibling ladder already covers it), and no `.name` (classification
must fall back to `automation_id` and label text). Writing must dispatch real
`input` events, because React/ProseMirror/Quill ignore a silent DOM mutation.
`je_idx` stamping must work on a `div`, not only on a form control.

**Alternatives considered and rejected**:

- **Flag rich-text boxes as needs-you without ever writing them** — honest but
  leaves the highest-value field manual forever. **Rejected**; it is the
  fallback for unknown editors, not the goal.
- **`document.execCommand('insertText')` alone** — deprecated and inconsistent
  across editors; used only as one branch behind feature detection.

---

## R6 — The companion's idle cost

> **CORRECTED during implementation, twice.** The measurement-first rule
> earned its keep here: the original claim overstated this in one way and the
> benchmark undercut it in another.

**Original (wrong) claim**: "this runs in every frame of every page, forever."

**What was wrong**: `discovery.js:14` is `if (window !== window.top) return;` —
the discovery poll is **top-frame only**. There is no per-iframe multiplier.
`main.js`'s 2 s safety scan does run in all frames, but only while a fill
session is active, which is not idle cost.

**Then the benchmark undercut the rest of it.** Timing the shipped
`scanner.probe()` (the whole-DOM shadow-root walk plus a forced layout per
candidate) on real page sizes:

| page | elements | probe, median | continuous cost |
|---|---|---|---|
| ordinary content page | 4,009 | **2.8 ms** | 0.19% of one core |
| large app page | 20,009 | **16.9 ms** | 1.1% |
| very large page | 60,009 | **52.4 ms** | 3.5% |

At typical sizes this was **never the problem it was described as**. What is
real is the top end: a 52 ms main-thread block every 1.5 s is visible jank,
and it lands on exactly the heavy pages an applicant browses.

**Decision**: keep the workstream, but as a small, safe change with an honest
claim. The poll widens from 1.5 s to 6 s after five consecutive ticks that
found nothing — a **4× reduction in idle cost**, comfortably past SC-008's
50% — and a `childList`-only `MutationObserver` wakes it instantly. The
per-tick cost is unchanged; only the frequency drops.

**Why the waker makes the backoff safe**: a form cannot appear without the DOM
changing. Any mutation, or an in-page navigation, returns the poll to full
speed, so the slow rate is only ever reached on a page that is both formless
and static. The regression this could cause — a form mounting after the poll
widened — has its own browser test (`late_form_after_idle.html`), because a
source-string assertion could not catch it.

**Alternatives considered and rejected**:

- **Narrow the manifest `matches` to known ATS hosts** — breaks the ad-hoc
  "fill any page" capability and the discovery badge on arbitrary postings,
  both deliberate 012/018 behaviours. **Rejected.**
- **Drop the periodic poll and rely on `MutationObserver` alone** — the poll
  covers observer blind spots (value mutations that change no observed
  attribute). **Rejected**; backed off, not removed.
- **Skip the `querySelectorAll("*")` shadow walk unless a shadow host
  exists** — there is no cheap way to know that without the walk, and caching
  it risks missing a late-mounted shadow form. **Rejected**: the interval
  change gets 4× with none of that risk.

---

## R7 — Feed listing index

> **CORRECTED during implementation.** The first version of this decision was
> based on a query the application never runs. The corrected finding is
> narrower and is recorded in full here, because the wrong version was
> approved and the difference matters.

**Original (wrong) claim**: "the default feed query measures 67.9 ms and plans
as `USE TEMP B-TREE FOR ORDER BY`; an expression index brings it to
single-digit ms."

**What was wrong**: that 67.9 ms was a hand-written query with **no date
window**, scanning all 22,145 rows. `db.query_jobs()` always applies a window
(14 days by default) and defaults to `sort="score"`, whose ORDER BY is
`j.match_score IS NULL, j.match_score DESC, COALESCE(j.posted_date,
j.first_seen) DESC`. An index on the date expression cannot serve that sort at
all — the leading keys are `match_score` — and the WHERE clause is built
dynamically from a dozen optional filters, so no single composite index serves
the general case either.

**Measured properly**, via `db.query_jobs()` itself against a copy of the real
database, median of 5, with and without the index:

| view | today | with index |
|---|---|---|
| **default** — 14 d, entry-level, score sort | 22.3 ms | 23.6 ms |
| All window, entry-level, score sort | 27.1 ms | 24.5 ms |
| All window, no entry filter, score sort | 332 ms | 318 ms |
| All window, no entry filter, **date sort** | 329 ms | **153 ms** |

**Decision**: keep the expression index, with an honest and much smaller
claim. It is worth **2.1× on exactly one view** — "All jobs, all levels, sorted
by date", the widest listing the app offers — and is neutral everywhere else
(the other three rows are within run-to-run noise). The default view was never
slow: **22 ms is not a problem and this feature does not pretend to fix it.**

`FR-022` and `SC-009` were rewritten to match this measurement instead of the
original one. The success criterion is now the date-sorted wide listing, not
"the feed listing", and it is stated as a time ratio rather than as the absence
of a temp B-tree — because the temp B-tree legitimately remains on the
score-sorted path and always will.

**Alternatives considered and rejected**:

- **A composite `(match_score DESC, COALESCE(posted_date, first_seen) DESC)`
  index** to serve the default sort — built and measured: 318 ms vs 332 ms on
  the wide view and no change on the default view, because the dynamic WHERE
  clause stops SQLite using it for ordering. **Rejected: measurably useless.**
- **Dropping the redundant `match_score IS NULL` sort key** (SQLite already
  sorts NULLs last under DESC, so it is a no-op there) — would make the ORDER
  BY marginally more indexable but changes documented feed ordering semantics
  on other engines for no measured gain. **Rejected.**
- **A stored `sort_date` column maintained by triggers** — more moving parts
  and a migration over 22k rows, for the same 2.1× on one view. **Rejected.**
- **Dropping the item entirely** — defensible, since the default view is fine.
  Kept only because the index is one line, measurably helps the widest view,
  and regresses nothing.

---

## R8 — iCIMS advance selectors

**Decision**: Promote iCIMS from generic fallback to allowlist-first, matching
Workday, Greenhouse, Lever and Ashby.

**Evidence**: `ADVANCE_ALLOWLIST` (`engine/autofill/adapters.py:46`) already
carries an iCIMS entry (`#quickApplyNextButton, .iCIMS_nextButton`), and 019
shipped it untested against any fixture — the assumption recorded in
`specs/019-door-to-door/spec.md` is that iCIMS receives "only the conservative
generic fallback this release".

**Rationale**: The parity test between `adapters.py` and `advancer.js` already
exists, so the work is a fixture plus a journey test rather than new
machinery. All 019 safety rules (one-shot per rendered step, hard cap,
final-class refusal, pause on needs-you/CAPTCHA) apply unchanged — this widens
recognition, not permission.
