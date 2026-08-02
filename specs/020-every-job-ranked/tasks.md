# Tasks: Every Job Ranked

**Input**: Design documents from `/specs/020-every-job-ranked/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R8), data-model.md,
contracts/scoring-tiers.md, contracts/upgrade-api.md, contracts/richtext-fill.md,
checklists/requirements.md (complete)

**Tests**: REQUIRED — hybrid speckit + superpowers TDD. Every pair is
red-then-green: the "Failing tests" task MUST be written and observed to fail
for the right reason before its implementation task starts. Two standing rules
from earlier features apply throughout:

- **Measure, don't guess** — the idle-cost workstream starts with a benchmark,
  not an optimisation (research R6).
- **Never let a string-presence assertion be a control's only coverage** — any
  new UI element gets a test of its observable effect.

**Organization**: grouped by user story (spec.md P1–P6), sequential delivery,
each story independently testable and shippable.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [x] T001 Baseline evidence: record pre-change counts and measurements in
      `specs/020-every-job-ranked/baseline.txt` — unit battery, `-m browser`
      suite, and against `data/jobs.db`: total/eligible/scored/unscored/embedded
      counts, the feed query plan, and the per-job AI assessment timing
- [x] T002 [P] Back up the real database to `data/backup/jobs-pre-2.0.0.db`
      before any stage touches it (quickstart §3)

---

## Phase 2: Foundational (blocks US1 and US2)

> **Corrected during implementation.** T003/T004 originally placed the
> assessment-progress record in `engine/db.py`. That contradicts
> data-model.md §2, which keeps pass state deliberately in-memory — persisting
> nothing is precisely what makes FR-010's resumability free, since every pass
> rebuilds its candidate list from the database anyway. The app serves the web
> layer from the same process, exactly as `browser_controller._state` already
> does, so no storage is involved. Retargeted to the module skeleton.

- [x] T003 [P] Failing tests `tests/test_upgrade.py::TestProgressShape020` —
      `upgrade.progress()` returns the full shape with safe defaults before any
      pass has run (`{running: False, done: 0, total: 0, failed: 0,
      paused_for_session: False}`), is safe to call from any thread, and never
      blocks; `reset_for_tests()` restores those defaults
- [x] T004 Create `engine/upgrade.py` with the state record, `progress()` and
      `reset_for_tests()` — T003 green. Pure Python, imports nothing from
      `web/`, and must not import `pipeline` (guarantee L5)
> **Narrowed during implementation, on measurement.** T005/T006 originally
> claimed the *default* feed view was slow (67.9 ms) and that an index would
> make it single-digit. That baseline came from a hand-written query the app
> never runs. Measured through `db.query_jobs()` the default view is **22 ms**,
> and its ORDER BY leads with `match_score`, which no date index can serve. The
> index helps exactly one view — all jobs, all levels, date order — and only
> **with statistics present**: index alone left the plan unchanged (316 ms);
> index + `ANALYZE` gave 159 ms. `PRAGMA optimize` was measured and does *not*
> substitute. FR-022, SC-009 and research R7 were rewritten to this. See
> baseline.txt.

- [x] T005 [P] Failing test `tests/test_db.py::TestFeedSortIndex020` — the
      date-ordered all-jobs listing plan contains no
      `USE TEMP B-TREE FOR ORDER BY` and names `idx_jobs_sort_date`; the
      score-sorted default still sorts **and that is pinned as expected**; the
      `posted_date`→`first_seen` fallback ordering is preserved. Queries are
      captured from `db.query_jobs` by tracing, never hand-copied
- [x] T006 `engine/db.py`: add `idx_jobs_sort_date` on
      `COALESCE(posted_date, first_seen) DESC` plus `refresh_statistics()` and a
      one-time `_ensure_statistics()` bootstrap in `init_db` — T005 green. A
      test pins that the index is **inert without statistics**, so nobody
      deletes the ANALYZE believing the index alone suffices

**Checkpoint**: storage can describe a pass and serve the feed sort from an
index; nothing user-visible has changed yet

---

## Phase 3: User Story 1 — Every job in my feed has a score (P1) 🎯 MVP

**Goal**: after one refresh, zero eligible jobs are unranked — with or without
the model.

**Independent Test**: seed a backlog of unscored eligible jobs, run one
refresh with inference patched to raise, assert full coverage.

> **Two corrections from implementation.**
> 1. **Embedding moved out of the refresh.** `_score_new_jobs` embedded up to
>    300 jobs inline at 0.60 s each — 180 s, which alone would blow SC-003's
>    60-second budget. Embeddings exist only to ORDER the assessment pass, so
>    they belong to that pass. `_rank_new_jobs` is purely deterministic.
> 2. **T012 was already done.** The plan claimed "the feed template never
>    reads `match_method`". It does — `partials/feed_table.html:52-54` has
>    rendered `~` for basic and `•` for local, with explanatory tooltips,
>    since an earlier feature. What was missing was a TEST, which this release
>    makes load-bearing because most scores now become `basic`.

- [x] T007 [P] [US1] Failing tests `tests/test_pipeline.py::TestRanking020` —
      (a) every eligible unscored job gets a score after one refresh with **no
      cap applied**; (b) coverage still 100% when `matcher._chat` and
      `local_llm` both raise (FR-002, guarantee R2); (c) an existing score of
      any tier is never overwritten (R3); (d) `profile_skills` reach
      `basic_match.score(extra_skills=…)` (R4); (e) a job with an empty
      description still receives a score
- [x] T008 [US1] `engine/pipeline.py`: extract `_rank_new_jobs()` from
      `_score_new_jobs()` — uncapped, model-free, `method: "basic"`, reusing
      `basic_match.score()` unchanged — T007 green
- [x] T009 [P] [US1] Failing test `tests/test_pipeline.py::TestRankingThroughput020`
      — ranking a backlog the size of the applicant's (627 jobs) completes well
      inside the SC-002 budget with the model never touched
- [x] T010 [US1] Verify T009 green against the real baseline; record the
      measured figure in `baseline.txt` beside the pre-change number
- [x] T011 [P] [US1] Failing test `tests/test_web.py::TestFeedScoreKind020` — a
      feed listing containing one `basic`-scored and one `local`-scored job
      renders two **distinguishable** markers (guarantee P1, FR-003); assert the
      rendered distinction, not merely that the template mentions `method`
- [x] T012 [US1] **No code change needed** — `partials/feed_table.html:52-54`
      already renders `~`/`•` from `match_method` with explanatory tooltips.
      Verified by T011 rather than rewritten

**Checkpoint**: the feed is 100% ranked and honest about which scores are
keyword-derived. Shippable on its own.

---

## Phase 4: User Story 2 — The refresh finishes, and says what it is doing (P2)

**Goal**: the run closes in seconds, alerts fire on time, and exactly one
assessment pass can exist.

**Independent Test**: run a refresh with a deliberately slow `matcher` stub;
the run still finishes promptly and alerts fire in the same refresh.

- [x] T013 [P] [US2] Failing tests `tests/test_upgrade.py::TestPassSelection020`
      — candidates come from `jobs_needing_score(upgrade_methods=("basic",))`
      ordered by `semantic.order_jobs`, truncated to the per-pass limit
      (guarantee G1, FR-004); with no resume vector the incoming order is kept
- [x] T014 [P] [US2] Failing tests `tests/test_upgrade.py::TestSingleFlight020`
      — `start()` while a pass is running returns `False`, spawns no second
      thread, and leaves `progress()["total"]` unchanged (FR-009, SC-005)
- [x] T015 [P] [US2] Failing tests `tests/test_upgrade.py::TestFailureIsolation020`
      — a job whose assessment raises keeps its `basic` score, increments
      `failed`, is not retried within the pass, and does not stop the pass
      (FR-012, guarantee G4)
- [x] T016 [P] [US2] Failing tests `tests/test_upgrade.py::TestResume020` —
      no pass state is persisted; a fresh pass rebuilds candidates from the
      database and never re-assesses an already-assessed job (FR-010, G5)
- [x] T017 [US2] `engine/upgrade.py`: implement `start` and `run_once` on the
      T004 skeleton, per contracts/upgrade-api.md — T013–T016 green
- [x] T018 [P] [US2] Failing tests `tests/test_pipeline.py::TestRunLifecycle020`
      — with a `matcher` stub that sleeps: (a) `db.finish_run()` is reached
      promptly (FR-007, L1); (b) `alerts.process()` runs in the same refresh
      that ingested the jobs (FR-008, L2); (c) `upgrade.start()` is called
      **after** `finish_run()` (L3); (d) a second refresh is accepted under the
      ordinary cooldown rather than refused as `running`
- [x] T019 [US2] `engine/pipeline.py`: reorder `_post_ingest` to
      delist → classify → rank → liveness → prune → alerts, and start the
      assessment pass after `db.finish_run()` — T018 green. Delete the old
      inline AI scoring loop; **do not keep it behind a flag**
- [x] T020 [P] [US2] Failing test `tests/test_pipeline.py::TestStaleWindow020`
      — a refresh no longer outlives `STALE_RUN_MINUTES`, so a run older than
      the window really has crashed (L4). `STALE_RUN_MINUTES` itself is
      unchanged — assert the value is still 30 so a future edit is deliberate
- [x] T021 [P] [US2] Failing tests `tests/test_settings.py::TestAssessmentLimit020`
      + `tests/test_api.py` — `MAX_SCORE_PER_RUN` now means AI assessments per
      pass, defaults to 40, is surfaced in Settings with copy that says so, and
      is read by `upgrade` rather than by ranking (FR-006)
- [x] T022 [US2] `web/templates/settings.html` + `engine/settings.py`: implement
      the changed key's default and disclosure — T021 green
- [x] T023 [P] [US2] Failing tests `tests/test_api.py::TestAssessmentProgress020`
      — the status payload carries the additive `assessment` object; absent or
      `running: false` renders nothing; the endpoint never blocks on the pass
      (FR-011)
- [x] T024 [US2] `web/routes_api.py` + `web/templates/feed.html`: expose and
      render "AI-scoring _n_ / _total_" — T023 green
- [x] T025 [US2] `cli.py`: wire `upgrade.run_once()` for headless parity
      (constitution: the full pipeline MUST be runnable headless)

**Checkpoint**: the refresh is honest and bounded; assessment runs in the
background, once, resumably, visibly.

---

## Phase 5: User Story 3 — Applying always beats ranking (P3)

**Goal**: the background pass never slows an application down. **This must land
with Phase 4, not after it** — Phase 4 is what creates the risk.

**Independent Test**: a drafter request issued during a live pass resolves
inside its normal budget.

- [x] T026 [P] [US3] Failing test
      `tests/test_browser_controller.py::TestLiveSessionPredicate020` — a public
      predicate reports whether a fill session is live, reading `_state.running`
      under `_lock`, and never deadlocks against a status call
- [x] T027 [US3] `engine/autofill/browser_controller.py`: add the predicate —
      T026 green
- [x] T028 [P] [US3] Failing test `tests/test_upgrade.py::TestOneAtATime020` —
      with a stub executor recording queue depth, the pass never has more than
      one assessment request outstanding; it blocks on each result before
      selecting the next (FR-014, guarantee G2)
- [x] T029 [P] [US3] Failing test `tests/test_upgrade.py::TestStandDown020` —
      while a fill session is live the pass sets `paused_for_session`, submits
      nothing, and resumes when the session ends (FR-013, G3)
- [x] T030 [US3] `engine/upgrade.py`: implement one-at-a-time submission and the
      fill-session stand-down — T028, T029 green
- [x] T031 [P] [US3] Failing test `tests/test_inference.py::TestNoStarvation020`
      — **the regression test that matters most**: a drafter request issued
      during a live pass resolves within its budget, and
      `inference.max_observed_concurrency()` is still `1` (FR-015, SC-006)
- [x] T032 [US3] Confirm T031 green with no change to `engine/inference.py` —
      if the module needs editing, stop and re-read research R3, which rejected
      a priority queue for exactly this reason

**Checkpoint**: ranking yields to applying, provably.

---

## Phase 6: User Story 4 — Rich-text cover letters fill (P4)

**Goal**: a rich-text cover letter is discovered, filled, or flagged — never
silently absent.

**Independent Test**: fixture pages with rich-text editors are counted, written,
and verified in a real browser.

- [x] T033 [P] [US4] Create fixtures
      `tests/fixtures/ats_pages/richtext_cover_letter.html` (Greenhouse-style
      `div[contenteditable=true]` labelled by `aria-labelledby`, required) and
      `lever_richtext.html` (`[role=textbox]` in a wrapping label, with an
      editor-rendered placeholder child)
- [x] T034 [P] [US4] Failing tests `tests/test_extension_assets.py` — the
      scanner selector covers `[contenteditable]` / `[role=textbox]`, and the
      `scanner.js` ↔ `watcher.py` SERIALIZE_JS parity assertion is extended to
      the rich-text branch (guarantee S3)
- [x] T035 [US4] `extension/content/scanner.js`: add rich-text to
      `FIELD_SELECTOR`; `type: "richtext"`; read `innerText`; apply the
      credential-form, readonly, visibility and placeholder exclusions — T034
      green
- [x] T036 [US4] `engine/autofill/watcher.py`: mirror the change in
      `SERIALIZE_JS` — parity green. **Edit the raw string with literal edits**;
      a heredoc mangles `\s` and broke the whole serializer in 019
- [x] T037 [P] [US4] Failing tests `tests/test_field_core.py::TestRichText020` +
      `tests/test_fields.py` — a `richtext` descriptor is decided like a
      `textarea` (D1); it counts as text-ish (S2); with no `name`,
      classification falls back to `automation_id`/`id`/label and an
      unclassifiable box stays `free_text_unknown`, never a wrong tag (D3)
- [x] T038 [US4] `engine/autofill/field_core.py` + `fields.py`: implement the
      rich-text decision path — T037 green
- [x] T039 [P] [US4] Failing test `tests/test_escort.py::TestRichTextPending020`
      — a visible required rich-text box holding no answer counts toward
      `visible_required_pending`, so the escort will not advance past an empty
      cover letter (FR-019, D2)
- [x] T040 [US4] Wire the rich-text field into the required-pending count in
      `engine/autofill/ext_backend.py` — T039 green
- [x] T041 [P] [US4] Failing browser tests
      `tests/integration/test_autofill_fixture_pages.py::TestRichTextFill020` —
      on both fixtures: the box is counted; the text lands; a real `input` event
      fires so the host page registers it (W1); the written value is verified by
      re-reading `innerText` (W2)
- [x] T042 [US4] `extension/content/filler.js`: add the `kind: "richtext"` write
      branch — focus, select contents, insert, dispatch `input`+`change`,
      re-read and verify — T041 green. **`filler.js` must still contain exactly
      one raw `.click(` site** (the 016 pin) — this branch adds none
- [x] T043 [P] [US4] Failing browser test — an editor that rejects the write
      degrades to `needs_manual` naming the field, and appears as a needs-you
      item on the panel; there is no silent third state (FR-018, W2)
- [x] T044 [US4] Implement the verify-and-degrade path — T043 green

**Checkpoint**: the last known silent gap in the fill path is closed.

---

## Phase 7: User Story 5 — Companion idle cost (P5)

**Goal**: at least halve the periodic inspection cost on form-free pages
without losing any detection.

**Independent Test**: the benchmark from T045, before and after.

- [x] T045 [US5] **Measure first.** Add a real-browser benchmark timing
      `scanner.probe()` per tick on a large form-free fixture page; record the
      pre-change number in `baseline.txt`. No optimisation in this task
- [x] T046 [P] [US5] Failing tests `tests/test_extension_assets.py` +
      `tests/integration/` — after N consecutive `classify() === "none"` ticks
      the poll interval increases (FR-020), and the shadow-root
      `querySelectorAll("*")` walk is skipped when the page has no shadow host
      and no cheap selector hit
- [x] T047 [US5] `extension/content/discovery.js` + `scanner.js`: implement the
      backoff and the shadow-walk skip — T046 green
- [x] T048 [P] [US5] Failing browser test — a form appearing after backoff,
      **including after in-page navigation**, is still detected without a
      noticeable delay (FR-021). This is the regression the backoff could cause
- [x] T049 [US5] Verify T048 green and re-run T045's benchmark; assert at least
      a 50% reduction (SC-008) and record both numbers

**Checkpoint**: the companion is cheap to keep installed.

---

## Phase 8: User Story 6 — iCIMS advance (P6)

**Goal**: iCIMS advances allowlist-first like every other supported site.

- [x] T050 [P] [US6] Create fixture `tests/fixtures/ats_pages/icims_step.html`
      with an iCIMS-shaped next control and a terminal submit step
- [x] T051 [P] [US6] Failing tests `tests/test_adapters.py` +
      `tests/test_extension_assets.py` — the iCIMS `ADVANCE_ALLOWLIST` entry is
      exercised and the `adapters.py` ↔ `advancer.js` parity assertion covers it
- [x] T052 [US6] `engine/autofill/adapters.py` + `extension/content/advancer.js`:
      finalise the iCIMS selectors — T051 green
- [x] T053 [P] [US6] Failing browser test
      `tests/integration/test_escort_journeys.py::TestICIMSAdvance020` — the
      step advances by the iCIMS control, once per rendered step, and **stops at
      the final Submit with it provably un-clicked** (FR-023, FR-024)
- [x] T054 [US6] Verify T053 green; confirm the click is recorded in the
      activity ledger like every other progression click

**Checkpoint**: iCIMS has parity with Workday and Greenhouse.

---

## Phase 9: Polish, docs, ship

- [ ] T055 [P] Update `docs/USER_MANUAL.md` — line 81's "a few minutes" becomes
      true rather than edited around; document the two scoring tiers, the
      background pass, and the changed meaning of `MAX_SCORE_PER_RUN`
- [ ] T056 [P] Update `docs/USER_GUIDE.md` and `README.md` for the two-tier
      scoring model and the rich-text cover-letter support
- [ ] T057 [P] Add `WHATS_NEW["2.0.0"]`
- [ ] T058 Re-run the full unit battery **twice** and the `-m browser` suite;
      counts must exceed the T001 baseline, never fall below it
- [ ] T059 Run `tests/test_secret_hygiene.py` — secrets remain fill-and-forget
      (FR-025)
- [ ] T060 Run the **real-data check** (quickstart §3) against the applicant's
      own database: 0 eligible unscored, refresh under 60 s, and the same run
      repeated with inference forced to fail
- [ ] T061 Frozen build + `packaging/smoke_test.py`; the smoke must still assert
      only against the HTTP surface and never import `engine`
- [ ] T062 Bump the version byte-safely in `engine/__init__.py`,
      `extension/manifest.json`, `packaging/windows.iss`
- [ ] T063 Manual: quickstart §4 (one pass, no duplicates, resume), §5
      (**applying beats ranking** — the regression most likely to be caused by
      this release), §6 (rich-text on a real Greenhouse or Lever form)
- [ ] T064 Manual: quickstart §10 — the automation line unchanged, **including
      019's still-outstanding T076**: install, press ↻ on the companion card at
      `chrome://extensions`, save a Workday login, run one real Workday
      application to Review and confirm Submit is never clicked; one real
      Greenhouse navigate-apply; one LinkedIn zero-click control
- [ ] T065 Tag `v2.0.0`; verify **both** installers from the release body by
      magic bytes (`4d5a` / `7801`) and SHA-256. A green build is not evidence
- [ ] T066 Update memory files with the release outcome and any new lessons

---

## Dependencies

```
Setup (T001-T002)
   └─▶ Foundational (T003-T006)
          ├─▶ US1 (T007-T012) ── shippable MVP: the feed is 100% ranked
          │      └─▶ US2 (T013-T025) ── the run lifecycle
          │             └─▶ US3 (T026-T032) ── MUST ship with US2
          ├─▶ US4 (T033-T044) ── independent of all scoring work
          ├─▶ US5 (T045-T049) ── independent; T045 strictly before T046
          └─▶ US6 (T050-T054) ── independent
                 └─▶ Polish + ship (T055-T066)
```

**Hard ordering rules**

- **US3 must not be deferred past US2.** US2 is what lets the pass run at any
  time; US3 is the only thing preventing that from breaking Apply Assist.
- **T045 before T046.** The benchmark precedes the optimisation — research R6.
- **T036 immediately after T035.** The serializer parity test fails the moment
  the scanner changes; leaving it red invites the 019 raw-string incident.

## Parallel opportunities

US4, US5 and US6 touch disjoint files and can run alongside the scoring work.
Within each phase, `[P]` tasks are independent; the failing-test task and its
implementation task are never parallel with each other.

## MVP scope

**Phase 1 → Phase 3.** That alone takes the applicant's feed from 33% to 100%
ranked, which is the reported problem. Everything after it is lifecycle
correctness, safety, and reach.
