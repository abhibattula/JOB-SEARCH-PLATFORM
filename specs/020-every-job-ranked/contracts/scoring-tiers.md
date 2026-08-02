# Contract: scoring tiers and the refresh lifecycle

Splits today's single `_score_new_jobs()` into two stages with different
guarantees, different costs, and different places in the run.

---

## Stage 1 — Ranking (`pipeline._rank_new_jobs`)

**Inside** the refresh run, in `_post_ingest`, before liveness/prune/alerts.

| property | value |
|---|---|
| tier | `basic_match.score()` only |
| cap | **none** (FR-001) |
| cost | 0.0044 s/job — the applicant's 627-job backlog in 2.8 s |
| model | never touched (FR-002) |
| writes | `match_score` + `match_json` with `method: "basic"` |
| candidates | every eligible job with `match_score IS NULL` |

**Guarantees**

- **R1** — after this stage, zero eligible jobs are unscored.
- **R2** — it completes with the on-device and cloud AI both unavailable.
  *Test: patch `local_llm` and `matcher._chat` to raise; assert full coverage.*
- **R3** — it never overwrites an existing score of any tier.
- **R4** — `profile_skills` from the applicant's Profile are passed through to
  `basic_match.score(extra_skills=…)`, as today.

---

## Stage 2 — Assessment (`engine/upgrade.py`)

**Outside** the run, on a background thread. Full contract in
[upgrade-api.md](./upgrade-api.md).

| property | value |
|---|---|
| tier | `matcher.analyze_match()` → `local` or `llm` |
| cap | `MAX_SCORE_PER_RUN`, default **40** per pass |
| cost | ~67 s/job on the applicant's laptop |
| writes | `match_score` + full analysis + `method: "local"`/`"llm"` |
| candidates | `jobs_needing_score(upgrade_methods=("basic",))`, best-first |

---

## `_post_ingest` order (changed)

```
  before                          after
  ──────                          ─────
  delist_missing                  delist_missing
  _classify_new_jobs              _classify_new_jobs
  _score_new_jobs   ◀── hours     _rank_new_jobs      ◀── seconds, uncapped
  _check_scraped_liveness         _check_scraped_liveness
  prune_old_jobs                  prune_old_jobs
  alerts.process    ◀── delayed   alerts.process      ◀── on time
  [finish_run]                    [finish_run]
                                  upgrade.start()     ◀── after the run closes
```

**Guarantees**

- **L1** (FR-007) — `db.finish_run()` is reached without waiting on any
  inference. *Test: with a `matcher` stub that sleeps, the run still finishes
  promptly.*
- **L2** (FR-008) — `alerts.process()` runs in the same refresh that ingested
  the matching jobs.
- **L3** — `upgrade.start()` is called **after** `finish_run()`, so a slow or
  failing pass can never re-open or extend the run.
- **L4** — `STALE_RUN_MINUTES = 30` is untouched and becomes correct again:
  with scoring out of the run, a run older than 30 minutes really has crashed.
- **L5** — `pipeline` may import `upgrade`; `upgrade` must never import
  `pipeline`.

---

## Presentation (FR-003)

`match_json.method` decides the badge. `job_detail.html:85` already renders
`~` for `basic` and `•` for `local`; `_JOB_COLUMNS` already selects
`match_method`. The feed listing must render the same distinction.

**Guarantee P1** — a `basic` score is never displayed in the same form as an
AI score, on any page. *Test: a feed containing one job of each tier renders
two distinguishable markers.*

This is the honesty requirement of the release: it is the reason making most
scores keyword-derived is acceptable at all.

---

## What does not change

- `MatchAnalysis` shape, its pydantic validation, and its bounded retry.
- `semantic.py` — `order_jobs`, `embed`, the 300/run embedding cap.
- `engine/inference.py` — single-owner worker, FIFO queue, timeouts, subprocess
  isolation.
- `matcher.scoring_tier()` and the cloud/local/basic precedence.
- `MAX_CHARS = 6000` prompt truncation (research R1 — rejected as a default).
- Every automation rule from v1.9.0 (FR-024) and secret hygiene (FR-025).
