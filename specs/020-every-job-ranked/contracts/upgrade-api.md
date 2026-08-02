# Contract: `engine/upgrade.py` — the background assessment pass

Pure Python. Imports nothing from `web/` (Principle IV). Every guarantee below
is a test in `tests/test_upgrade.py`.

---

## Public surface

```python
def start(reason: str = "refresh") -> bool
```

Begin one assessment pass on a daemon thread.

- Returns `True` if a pass was started, `False` if one was already running.
- **Single-flight (FR-009)**: calling `start()` while a pass is live is a
  no-op — never a queued second pass, never a second thread. This is the
  direct fix for the duplicate-loop defect (research R2).
- Never raises. A pass that cannot select candidates simply ends.

```python
def progress() -> dict
```

Read-only snapshot for the status endpoint. Always returns the full shape:

```python
{"running": bool, "done": int, "total": int,
 "failed": int, "paused_for_session": bool}
```

- Safe to call from any thread; never blocks on the pass.
- Before the first pass: `{"running": False, "done": 0, "total": 0,
  "failed": 0, "paused_for_session": False}`.

```python
def run_once(limit: int | None = None) -> dict
```

Synchronous execution of one pass — the seam used by tests and the CLI, the
same way `pipeline.run_refresh` mirrors `trigger_refresh`. Returns the final
`progress()` snapshot. Honours every guarantee below except threading.

```python
def reset_for_tests() -> None
```

Clears pass state. Mirrors the existing `reset_for_tests` convention in
`ext_backend`, `inference`, and `browser_controller`.

---

## Guarantees

### G1 — Candidate selection

Candidates come from `db.jobs_needing_score(limit=…, upgrade_methods=("basic",))`
ordered by `semantic.order_jobs(resume_vec, candidates)`, truncated to the
per-pass limit (`MAX_SCORE_PER_RUN`, default 40).

- Best-first by cosine similarity to the resume (FR-004).
- With no resume vector, incoming date order is kept — `order_jobs` already
  degrades this way and is unchanged.
- Jobs that became ineligible between ranking and assessment are simply not
  returned by the query.

### G2 — One request at a time (FR-014)

The pass calls `matcher.analyze_match()` for **one job, blocks on the result,
then moves to the next**. It MUST NOT enqueue a batch into
`engine/inference.py`.

*Why this is load-bearing*: the inference queue is strict FIFO with no
priority. One-at-a-time submission means any concurrent Apply Assist draft
waits behind at most one assessment (~67 s, inside its 180 s budget). Batching
40 would put a draft behind ~45 minutes.

**Test**: with a stub executor that records queue depth, depth never exceeds
one assessment request attributable to the pass.

### G3 — Yield to applying (FR-013)

Before each job, the pass checks whether an application fill session is live
(a public predicate on `browser_controller`). If one is:

- the pass sets `paused_for_session` and waits;
- it does **not** submit the next assessment;
- it resumes when the session ends.

Applying always outranks ranking. There is no negotiation and no priority
scheme — the pass simply stands down.

**Test**: a drafter request issued while a pass is live resolves within its
normal budget, and `inference.max_observed_concurrency()` stays `1`.

### G4 — Failure isolation (FR-012)

A job whose assessment raises, times out, or returns unparseable output:

- keeps its existing `basic` score — nothing is written;
- increments `failed` and `done`;
- is **not** retried within this pass;
- does not stop the pass.

`matcher.analyze_match()` keeps its own bounded single retry; this contract
adds no second retry layer on top of it.

### G5 — Resumability (FR-010)

No pass state is persisted. Every pass rebuilds its candidate list from the
database, so an interrupted pass (including app close) loses at most the one
job in flight. Restarting is always safe and never double-scores: a job
assessed in a previous pass no longer matches `upgrade_methods=("basic",)`.

### G6 — Never the ranking path

`upgrade.py` never assigns a first score to an unranked job. Ranking is the
refresh's job (`pipeline._rank_new_jobs`) and must not depend on this module
being reachable, running, or successful (FR-002).

---

## Caller contract

| caller | call | notes |
|---|---|---|
| `pipeline._post_ingest` | `upgrade.start("refresh")` | **after** `db.finish_run()`, so the run never waits on it (FR-007) |
| `web/routes_api.py` status | `upgrade.progress()` | read-only; must not block the endpoint |
| `cli.py` | `upgrade.run_once()` | synchronous, headless parity |

`pipeline` imports `upgrade`; `upgrade` MUST NOT import `pipeline` — the
dependency runs one way only.
