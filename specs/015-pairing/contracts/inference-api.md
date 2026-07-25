# Contract: engine-internal inference API (R1/R2)

Module: `engine/inference.py` — the ONLY path by which on-device models
execute. `engine/local_llm.chat()` and `engine/semantic.embed()` are thin
wrappers over it; no other module may invoke llama objects directly (guarded
by test).

## API

```python
run_chat(messages: list[dict], json_mode: bool = False,
         timeout_s: float | None = None) -> str
    # raises RuntimeError on: model unavailable, load failure, timeout,
    # queue saturation, runtime fault. Never raises anything else.

run_embed(text: str, timeout_s: float | None = None) -> list[float]
    # same failure contract; semantic.embed() converts failures to None
    # (its existing public behavior is unchanged).
```

Defaults: `timeout_s` = 180 (chat) / 30 (embed), env-overridable via
`JOBS_AI_TIMEOUT_CHAT` / `JOBS_AI_TIMEOUT_EMBED`.

## Guarantees

1. **Single-flight**: at most one model call executes at any instant,
   process-wide, regardless of caller count (SC-001). Loading counts as a
   call.
2. **Bounded wait**: every submission resolves within its timeout or fails
   with `RuntimeError` — no indefinite blocking.
3. **Bounded backlog**: queue maxsize 32; a full queue fails the submission
   immediately (clean `RuntimeError`), it does not block the caller.
4. **Callers' contracts unchanged**: `local_llm.chat` raises `RuntimeError`
   exactly as today; `semantic.embed` returns `None` on any failure exactly
   as today. No call-site changes are required for correctness.
5. **No lock coupling**: callers MUST NOT hold `browser_controller._lock` (or
   any facade lock a status endpoint needs) while calling this API. The
   pending-suggestion flow parks first, generates after (R3).

## Test hooks

- `inference._max_observed_concurrency()` (or equivalent) for the 8-thread
  hammer assertion (== 1).
- Stub-model injection seam (factory/monkeypatch) so unit tests never load a
  real model.

## Subprocess mode (spike, R2)

`JOBS_AI_SUBPROCESS=1` routes execution to a spawned child over a Pipe with
the SAME API and guarantees, plus:

6. **Fault containment**: child death fails only the in-flight request
   (`RuntimeError`), sets a `runtime_restarted` flag (doctor-visible), and the
   next request relaunches the child. The app process never dies from a model
   fault (SC-011).

GO/NO-GO: frozen Windows smoke + mac CI green with the mode ON. NO-GO ⇒ the
env default stays off and this section remains spike-documented only.
