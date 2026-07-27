"""016 (T003, R2/R7): the bounded background drafter.

The ONLY component allowed to invoke generation for form questions. The
bridge decide loop and every message handler stay model-free (R1): they
call `ensure()` (fire-and-forget) and read `answer_for()`; completed
drafts land here first, then flow to the answer bank and the page.

Guarantees (contracts/drafter-api.md):
- one draft per (job, normalized question) per session — the direct fix
  for the observed infinite re-draft loop;
- bounded concurrency (2 workers) feeding the serialized inference owner;
- validated output (option membership / maxlength) — never prose into a
  choice field;
- sensitive questions NEVER generate (structural replacement for the
  removed human approval gate);
- exponential backoff on failure (30 s → ×2 → 600 s cap), reset once per
  explicit user Fill-again;
- completion side-effect order: cache (+version bump) → bank auto-save →
  on-complete callbacks (ledger clear + rescan push are registered by the
  backends, keeping this module free of transport imports).
"""
from __future__ import annotations

import logging
import queue
import re
import threading
import time

log = logging.getLogger(__name__)

POOL_SIZE = 2
_DEFAULT_BACKOFF_BASE_S = 30.0
_DEFAULT_BACKOFF_CAP_S = 600.0

# Question classes that must NEVER be AI-answered (FR-013). Left unfilled
# and flagged for the human on the page.
SENSITIVE_TAGS = {
    "eeo_disclosure", "demographics", "disability", "veteran_status",
    "criminal_history", "references",
}

# Auto-saved answers for these tags are scoped to their job — a "why this
# company" essay must never auto-fill another company's form (spec
# clarification 2026-07-27). Everything else saves as reusable fact.
JOB_SCOPED_TAGS = {"cover_letter", "free_text_unknown"}

_lock = threading.Lock()
_records: dict[tuple[int, str], dict] = {}
_tasks: queue.Queue | None = None
_workers: list[threading.Thread] = []
_cache_version = 0
_backoff_base_s = _DEFAULT_BACKOFF_BASE_S
_backoff_cap_s = _DEFAULT_BACKOFF_CAP_S

_generator_override = None
_bank_save_override = None
_on_complete: list = []


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip()).casefold()


def _key(job_id: int, question: str) -> tuple[int, str]:
    return (int(job_id), normalize_question(question))


def _default_generator(question: str, descriptor_ctx: dict, profile: dict):
    """Production generation — descriptor-aware prompting lands in T012;
    until then route to the existing suggester."""
    from . import answer_bank

    return answer_bank.suggest(question, descriptor_ctx.get("tag"), profile)


def _default_bank_save(*, question: str, answer: str, tag: str,
                       origin: str, job_id: int | None) -> None:
    from . import answer_bank

    answer_bank.save_auto(question=question, answer=answer, tag=tag,
                          origin=origin, job_id=job_id)


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def _validate(answer: str | None, descriptor_ctx: dict):
    """Returns (ok, canonical_answer_or_None, fail_reason)."""
    if not answer or not str(answer).strip():
        return False, None, "empty"
    answer = str(answer).strip()
    options = descriptor_ctx.get("options") or []
    if options:
        wanted = _normalize_for_match(answer)
        for option in options:
            if _normalize_for_match(option) == wanted:
                return True, option, None  # canonical option text wins
        return False, None, "no_valid_option"
    maxlength = descriptor_ctx.get("maxlength")
    if maxlength and len(answer) > int(maxlength):
        answer = answer[:int(maxlength)].rstrip()
    return True, answer, None


def _worker_loop(tasks: queue.Queue) -> None:
    global _cache_version
    while True:
        item = tasks.get()
        if item is None:  # shutdown sentinel
            return
        key, question, descriptor_ctx, profile = item
        generator = _generator_override or _default_generator
        try:
            raw = generator(question, descriptor_ctx, profile)
        except Exception as exc:  # noqa: BLE001 — a draft may never crash a worker
            log.warning("draft generation failed for %r", question,
                        exc_info=True)
            raw, gen_error = None, f"generator_error: {exc}"
        else:
            gen_error = None
        ok, canonical, reason = _validate(raw, descriptor_ctx)
        if gen_error is not None:
            ok, reason = False, "generator_error"
        if ok:
            with _lock:
                rec = _records.get(key)
                if rec is None:
                    continue  # reset happened mid-flight
                rec.update(state="done", answer=canonical, reason=None)
                _cache_version += 1
            _run_completion_effects(key[0], question, canonical,
                                    descriptor_ctx)
        else:
            with _lock:
                rec = _records.get(key)
                if rec is None:
                    continue
                rec["attempts"] += 1
                delay = min(_backoff_cap_s,
                            _backoff_base_s * (2 ** (rec["attempts"] - 1)))
                rec.update(state="failed", reason=reason,
                           next_retry_at=time.monotonic() + delay)


