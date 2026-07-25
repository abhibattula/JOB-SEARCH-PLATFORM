"""015 (US1, FR-001/FR-001a/FR-004): the single-owner on-device AI worker.

Every local-model call in the app routes through this module. ONE daemon
worker thread executes requests strictly one-at-a-time — llama-cpp model
objects are not thread-safe, and unserialized concurrent inference is exactly
what produced the recorded ggml-cpu.dll access violation (feature 015 root
cause). Serialization here is by construction, not by caller discipline:
`local_llm.chat()` and `semantic.embed()` are thin wrappers over `run_chat`/
`run_embed`, so every existing call site (scoring, drafting, suggestions,
tailoring, profile import, embeddings) is covered without edits.

Guarantees (contracts/inference-api.md):
- single-flight: at most one model call executes at any instant;
- bounded wait: every submission resolves or raises RuntimeError within its
  time budget (chat 180s / embed 30s, JOBS_AI_TIMEOUT_* overridable);
- bounded backlog: a full queue (maxsize 32) fails the submission immediately
  instead of stacking caller threads (FR-001a);
- callers MUST NOT hold browser_controller._lock (or any lock a status
  endpoint needs) while calling in — see _value_for_tag's park-then-draft.

The worker seam is also where R2's subprocess isolation slots in
(JOBS_AI_SUBPROCESS routes execution to a supervised child with the same
guarantees) — see run_subprocess notes in research.md R2.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as _FutureTimeout

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUTS = {"chat": 180.0, "embed": 30.0}
_TIMEOUT_ENV = {"chat": "JOBS_AI_TIMEOUT_CHAT", "embed": "JOBS_AI_TIMEOUT_EMBED"}
_DEFAULT_QUEUE_MAX = 32

_lifecycle_lock = threading.Lock()  # guards worker/queue creation + teardown
_queue: queue.Queue | None = None
_worker: threading.Thread | None = None
_queue_max = _DEFAULT_QUEUE_MAX

# test seam: {"chat": fn(payload)->str, "embed": fn(payload)->list} or None
_executors_override: dict | None = None

# single-flight instrumentation (FR-001 proof hook)
_metrics_lock = threading.Lock()
_in_flight = 0
_max_seen = 0


class _Request:
    __slots__ = ("kind", "payload", "future", "abandoned")

    def __init__(self, kind: str, payload: dict) -> None:
        self.kind = kind
        self.payload = payload
        self.future: Future = Future()
        # set when the submitting caller gave up (timeout) while this request
        # was still queued — the worker skips it instead of wasting minutes
        self.abandoned = False


def _timeout_for(kind: str) -> float:
    env = os.environ.get(_TIMEOUT_ENV[kind])
    if env:
        try:
            return float(env)
        except ValueError:
            log.warning("ignoring invalid %s=%r", _TIMEOUT_ENV[kind], env)
    return _DEFAULT_TIMEOUTS[kind]


def _resolve_executor(kind: str):
    """Late-bound so importing this module never imports llama-cpp; the real
    executors live where the models live."""
    if _executors_override is not None:
        return _executors_override[kind]
    if kind == "chat":
        from . import local_llm

        return local_llm._chat_impl
    from . import semantic

    return semantic._embed_impl


def _worker_loop(q: queue.Queue) -> None:
    global _in_flight, _max_seen
    while True:
        req = q.get()
        if req is None:  # shutdown sentinel (tests)
            return
        if req.abandoned:
            continue  # caller already gave up while this sat in the queue
        with _metrics_lock:
            _in_flight += 1
            _max_seen = max(_max_seen, _in_flight)
        try:
            executor = _resolve_executor(req.kind)
            result = executor(req.payload)
        except Exception as exc:
            log.warning("on-device AI %s failed", req.kind, exc_info=True)
            if not req.future.done():
                req.future.set_exception(
                    RuntimeError(f"on-device AI {req.kind} failed: {exc}")
                )
        else:
            if not req.future.done():
                req.future.set_result(result)
        finally:
            with _metrics_lock:
                _in_flight -= 1


def _ensure_worker() -> queue.Queue:
    global _queue, _worker
    with _lifecycle_lock:
        if _queue is None:
            _queue = queue.Queue(maxsize=_queue_max)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(
                target=_worker_loop, args=(_queue,),
                name="je-inference", daemon=True,
            )
            _worker.start()
        return _queue


def _submit(kind: str, payload: dict, timeout_s: float | None):
    timeout = timeout_s if timeout_s is not None else _timeout_for(kind)
    request = _Request(kind, payload)
    q = _ensure_worker()
    try:
        q.put_nowait(request)
    except queue.Full:
        raise RuntimeError(
            "the on-device AI is busy (request queue full) — try again shortly"
        ) from None
    try:
        return request.future.result(timeout=timeout)
    except _FutureTimeout:
        request.abandoned = True
        raise RuntimeError(
            f"on-device AI {kind} timed out after {timeout:g}s"
        ) from None


def run_chat(messages: list[dict], json_mode: bool = False,
             timeout_s: float | None = None) -> str:
    """Serialized chat completion. Raises RuntimeError on unavailability,
    failure, timeout, or saturation — the exact failure class every caller
    already tolerates (matcher tier fall-through / qa.draft → None)."""
    return _submit("chat", {"messages": messages, "json_mode": bool(json_mode)},
                   timeout_s)


def run_embed(text: str, timeout_s: float | None = None) -> list[float]:
    """Serialized embedding. Same failure contract as run_chat;
    semantic.embed() converts failures to None (its public behavior)."""
    return _submit("embed", {"text": text}, timeout_s)


def max_observed_concurrency() -> int:
    """Test/diagnostics hook: the highest number of simultaneously executing
    model calls ever observed in this process. MUST be 1 (FR-001)."""
    with _metrics_lock:
        return _max_seen


def set_executors_for_tests(executors: dict | None) -> None:
    global _executors_override
    _executors_override = executors


def reset_for_tests(queue_max: int | None = None) -> None:
    """Tear down the worker/queue and reset metrics + overrides so each test
    starts from a clean, optionally re-sized owner."""
    global _queue, _worker, _queue_max, _executors_override, _in_flight, _max_seen
    with _lifecycle_lock:
        if _queue is not None:
            try:
                _queue.put_nowait(None)
            except queue.Full:  # drain one slot, then insist on the sentinel
                try:
                    _queue.get_nowait()
                except queue.Empty:
                    pass
                _queue.put_nowait(None)
        if _worker is not None:
            _worker.join(timeout=2)
        _queue = None
        _worker = None
        _queue_max = queue_max or _DEFAULT_QUEUE_MAX
        _executors_override = None
    with _metrics_lock:
        _in_flight = 0
        _max_seen = 0
