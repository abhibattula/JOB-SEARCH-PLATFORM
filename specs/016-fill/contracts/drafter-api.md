# Contract: Drafter API (engine-internal, 016)

Module: `engine/autofill/drafter.py`. Consumers: `ext_backend` (decide
loop), `browser_controller` (assistant path + activity list), web status
payloads (read-only). The drafter is the ONLY component that may invoke
generation for form questions; `_handle_fields` and every bridge handler
are forbidden from calling models (regression-tested).

## API

```python
ensure(job_id: int, question: str, descriptor_ctx: dict, profile: dict) -> None
    # Idempotent; schedules at most one draft per key per session.
    # descriptor_ctx: {"type", "options", "maxlength", "tag"}.
    # Returns immediately; never blocks on inference.

get(job_id: int, question: str) -> dict | None
    # {"state": "drafting|done|failed", "answer": str|None,
    #  "attempts": int, "next_retry_at": float}
    # None if never requested.

answer_for(job_id: int, question: str) -> str | None
    # Fast path for the decide loop: validated answer or None.

reset_backoff_for(job_id: int, questions: list[str]) -> None
    # Fill-again support: failed keys become immediately retryable.

cache_version() -> int
    # Monotonic; bumps on every completed draft (ledger retryability).

stats() -> dict          # counts for doctor/tests
reset_for_tests() -> None
```

## Behavioral guarantees

1. **One draft per key per session** — `key = (job_id, normalized
   question)`; concurrent `ensure` calls coalesce (SC-003).
2. **Bounded concurrency** — pool of 2; all generation goes through the
   serialized inference owner with purpose-scoped `max_tokens` and
   timeouts (R13).
3. **Constrained output** (R7):
   - options present → answer MUST be one of them (post-validated) else
     state=`failed:no_valid_option` → field stays unfilled + `needs_you`;
   - `custom_combobox` → ≤4-word literal label;
   - text → length ≤ `maxlength` when set.
4. **No-AI paths**: profile-fact yes/no tags answer from the profile
   synchronously (not via the pool); SENSITIVE tags (`eeo_*`,
   demographic/disability/veteran/criminal/references) never enter the
   drafter — `ensure` records state `failed:sensitive` immediately.
5. **Backoff**: failures retry no sooner than 30 s, doubling to a 600 s
   cap; `reset_backoff_for` clears the wait once per explicit user action.
6. **Completion side effects** (in order): validate → cache write + bump
   `cache_version` → answer-bank auto-save (`origin='ai'`, `job_id` scoped
   for job-specific prose per data-model §6) → ledger clear for affected
   fields → `rescan` push (companion) / FORCE_TICK (assistant window).
7. **Isolation**: drafter threads hold NO browser_controller lock while
   drafting (015 R3 invariant preserved).

## Error contract

All failures are absorbed into `state="failed"` + reason string; the
drafter never raises into the decide loop and never crashes a worker
thread (blanket per-task guard, logged at WARNING).