def _run_completion_effects(job_id: int, question: str, answer: str,
                            descriptor_ctx: dict) -> None:
    tag = descriptor_ctx.get("tag") or "free_text_unknown"
    scoped_job = job_id if tag in JOB_SCOPED_TAGS else None
    bank_save = _bank_save_override or _default_bank_save
    try:
        bank_save(question=question, answer=answer, tag=tag, origin="ai",
                  job_id=scoped_job)
    except Exception:  # noqa: BLE001 — bank trouble must not lose the draft
        log.warning("auto-save to answer bank failed", exc_info=True)
    for callback in list(_on_complete):
        try:
            callback(job_id, question, answer)
        except Exception:  # noqa: BLE001
            log.warning("drafter on_complete callback failed", exc_info=True)


def _ensure_workers() -> queue.Queue:
    global _tasks
    if _tasks is None:
        _tasks = queue.Queue()
    while len(_workers) < POOL_SIZE:
        worker = threading.Thread(target=_worker_loop, args=(_tasks,),
                                  name=f"je-drafter-{len(_workers)}",
                                  daemon=True)
        _workers.append(worker)
        worker.start()
    return _tasks


def ensure(job_id: int, question: str, descriptor_ctx: dict,
           profile: dict) -> None:
    """Idempotent, non-blocking: schedule at most one draft per key."""
    key = _key(job_id, question)
    with _lock:
        rec = _records.get(key)
        tag = (descriptor_ctx or {}).get("tag")
        if tag in SENSITIVE_TAGS:
            if rec is None:
                _records[key] = {"question": question, "state": "failed",
                                 "reason": "sensitive", "answer": None,
                                 "attempts": 0, "next_retry_at": float("inf")}
            return
        if rec is not None:
            if rec["state"] in ("drafting", "done"):
                return
            if time.monotonic() < rec["next_retry_at"]:
                return
            rec.update(state="drafting")
        else:
            _records[key] = {"question": question, "state": "drafting",
                             "reason": None, "answer": None, "attempts": 0,
                             "next_retry_at": 0.0}
        tasks = _ensure_workers()
    tasks.put((key, question, dict(descriptor_ctx or {}), dict(profile or {})))


def get(job_id: int, question: str) -> dict | None:
    with _lock:
        rec = _records.get(_key(job_id, question))
        return dict(rec) if rec is not None else None


def answer_for(job_id: int, question: str) -> str | None:
    with _lock:
        rec = _records.get(_key(job_id, question))
        if rec is not None and rec["state"] == "done":
            return rec["answer"]
        return None


def reset_backoff_for(job_id: int, questions: list[str]) -> None:
    """Fill-again support: failed keys become immediately retryable
    (sensitive stays permanently non-generating)."""
    with _lock:
        for question in questions:
            rec = _records.get(_key(job_id, question))
            if rec is not None and rec["state"] == "failed" \
                    and rec["reason"] != "sensitive":
                rec["next_retry_at"] = 0.0


def cache_version() -> int:
    with _lock:
        return _cache_version


def stats() -> dict:
    with _lock:
        states: dict[str, int] = {}
        for rec in _records.values():
            states[rec["state"]] = states.get(rec["state"], 0) + 1
        return {"records": len(_records), "by_state": states,
                "cache_version": _cache_version}


def register_on_complete(callback) -> None:
    _on_complete.append(callback)


def set_generator_for_tests(fn) -> None:
    global _generator_override
    _generator_override = fn


def set_bank_save_for_tests(fn) -> None:
    global _bank_save_override
    _bank_save_override = fn


def reset_for_tests(backoff_base_s: float | None = None,
                    backoff_cap_s: float | None = None) -> None:
    global _tasks, _records, _cache_version, _generator_override, \
        _bank_save_override, _backoff_base_s, _backoff_cap_s
    with _lock:
        tasks = _tasks
        worker_count = len(_workers)
    if tasks is not None:
        for _ in range(worker_count):
            tasks.put(None)
    for worker in _workers:
        worker.join(timeout=2)
    _workers.clear()
    with _lock:
        _tasks = None
        _records = {}
        _cache_version = 0
        _generator_override = None
        _bank_save_override = None
        _on_complete.clear()
        _backoff_base_s = backoff_base_s or _DEFAULT_BACKOFF_BASE_S
        _backoff_cap_s = backoff_cap_s or _DEFAULT_BACKOFF_CAP_S
